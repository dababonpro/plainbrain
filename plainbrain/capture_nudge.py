"""Claude Code Stop hook: before a session ends with finished work it has not captured, ask the agent to capture it.

AGENTS.md says "From a project folder, record what the next session should know with one capture call per fact."
An agent working in a project can end the session without doing it. This hook reads the session's own record
and, when finished work came after the last capture, sends the agent back once to capture it.

Finished work: a `git commit`, `gh pr create` or `gh pr merge` in a shell call, and a Jira ticket created or
moved through an MCP tool. Captured: a `brain.py capture` call, or the Plainbrain MCP `capture` tool. A `git push`
does not count, because it ships commits that were already counted.

It asks at most once for each batch of new work, never while Claude Code is already continuing because of a stop
hook, and an answer of "nothing worth tracking" ends the matter until new work arrives. What it has already asked
about is kept per session in the system's temporary folder, never in the owner's Plainbrain folder. Any error
lets the session end normally.

Reads the transcript format of Claude Code only. Cursor and Antigravity are not supported: their stop hooks are
reported unreliable, and their transcripts differ."""
import datetime as _dt
import json
import re
import sys
import tempfile
from pathlib import Path

CHECKOUT = Path(__file__).resolve().parents[1]
if str(CHECKOUT) not in sys.path:
    sys.path.insert(0, str(CHECKOUT))

from plainbrain.home import data_root, is_packaged  # noqa: E402

STATE = Path(tempfile.gettempdir()) / "plainbrain-capture-nudge"

_SHELL = {"bash", "powershell", "shell"}
_OUTCOME = re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?(commit)\b|\bgh\s+pr\s+(create|merge)\b", re.IGNORECASE)
_CAPTURE = re.compile(
    r"brain\.py[\"']?\s+capture\b"
    r"|(?:^|[\s&;|\"'/\\])plainbrain(?:\.exe)?[\"']?\s+capture\b",
    re.IGNORECASE,
)
# The folder after cd / Set-Location / git -C: a quoted path (which may hold spaces) or a bare one.
_CD = re.compile(r"(?:\bcd|\bSet-Location|\bgit\s+-C)\s+(?:\"([^\"]+)\"|'([^']+)'|([A-Za-z]:[\\/][^\s;&|]+|/[^\s;&|]+))",
                 re.IGNORECASE)
_JIRA = re.compile(r"__(createJiraIssue|transitionJiraIssue)$")


def _folder_name(path: str) -> str:
    return Path(path.replace("\\", "/").rstrip("/")).name


def _is_capture_tool(name: str) -> bool:
    return name.endswith("__capture") and "plainbrain" in name.lower()


def _tool_calls(transcript: Path):
    """Main-thread tool calls in order. Subagent lines and other record types are skipped."""
    try:
        handle = transcript.open(encoding="utf-8", errors="replace")
    except OSError:
        return
    with handle:
        for line in handle:
            if '"tool_use"' not in line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("type") != "assistant" or row.get("isSidechain"):
                continue
            content = (row.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    args = block.get("input") if isinstance(block.get("input"), dict) else {}
                    yield str(block.get("name") or ""), args


def scan(transcript: Path, cwd: str) -> tuple[int, list[str]]:
    """Total finished work in the session, and the items since the last capture."""
    total, pending = 0, []
    for name, args in _tool_calls(transcript):
        if name.lower() in _SHELL and isinstance(args.get("command"), str):
            command = args["command"]
            folders = [next(part for part in found if part) for found in _CD.findall(command)]
            where = _folder_name(folders[-1] if folders else cwd) or "?"
            for match in _OUTCOME.finditer(command):
                total += 1
                what = f"gh pr {match.group(2).lower()}" if match.group(2) else "git commit"
                pending.append(f"{what} in {where}")
            if _CAPTURE.search(command):
                pending = []
        elif _is_capture_tool(name):
            pending = []
        elif _JIRA.search(name):
            total += 1
            key = args.get("issueIdOrKey") or args.get("summary") or "a ticket"
            pending.append(f"Jira {'created' if 'create' in name else 'moved'}: {str(key)[:80]}")
    return total, pending


def _seen(session: str) -> int:
    try:
        return int((STATE / f"{session}.txt").read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        return 0


def _remember(session: str, total: int) -> None:
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        (STATE / f"{session}.txt").write_text(str(total), encoding="utf-8")
    except OSError:
        pass


def reason(pending: list[str], cwd: str, brain: Path, today: str) -> str:
    listed = "; ".join(dict.fromkeys(pending))
    repo = _folder_name(cwd) or "<folder-name>"
    if is_packaged():
        command = (
            f'plainbrain capture --repo "{repo}" --today {today} '
            '--text "<what happened, and what is left>"'
        )
    else:
        script = (CHECKOUT / "scripts" / "brain.py").as_posix()
        command = (
            f'python "{script}" capture --root "{brain.as_posix()}" --repo "{repo}" --today {today} '
            '--text "<what happened, and what is left>"'
        )
    return (
        f"Before you stop: this session finished work that is not in the owner's Plainbrain inbox yet ({listed}). "
        f"Capture what the next session should know, one sentence per fact: {command} "
        "(use the folder name of the project the work was in as --repo), or the Plainbrain MCP capture tool. "
        "Tell the owner what you captured. If nothing here is worth tracking, say so in one line and stop."
    )


def decide(payload: dict, today: str | None = None, brain: Path | None = None) -> dict:
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        return {}
    brain = brain or data_root(CHECKOUT)
    transcript = payload.get("transcript_path")
    session = re.sub(r"[^A-Za-z0-9_-]", "", str(payload.get("session_id") or ""))
    if brain is None or not transcript or not session:
        return {}
    cwd = str(payload.get("cwd") or "")
    total, pending = scan(Path(transcript), cwd)
    if not pending or total <= _seen(session):
        return {}
    _remember(session, total)
    return {"decision": "block", "reason": reason(pending, cwd, Path(brain), today or _dt.date.today().isoformat())}


def main() -> int:
    stream = getattr(sys.stdin, "buffer", None)
    raw = stream.read().decode("utf-8-sig") if stream is not None else sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
        result = decide(payload)
    except Exception:  # a broken nudge must never stop a session from ending
        result = {}
    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
