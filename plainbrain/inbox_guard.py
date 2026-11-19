"""Deny agent edits to the Plainbrain INBOX.md, and ask the owner before a direct edit to REGISTRY.md.

Reads, capture, inbox-drop and the `registry` commands stay allowed. A direct edit to REGISTRY.md is not
denied, because AGENTS.md allows one after the owner accepts it; the hook turns it into the agent's own
permission prompt, so the owner decides at the moment of the edit instead of the rule living only in prose.

Speaks the hook formats of Claude Code and Codex (PreToolUse), Cursor (preToolUse and beforeShellExecution)
and Antigravity (PreToolUse with toolCall). Antigravity has no ask decision, so there the registry rule stays
an instruction in AGENTS.md. Codex file edits arrive as apply_patch text, so the patch's file headers are
read as paths."""
import json
import os
import re
import sys
from pathlib import Path

CHECKOUT = Path(__file__).resolve().parents[1]
if str(CHECKOUT) not in sys.path:
    sys.path.insert(0, str(CHECKOUT))

from plainbrain.home import as_plugin, is_packaged, resolve_global_root  # noqa: E402

AS_PLUGIN = as_plugin()
PACKAGED = is_packaged()
GLOBAL_MODE = AS_PLUGIN or PACKAGED
# A plugin or packaged install runs from a folder that holds no data, so it looks the owner's folder up. A cloned
# folder holds this script beside its own inbox and guards that inbox, whatever BRAIN_ROOT names.
HOME = resolve_global_root(CHECKOUT) if GLOBAL_MODE else CHECKOUT
# With no folder, this path names a file that never exists, so no edit can match it.
INBOX = (HOME or CHECKOUT / ".not-set-up") / "INBOX.md"
REGISTRY = INBOX.parent / "REGISTRY.md"

WRITE_TOOLS = {
    "write",
    "delete",
    "strreplace",
    "searchreplace",
    "editnotebook",
    "edit",
    "notebookedit",
    "tabwrite",
    "applypatch",
    "writetofile",
    "replacefilecontent",
    "multireplacefilecontent",
}
READ_TOOLS = {"read", "grep", "glob", "semanticsearch", "tabread"}
SHELL_TOOLS = {"bash", "powershell", "shell", "runterminalcmd", "terminal", "runcommand", "execcommand"}

_HOME = INBOX.parent.as_posix()
if PACKAGED:
    REASON = (
        "Do not edit INBOX.md. Append with: "
        'plainbrain capture --repo <repo-name> --today YYYY-MM-DD --text "one sentence". '
        'Remove an accepted triage line with: plainbrain inbox-drop --line "<exact line>"'
    )
    REGISTRY_REASON = (
        "REGISTRY.md changes go through a command after the owner accepts them: "
        "plainbrain registry add|update|done|focus|archive ... "
        "Edit the file by hand only when no command covers the change and the owner has accepted the exact lines."
    )
else:
    _SCRIPT = (CHECKOUT / "scripts" / "brain.py").as_posix()
    REASON = (
        "Do not edit INBOX.md. Append with: "
        f'python "{_SCRIPT}" capture --root "{_HOME}" --repo <repo-name> '
        '--today YYYY-MM-DD --text "one sentence". '
        f'Remove an accepted triage line with: python "{_SCRIPT}" inbox-drop --root "{_HOME}" --line "<exact line>"'
    )
    REGISTRY_REASON = (
        "REGISTRY.md changes go through a command after the owner accepts them: "
        f'python "{_SCRIPT}" registry add|update|done|focus|archive --root "{_HOME}" ... '
        "Edit the file by hand only when no command covers the change and the owner has accepted the exact lines."
    )

_PATH_KEYS = {"path", "file_path", "filepath", "target_file", "targetfile", "file", "notebook_path"}
# File headers in a Codex apply_patch body: Add, Update, Delete, and the target of a move.
_PATCH_FILE = re.compile(r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+?)\s*$", re.MULTILINE)
_WRITE_WORDS = re.compile(
    r"\b(set-content|out-file|add-content|clear-content|remove-item|copy-item|move-item|"
    r"del|erase|rm|cp|mv|copy|move|ren|tee|truncate|"
    # PowerShell items: New-Item -Force empties an existing file.
    r"new-item|ni|set-item|rename-item|rni)\b"
    # .NET file calls from PowerShell, such as [IO.File]::WriteAllText(...) or a StreamWriter.
    r"|\[(?:system\.)?io\.(?:file|fileinfo|streamwriter|filestream)\]::(?!read|exists|open(?:read|text)\b)"
    r"|\bnew-object\s+(?:system\.)?io\.(?:streamwriter|filestream)\b"
    r"|\bperl\s+(-\S*\s+)*-\S*i"
    r"|\bsed\s+(-\S*\s+)*-i"
    r"|\bgit\s+(checkout|restore|reset|stash|clean)\b",
    re.IGNORECASE,
)
_REDIRECT = re.compile(r">\s*[\"']?\S*inbox\.md", re.IGNORECASE)
_REDIRECT_REGISTRY = re.compile(r">\s*[\"']?\S*registry\.md", re.IGNORECASE)
_QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"|\'[^\']*\'')
_CHAIN = re.compile(r"[;&|<>`\n]|\$\(")
_OWN_COMMAND = re.compile(
    r"^\s*(?:"
    r"(?:\S*python\S*|py)(?:\s+-\S+)*\s+\S*brain\.py"
    r"|\"(?:[^\"]*[/\\])?plainbrain(?:\.exe)?\""
    r"|'(?:[^']*[/\\])?plainbrain(?:\.exe)?'"
    r"|(?:[^\s\"']*[/\\])?plainbrain(?:\.exe)?"
    r")\s+(capture|inbox-drop|for-repo|registry)(\s|$)",
    re.IGNORECASE,
)


def _norm(path: str) -> str:
    text = path.strip().strip("'\"").replace("\\", "/")
    found = re.match(r"^/([a-zA-Z])/(.*)$", text)
    if found:
        text = f"{found.group(1)}:/{found.group(2)}"
    return text.casefold()


def _real(path: str) -> str:
    """The path as the file system spells it, so `..`, links and Windows short names all give one answer.

    A path that cannot be resolved keeps its text, which the plain comparison has already checked."""
    text = path.strip().strip("'\"")
    if os.name == "nt":
        found = re.match(r"^/([a-zA-Z])/(.*)$", text.replace("\\", "/"))
        if found:  # Git Bash spells C:/Users as /c/Users
            text = f"{found.group(1)}:/{found.group(2)}"
    try:
        return _norm(os.path.realpath(text))
    except (OSError, ValueError):
        return _norm(text)


INBOX_KEY = _norm(str(INBOX))
REGISTRY_KEY = _norm(str(REGISTRY))
ROOT_KEY = _norm(str(INBOX.parent))
_REAL = {INBOX_KEY: _real(str(INBOX)), REGISTRY_KEY: _real(str(REGISTRY)), ROOT_KEY: _real(str(INBOX.parent))}
# A path inside a shell command: one quoted run, or one run with no blank, quote or shell operator in it.
_SHELL_PATH = re.compile(r'"([^"]*)"|\'([^\']*)\'|([^\s"\'<>|;&()=]+)')


def _cwd(payload: dict) -> str:
    for key in ("cwd", "working_directory"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    roots = payload.get("workspace_roots")
    if isinstance(roots, list) and len(roots) == 1 and isinstance(roots[0], str):
        return roots[0]
    return ""


def _is_file(path: str, cwd: str, target: str) -> bool:
    key = _norm(path)
    if HOME is None or Path(key).name != Path(target).name:
        return False
    if re.match(r"^[a-z]:/", key) or key.startswith("/"):
        return key == target or _real(path) == _REAL.get(target, target)
    if not cwd:
        # The folder the tool ran in is unknown. In the owner's own folder, assume the worst. As a plugin or
        # packaged install the hook runs in every project, where a bare file of this name is most likely someone else's.
        return not GLOBAL_MODE
    if _norm(f"{cwd.rstrip('/')}/{key}").replace("/./", "/") == target:
        return True
    # Resolved with the letters as given: on Linux a folded name would not find the link it has to follow.
    as_given = path.strip().strip("'\"")
    return _real(f"{cwd.rstrip('/')}/{as_given}") == _REAL.get(target, target)


def _is_inbox(path: str, cwd: str = "") -> bool:
    return _is_file(path, cwd, INBOX_KEY)


def _is_registry(path: str, cwd: str = "") -> bool:
    return _is_file(path, cwd, REGISTRY_KEY)


def _mentions_inbox(command: str, cwd: str) -> bool:
    return _mentions(command, cwd, INBOX_KEY)


def _mentions(command: str, cwd: str, target: str) -> bool:
    lowered = command.replace("\\", "/").casefold()
    if HOME is None or Path(target).name not in lowered:
        return False
    if target in _norm(lowered):
        return True
    # A bare INBOX.md counts when the shell runs in Plainbrain, or when the folder is unknown outside global mode.
    if not cwd:
        return not GLOBAL_MODE
    if _norm(cwd).rstrip("/") == ROOT_KEY or _real(cwd) == _REAL.get(ROOT_KEY, ROOT_KEY):
        return True
    # The file named another way: through `..`, a link, or a Windows short name.
    name = Path(target).name
    for match in _SHELL_PATH.finditer(command):
        token = next(group for group in match.groups() if group is not None)
        if _norm(token).endswith(name) and _is_file(token, cwd, target):
            return True
    return False


def _paths(obj, found: list[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in _PATH_KEYS and isinstance(value, str):
                found.append(value)
            else:
                _paths(value, found)
    elif isinstance(obj, list):
        for value in obj:
            _paths(value, found)


def _cursor_deny() -> dict:
    return {
        "permission": "deny",
        "agent_message": REASON,
        "user_message": "Blocked an edit to INBOX.md. Capture appends; it does not rewrite the file.",
    }


def _claude_deny() -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": REASON,
        }
    }


def _cursor_ask() -> dict:
    return {
        "permission": "ask",
        "agent_message": REGISTRY_REASON,
        "user_message": "The agent wants to edit REGISTRY.md directly. Allow only if you accepted these exact lines.",
    }


def _claude_ask() -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": REGISTRY_REASON,
        }
    }


def _match_python_brain(tail: str) -> bool:
    """Match optional python flags + quoted/unquoted brain.py + subcommand, without shell chaining."""
    m = re.match(r'^(?:\s+-\S+)*\s+(?:"([^"]*)"|\'([^\']*)\')', tail)
    if m:
        script = m.group(1) if m.group(1) is not None else m.group(2)
        if m.group(1) is not None and ("$(" in script or "`" in script):
            return False
        if not re.search(r"(?:^|[/\\])brain\.py$", script, re.IGNORECASE):
            return False
        rest = _QUOTED.sub('""', tail[m.end():])
        return _OWN_COMMAND.match("python brain.py" + rest) is not None and _CHAIN.search(rest) is None
    rest = _QUOTED.sub('""', tail)
    bare = "python" + rest
    return _OWN_COMMAND.match(bare) is not None and _CHAIN.search(bare) is None


def _own_command(command: str) -> bool:
    """One brain.py or plainbrain capture/inbox-drop/for-repo/registry call with nothing chained after it."""
    text = re.sub(r"^\s*&\s*", "", command.strip())
    # The shell runs $(...) and backticks inside double quotes before the command starts, so that is a second
    # command hidden in an argument. Single quotes keep their text as it is.
    for quoted in _QUOTED.finditer(text):
        if quoted.group(0).startswith('"') and ("$(" in quoted.group(0) or "`" in quoted.group(0)):
            return False
    exe = re.match(r'^"([^"]*)"|^\'([^\']*)\'', text)
    if exe:
        inner = exe.group(1) if exe.group(1) is not None else exe.group(2)
        if exe.group(0).startswith('"') and ("$(" in inner or "`" in inner):
            return False
        rest = _QUOTED.sub('""', text[exe.end():])
        if _OWN_COMMAND.match(exe.group(0) + rest) is not None:
            return _CHAIN.search(rest) is None
        if "python" not in inner.casefold():
            return False
        return _match_python_brain(text[exe.end():])
    py = re.match(r"^(?:\S*python\S*|py)(?=\s)", text, re.IGNORECASE)
    if py:
        return _match_python_brain(text[py.end():])
    bare = _QUOTED.sub('""', text)
    return _OWN_COMMAND.match(bare) is not None and _CHAIN.search(bare) is None


def _writes(command: str, redirect: re.Pattern) -> bool:
    lowered = command.lower()
    if _WRITE_WORDS.search(_QUOTED.sub('""', command)) or redirect.search(command):
        return True
    return bool(re.search(r"\b(python|py|node)\b", lowered) and re.search(r"\bopen\s*\(|\.write|writefile|\bunlink\(", lowered))


def _shell(command: str, claude: bool, cwd: str) -> dict:
    allow = {} if claude else {"permission": "allow"}
    inbox, registry = _mentions(command, cwd, INBOX_KEY), _mentions(command, cwd, REGISTRY_KEY)
    if not (inbox or registry) or _own_command(command):
        return allow
    if inbox and _writes(command, _REDIRECT):
        return _claude_deny() if claude else _cursor_deny()
    if registry and _writes(command, _REDIRECT_REGISTRY):
        return _claude_ask() if claude else _cursor_ask()
    return allow


def _antigravity(payload: dict, call: dict) -> dict:
    """Antigravity sends toolCall.name and toolCall.args, and reads a decision of allow or deny."""
    name = str(call.get("name") or "")
    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    roots = payload.get("workspacePaths")
    cwd = args.get("Cwd") if isinstance(args.get("Cwd"), str) else ""
    if not cwd and isinstance(roots, list) and len(roots) == 1 and isinstance(roots[0], str):
        cwd = roots[0]
    command = args.get("CommandLine") if isinstance(args.get("CommandLine"), str) else args.get("command")
    if isinstance(command, str):
        # Tool names differ between Antigravity versions (run_command, run_shell_command), so a command line
        # alone marks a shell call.
        name, tool_input = "run_command", {"command": command}
    else:
        tool_input = args
    verdict = decide({"hook_event_name": "PreToolUse", "tool_name": name, "tool_input": tool_input, "cwd": cwd})
    if verdict.get("hookSpecificOutput", {}).get("permissionDecision") == "deny":
        return {"decision": "deny", "reason": REASON}
    # Antigravity has no ask decision; the registry rule stays an instruction in AGENTS.md there.
    return {"decision": "allow"}


def decide(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {"permission": "allow"}
    call = payload.get("toolCall")
    if isinstance(call, dict):
        return _antigravity(payload, call)
    claude = payload.get("hook_event_name") == "PreToolUse"
    cwd = _cwd(payload)
    command = payload.get("command")
    if isinstance(command, str) and "tool_name" not in payload and "tool_input" not in payload:
        return _shell(command, claude, cwd)
    tool = str(payload.get("tool_name") or payload.get("tool") or "").replace("_", "").lower()
    tool_input = payload.get("tool_input")
    if tool in SHELL_TOOLS and isinstance(tool_input, dict) and isinstance(tool_input.get("command"), str):
        return _shell(tool_input["command"], claude, cwd)
    found: list[str] = []
    _paths(payload, found)
    patch = tool_input.get("command") if isinstance(tool_input, dict) else None
    if isinstance(patch, str) and "*** Begin Patch" in patch:
        found.extend(match.group(1) for match in _PATCH_FILE.finditer(patch))
    allow = {} if claude else {"permission": "allow"}
    inbox = any(_is_inbox(path, cwd) for path in found)
    registry = any(_is_registry(path, cwd) for path in found)
    if not (inbox or registry) or tool in READ_TOOLS:
        return allow
    writing = tool in WRITE_TOOLS or any(part in tool for part in ("write", "edit", "delete", "patch"))
    if not writing:
        return allow
    if inbox:
        return _claude_deny() if claude else _cursor_deny()
    return _claude_ask() if claude else _cursor_ask()


def main() -> int:
    stream = getattr(sys.stdin, "buffer", None)
    raw = stream.read().decode("utf-8-sig") if stream is not None else sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    result = decide(payload)
    # Codex parses permissionDecision "ask" but does not support it: it marks the hook failed, shows an error,
    # and runs the tool anyway. Its hook passes --codex, so there the registry rule stays an AGENTS.md instruction.
    if "--codex" in sys.argv[1:] and result.get("hookSpecificOutput", {}).get("permissionDecision") == "ask":
        result = {}
    sys.stdout.write(json.dumps(result))
    denied = result.get("permission") == "deny" or result.get("decision") == "deny" or (
        result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
    )
    # Antigravity reads the JSON decision; a non-zero exit could count as a failed hook, so only the others get exit 2.
    if denied and payload.get("hook_event_name") == "PreToolUse" and "toolCall" not in payload:
        print(REASON, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
