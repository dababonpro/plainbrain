"""Deny agent edits to the Second Brain INBOX.md. Reads, capture, and inbox-drop stay allowed."""
import json
import re
import sys
from pathlib import Path

INBOX = Path(__file__).resolve().parents[1] / "INBOX.md"

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
}
READ_TOOLS = {"read", "grep", "glob", "semanticsearch", "tabread"}
SHELL_TOOLS = {"bash", "powershell", "shell", "runterminalcmd", "terminal"}

_HOME = INBOX.parent.as_posix()
REASON = (
    "Do not edit INBOX.md. Append with: "
    f"python {_HOME}/scripts/brain.py capture --root {_HOME} --repo <repo-name> "
    '--today YYYY-MM-DD --text "one sentence". '
    f'Remove an accepted triage line with: python {_HOME}/scripts/brain.py inbox-drop --root {_HOME} --line "<exact line>"'
)

_PATH_KEYS = {"path", "file_path", "filepath", "target_file", "file", "notebook_path"}
_WRITE_WORDS = re.compile(
    r"\b(set-content|out-file|add-content|clear-content|remove-item|copy-item|move-item|"
    r"del|erase|rm|cp|mv|copy|move|ren|tee|truncate)\b"
    r"|\bsed\s+(-\S*\s+)*-i"
    r"|\bgit\s+(checkout|restore|reset|stash|clean)\b",
    re.IGNORECASE,
)
_REDIRECT = re.compile(r">\s*[\"']?\S*inbox\.md", re.IGNORECASE)
_QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"|\'[^\']*\'')
_CHAIN = re.compile(r"[;&|<>`\n]|\$\(")
_OWN_COMMAND = re.compile(
    r"^\s*(\S*python\S*|py)(\s+-\S+)*\s+\S*brain\.py\s+(capture|inbox-drop|for-repo)(\s|$)",
    re.IGNORECASE,
)


def _norm(path: str) -> str:
    text = path.strip().strip("'\"").replace("\\", "/")
    found = re.match(r"^/([a-zA-Z])/(.*)$", text)
    if found:
        text = f"{found.group(1)}:/{found.group(2)}"
    return text.casefold()


INBOX_KEY = _norm(str(INBOX))
ROOT_KEY = _norm(str(INBOX.parent))


def _cwd(payload: dict) -> str:
    for key in ("cwd", "working_directory"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    roots = payload.get("workspace_roots")
    if isinstance(roots, list) and len(roots) == 1 and isinstance(roots[0], str):
        return roots[0]
    return ""


def _is_inbox(path: str, cwd: str = "") -> bool:
    key = _norm(path)
    if Path(key).name != "inbox.md":
        return False
    if re.match(r"^[a-z]:/", key) or key.startswith("/"):
        return key == INBOX_KEY
    if not cwd:
        return True
    return _norm(f"{cwd.rstrip('/')}/{key}").replace("/./", "/") == INBOX_KEY


def _mentions_inbox(command: str, cwd: str) -> bool:
    lowered = command.replace("\\", "/").casefold()
    if "inbox.md" not in lowered:
        return False
    if INBOX_KEY in _norm(lowered):
        return True
    # A bare INBOX.md counts when the shell runs in Second Brain, or when the folder is unknown.
    return not cwd or _norm(cwd).rstrip("/") == ROOT_KEY


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


def _own_command(command: str) -> bool:
    """One brain.py capture/inbox-drop/for-repo call with nothing chained after it."""
    text = re.sub(r"^\s*&\s*", "", command.strip())
    exe = re.match(r"^\"([^\"]*)\"|^'([^']*)'", text)
    if exe:
        if "python" not in (exe.group(1) or exe.group(2) or "").casefold():
            return False
        text = "python" + text[exe.end():]
    bare = _QUOTED.sub('""', text)
    return _OWN_COMMAND.match(bare) is not None and _CHAIN.search(bare) is None


def _shell(command: str, claude: bool, cwd: str) -> dict:
    allow = {} if claude else {"permission": "allow"}
    if not _mentions_inbox(command, cwd):
        return allow
    if _own_command(command):
        return allow
    lowered = command.lower()
    if _WRITE_WORDS.search(_QUOTED.sub('""', command)) or _REDIRECT.search(command):
        return _claude_deny() if claude else _cursor_deny()
    if re.search(r"\b(python|py|node)\b", lowered) and re.search(r"\bopen\s*\(|\.write|writefile|\bunlink\(", lowered):
        return _claude_deny() if claude else _cursor_deny()
    return allow


def decide(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {"permission": "allow"}
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
    if not any(_is_inbox(path, cwd) for path in found):
        return {} if claude else {"permission": "allow"}
    if tool in READ_TOOLS:
        return {} if claude else {"permission": "allow"}
    writing = tool in WRITE_TOOLS or any(part in tool for part in ("write", "edit", "delete", "patch"))
    if writing:
        return _claude_deny() if claude else _cursor_deny()
    return {} if claude else {"permission": "allow"}


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
    sys.stdout.write(json.dumps(result))
    denied = result.get("permission") == "deny" or (
        result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
    )
    if denied and payload.get("hook_event_name") == "PreToolUse":
        print(REASON, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
