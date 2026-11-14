"""Append-only capture. A session may add a line; it may not rewrite the inbox."""
import re
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from scripts.filelock import hold
from scripts.model import RegistryParseError, inbox_items, parse_registry, valid_date
from scripts.unshipped import scan_repo, summary_line

class CaptureError(Exception):
    pass


LOCK_WAIT_SECONDS = 10.0


@contextmanager
def inbox_lock(root: Path):
    """One writer at a time. Two sessions finishing together must not lose a line."""
    with hold(Path(root) / "INBOX.md.lock", LOCK_WAIT_SECONDS,
              CaptureError("INBOX.md is locked by another capture; try again")):
        yield


REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
FROM_RE = re.compile(r"\(from [^,\n]+, \d{4}-\d{2}-\d{2}\)\s*$")

TRIAGE_BODIES = (
    "Action: a concrete next step.",
    "Project: an outcome requiring multiple actions.",
    "Waiting: blocked by someone or something else.",
    "Someday: useful, but not active.",
    "Reference: context to keep, not something to do.",
    "Drop: not worth carrying.",
)

DEFAULT_INTRO = (
    "Raw capture goes here. Do not organize while capturing.\n\n"
    "Add anything competing for attention: tasks, worries, ideas, obligations, "
    "deadlines, people to follow up with, things to decide, and loose ends."
)

TRIAGE_PROSE = "For each captured item, decide whether it is:"


def _bodies(text: str) -> list[str]:
    found = []
    for line in text.splitlines():
        if line.startswith("- ") or line.startswith("* "):
            body = line[2:].strip()
            if body:
                found.append(body)
    return found


def assert_keeps(before: str, after: str) -> None:
    """Refuse when a bullet or a prose line from the inbox would disappear."""
    old = Counter(_bodies(before))
    new = Counter(_bodies(after))
    if any(new[body] < count for body, count in old.items()):
        raise CaptureError("refusing to shrink INBOX.md")
    for line in before.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            continue
        if stripped not in after:
            raise CaptureError("refusing to shrink INBOX.md")


def _brain_dump_is_last(text: str) -> bool:
    headings = [line.strip() for line in text.splitlines() if line.startswith("## ")]
    return bool(headings) and headings[-1] == "## Brain Dump"


def _skeleton() -> str:
    triage = "\n".join(f"- {body}" for body in TRIAGE_BODIES)
    return (
        f"# Inbox\n\n{DEFAULT_INTRO}\n\n## Triage Rules\n\n{TRIAGE_PROSE}\n\n"
        f"{triage}\n\n## Brain Dump\n"
    )


def repair(text: str) -> str:
    """Make Brain Dump the last heading. Keep every existing line."""
    if not text.strip():
        return _skeleton()
    if _brain_dump_is_last(text):
        return text if text.endswith("\n") else text + "\n"
    # Only stray bullets from the intro and Triage Rules move into Brain Dump. The owner's own sections keep their
    # lines, and Brain Dump keeps every line as written, including indented details and prose under a bullet.
    intro: list[str] = []
    triage_prose: list[str] = []
    strays: list[str] = []
    brain: list[str] = []
    others: list[list[str]] = []
    seen_triage: set[str] = set()
    section = "intro"
    for line in text.splitlines():
        if line.startswith("## "):
            name = line.strip()
            if name == "## Triage Rules":
                section = "triage"
            elif name == "## Brain Dump":
                section = "brain"
            else:
                section = "other"
                others.append([line])
            continue
        if section == "brain":
            brain.append(line)
            continue
        if section == "other":
            others[-1].append(line)
            continue
        if line.startswith("# ") and section == "intro":
            continue
        if line.startswith("- ") or line.startswith("* "):
            body = line[2:].strip()
            if not body:
                continue
            if section == "triage" and body in TRIAGE_BODIES:
                seen_triage.add(body)
            else:
                strays.append(f"- {body}")
            continue
        if section == "intro":
            intro.append(line)
        elif line.strip():
            triage_prose.append(line)
    intro_text = "\n".join(intro).strip() or DEFAULT_INTRO
    present = [f"- {body}" for body in TRIAGE_BODIES if body in seen_triage]
    missing = [f"- {body}" for body in TRIAGE_BODIES if body not in seen_triage]
    parts = ["# Inbox", "", intro_text, "", "## Triage Rules", ""]
    if triage_prose:
        parts.extend(triage_prose)
        parts.append("")
    elif TRIAGE_PROSE not in intro_text:
        parts.extend([TRIAGE_PROSE, ""])
    parts.extend(present + missing)
    parts.append("")
    for block in others:
        while len(block) > 1 and not block[-1].strip():
            block.pop()
        parts.extend(block)
        parts.append("")
    while brain and not brain[0].strip():
        brain.pop(0)
    parts.extend(["## Brain Dump", ""])
    parts.extend(strays)
    parts.extend(brain)
    result = "\n".join(parts).rstrip() + "\n"
    assert_keeps(text, result)
    return result


def format_bullet(repo: str, text: str, today: str) -> str:
    repo = repo.strip()
    if not REPO_RE.fullmatch(repo):
        raise CaptureError("repo must be a folder name without spaces or commas")
    if not valid_date(today):
        raise CaptureError("today must be YYYY-MM-DD")
    body = text.strip()
    if body.startswith("- "):
        body = body[2:].strip()
    if not body or "\n" in body or "\r" in body or body.startswith("#"):
        raise CaptureError("capture text must be one non-empty line")
    if FROM_RE.search(body):
        return f"- {body}"
    return f"- {body} (from {repo}, {today})"


def check_root(root: Path) -> Path:
    """Refuse a root that is not an existing Plainbrain folder.

    Git Bash turns an unquoted C:\\Plainbrain into the drive-relative C:Plainbrain, which
    quietly resolved to a new folder and a new, empty inbox. A root must be absolute (after
    resolving '.') and already hold REGISTRY.md or INBOX.md.
    """
    raw = Path(root)
    if raw.drive and not raw.is_absolute():
        raise CaptureError(f"--root {root} is drive-relative; quote it or use C:/Plainbrain")
    resolved = raw.resolve()
    if not resolved.is_dir() or not any((resolved / name).is_file() for name in ("REGISTRY.md", "INBOX.md")):
        raise CaptureError(f"--root {resolved} is not a Plainbrain folder (no REGISTRY.md or INBOX.md)")
    return resolved


def capture_line(root: Path, repo: str, text: str, today: str) -> str:
    bullet = format_bullet(repo, text, today)
    root = check_root(root)
    path = Path(root) / "INBOX.md"
    with inbox_lock(root):
        original = path.read_text(encoding="utf-8") if path.is_file() else ""
        updated = repair(original)
        if not updated.endswith("\n"):
            updated += "\n"
        updated += bullet + "\n"
        assert_keeps(original, updated)
        if not _brain_dump_is_last(updated):
            raise CaptureError("refusing to shrink INBOX.md")
        if bullet[2:] not in inbox_items(updated):
            raise CaptureError("refusing to shrink INBOX.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8", newline="\n")
    return bullet


def _pick(bodies: list[str], taken: set[int], exact: str | None, contains: str | None) -> int:
    if exact is not None:
        wanted = exact.strip()
        if wanted.startswith("- "):
            wanted = wanted[2:].strip()
        hits = [i for i, body in enumerate(bodies) if body == wanted and i not in taken]
        if not hits:
            raise CaptureError(f"no Brain Dump line is exactly: {wanted[:80]}")
        return hits[0]
    needle = (contains or "").strip().casefold()
    if not needle:
        raise CaptureError("--contains needs some text")
    hits = [i for i, body in enumerate(bodies) if needle in body.casefold() and i not in taken]
    if not hits:
        raise CaptureError(f"no Brain Dump line contains: {contains[:80]}")
    if len(hits) > 1:
        raise CaptureError(f"{len(hits)} Brain Dump lines contain: {contains[:80]}; use more of the line")
    return hits[0]


def drop_lines(root: Path, exact: list[str] | None = None, contains: list[str] | None = None) -> list[str]:
    """Remove accepted triage lines from Brain Dump. Every match must be found, or nothing is written."""
    exact = exact or []
    contains = contains or []
    if not exact and not contains:
        raise CaptureError("name a line with --line or --contains")
    root = check_root(root)
    path = Path(root) / "INBOX.md"
    with inbox_lock(root):
        if not path.is_file():
            raise CaptureError("INBOX.md is missing")
        original = path.read_text(encoding="utf-8")
        lines = original.splitlines()
        positions: list[int] = []
        bodies: list[str] = []
        in_section = False
        for index, line in enumerate(lines):
            if line.startswith("## "):
                in_section = line.strip() == "## Brain Dump"
                continue
            if in_section and (line.startswith("- ") or line.startswith("* ")) and line[2:].strip():
                positions.append(index)
                bodies.append(line[2:].strip())
        taken: set[int] = set()
        for text in exact:
            taken.add(_pick(bodies, taken, text, None))
        for text in contains:
            taken.add(_pick(bodies, taken, None, text))
        removed = [bodies[i] for i in sorted(taken)]
        cut = {positions[i] for i in taken}
        updated = "\n".join(line for index, line in enumerate(lines) if index not in cut).rstrip() + "\n"
        lost = Counter(_bodies(original)) - Counter(_bodies(updated))
        if lost != Counter(removed) or not _brain_dump_is_last(updated):
            raise CaptureError("drop would change more than the named lines; nothing written")
        for line in original.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith(("- ", "* ", "#")) and stripped not in updated:
                raise CaptureError("drop would change more than the named lines; nothing written")
        path.write_text(updated, encoding="utf-8", newline="\n")
    return removed


def _pointer_matches(pointer: str, repo: str) -> bool:
    pointer = pointer.strip().strip("'\"")
    if not pointer:
        return False
    return Path(pointer.replace("\\", "/")).name.casefold() == repo.casefold()


def _section(text: str, heading: str) -> str:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == heading:
            start = index + 1
            break
    if start is None:
        return ""
    body = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body).strip()


def _card_repo(text: str) -> str:
    for pattern in (r"(?m)^repo:\s*'([^']*)'", r'(?m)^repo:\s*"([^"]*)"', r"(?m)^repo:\s*(\S+)"):
        found = re.search(pattern, text)
        if found:
            return found.group(1).strip()
    return ""


def repo_view(root: Path, repo: str, today: str) -> str:
    """Open commitments, the newest inbox line, the card, and unshipped work for one repo."""
    root = Path(root)
    repo = repo.strip()
    lines = [f"# {repo}", "", f"As of {today}.", ""]
    open_items: list[str] = []
    registry = root / "REGISTRY.md"
    if registry.is_file():
        try:
            items = parse_registry(registry.read_text(encoding="utf-8")).items
        except RegistryParseError:
            items = []
        for item in items:
            if item.reason is not None or item.fields.get("status", "").strip() == "done":
                continue
            if _pointer_matches(item.fields.get("pointer", ""), repo):
                open_items.append(f"- {item.id}: {item.fields.get('next', '').strip()}")
    lines.extend(["## Open registry items", ""])
    lines.extend(open_items or ["- None."])
    lines.append("")
    inbox = root / "INBOX.md"
    captured = inbox_items(inbox.read_text(encoding="utf-8")) if inbox.is_file() else []
    newest = ""
    for line in captured:
        if re.search(rf"\(from {re.escape(repo)}, \d{{4}}-\d{{2}}-\d{{2}}\)\s*$", line):
            newest = line
    lines.extend(["## Newest inbox line", "", f"- {newest}" if newest else "- None.", ""])
    card_path = root / "knowledge" / "projects" / f"{repo}.md"
    now = ""
    checkout = ""
    if card_path.is_file():
        card = card_path.read_text(encoding="utf-8")
        now = _section(card, "## Now")
        checkout = _card_repo(card)
    lines.extend(["## Now", "", now or "- No project card.", ""])
    lines.extend(["## Unshipped", ""])
    folder = Path(checkout) if checkout else None
    if folder is None or not folder.is_dir() or not (folder / ".git").exists():
        lines.append("- No checkout to scan.")
    else:
        row = scan_repo(repo, folder)
        row["area"] = "local"
        if row["branches"] or row["trees"] or row["stashes"]:
            lines.append(summary_line(row))
        else:
            lines.append("- Nothing unpushed.")
    lines.append("")
    return "\n".join(lines)
