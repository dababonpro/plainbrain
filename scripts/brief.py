import json
import re
from datetime import date
from pathlib import Path

from scripts.flow import latest_flow
from scripts.impact import due_lines
from scripts.model import (
    DATE_RE,
    Item,
    RegistryParseError,
    capacity_line,
    counts,
    inbox_items,
    parse_registry,
    previous_brief_path,
    snapshot_inbox,
)
from scripts.rollup import rollup, summary
from scripts.unshipped import latest_summary

UNSHIPPED_FRESH_DAYS = 2
JIRA_FRESH_DAYS = 7
RESOLVED_SHOWN = 12
_NOT_PUSHED = ("not pushed", "unpushed", "not yet pushed", "haven't pushed", "have not pushed")
_FROM_REPO = re.compile(r"\(from ([^,\n]+), \d{4}-\d{2}-\d{2}\)\s*$")
_FROM_DATE = re.compile(r"\(from [^,\n]+, (\d{4}-\d{2}-\d{2})\)")
_TICKET = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
_COMPLETION = (
    "marked done",
    "mark done",
    "fully done",
    "nothing left",
    "nothing else",
    "moved to done",
    "move to waiting",
    "now waiting",
    "looks done",
    "can be closed",
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _item_line(item: Item) -> str:
    title = item.fields.get("title", "").strip()
    status = item.fields.get("status", "").strip()
    return f"- {item.id}: {title} ({status})"


def since_lines(
    items: list[Item],
    focus: str,
    previous_text: str | None,
    previous_date: str | None,
    inbox_count: int,
) -> list[str]:
    lines: list[str] = []
    if previous_date is None:
        lines.append("- No previous brief.")
        for item in items:
            status = item.fields.get("status", "").strip()
            if item.reason is None and status in ("active", "waiting"):
                lines.append(_item_line(item))
    else:
        for item in items:
            opened = item.fields.get("opened", "").strip()
            updated = item.fields.get("updated", "").strip()
            changed = (DATE_RE.fullmatch(opened) is not None and opened > previous_date) or (
                DATE_RE.fullmatch(updated) is not None and updated > previous_date
            )
            if changed:
                lines.append(_item_line(item))
        if previous_text is not None:
            old_inbox = snapshot_inbox(previous_text)
            if old_inbox is not None and old_inbox != inbox_count:
                lines.append(f"- inbox: {old_inbox} -> {inbox_count}")
    for item in items:
        if item.reason:
            lines.append(f"- unusable {item.id}: {item.reason}")
    ids = {item.id for item in items}
    if focus and focus not in ids:
        lines.append(f"- unusable {focus}: missing focus")
    return lines


def blocked_lines(items: list[Item], today: str) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item.reason is not None or item.id in seen:
            continue
        status = item.fields.get("status", "").strip()
        blocked_on = item.fields.get("blocked_on", "").strip()
        follow = item.fields.get("follow_up", "").strip()
        due = DATE_RE.fullmatch(follow) is not None and follow <= today
        if status == "waiting" or (status == "active" and blocked_on != "") or due:
            seen.add(item.id)
            title = item.fields.get("title", "").strip()
            lines.append(f"- {item.id}: {title} — {blocked_on} — {follow}")
    return lines


def next_action(items: list[Item], focus: str, inbox_count: int, today: str = "") -> str:
    first: dict[str, Item] = {}
    for item in items:
        first.setdefault(item.id, item)
    def available(item: Item) -> bool:
        dependencies = item.fields.get("depends_on", "").split(",")
        return all(not dep.strip() or (dep.strip() in first and first[dep.strip()].reason is None
                   and first[dep.strip()].fields.get("status") == "done") for dep in dependencies)
    chosen_focus = first.get(focus) if focus else None
    if (
        chosen_focus is not None
        and chosen_focus.reason is None
        and chosen_focus.fields.get("status", "").strip() == "active"
        and chosen_focus.fields.get("blocked_on", "").strip() == ""
        and available(chosen_focus)
    ):
        return chosen_focus.fields.get("next", "").strip()

    followups = [item for item in first.values() if item.reason is None
                 and item.fields.get("status") in ("waiting", "someday")
                 and item.fields.get("follow_up", "") and item.fields["follow_up"] <= today]
    if followups:
        winner = min(followups, key=lambda item: item.fields["follow_up"])
        return f"Revisit {winner.id}: {winner.fields.get('next', '')}"

    def sort_key(item: Item) -> tuple:
        opened = item.fields.get("opened", "").strip()
        due = item.fields.get("due", "")
        prefix = (0 if due else 1, due, 0 if item.fields.get("weekly") == "yes" else 1)
        if DATE_RE.fullmatch(opened):
            return (*prefix, 0, opened)
        return (*prefix, 1, "")

    candidates = [
        item
        for item in items
        if item.reason is None
        and item.fields.get("status", "").strip() == "active"
        and item.fields.get("blocked_on", "").strip() == ""
        and available(item)
    ]
    if inbox_count > 0 and not any(item.fields.get("due") or item.fields.get("weekly") == "yes" for item in candidates):
        return "Triage the inbox."
    if not candidates:
        return "No usable next action today."
    winner = sorted(candidates, key=sort_key)[0]
    return winner.fields.get("next", "").strip()


def newest_inbox_date(lines: list[str]) -> str:
    found = [match for line in lines for match in _FROM_DATE.findall(line)]
    return max(found) if found else ""


def latest_weekly_review(root: Path) -> str | None:
    folder = root / "reviews" / "weekly"
    if not folder.is_dir():
        return None
    stems = [path.stem for path in folder.glob("*.md") if DATE_RE.fullmatch(path.stem)]
    return max(stems) if stems else None


def attention_lines(
    items: list[Item],
    focus: str,
    lines: list[str],
    today: str,
    weekly_date: str | None,
) -> list[str]:
    notes: list[str] = []
    first: dict[str, Item] = {}
    for item in items:
        first.setdefault(item.id, item)
    chosen = first.get(focus) if focus else None
    newest = newest_inbox_date(lines)
    updated = chosen.fields.get("updated", "").strip() if chosen and chosen.reason is None else ""
    if DATE_RE.fullmatch(updated) and DATE_RE.fullmatch(newest):
        if (date.fromisoformat(newest) - date.fromisoformat(updated)).days > 2:
            notes.append(
                f"Attention: focus {focus} was last updated {updated}; the newest inbox line is {newest}."
            )
    if weekly_date and DATE_RE.fullmatch(weekly_date) and DATE_RE.fullmatch(today):
        if (date.fromisoformat(today) - date.fromisoformat(weekly_date)).days > 7:
            notes.append(f"Weekly review is due. The last one is {weekly_date}.")
    return notes


def inbox_rollup_note(lines: list[str], items: list[Item]) -> list[str]:
    _total, groups, older = summary(rollup(lines, items))
    if older == 0:
        return []
    return [f"Inbox: {groups} open lines; {older} earlier lines share a group. "
            "Run the inbox roll-up before triage."]


def unshipped_lines(root: Path, today: str) -> tuple[list[str], list[str]]:
    """(notices, section lines) from the newest unshipped scan."""
    found = latest_summary(root, today)
    if found is None:
        return [], []
    stem, lines = found
    if DATE_RE.fullmatch(today) and (date.fromisoformat(today) - date.fromisoformat(stem)).days > UNSHIPPED_FRESH_DAYS:
        return [f"Unshipped scan is from {stem}. Run it again."], []
    return [], lines


def _names_id(line: str, item_id: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(item_id.casefold())}(?![a-z0-9])", line.casefold()) is not None


def _quote(line: str) -> str:
    text = " ".join(line.split())
    if len(text) > 180:
        return text[:177] + "..."
    return text


def inbox_clashes(items: list[Item], lines: list[str]) -> list[str]:
    first: dict[str, Item] = {}
    for item in items:
        if item.reason is None:
            first.setdefault(item.id, item)
    found: list[str] = []
    open_items = [
        item for item in first.values() if item.fields.get("status", "").strip() != "done"
    ]
    for line in lines:
        folded = line.casefold()
        completion = any(cue in folded for cue in _COMPLETION)
        named = [item for item in open_items if _names_id(line, item.id)]
        if named:
            targets = named
        elif completion:
            tickets = set(_TICKET.findall(line))
            targets = []
            for item in open_items:
                blob = " ".join(item.fields.get(key, "") for key in ("title", "next", "notes", "outcome"))
                if tickets & set(_TICKET.findall(blob)):
                    targets.append(item)
        else:
            targets = []
        for item in targets:
            status = item.fields.get("status", "").strip()
            nxt = item.fields.get("next", "").strip()
            found.append(f"- {item.id} ({status}): {_quote(line)} Registry next: {nxt}")
    return found


def _jira_done(root: Path, today: str) -> tuple[str | None, str | None, set[str] | None]:
    """(stale notice, snapshot date, Done keys). Keys are None when the snapshot is missing or stale."""
    folder = Path(root) / "reviews" / "team"
    if not folder.is_dir():
        return None, None, None
    found = []
    for path in folder.glob("jira-*.json"):
        stem = path.stem[5:]
        if DATE_RE.fullmatch(stem) and stem <= today:
            found.append((stem, path))
    if not found:
        return None, None, None
    stem, path = max(found)
    if DATE_RE.fullmatch(today) and (date.fromisoformat(today) - date.fromisoformat(stem)).days > JIRA_FRESH_DAYS:
        return f"Jira snapshot is from {stem}. Resolved-line check skipped.", stem, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None, None
    open_keys = {issue.get("key", "") for issue in data.get("open", []) + data.get("qa", [])}
    done = {issue.get("key", "") for issue in data.get("done", [])} - open_keys - {""}
    return None, stem, done


def _unshipped_state(root: Path, today: str) -> tuple[str, set[str], set[str]] | None:
    """Newest fresh scan: (date, repos with local work, repos the scan actually visited)."""
    folder = Path(root) / "reviews" / "unshipped"
    if not folder.is_dir():
        return None
    stems = [path.stem for path in folder.glob("*.md") if DATE_RE.fullmatch(path.stem) and path.stem <= today]
    if not stems:
        return None
    stem = max(stems)
    if DATE_RE.fullmatch(today) and (date.fromisoformat(today) - date.fromisoformat(stem)).days > UNSHIPPED_FRESH_DAYS:
        return None
    dirty: set[str] = set()
    scanned: set[str] = set()
    in_scanned = False
    for line in (folder / f"{stem}.md").read_text(encoding="utf-8").splitlines():
        if line.strip() == "## Scanned":
            in_scanned = True
            continue
        if line.startswith("## "):
            in_scanned = False
            continue
        if not line.startswith("- ") or "/" not in line:
            continue
        name = line[2:].split(":", 1)[0].strip().split("/")[-1].casefold()
        if not name:
            continue
        if in_scanned:
            scanned.add(name)
        elif ":" in line:
            dirty.add(name)
    return stem, dirty, scanned


def resolved_proposals(root: Path, lines: list[str], today: str) -> list[str]:
    """Inbox lines that look finished. The brief asks; it does not delete them."""
    _notice, jira_day, done = _jira_done(root, today)
    work = _unshipped_state(root, today)
    proposals: list[str] = []
    for line in lines:
        tickets = _TICKET.findall(line)
        if done is not None and tickets and all(ticket in done for ticket in tickets):
            keys = ", ".join(dict.fromkeys(tickets))
            proposals.append(f"- {_quote(line)} {keys} is Done in Jira (snapshot {jira_day}); "
                             "Done is not always released, so check the release first. Drop it?")
            continue
        if work is None:
            continue
        found = _FROM_REPO.search(line)
        if found is None or not any(cue in line.casefold() for cue in _NOT_PUSHED):
            continue
        repo = found.group(1).strip().casefold()
        stem, dirty, scanned = work
        if repo not in scanned or repo in dirty:
            continue
        proposals.append(f"- {_quote(line)} Unshipped scan {stem} has no local work for {found.group(1).strip()}. Drop it?")
    if len(proposals) <= RESOLVED_SHOWN:
        return proposals
    extra = len(proposals) - RESOLVED_SHOWN
    return proposals[:RESOLVED_SHOWN] + [f"- {extra} more."]


def render_brief(
    today: str,
    since: list[str],
    blocked: list[str],
    action: str,
    totals: dict[str, int],
    capacity: str,
    inbox_count: int,
    focus: str,
    notices: list[str] | None = None,
    clashes: list[str] | None = None,
    unshipped: list[str] | None = None,
    resolved: list[str] | None = None,
) -> str:
    focus_line = f"focus: {focus}" if focus else "focus:"
    notices = notices or []
    clashes = clashes or []
    resolved = resolved or []
    lines = [f"# Brief {today}", ""]
    if notices:
        lines.extend(notices)
        lines.append("")
    lines.extend([
        "## Since yesterday",
        *since,
        "",
        "## Blocked",
        *blocked,
        "",
    ])
    if clashes:
        lines.extend(["## Inbox clashes", *clashes, ""])
    if resolved:
        lines.extend(["## Looks resolved", "These lines look finished. Dropping one is a triage decision.",
                      *resolved, ""])
    if unshipped:
        lines.extend(["## Unshipped", *unshipped, ""])
    lines.extend([
        "## Next hour",
        f"Do this: {action}",
        "",
        "## Left quiet",
        f"active: {totals['active']}",
        f"waiting: {totals['waiting']}",
        f"someday: {totals['someday']}",
        f"done: {totals['done']}",
        "",
        capacity,
        "",
        "snapshot:",
        f"inbox: {inbox_count}",
        focus_line,
        f"active: {totals['active']}",
        f"waiting: {totals['waiting']}",
        f"someday: {totals['someday']}",
        f"done: {totals['done']}",
        "",
    ])
    return "\n".join(lines)


def render_dashboard(
    today: str,
    action: str,
    blocked_count: int,
    since: list[str],
    notices: list[str] | None = None,
    clash_count: int = 0,
    unshipped_count: int = 0,
    resolved_count: int = 0,
) -> str:
    notices = notices or []
    lines = [
        "# Dashboard",
        "",
        f"Generated: {today}",
        "",
    ]
    if notices:
        lines.extend(notices)
        lines.append("")
    if clash_count:
        lines.append(f"Inbox clashes: {clash_count}. See the brief.")
        lines.append("")
    if resolved_count:
        lines.append(f"Looks resolved: {resolved_count}. See the brief.")
        lines.append("")
    if unshipped_count:
        lines.append(f"Unshipped: {unshipped_count} repos. See the brief.")
        lines.append("")
    lines.extend([
        "## Next hour",
        f"Do this: {action}",
        "",
        "## Blocked",
        f"{blocked_count} blocked",
        "",
        "## Since yesterday",
        *since,
        "",
    ])
    return "\n".join(lines)


def write_brief(root: Path, today: str) -> int:
    root = Path(root)
    registry_path = root / "REGISTRY.md"
    inbox_path = root / "INBOX.md"
    context_path = root / "CONTEXT.md"
    daily = root / "reviews" / "daily"
    captured: list[str] = []
    if inbox_path.is_file():
        captured = inbox_items(inbox_path.read_text(encoding="utf-8"))
    inbox_count = len(captured)
    context_text = context_path.read_text(encoding="utf-8") if context_path.is_file() else None
    capacity = capacity_line(context_text)
    weekly = latest_weekly_review(root)
    if not registry_path.is_file():
        since = ["- The registry is missing."]
        zeros = {"active": 0, "waiting": 0, "someday": 0, "done": 0}
        notices = attention_lines([], "", captured, today, weekly)
        _write(
            daily / f"{today}.md",
            render_brief(today, since, [], "The registry is missing.", zeros, capacity, inbox_count, "", notices, []),
        )
        _write(root / "DASHBOARD.md", render_dashboard(today, "The registry is missing.", 0, since, notices, 0))
        return 2
    try:
        doc = parse_registry(registry_path.read_text(encoding="utf-8"))
    except RegistryParseError as exc:
        print(f"unreadable registry: {exc.report}")
        return 1
    previous = previous_brief_path(daily, today)
    previous_text = previous.read_text(encoding="utf-8") if previous is not None else None
    previous_date = previous.stem if previous is not None else None
    since = since_lines(doc.items, doc.focus, previous_text, previous_date, inbox_count)
    blocked = blocked_lines(doc.items, today)
    action = next_action(doc.items, doc.focus, inbox_count, today)
    totals = counts(doc.items)
    stale_scan, unshipped = unshipped_lines(root, today)
    notices = attention_lines(doc.items, doc.focus, captured, today, weekly)
    try:
        impact_due = due_lines(root, today)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        impact_due = [f"Impact ledger unreadable: {exc}"]
    if impact_due:
        notices.extend(["## Impact due", *impact_due])
    notices += inbox_rollup_note(captured, doc.items) + stale_scan
    jira_note, _jira_day, _done = _jira_done(root, today)
    if jira_note:
        notices.append(jira_note)
    stuck_note = latest_flow(root, today)
    if stuck_note:
        notices.append(stuck_note)
    clashes = inbox_clashes(doc.items, captured)
    resolved = resolved_proposals(root, captured, today)
    _write(
        daily / f"{today}.md",
        render_brief(
            today, since, blocked, action, totals, capacity, inbox_count, doc.focus, notices, clashes, unshipped,
            resolved,
        ),
    )
    _write(root / "DASHBOARD.md", render_dashboard(today, action, len(blocked), since, notices, len(clashes),
                                                   len(unshipped), len(resolved)))
    return 0
