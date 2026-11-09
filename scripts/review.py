"""Read-only diagnostics; the report proposes decisions, never changes commitments."""
import re
from datetime import date
from pathlib import Path

from scripts.brief import inbox_clashes
from scripts.model import parse_registry, RegistryParseError, counts, inbox_items, capacity_line, valid_date
from scripts.search import search
from scripts.impact import review_impact_lines


def _knowledge_exists(root: Path, knowledge: str) -> bool:
    named = root / "knowledge" / knowledge
    candidates = [root / knowledge, named]
    if named.suffix == "":
        candidates.append(named.with_suffix(".md"))
    return any(path.is_file() for path in candidates)


def _now_names(text: str, item_id: str) -> bool:
    in_now = False
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if in_now:
                break
            in_now = line.strip() == "## Now"
            continue
        if in_now:
            body.append(line)
    if not body:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(item_id.casefold())}(?![a-z0-9])", "\n".join(body).casefold()) is not None


def _overflow(doc) -> list:
    """Active items that are not the focus, not weekly, and have no deadline. Oldest update first."""
    found = []
    for item in doc.items:
        if item.reason is not None:
            continue
        fields = item.fields
        if fields.get("status", "").strip() != "active":
            continue
        if item.id == doc.focus or fields.get("weekly", "").strip() == "yes":
            continue
        if fields.get("due", "").strip():
            continue
        found.append(item)
    return sorted(found, key=lambda item: (item.fields.get("updated", "") or "9999-99-99", item.id))


def closure_gap(item, root: Path) -> str | None:
    if item.reason or item.fields.get("status", "").strip() != "done":
        return None
    if item.fields.get("outcome", "").strip().casefold() == "nothing to keep":
        return None
    knowledge = item.fields.get("knowledge", "").strip()
    if knowledge and _knowledge_exists(root, knowledge):
        return None
    projects = root / "knowledge" / "projects"
    if projects.is_dir():
        for card in projects.glob("*.md"):
            if card.name == "TEMPLATE.md":
                continue
            if _now_names(card.read_text(encoding="utf-8"), item.id):
                return None
    return "record a lesson in knowledge, set outcome to nothing to keep, or name this id under Now on the project card"


def review_report(root: Path, today: str) -> str:
    doc = parse_registry((root / "REGISTRY.md").read_text(encoding="utf-8"))
    totals = counts(doc.items)
    lines = [f"# Weekly review {today}", "", "Generated assessment; decisions require acceptance.",
             "", f"Active: {totals['active']}; waiting: {totals['waiting']}; someday: {totals['someday']}.",
             f"Focus: {doc.focus or 'Not selected'}", "", "## Working set"]
    shortlist = [i for i in doc.items if i.fields.get("weekly") == "yes"]
    lines += [f"- {i.id}: {i.fields.get('outcome') or i.fields.get('title')}" for i in shortlist]
    if not shortlist:
        lines.append("- Choose up to three outcomes for the week.")
    if len(shortlist) > 3:
        lines.append("- Reduce the weekly shortlist to three outcomes.")
    lines += ["", "## Decisions and repairs"]
    by_id = {i.id: i for i in doc.items}
    for item in doc.items:
        f = item.fields
        issues = []
        if item.reason:
            issues.append(item.reason)
        if f.get("status") == "waiting":
            if not f.get("follow_up"):
                issues.append("set a follow-up date")
            if not f.get("requested_on"):
                issues.append("confirm request was sent and record its actual date")
        if f.get("follow_up") and f["follow_up"] <= today and f.get("status") != "done":
            issues.append("follow-up is due")
        if f.get("due") and f["due"] <= today and f.get("status") != "done":
            issues.append("deadline is due")
        updated = f.get("updated", "")
        if valid_date(updated) and (date.fromisoformat(today) - date.fromisoformat(updated)).days >= 7 and f.get("status") != "done":
            issues.append("no recorded update in seven days; review, defer, or drop")
        for dep in filter(None, (d.strip() for d in f.get("depends_on", "").split(","))):
            if dep not in by_id:
                issues.append(f"missing dependency {dep}")
            elif by_id[dep].fields.get("status") != "done":
                issues.append(f"depends on {dep}")
        if f.get("kind") == "project" and not f.get("outcome"):
            issues.append("define a done condition")
        if issues:
            lines.append(f"- {item.id}: {'; '.join(issues)}.")
    inbox = root / "INBOX.md"
    captured = inbox_items(inbox.read_text(encoding="utf-8")) if inbox.exists() else []
    n = len(captured)
    clashes = inbox_clashes(doc.items, captured)
    if clashes:
        lines += ["", "## Inbox clashes", *clashes]
    lines += ["", "## Impact", *review_impact_lines(root, today)]
    overflow = _overflow(doc)
    lines += ["", "## Outside the working set", ""]
    if not overflow:
        lines.append("No active item sits outside the focus and the weekly shortlist.")
    else:
        shown = overflow[:3]
        noun = "item" if len(overflow) == 1 else "items"
        verb = "sits" if len(overflow) == 1 else "sit"
        lines.append(f"{len(overflow)} active {noun} {verb} outside the focus and the weekly shortlist and have no deadline.")
        lines.append("Propose moving these to someday. Accept each in an update. This review does not change the registry.")
        for item in shown:
            updated = item.fields.get("updated", "").strip()
            lines.append(f"- {item.id} (updated {updated}): {item.fields.get('next', '').strip()}")
        rest = len(overflow) - len(shown)
        if rest:
            lines.append("")
            stay = "stays" if rest == 1 else "stay"
            lines.append(f"{rest} more {stay} active until a later review.")
    gaps = [item for item in doc.items if closure_gap(item, root)]
    if gaps:
        lines += ["", "## Close the loop"]
        for item in gaps:
            lines.append(f"- {item.id}: {closure_gap(item, root)}.")
    context = root / "CONTEXT.md"
    lines += ["", "## Review checklist", f"- Process {n} inbox entries: action, reference, or drop.",
              "- Reconsider each active commitment; keep only work you intend to advance.",
              "- Confirm waiting owners, sent requests, and follow-up dates.",
              "- Capture decisions and reusable lessons in knowledge/; link them from the item.",
              "- Propose registry changes for acceptance; archive only on a separate ask.",
              "- " + capacity_line(context.read_text(encoding="utf-8") if context.exists() else None)]
    return "\n".join(lines) + "\n"


def write_review(root: Path, today: str) -> int:
    try:
        report = review_report(root, today)
    except (OSError, RegistryParseError) as exc:
        print(f"unreadable registry: {exc}")
        return 1
    path = root / "reviews" / "weekly" / f"{today}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return 0


def search_knowledge(root: Path, query: str, limit: int = 15) -> int:
    """Ranked matches from knowledge notes, the registry, the inbox, and the archive. Best first."""
    results = search(Path(root), query, limit)
    for result in results:
        print(f"{result['path']}:{result['line']}: [{result['title']}] {result['snippet']}")
    if not results:
        print("No matching knowledge notes.")
    return 0
