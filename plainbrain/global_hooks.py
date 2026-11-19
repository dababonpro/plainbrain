"""Add Plainbrain's hooks to the agents' files that apply in every project, so they work outside this folder too.

    python scripts/brain.py hooks status --root .
    python scripts/brain.py hooks install --root . [--agent claude|cursor|antigravity] [--dry-run]
    plainbrain hooks status
    plainbrain hooks install [--agent claude|cursor|antigravity] [--dry-run]

The hooks in `.claude/`, `.cursor/` and `.agents/` inside this folder only run while the agent works in this
folder. From a project folder, an agent could still edit INBOX.md by its full path, and the capture nudge never
runs. This command adds the same hooks to each agent's user-level file:

| Agent | File | Hooks added |
|---|---|---|
| Claude Code | `~/.claude/settings.json` | inbox guard before file and shell tools; capture nudge at Stop |
| Cursor | `~/.cursor/hooks.json` | inbox guard before file tools and before shell commands that name INBOX.md |
| Antigravity | `~/.gemini/config/hooks.json` | inbox guard before every tool call |

From a checkout or plugin, it points each hook at the checkout's own scripts, run with the Python that ran this
command. When installed as a package, it points each hook at `plainbrain-guard` and `plainbrain-nudge` (on `PATH` or
beside the running interpreter). In both cases the hooks keep working when the agent runs elsewhere. It adds only what
copy of each file it changes beside it (`<file>.bak-YYYYMMDD-HHMMSS`), and leaves a file it cannot read as JSON
untouched, as is a file whose hooks section has an unexpected shape (such as `"hooks": null`). With the Plainbrain plugin enabled in Claude Code, Claude Code is skipped because the plugin already
does this. Nothing else is written, and nothing leaves the machine."""
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from plainbrain import home as brain_home

CHECKOUT = Path(__file__).resolve().parents[1]
AGENTS = ("claude", "cursor", "antigravity")
_EPHEMERAL_PAIRS = {("uv", "cache"), (".cache", "uv"), ("caches", "uv")}
_TOKEN_RE = re.compile(r'"([^"]*)"|\'([^\']*)\'|(\S+)')
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


class EphemeralInstallError(ValueError):
    """Raised when hook resolution runs inside an ephemeral cache/temp environment such as uvx."""


def _default_temp_root() -> Path:
    named = os.environ.get("PLAINBRAIN_TEMP_ROOT", "").strip()
    return Path(named).resolve() if named else Path(tempfile.gettempdir()).resolve()


def is_ephemeral_path(path: Path, temp_root: Path | None = None) -> bool:
    """Whether `path` lives inside a temporary directory or uv's ephemeral cache."""
    # Both spellings count. A virtualenv's `python` is a link to the base interpreter on Linux and macOS, and
    # following it would place an install in uv's cache at the base interpreter's own, permanent address.
    base = temp_root or _default_temp_root()
    bases = {Path(os.path.abspath(base)), Path(base).resolve()}
    for spelled in {Path(os.path.abspath(path)), Path(path).resolve()}:
        if any(spelled == one or one in spelled.parents for one in bases):
            return True
        parts = tuple(part.lower() for part in spelled.parts)
        if any((parts[i], parts[i + 1]) in _EPHEMERAL_PAIRS for i in range(len(parts) - 1)):
            return True
    return False


def resolve_hook_command(kind: str, root: Path | None = None, temp_root: Path | None = None) -> str:
    """Resolve the command string for Plainbrain's `guard` or `nudge` hook."""
    if kind == "guard":
        bin_name, script = "plainbrain-guard", "inbox_guard.py"
    elif kind == "nudge":
        bin_name, script = "plainbrain-nudge", "capture_nudge.py"
    else:
        raise ValueError(f"unknown hook kind: {kind!r}")
    if not brain_home.is_packaged() and root is not None and (root / "scripts" / script).is_file():
        return f'"{Path(sys.executable).as_posix()}" "{(root / "scripts" / script).as_posix()}"'
    on_path = shutil.which(bin_name)
    if on_path and not is_ephemeral_path(Path(on_path), temp_root):
        return bin_name
    if is_ephemeral_path(Path(sys.executable), temp_root):
        raise EphemeralInstallError(
            "Plainbrain is running from a temporary cache (such as uvx). "
            "Install persistently with pipx or uv tool install before installing hooks."
        )
    exe_dir = Path(sys.executable).parent
    candidates = [exe_dir / f"{bin_name}.exe", exe_dir / bin_name] if os.name == "nt" else [exe_dir / bin_name]
    for sibling in candidates:
        if sibling.is_file():
            return f'"{sibling.as_posix()}"'
    raise ValueError(
        f"{bin_name} was not found on PATH or beside {sys.executable}. "
        "Install Plainbrain with pipx or uv tool install first."
    )


def _tokenize_command(command: str) -> list[str]:
    tokens = []
    for match in _TOKEN_RE.finditer(command):
        tok = match.group(1) if match.group(1) is not None else (
            match.group(2) if match.group(2) is not None else match.group(3)
        )
        if tok:
            tokens.append(tok)
    return tokens


def _is_plainbrain_hook(command: str, kind: str, recorded: Path | None = None) -> bool:
    """Whether `command` is a Plainbrain-owned hook of `kind`, never matching another tool's script."""
    tokens = _tokenize_command(command)
    if not tokens:
        return False
    if kind == "guard":
        bins = ("plainbrain-guard", "plainbrain-guard.exe")
        suffix = "/scripts/inbox_guard.py"
    elif kind == "nudge":
        bins = ("plainbrain-nudge", "plainbrain-nudge.exe")
        suffix = "/scripts/capture_nudge.py"
    else:
        return False
    idx = 0
    while idx < len(tokens) and (tokens[idx] == "&" or _ENV_ASSIGN.match(tokens[idx])):
        idx += 1
    if idx < len(tokens):
        exe_name = tokens[idx].replace("\\", "/").rsplit("/", 1)[-1].lower()
        if exe_name in bins:
            return True
    recorded_resolved = None
    if recorded is not None:
        try:
            recorded_resolved = recorded.resolve()
        except OSError:
            recorded_resolved = None
    for tok in tokens:
        norm = tok.replace("\\", "/")
        if norm.lower().endswith(suffix):
            folder = Path(norm).parent.parent
            if (folder / "scripts" / "brain.py").is_file():
                return True
            if recorded_resolved is not None:
                try:
                    if folder.resolve() == recorded_resolved:
                        return True
                except OSError:
                    pass
    return False


def _recorded_for_home(home: Path | None) -> Path | None:
    if home is None:
        return brain_home.recorded_folder()
    try:
        named = (home / brain_home.POINTER_NAME).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    folder = Path(named).expanduser() if named else None
    return folder if folder and folder.is_dir() else None


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


def _sync_entries(entries, kind: str, target: str, recorded: Path | None) -> tuple[bool, bool]:
    """Check if `target` is already present and replace any stale Plainbrain hook in place."""
    has_target = False
    replaced = False
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        cmd = entry.get("command")
        if isinstance(cmd, str):
            if cmd == target:
                has_target = True
            elif _is_plainbrain_hook(cmd, kind, recorded):
                entry["command"] = target
                has_target = True
                replaced = True
        nested = entry.get("hooks")
        if isinstance(nested, list):
            for hook in nested:
                if not isinstance(hook, dict):
                    continue
                hcmd = hook.get("command")
                if isinstance(hcmd, str):
                    if hcmd == target:
                        has_target = True
                    elif _is_plainbrain_hook(hcmd, kind, recorded):
                        hook["command"] = target
                        has_target = True
                        replaced = True
    return has_target, replaced


def _claude(data: dict, guard_cmd: str, nudge_cmd: str, recorded: Path | None = None) -> tuple[list[str], list[str]]:
    hooks = data.setdefault("hooks", {})
    added, updated = [], []
    pre = hooks.setdefault("PreToolUse", [])
    has_guard, replaced_guard = _sync_entries(pre, "guard", guard_cmd, recorded)
    if replaced_guard:
        updated.append("inbox guard (PreToolUse)")
    elif not has_guard:
        pre.append({"matcher": "Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell",
                    "hooks": [{"type": "command", "command": guard_cmd, "timeout": 5}]})
        added.append("inbox guard (PreToolUse)")
    stop = hooks.setdefault("Stop", [])
    has_nudge, replaced_nudge = _sync_entries(stop, "nudge", nudge_cmd, recorded)
    if replaced_nudge:
        updated.append("capture nudge (Stop)")
    elif not has_nudge:
        stop.append({"hooks": [{"type": "command", "command": nudge_cmd, "timeout": 10}]})
        added.append("capture nudge (Stop)")
    return added, updated


def _cursor(data: dict, guard_cmd: str, _nudge_cmd: str, recorded: Path | None = None) -> tuple[list[str], list[str]]:
    data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    added, updated = [], []
    pre = hooks.setdefault("preToolUse", [])
    has_pre, replaced_pre = _sync_entries(pre, "guard", guard_cmd, recorded)
    if replaced_pre:
        updated.append("inbox guard (preToolUse)")
    elif not has_pre:
        pre.append({"command": guard_cmd, "matcher": "Write|StrReplace|Delete|EditNotebook", "timeout": 5})
        added.append("inbox guard (preToolUse)")
    shell = hooks.setdefault("beforeShellExecution", [])
    has_shell, replaced_shell = _sync_entries(shell, "guard", guard_cmd, recorded)
    if replaced_shell:
        updated.append("inbox guard (beforeShellExecution)")
    elif not has_shell:
        shell.append({"command": guard_cmd, "matcher": "INBOX\\.md|REGISTRY\\.md", "timeout": 5})
        added.append("inbox guard (beforeShellExecution)")
    return added, updated


def _antigravity(
    data: dict, guard_cmd: str, _nudge_cmd: str, recorded: Path | None = None
) -> tuple[list[str], list[str]]:
    has_guard = False
    replaced_guard = False
    for group in data.values():
        if isinstance(group, dict):
            has_one, replaced_one = _sync_entries(group.get("PreToolUse"), "guard", guard_cmd, recorded)
            has_guard = has_guard or has_one
            replaced_guard = replaced_guard or replaced_one
    if replaced_guard:
        return [], ["inbox guard (PreToolUse)"]
    if has_guard:
        return [], []
    entry = {"matcher": "*", "hooks": [{"type": "command", "command": guard_cmd, "timeout": 10}]}
    existing = data.get("plainbrain-inbox-guard")
    if isinstance(existing, dict):
        existing.setdefault("PreToolUse", []).append(entry)
    else:
        data["plainbrain-inbox-guard"] = {"PreToolUse": [entry]}
    return ["inbox guard (PreToolUse)"], []


_SYNC = {"claude": _claude, "cursor": _cursor, "antigravity": _antigravity}


def status(root: Path | None = None, home: Path | None = None, temp_root: Path | None = None) -> dict[str, str]:
    """Per agent: 'installed', 'stale', 'missing', 'ephemeral', 'plugin', or 'unreadable'."""
    try:
        guard_cmd = resolve_hook_command("guard", root, temp_root=temp_root)
        nudge_cmd = resolve_hook_command("nudge", root, temp_root=temp_root)
    except EphemeralInstallError:
        return {agent: "ephemeral" for agent in AGENTS}
    recorded = _recorded_for_home(home)
    home = home or Path.home()
    found = {}
    for agent, path in files(home).items():
        data = _load(path)
        if data is None or not _editable(agent, data):
            found[agent] = "unreadable"
        elif agent == "claude" and _plugin_enabled(data):
            found[agent] = "plugin"
        else:
            added, updated = _SYNC[agent](json.loads(json.dumps(data)), guard_cmd, nudge_cmd, recorded)
            if updated:
                found[agent] = "stale"
            elif added:
                found[agent] = "missing"
            else:
                found[agent] = "installed"
    return found


def _format_change(agent: str, path: Path, added: list[str], updated: list[str], dry_run: bool) -> str:
    if updated and added:
        verb_u = "would update" if dry_run else "updated"
        verb_a = "add" if dry_run else "added"
        return f"{agent}: {verb_u} {', '.join(updated)} and {verb_a} {', '.join(added)} in {path}."
    if updated:
        verb = "would update" if dry_run else "updated"
        return f"{agent}: {verb} {', '.join(updated)} in {path}."
    verb = "would add" if dry_run else "added"
    return f"{agent}: {verb} {', '.join(added)} to {path}."


def install(
    root: Path | None = None,
    agents=AGENTS,
    home: Path | None = None,
    dry_run: bool = False,
    temp_root: Path | None = None,
) -> list[str]:
    """Add missing hooks and update stale Plainbrain hooks in place; return one line per agent."""
    guard_cmd = resolve_hook_command("guard", root, temp_root=temp_root)
    nudge_cmd = resolve_hook_command("nudge", root, temp_root=temp_root)
    recorded = _recorded_for_home(home)
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
        added, updated = _SYNC[agent](data, guard_cmd, nudge_cmd, recorded)
        if not added and not updated:
            lines.append(f"{agent}: already installed in {path}.")
            continue
        if dry_run:
            lines.append(_format_change(agent, path, added, updated, dry_run=True))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            shutil.copy2(path, path.with_name(f"{path.name}.bak-{stamp}"))
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        lines.append(_format_change(agent, path, added, updated, dry_run=False))
    return lines


def add_parser(sub) -> None:
    p = sub.add_parser("hooks", help="add Plainbrain's hooks to the agents' files for every project")
    p.add_argument("action", choices=("status", "install"))
    p.add_argument("--root", default=None)
    p.add_argument("--agent", action="append", choices=AGENTS, help="repeat for each agent; default all three")
    p.add_argument("--dry-run", action="store_true", help="show what install would change, and change nothing")


def run(args) -> str:
    root = (
        Path(args.root.strip()).expanduser().resolve()
        if isinstance(args.root, str) and args.root.strip()
        else brain_home.resolve_cli_root()
    )
    if root is not None:
        root = root.resolve()
    hook_root = root
    if not brain_home.is_packaged():
        if root is None:
            raise ValueError("No Plainbrain folder found. Pass --root <folder> or set up Plainbrain first.")
        if (root / "scripts" / "inbox_guard.py").is_file():
            hook_root = root
        elif (brain_home.as_plugin() or (root / brain_home.MARKER_NAME).is_file()) and (
            CHECKOUT / "scripts" / "inbox_guard.py"
        ).is_file():
            hook_root = CHECKOUT
        else:
            raise ValueError(f"{root} has no scripts/inbox_guard.py; pass the Plainbrain folder as --root")
    if args.action == "status":
        return "\n".join(f"{agent}: {state}" for agent, state in status(hook_root).items())
    return "\n".join(install(hook_root, tuple(args.agent or AGENTS), dry_run=args.dry_run))
