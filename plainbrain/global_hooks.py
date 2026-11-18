"""Add Plainbrain's hooks to the agents' files that apply in every project, so they work outside this folder too.

    python scripts/brain.py hooks status --root .
    python scripts/brain.py hooks install --root . [--agent claude|cursor|antigravity] [--dry-run]

The hooks in `.claude/`, `.cursor/` and `.agents/` inside this folder only run while the agent works in this
folder. From a project folder, an agent could still edit INBOX.md by its full path, and the capture nudge never
runs. This command adds the same hooks to each agent's user-level file:

| Agent | File | Hooks added |
|---|---|---|
| Claude Code | `~/.claude/settings.json` | inbox guard before file and shell tools; capture nudge at Stop |
| Cursor | `~/.cursor/hooks.json` | inbox guard before file tools and before shell commands that name INBOX.md |
| Antigravity | `~/.gemini/config/hooks.json` | inbox guard before every tool call |

It points each hook at this folder's own scripts, run with the Python that ran this command, so the hooks keep
working when the agent runs elsewhere. It adds only what is missing, keeps every other setting and hook, saves a
copy of each file it changes beside it (`<file>.bak-YYYYMMDD-HHMMSS`), and leaves a file it cannot read as JSON
untouched, as is a file whose hooks section has an unexpected shape (such as `"hooks": null`). With the Plainbrain plugin enabled in Claude Code, Claude Code is skipped because the plugin already
does this. Nothing else is written, and nothing leaves the machine."""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

AGENTS = ("claude", "cursor", "antigravity")


def _cmd(root: Path, script: str) -> str:
    return f'"{Path(sys.executable).as_posix()}" "{(root / "scripts" / script).as_posix()}"'


def files(home: Path) -> dict[str, Path]:
    return {
        "claude": home / ".claude" / "settings.json",
        "cursor": home / ".cursor" / "hooks.json",
        "antigravity": home / ".gemini" / "config" / "hooks.json",
    }


def _load(path: Path) -> dict | None:
    """The file's JSON object, {} when the file does not exist, or None when it exists but cannot be read."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig") or "{}")
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


_EVENTS = {"claude": ("PreToolUse", "Stop"), "cursor": ("preToolUse", "beforeShellExecution")}


def _editable(agent: str, data: dict) -> bool:
    """Whether the parts this command would change have the shape it expects. A file with, say, `"hooks": null`
    or a hook list that is not a list is treated like an unreadable file and left untouched."""
    if agent in _EVENTS:
        hooks = data.get("hooks", {})
        if not isinstance(hooks, dict):
            return False
        return all(isinstance(hooks.get(event, []), list) for event in _EVENTS[agent])
    for group in data.values():  # antigravity: named groups of events
        if isinstance(group, dict) and not isinstance(group.get("PreToolUse", []), list):
            return False
    return True


def _plugin_enabled(settings: dict) -> bool:
    plugins = settings.get("enabledPlugins")
    return isinstance(plugins, dict) and any(str(k).startswith("plainbrain@") and v for k, v in plugins.items())


def _has(entries, command: str) -> bool:
    """Whether a hook list (Claude/Antigravity nested shape or Cursor flat shape) already runs `command`."""
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        if entry.get("command") == command:
            return True
        for hook in entry.get("hooks", []) if isinstance(entry.get("hooks"), list) else []:
            if isinstance(hook, dict) and hook.get("command") == command:
                return True
    return False


def _claude(data: dict, root: Path) -> list[str]:
    hooks = data.setdefault("hooks", {})
    added = []
    guard, nudge = _cmd(root, "inbox_guard.py"), _cmd(root, "capture_nudge.py")
    pre = hooks.setdefault("PreToolUse", [])
    if not _has(pre, guard):
        pre.append({"matcher": "Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell",
                    "hooks": [{"type": "command", "command": guard, "timeout": 5}]})
        added.append("inbox guard (PreToolUse)")
    stop = hooks.setdefault("Stop", [])
    if not _has(stop, nudge):
        stop.append({"hooks": [{"type": "command", "command": nudge, "timeout": 10}]})
        added.append("capture nudge (Stop)")
    return added


def _cursor(data: dict, root: Path) -> list[str]:
    data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    guard = _cmd(root, "inbox_guard.py")
    added = []
    pre = hooks.setdefault("preToolUse", [])
    if not _has(pre, guard):
        pre.append({"command": guard, "matcher": "Write|StrReplace|Delete|EditNotebook", "timeout": 5})
        added.append("inbox guard (preToolUse)")
    shell = hooks.setdefault("beforeShellExecution", [])
    if not _has(shell, guard):
        shell.append({"command": guard, "matcher": "INBOX\\.md|REGISTRY\\.md", "timeout": 5})
        added.append("inbox guard (beforeShellExecution)")
    return added


def _antigravity(data: dict, root: Path) -> list[str]:
    guard = _cmd(root, "inbox_guard.py")
    if any(_has(group.get("PreToolUse"), guard) for group in data.values() if isinstance(group, dict)):
        return []
    data["plainbrain-inbox-guard"] = {"PreToolUse": [{"matcher": "*", "hooks": [
        {"type": "command", "command": guard, "timeout": 10}]}]}
    return ["inbox guard (PreToolUse)"]


_ADD = {"claude": _claude, "cursor": _cursor, "antigravity": _antigravity}


def status(root: Path, home: Path | None = None) -> dict[str, str]:
    """Per agent: 'installed', 'plugin', 'missing', or 'unreadable'."""
    home = home or Path.home()
    found = {}
    for agent, path in files(home).items():
        data = _load(path)
        if data is None or not _editable(agent, data):
            found[agent] = "unreadable"
        elif agent == "claude" and _plugin_enabled(data):
            found[agent] = "plugin"
        else:
            found[agent] = "installed" if not _ADD[agent](json.loads(json.dumps(data)), root) else "missing"
    return found


def install(root: Path, agents=AGENTS, home: Path | None = None, dry_run: bool = False) -> list[str]:
    """Add the missing hooks and return one line per agent saying what happened."""
    home = home or Path.home()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    lines = []
    for agent in agents:
        path = files(home)[agent]
        data = _load(path)
        if data is None:
            lines.append(f"{agent}: {path} is not valid JSON; left untouched. Fix it, then run this again.")
            continue
        if not _editable(agent, data):
            lines.append(f"{agent}: {path} has a hooks section that is not the expected shape (for example "
                         '"hooks": null); left untouched. Fix it, then run this again.')
            continue
        if agent == "claude" and _plugin_enabled(data):
            lines.append(f"{agent}: the Plainbrain plugin is enabled and already adds these hooks; nothing to do.")
            continue
        added = _ADD[agent](data, root)
        if not added:
            lines.append(f"{agent}: already installed in {path}.")
            continue
        if dry_run:
            lines.append(f"{agent}: would add {', '.join(added)} to {path}.")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            shutil.copy2(path, path.with_name(f"{path.name}.bak-{stamp}"))
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        lines.append(f"{agent}: added {', '.join(added)} to {path}.")
    return lines


def add_parser(sub) -> None:
    p = sub.add_parser("hooks", help="add Plainbrain's hooks to the agents' files for every project")
    p.add_argument("action", choices=("status", "install"))
    p.add_argument("--root", required=True)
    p.add_argument("--agent", action="append", choices=AGENTS, help="repeat for each agent; default all three")
    p.add_argument("--dry-run", action="store_true", help="show what install would change, and change nothing")


def run(args) -> str:
    root = Path(args.root).resolve()
    if not (root / "scripts" / "inbox_guard.py").is_file():
        raise ValueError(f"{root} has no scripts/inbox_guard.py; pass the Plainbrain folder as --root")
    if args.action == "status":
        return "\n".join(f"{agent}: {state}" for agent, state in status(root).items())
    return "\n".join(install(root, tuple(args.agent or AGENTS), dry_run=args.dry_run))
