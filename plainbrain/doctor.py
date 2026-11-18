"""Check that Plainbrain can run on this machine, and that the inbox guard really blocks an edit.

    python scripts/brain.py doctor --root .

It reads files and starts the guard with a made-up edit. It changes nothing.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from plainbrain import global_hooks, home
from plainbrain.model import RegistryParseError, parse_registry

HOME = Path(__file__).resolve().parents[1]
GUARD = HOME / "scripts" / "inbox_guard.py"
MINIMUM = (3, 11)
OK, WARN, FAIL, NOTE = "ok", "warn", "fail", "note"


def interpreter(name: str):
    """The (major, minor) version `name` starts on this machine, or None when it does not start.

    Windows ships a `python3` that only opens the Store, so finding the name on PATH is not enough."""
    path = shutil.which(name)
    if not path:
        return None
    try:
        done = subprocess.run([path, "-c", "import sys;print('%d %d' % sys.version_info[:2])"],
                              capture_output=True, text=True, timeout=15)
        major, minor = done.stdout.split()
        return (int(major), int(minor)) if done.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _edit(target_root: Path | None = None) -> str:
    """A direct edit to the folder's inbox, as Claude Code describes one to a hook."""
    folder = target_root or HOME
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "cwd": str(folder),
        "tool_input": {"file_path": str(folder / "INBOX.md"), "content": "x"},
    })


def _blocks(argv: list[str], env=None, target_root: Path | None = None) -> bool:
    # This checks the guard that belongs to this folder. When the check runs inside Claude Code with the
    # Plainbrain plugin on, the plugin's variable would make the guard protect the plugin's folder instead,
    # and a working guard would be reported as broken.
    env = {k: v for k, v in (env or os.environ).items() if k != "CLAUDE_PLUGIN_ROOT"}
    try:
        done = subprocess.run(argv, input=_edit(target_root), capture_output=True, text=True, timeout=30, env=env)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 2


def find_sh():
    """The shell Claude Code runs hooks in: sh, or Git Bash on Windows even when it is not on PATH."""
    found = shutil.which("sh")
    if found or os.name != "nt":
        return found
    git = shutil.which("git")
    if git:
        candidate = Path(git).resolve().parents[1] / "bin" / "sh.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def claude_hook_command(folder: Path | None = None):
    base = folder or HOME
    try:
        settings = json.loads((base / ".claude" / "settings.json").read_text(encoding="utf-8"))
        return settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None


def _python_fix() -> str:
    if sys.platform == "darwin":
        return ("With Homebrew, add the folder printed by `echo $(brew --prefix python)/libexec/bin` "
                "to your PATH.")
    if os.name == "nt":
        return "Install Python from python.org and tick \"Add python.exe to PATH\"."
    return "On Ubuntu or Debian: sudo apt install python-is-python3."


_AGENT_NAMES = {"claude": "Claude Code", "cursor": "Cursor", "antigravity": "Antigravity"}


def _outside(root: Path) -> tuple[str, str]:
    """Whether the hooks also run outside this folder, from each agent's user-level file."""
    packaged = home.is_packaged()
    folder = root if packaged or (root / "scripts" / "inbox_guard.py").is_file() else HOME
    try:
        states = global_hooks.status(folder.resolve())
    except Exception:  # a doctor check must not crash on a strange settings file
        return (NOTE, "Outside this folder: could not read the agents' user-level hook files.")
    if any(s == "ephemeral" for s in states.values()):
        return (WARN, "Outside this folder: Plainbrain is running from a temporary cache (such as uvx), so global "
                      "hooks cannot be installed permanently. Install Plainbrain with pipx or uv tool install first.")
    unreadable = [_AGENT_NAMES[a] for a, s in states.items() if s == "unreadable"]
    if unreadable:
        return (WARN, "Outside this folder: " + ", ".join(unreadable) + " has a user-level hook file that is not "
                      "valid JSON, so Plainbrain could not check or add its hooks there.")
    hooks_cmd = "plainbrain hooks install" if packaged else "python scripts/brain.py hooks install --root ."
    stale = [_AGENT_NAMES[a] for a, s in states.items() if s == "stale"]
    if stale:
        return (WARN, "Outside this folder: " + ", ".join(stale) + " has stale Plainbrain hooks pointing at an "
                      f"older install. To update them: {hooks_cmd} (add --dry-run to see the changes first).")
    missing = [_AGENT_NAMES[a] for a, s in states.items() if s == "missing"]
    if not missing:
        return (OK, "Outside this folder: the inbox guard (and in Claude Code the capture nudge) runs in every project.")
    return (NOTE, "Outside this folder: no Plainbrain hooks in the user-level hook file of " + ", ".join(missing)
                  + ", so in other projects nothing blocks a direct edit to INBOX.md there. To add them: "
                  f"{hooks_cmd} (add --dry-run to see the changes first).")


def _packaged_guard_env(root: Path) -> dict[str, str]:
    env = {**os.environ, "BRAIN_ROOT": str(root)}
    existing = env.get("PYTHONPATH", "")
    parts = existing.split(os.pathsep) if existing else []
    if str(HOME) not in parts:
        env["PYTHONPATH"] = os.pathsep.join(parts + [str(HOME)]) if parts else str(HOME)
    return env


def checks(root: Path) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    running = sys.version_info[:2]
    version = "%d.%d" % running
    if running >= MINIMUM:
        found.append((OK, f"Python {version} runs Plainbrain."))
    else:
        found.append((FAIL, f"Python {version} is too old. Plainbrain needs {MINIMUM[0]}.{MINIMUM[1]} or later."))

    if shutil.which("git"):
        found.append((OK, "Git is installed."))
    else:
        found.append((WARN, "Git is not found. Plainbrain runs without it, but \"Update Plainbrain\" needs it."))

    missing = [name for name in ("REGISTRY.md", "INBOX.md", "CONTEXT.md") if not (root / name).is_file()]
    if missing:
        found.append((FAIL, "Missing: " + ", ".join(missing) + ". Run init to create them."))
    else:
        try:
            parse_registry((root / "REGISTRY.md").read_text(encoding="utf-8"))
            found.append((OK, "Your commitments, inbox and context files are in place, and the commitments read cleanly."))
        except RegistryParseError as exc:
            found.append((FAIL, f"REGISTRY.md cannot be read: {exc}"))

    packaged = home.is_packaged()
    if packaged:
        guard_env = _packaged_guard_env(root)
        if _blocks([sys.executable, "-m", "plainbrain.inbox_guard"], env=guard_env, target_root=root):
            found.append((OK, "The inbox guard blocks a direct edit to INBOX.md when it runs."))
        else:
            found.append((FAIL, "The inbox guard did not block a direct edit to INBOX.md."))

        guard_bin = shutil.which("plainbrain-guard")
        if guard_bin and not global_hooks.is_ephemeral_path(Path(guard_bin)):
            found.append((OK, "plainbrain-guard is on PATH."))
        else:
            found.append((WARN, "plainbrain-guard is not on PATH. Install Plainbrain persistently with pipx or "
                                "uv tool install so agent hooks can find it."))

        mcp_bin = shutil.which("plainbrain-mcp")
        if mcp_bin and not global_hooks.is_ephemeral_path(Path(mcp_bin)):
            found.append((OK, "plainbrain-mcp is on PATH."))
        else:
            found.append((NOTE, "plainbrain-mcp is not on PATH. Only the optional MCP server needs it."))

        if (root / ".claude" / "settings.json").is_file():
            command, sh = claude_hook_command(root), find_sh()
            if command is None:
                found.append((WARN, "Claude Code: no hook found in .claude/settings.json, so nothing blocks inbox edits there."))
            elif sh is None:
                found.append((WARN, "Claude Code: no sh or Git Bash found, so its hook could not be tried here."))
            elif _blocks([sh, "-c", command], env={**guard_env, "CLAUDE_PROJECT_DIR": str(root)}, target_root=root):
                found.append((OK, "Claude Code: the hook starts and blocks a direct inbox edit."))
            else:
                found.append((WARN, "Claude Code: the hook did not block a direct inbox edit on this machine. "
                                    "Edits to INBOX.md are not blocked there; rely on AGENTS.md and keep backups."))
    else:
        if _blocks([sys.executable, str(GUARD)]):
            found.append((OK, "The inbox guard blocks a direct edit to INBOX.md when it runs."))
        else:
            found.append((FAIL, "The inbox guard did not block a direct edit to INBOX.md."))

        command, sh = claude_hook_command(), find_sh()
        if command is None:
            found.append((WARN, "Claude Code: no hook found in .claude/settings.json, so nothing blocks inbox edits there."))
        elif sh is None:
            found.append((WARN, "Claude Code: no sh or Git Bash found, so its hook could not be tried here."))
        elif _blocks([sh, "-c", command], env={**os.environ, "CLAUDE_PROJECT_DIR": str(HOME)}):
            found.append((OK, "Claude Code: the hook starts and blocks a direct inbox edit."))
        else:
            found.append((WARN, "Claude Code: the hook did not block a direct inbox edit on this machine. "
                                "Edits to INBOX.md are not blocked there; rely on AGENTS.md and keep backups."))

        python = interpreter("python")
        if python is not None and python >= MINIMUM:
            found.append((OK, "Cursor, Codex and Antigravity: their hooks call `python`, and it starts here."))
        else:
            why = "is older than Plainbrain needs" if python else "does not start on this machine"
            found.append((WARN, f"Cursor, Codex and Antigravity: their hooks call `python`, which {why}. "
                                "In those three agents nothing blocks an edit to INBOX.md; they follow AGENTS.md only. "
                                "Claude Code has its own check above. To fix it, make `python` start Python 3. "
                                + _python_fix() + " Then run doctor again."))

    found.append(_outside(root))

    if importlib.util.find_spec("mcp") is None:
        install_hint = "pip install 'plainbrain[mcp]'" if packaged else "python -m pip install -r requirements.txt"
        found.append((NOTE, f"The MCP library is not installed. Only the optional MCP server needs it: {install_hint}"))
    return found


def run_doctor(root: Path, _today: str = "") -> int:
    found = checks(Path(root))
    for status, text in found:
        print(f"{status:<5} {text}")
    failed = sum(1 for status, _text in found if status == FAIL)
    warned = sum(1 for status, _text in found if status == WARN)
    if failed:
        print(f"\n{failed} problem(s) to fix before Plainbrain works.")
        return 1
    if warned:
        print(f"\nPlainbrain works. {warned} warning(s) above are worth reading.")
    else:
        print("\nEverything checks out.")
    return 0
