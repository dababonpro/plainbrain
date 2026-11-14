"""Change REGISTRY.md one item at a time, through checks, and keep a record of each change.

    python scripts/brain.py registry add --root . --id dentist-call --set "title=Book the dentist" --set "next=Call the clinic"
    python scripts/brain.py registry update --root . --id dentist-call --set status=waiting --set "blocked_on=Clinic" --set follow_up=2026-11-20
    python scripts/brain.py registry done --root . --id dentist-call --set "outcome=nothing to keep"
    python scripts/brain.py registry focus --root . --id dentist-call        (or --clear)
    python scripts/brain.py registry archive --root . --id dentist-call
    python scripts/brain.py registry show --root . --id dentist-call

Run a command only after the owner has accepted the change. Each one edits a single block, refuses anything the
registry rules do not allow, leaves every other item exactly as it was, and adds a line to reviews/registry/YYYY-MM.md
saying what changed.
"""
import os
import re
from contextlib import contextmanager
from pathlib import Path

from scripts.filelock import hold
from scripts.model import ID_RE, KNOWN_STATUS, RegistryParseError, parse_registry, valid_date

CORE_FIELDS = ["title", "area", "kind", "status", "next", "blocked_on", "follow_up", "pointer", "opened", "updated",
               "outcome", "notes"]
OPTIONAL_FIELDS = ["weekly", "due", "depends_on", "requested_on", "knowledge"]
FIELDS = CORE_FIELDS + OPTIONAL_FIELDS
DEFAULT_AREAS = ["Work", "Personal"]
LOCK_WAIT_SECONDS = 10.0
LOG_VALUE_LIMIT = 80


class RegistryError(Exception):
    pass


@contextmanager
def registry_lock(root: Path):
    """One writer at a time, the same way capture guards the inbox."""
    with hold(Path(root) / "REGISTRY.md.lock", LOCK_WAIT_SECONDS,
              RegistryError("REGISTRY.md is locked by another change; try again")):
        yield


def _read(root: Path) -> tuple[list[str], str]:
    path = Path(root) / "REGISTRY.md"
    if not path.is_file():
        raise RegistryError("REGISTRY.md is missing")
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.split(newline), newline


def _parse(lines: list[str]):
    try:
        return parse_registry("\n".join(lines))
    except RegistryParseError as exc:
        raise RegistryError(f"REGISTRY.md cannot be read near: {exc.report}. Fix it by hand before using a command.")


def _block(lines: list[str], item_id: str) -> tuple[int, int]:
    """First line of the item's heading, and the line after its last field."""
    start = next((i for i, line in enumerate(lines) if line.strip() == f"## {item_id}"), None)
    if start is None:
        raise RegistryError(f"no item called {item_id}")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    while end > start + 1 and lines[end - 1].strip() == "":
        end -= 1
    return start, end


def _areas(root: Path) -> list[str]:
    context = Path(root) / "CONTEXT.md"
    if context.is_file():
        for line in context.read_text(encoding="utf-8").splitlines():
            if line.startswith("areas:"):
                found = [a.strip() for a in line.split(":", 1)[1].split(",") if a.strip()]
                if found:
                    return found
    return DEFAULT_AREAS


def parse_sets(pairs: list[str] | None) -> dict[str, str]:
    changes: dict[str, str] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise RegistryError(f"--set takes field=value, got: {pair}")
        key, value = pair.split("=", 1)
        key, value = key.strip(), value.strip()
        if key not in FIELDS:
            raise RegistryError(f"unknown field {key}. Fields are: {', '.join(FIELDS)}")
        if "\n" in value or "\r" in value:
            raise RegistryError(f"{key} must be one line")
        changes[key] = value
    return changes


def _check_fields(root: Path, fields: dict[str, str], known_ids: set[str]) -> None:
    """Rules that need more than the item itself: the owner's areas and the other ids.

    Status, blocked_on, follow_up and the dates are checked once, by model._unusable_reason, when _validate parses
    the result. Keeping one rule set means the brief and the commands cannot disagree about what is usable.
    """
    status = fields.get("status", "")
    if status not in KNOWN_STATUS:
        raise RegistryError(f"status must be one of: {', '.join(KNOWN_STATUS)}")
    area = fields.get("area", "")
    if area and area not in _areas(root):
        raise RegistryError(f"area must be one of: {', '.join(_areas(root))}")
    if fields.get("weekly", "") not in ("", "yes"):
        raise RegistryError("weekly is yes or empty")
    for dep in filter(None, (d.strip() for d in fields.get("depends_on", "").split(","))):
        if dep not in known_ids:
            raise RegistryError(f"depends_on names {dep}, which is not in the registry")


def _line(key: str, value: str) -> str:
    return f"{key}: {value}" if value else f"{key}:"


def _short(value: str) -> str:
    value = value.strip()
    return value if len(value) <= LOG_VALUE_LIMIT else value[:LOG_VALUE_LIMIT - 3] + "..."


def _log(root: Path, today: str, action: str, item_id: str, changes: list[tuple[str, str, str]], why: str) -> None:
    folder = Path(root) / "reviews" / "registry"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{today[:7]}.md"
    parts = "; ".join(f'{key}: "{_short(old)}" -> "{_short(new)}"' for key, old, new in changes)
    line = f"- {today} {action} {item_id}" + (f": {parts}" if parts else "") + (f" (why: {_short(why)})" if why else "")
    head = "" if path.exists() else f"# Registry changes {today[:7]}\n\nOne line per accepted change, written by the registry commands.\n\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(head + line + "\n")


def _validate(before: list[str], after: list[str], touched: set[str], removed: set[str] = frozenset()) -> None:
    """Refuse a result that fails the registry's own rules, or that changed an item other than the ones named."""
    old, new = _parse(before), _parse(after)
    for item in new.items:
        if item.id in touched and item.reason:
            raise RegistryError(f"{item.id} would be unusable: {item.reason}. Nothing was changed.")
    old_others = {i.id: i.fields for i in old.items if i.id not in touched and i.id not in removed}
    new_others = {i.id: i.fields for i in new.items if i.id not in touched}
    if old_others != new_others:
        raise RegistryError("the change would have altered another item. Nothing was changed.")
    if {i.id for i in old.items} - {i.id for i in new.items} != set(removed):
        raise RegistryError("the change would have dropped an item. Nothing was changed.")


def _commit(root: Path, after: list[str], newline: str) -> None:
    path = Path(root) / "REGISTRY.md"
    tmp = path.with_name("REGISTRY.md.tmp")
    tmp.write_bytes(newline.join(after).encode("utf-8"))
    os.replace(tmp, path)


def _write(root: Path, before: list[str], after: list[str], newline: str, touched: set[str]) -> None:
    _validate(before, after, touched)
    _commit(root, after, newline)


def show(root: Path, item_id: str) -> str:
    lines, _newline = _read(root)
    start, end = _block(lines, item_id)
    return "\n".join(lines[start:end])


def add(root: Path, item_id: str, changes: dict[str, str], today: str, why: str = "") -> str:
    if not ID_RE.fullmatch(item_id or ""):
        raise RegistryError("an id is lowercase letters, digits and hyphens")
    with registry_lock(root):
        lines, newline = _read(root)
        doc = _parse(lines)
        if any(item.id == item_id for item in doc.items):
            raise RegistryError(f"{item_id} already exists; use update")
        fields = {"status": "active", "kind": "task", "opened": today, **changes, "updated": today}
        for key in ("title", "next"):
            if not fields.get(key):
                raise RegistryError(f"a new item needs {key}")
        _check_fields(root, fields, {item.id for item in doc.items})
        # Write the optional fields too when the registry already keeps them on its items, so blocks stay alike.
        keeps_optional = any(key in item.fields for item in doc.items for key in OPTIONAL_FIELDS)
        keys = CORE_FIELDS + [key for key in OPTIONAL_FIELDS if keeps_optional or key in fields]
        block = [f"## {item_id}"] + [_line(key, fields.get(key, "")) for key in keys]
        body = list(lines)
        while body and body[-1].strip() == "":
            body.pop()
        after = body + ["", *block, ""]
        _write(root, lines, after, newline, {item_id})
        _log(root, today, "add", item_id, [(k, "", fields[k]) for k in keys if fields.get(k)], why)
    return "\n".join(block)


def update(root: Path, item_id: str, changes: dict[str, str], today: str, why: str = "", action: str = "update") -> str:
    if not changes:
        raise RegistryError("nothing to change; pass --set field=value")
    with registry_lock(root):
        lines, newline = _read(root)
        doc = _parse(lines)
        item = next((i for i in doc.items if i.id == item_id), None)
        if item is None:
            raise RegistryError(f"no item called {item_id}")
        changes = {**changes, **_released(item.fields, changes)}
        fields = {**item.fields, **changes, "updated": today}
        _check_fields(root, fields, {i.id for i in doc.items} - {item_id})
        start, end = _block(lines, item_id)
        after = list(lines)
        changed = []
        for key in [*changes, "updated"]:
            old = item.fields.get(key, "")
            if key != "updated" and old == fields[key]:
                continue
            at = next((i for i in range(start + 1, end) if after[i].partition(":")[0].strip() == key), None)
            if at is None:
                after.insert(end, _line(key, fields[key]))
                end += 1
            else:
                after[at] = _line(key, fields[key])
            if key != "updated":
                changed.append((key, old, fields[key]))
        if not changed:
            raise RegistryError("every field already has that value. Nothing was changed.")
        _write(root, lines, after, newline, {item_id})
        _log(root, today, action, item_id, changed, why)
        return "\n".join(after[start:end])


def _released(old: dict[str, str], changes: dict[str, str]) -> dict[str, str]:
    """Empty blocked_on and follow_up when an item moves to active or done, unless the change sets them.

    A waiting item that becomes active is no longer blocked, and a finished one has nothing to follow up. Left in
    place, blocked_on keeps an active item out of the next action, and an old follow_up lists a done item as blocked.
    """
    before = old.get("status", "").strip()
    after = changes.get("status", before).strip()
    if after == before or after not in ("active", "done"):
        return {}
    return {key: "" for key in ("blocked_on", "follow_up") if key not in changes and old.get(key, "").strip()}


def done(root: Path, item_id: str, changes: dict[str, str], today: str, why: str = "") -> str:
    return update(root, item_id, {**changes, "status": "done"}, today, why, action="done")


def focus(root: Path, item_id: str | None, today: str, why: str = "") -> str:
    with registry_lock(root):
        lines, newline = _read(root)
        doc = _parse(lines)
        if item_id:
            item = next((i for i in doc.items if i.id == item_id), None)
            if item is None:
                raise RegistryError(f"no item called {item_id}")
            if item.fields.get("status") == "done":
                raise RegistryError(f"{item_id} is done; it cannot be the focus")
        at = next(i for i, line in enumerate(lines) if line.startswith("focus:"))
        after = list(lines)
        after[at] = _line("focus", item_id or "")
        if after[at] == lines[at].rstrip():
            raise RegistryError("the focus is already that. Nothing was changed.")
        _write(root, lines, after, newline, set())
        _log(root, today, "focus", item_id or "(cleared)", [("focus", doc.focus, item_id or "")], why)
    return after[at]


def _has_record(root: Path, item_id: str, fields: dict[str, str]) -> bool:
    """An item may leave the registry only when what it taught is already kept somewhere."""
    knowledge = fields.get("knowledge", "").strip()
    if knowledge and (Path(root) / knowledge).is_file():
        return True
    if fields.get("outcome", "").strip().lower() == "nothing to keep":
        return True
    cards = Path(root) / "knowledge" / "projects"
    if cards.is_dir():
        for card in cards.glob("*.md"):
            text = card.read_text(encoding="utf-8", errors="replace")
            now = re.search(r"^## Now\s*$(.*?)(?=^## |\Z)", text, flags=re.M | re.S)
            if now and re.search(rf"(?<![a-z0-9-]){re.escape(item_id)}(?![a-z0-9-])", now.group(1)):
                return True
    return False


def archive(root: Path, item_id: str, today: str, why: str = "", not_done: bool = False) -> str:
    with registry_lock(root):
        lines, newline = _read(root)
        doc = _parse(lines)
        item = next((i for i in doc.items if i.id == item_id), None)
        if item is None:
            raise RegistryError(f"no item called {item_id}")
        if item.fields.get("status") != "done" and not not_done:
            raise RegistryError(f"{item_id} is not done. Archive it only when the owner names it and confirms again, with --not-done.")
        if item.fields.get("status") == "done" and not _has_record(root, item_id, item.fields):
            raise RegistryError(f"{item_id} has no record to keep: set knowledge to a note that exists, set outcome to "
                                "'nothing to keep', or name the id in a project card's Now section.")
        if doc.focus == item_id:
            raise RegistryError(f"{item_id} is the focus; clear the focus first")
        start, end = _block(lines, item_id)
        block = lines[start:end]
        after = lines[:start] + lines[end:]
        # One blank line between the neighbours where the block was.
        while start < len(after) and start > 0 and after[start].strip() == "" and after[start - 1].strip() == "":
            del after[start]
        _validate(lines, after, set(), removed={item_id})
        folder = Path(root) / "archive"
        folder.mkdir(exist_ok=True)
        target = folder / f"{today[:7]}.md"
        size = target.stat().st_size if target.is_file() else 0
        gap = "\n" if size > 0 else ""
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(gap + f"archived: {today}\n" + "\n".join(block) + "\n")
        try:
            _commit(root, after, newline)
        except OSError:
            # The registry still holds the item, so take the copy back out of the archive: a retry must not add
            # it twice.
            with target.open("r+b") as handle:
                handle.truncate(size)
            if size == 0:
                target.unlink()
            raise
        _log(root, today, "archive", item_id, [("status", item.fields.get("status", ""), "archived")], why)
    return f"archived {item_id} to archive/{today[:7]}.md"


def add_parser(sub) -> None:
    registry = sub.add_parser("registry", help="change one registry item, after the owner accepts")
    actions = registry.add_subparsers(dest="registry_cmd", required=True)
    for name in ("add", "update", "done", "focus", "archive", "show"):
        command = actions.add_parser(name)
        command.add_argument("--root", required=True)
        command.add_argument("--today", default=None)
        command.add_argument("--id", required=name != "focus")
        if name in ("add", "update", "done"):
            command.add_argument("--set", action="append", metavar="FIELD=VALUE")
        if name != "show":
            command.add_argument("--why", default="", help="what the owner accepted, in a few words, for the record")
        if name == "focus":
            command.add_argument("--clear", action="store_true")
        if name == "archive":
            command.add_argument("--not-done", action="store_true", help="the owner named this item and confirmed again")


def run(args, today: str) -> str:
    root = Path(args.root)
    action = args.registry_cmd
    if action == "show":
        return show(root, args.id)
    if action == "add":
        return add(root, args.id, parse_sets(args.set), today, args.why)
    if action == "update":
        return update(root, args.id, parse_sets(args.set), today, args.why)
    if action == "done":
        return done(root, args.id, parse_sets(args.set), today, args.why)
    if action == "focus":
        if bool(args.id) == bool(args.clear):
            raise RegistryError("pass --id to set the focus, or --clear to empty it")
        return focus(root, None if args.clear else args.id, today, args.why)
    return archive(root, args.id, today, args.why, args.not_done)
