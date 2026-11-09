"""Read-only grouping of inbox lines for triage; never edits INBOX.md or the registry."""
import re
from pathlib import Path

from scripts.model import Item, RegistryParseError, inbox_items, parse_registry

_FROM = re.compile(r"\(from ([^,\n]+), (\d{4}-\d{2}-\d{2})\)\s*$")
_TICKET = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


def _names_id(line: str, item_id: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(item_id.casefold())}(?![a-z0-9])", line.casefold()) is not None


def _open_items(items: list[Item]) -> list[Item]:
    first: dict[str, Item] = {}
    for item in items:
        if item.reason is None and item.fields.get("status", "").strip() != "done":
            first.setdefault(item.id, item)
    return list(first.values())


def group_key(line: str, open_items: list[Item]) -> tuple[str, str]:
    """(kind, key): an open registry id named or holding the line's ticket, else the first ticket, else the repo."""
    for item in open_items:
        if _names_id(line, item.id):
            return "registry", item.id
    tickets = _TICKET.findall(line)
    for item in open_items:
        blob = " ".join(item.fields.get(key, "") for key in ("title", "next", "notes"))
        if set(tickets) & set(_TICKET.findall(blob)):
            return "registry", item.id
    if tickets:
        return "ticket", tickets[0]
    found = _FROM.search(line)
    return "repo", found.group(1).strip() if found else "no source"


def rollup(lines: list[str], items: list[Item]) -> list[dict]:
    """Groups in triage order: registry ids, then tickets, then repos; larger groups first."""
    open_items = _open_items(items)
    by_id = {item.id: item for item in open_items}
    groups: dict[tuple[str, str], dict] = {}
    for line in lines:
        kind, key = group_key(line, open_items)
        found = _FROM.search(line)
        group = groups.setdefault((kind, key), {"kind": kind, "key": key, "lines": []})
        group["lines"].append({"text": line, "date": found.group(2) if found else ""})
    order = {"registry": 0, "ticket": 1, "repo": 2}
    result = sorted(groups.values(), key=lambda g: (order[g["kind"]], -len(g["lines"]), g["key"].casefold()))
    for group in result:
        dated = sorted(l["date"] for l in group["lines"] if l["date"])
        group["first"], group["last"] = (dated[0], dated[-1]) if dated else ("", "")
        item = by_id.get(group["key"]) if group["kind"] == "registry" else None
        group["status"] = item.fields.get("status", "").strip() if item else ""
        group["next"] = item.fields.get("next", "").strip() if item else ""
    return result


def summary(groups: list[dict]) -> tuple[int, int, int]:
    """(lines, groups, lines that share a group with a later line)."""
    total = sum(len(g["lines"]) for g in groups)
    return total, len(groups), sum(len(g["lines"]) - 1 for g in groups)


def open_lines(lines: list[str], items: list[Item]) -> list[str]:
    """Newest line in each group. Empty when the inbox has nothing to show."""
    groups = rollup(lines, items)
    return [group["lines"][-1]["text"] for group in groups]


def render(today: str, groups: list[dict]) -> str:
    total, count, older = summary(groups)
    lines = [f"# Inbox roll-up {today}", "",
             f"{total} lines in {count} groups. {older} lines share a group with a later line.",
             "Triage the newest line in each group. Earlier lines stay in the inbox until you remove them.", ""]
    lines.extend(["## Open", ""])
    for group in groups:
        lines.append(f"- {group['key']}: {group['lines'][-1]['text']}")
    lines.append("")
    for group in groups:
        label = {"registry": "registry item", "ticket": "ticket", "repo": "from"}[group["kind"]]
        span = group["first"] if group["first"] == group["last"] else f"{group['first']} to {group['last']}"
        size = len(group["lines"])
        lines.append(f"## {group['key']} ({label}, {size} line{'' if size == 1 else 's'}{', ' + span if span else ''})")
        if group["kind"] == "registry":
            lines.append(f"Registry: {group['status']}. Next: {group['next']}")
        lines.append("")
        newest = group["lines"][-1]["text"]
        earlier = size - 1
        lines.append(f"- {newest}")
        if earlier:
            word = "line" if earlier == 1 else "lines"
            lines.append(f"{earlier} earlier {word} in this group stay in the inbox.")
        lines.append("")
    return "\n".join(lines)


def load(root: Path) -> tuple[list[str], list[Item]]:
    root = Path(root)
    inbox = root / "INBOX.md"
    lines = inbox_items(inbox.read_text(encoding="utf-8")) if inbox.is_file() else []
    registry = root / "REGISTRY.md"
    items: list[Item] = []
    if registry.is_file():
        try:
            items = parse_registry(registry.read_text(encoding="utf-8")).items
        except RegistryParseError:
            items = []
    return lines, items


def write_rollup(root: Path, today: str) -> int:
    lines, items = load(root)
    path = Path(root) / "reviews" / "inbox" / f"{today}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(today, rollup(lines, items)))
    print(path)
    return 0
