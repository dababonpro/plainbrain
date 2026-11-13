import re
from datetime import date
from dataclasses import dataclass
from pathlib import Path

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[a-z0-9-]+$")
KNOWN_STATUS = ("active", "waiting", "someday", "done")


def valid_date(value: str) -> bool:
    try:
        return bool(DATE_RE.fullmatch(value)) and date.fromisoformat(value) is not None
    except ValueError:
        return False


NOTE_SKIP_DIRS = {"team"}
NOTE_SKIP_FILES = {"TEMPLATE.md", "LOG.md", "README.md", "INDEX.md"}
_NOTE_FIELD = re.compile(r"^([a-z_]+):\s*(.*)$")


def note_paths(folder: Path) -> list[Path]:
    """Notes under a knowledge folder, sorted. Staff cards, templates, logs and indexes are left out."""
    found = []
    for path in sorted(Path(folder).rglob("*.md")):
        rel = path.relative_to(folder)
        if NOTE_SKIP_DIRS & set(rel.parts[:-1]) or path.name in NOTE_SKIP_FILES:
            continue
        found.append(path)
    return found


def note_head(text: str) -> tuple[str, dict[str, str]]:
    """A note's title and its `key: value` header fields, read from the text before the first `## ` heading.

    The first value of a field wins, so the frontmatter is not overridden by a line in the body. The title is the
    first `# ` line outside the frontmatter block and outside fenced code, or "" when there is none.
    """
    title = ""
    fields: dict[str, str] = {}
    lines = text.splitlines()
    front = bool(lines) and lines[0].strip() == "---"
    fenced = False
    for number, line in enumerate(lines):
        if front:
            if number and line.strip() == "---":
                front = False
                continue
        elif line.startswith("```"):
            fenced = not fenced
            continue
        elif fenced:
            continue
        elif line.startswith("## "):
            break
        elif line.startswith("# "):
            title = title or line[2:].strip()
            continue
        found = _NOTE_FIELD.match(line)
        if found:
            fields.setdefault(found.group(1), found.group(2).strip())
    return title, fields


@dataclass
class Item:
    id: str
    fields: dict[str, str]
    reason: str | None


@dataclass
class RegistryDoc:
    focus: str
    items: list[Item]


class RegistryParseError(Exception):
    def __init__(self, report: str) -> None:
        super().__init__(report)
        self.report = report


def _value(fields: dict[str, str], key: str) -> str | None:
    if key not in fields:
        return None
    return fields[key].strip()


def _unusable_reason(fields: dict[str, str], duplicate: bool) -> str | None:
    if duplicate:
        return "duplicate id"
    title = _value(fields, "title")
    if not title:
        return "missing title"
    status = _value(fields, "status")
    if not status:
        return "missing status"
    nxt = _value(fields, "next")
    if not nxt and status != "done":
        return "missing next"
    updated = _value(fields, "updated")
    if not updated:
        return "missing updated"
    if not valid_date(updated):
        return "bad updated"
    if status not in KNOWN_STATUS:
        return "bad status"
    follow = _value(fields, "follow_up") or ""
    if follow and not valid_date(follow):
        return "bad follow_up"
    blocked_on = _value(fields, "blocked_on") or ""
    if status == "waiting" and blocked_on == "":
        return "waiting without blocked_on"
    if status == "someday" and follow == "":
        return "someday without follow_up"
    for key in ("opened", "due", "requested_on"):
        value = _value(fields, key) or ""
        if value and not valid_date(value):
            return f"bad {key}"
    if fields.get("kind") not in (None, "task", "project"):
        return "bad kind"
    return None


def parse_registry(text: str) -> RegistryDoc:
    lines = text.splitlines()
    if not any(line.strip() == "# Registry" for line in lines):
        raise RegistryParseError("line 1")
    first_item = next((i for i, line in enumerate(lines) if line.startswith("## ")), None)
    preamble = lines if first_item is None else lines[:first_item]
    focus = None
    for line in preamble:
        if line.startswith("focus:"):
            focus = line.split(":", 1)[1].strip()
            break
    if focus is None:
        raise RegistryParseError("line 1")
    items: list[Item] = []
    seen: set[str] = set()
    current_id: str | None = None
    current_fields: dict[str, str] = {}

    def finish() -> None:
        nonlocal current_id, current_fields
        if current_id is None:
            return
        duplicate = current_id in seen
        if not duplicate:
            seen.add(current_id)
        items.append(
            Item(
                id=current_id,
                fields=current_fields,
                reason=_unusable_reason(current_fields, duplicate),
            )
        )

    if first_item is None:
        return RegistryDoc(focus=focus, items=[])
    for index in range(first_item, len(lines)):
        line = lines[index]
        lineno = index + 1
        if line.startswith("## "):
            finish()
            raw = line[3:].strip()
            if raw == "" or ID_RE.fullmatch(raw) is None:
                raise RegistryParseError(raw if raw else f"line {lineno}")
            current_id = raw
            current_fields = {}
            continue
        if current_id is None or line.strip() == "":
            continue
        if ":" not in line:
            raise RegistryParseError(current_id)
        key, _, value = line.partition(":")
        key = key.strip()
        if key == "":
            raise RegistryParseError(current_id)
        current_fields[key] = value.strip()
    finish()
    return RegistryDoc(focus=focus, items=items)


def inbox_items(text: str) -> list[str]:
    found: list[str] = []
    in_section = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_section = line.strip() == "## Brain Dump"
            continue
        if in_section and (line.startswith("- ") or line.startswith("* ")):
            body = line[2:].strip()
            if body:
                found.append(body)
    return found


def capacity_line(text: str | None) -> str:
    if not text:
        return "Capacity is unknown."
    for line in text.splitlines():
        if line.startswith("capacity:"):
            value = line.split(":", 1)[1].strip()
            if value == "" or value == "Unknown":
                return "Capacity is unknown."
            return f"Capacity: {value}."
    return "Capacity is unknown."


def _dated_briefs(daily: Path) -> list[Path]:
    if not daily.is_dir():
        return []
    return sorted(
        (path for path in daily.glob("*.md") if DATE_RE.fullmatch(path.stem)),
        key=lambda path: path.stem,
    )


def previous_brief_path(daily: Path, today: str) -> Path | None:
    earlier = [path for path in _dated_briefs(daily) if path.stem < today]
    return earlier[-1] if earlier else None


def latest_brief_path(daily: Path) -> Path | None:
    found = _dated_briefs(daily)
    return found[-1] if found else None


def snapshot_inbox(brief_text: str) -> int | None:
    in_snapshot = False
    for line in brief_text.splitlines():
        if line.strip() == "snapshot:":
            in_snapshot = True
            continue
        if in_snapshot and line.startswith("inbox:"):
            raw = line.split(":", 1)[1].strip()
            return int(raw) if raw.isdigit() else None
    return None


def counts(items: list[Item]) -> dict[str, int]:
    totals = {status: 0 for status in KNOWN_STATUS}
    seen: set[str] = set()
    for item in items:
        if item.id in seen:
            continue
        seen.add(item.id)
        if item.reason == "bad status":
            continue
        status = item.fields.get("status", "").strip()
        if status in totals:
            totals[status] += 1
    return totals
