import html
import json
from datetime import date, timedelta
from pathlib import Path

from scripts.brief import blocked_lines
from scripts.model import (
    RegistryParseError,
    counts,
    inbox_items,
    latest_brief_path,
    parse_registry,
)
from scripts.rollup import open_lines


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _brief_view(text: str) -> tuple[str, str, list[str], list[str], int]:
    date = ""
    action = ""
    since: list[str] = []
    notices: list[str] = []
    clash_count = 0
    section = ""
    preamble = False
    for line in text.splitlines():
        if line.startswith("# Brief "):
            date = line[len("# Brief ") :].strip()
            preamble = True
        elif line.startswith("## "):
            section = line[3:].strip()
            preamble = False
        elif preamble and line.strip():
            notices.append(line.strip())
        elif section == "Since yesterday" and line.startswith("- "):
            since.append(line[2:])
        elif section == "Inbox clashes" and line.startswith("- "):
            clash_count += 1
        elif section == "Next hour" and line.startswith("Do this: "):
            action = line[len("Do this: ") :]
    return date, action, since, notices, clash_count


def _rows(items: list, focus: str, status: str | None) -> list[str]:
    chosen = []
    for item in items:
        item_status = item.fields.get("status", "").strip()
        if status is None:
            if item_status in ("active", "waiting", "someday", "done"):
                continue
        elif item_status != status:
            continue
        chosen.append(item)
    if status == "active":
        chosen.sort(key=lambda item: 0 if item.id == focus else 1)
    rows = []
    for item in chosen:
        title = html.escape(item.fields.get("title", "").strip())
        area = html.escape(item.fields.get("area", "").strip())
        kind = html.escape(item.fields.get("kind", "").strip())
        nxt = html.escape(item.fields.get("next", "").strip())
        pointer = item.fields.get("pointer", "").strip()
        reason = item.reason or ""
        pointer_html = f' <span class="pointer">{html.escape(pointer)}</span>' if pointer else ""
        reason_html = f' <span class="reason">{html.escape(reason)}</span>' if reason else ""
        metadata = " ".join(f"{key}: {html.escape(item.fields[key])}" for key in
                            ("due", "depends_on", "knowledge") if item.fields.get(key))
        rows.append(
            f'<li data-id="{html.escape(item.id)}">{title} {area} {kind} {nxt}{pointer_html}{reason_html} {metadata}</li>'
        )
    return rows


def _details(element_id: str, label: str, count: int, rows: list[str], start_open: bool) -> str:
    open_attr = " open" if start_open else ""
    body = "\n".join(rows)
    return (
        f'<details id="{element_id}"{open_attr}>\n'
        f"<summary>{label}: {count}</summary>\n<ul>\n{body}\n</ul>\n</details>"
    )


def render_board(
    date: str,
    action: str,
    since: list[str],
    blocked: list[str],
    inbox: list[str],
    items: list,
    focus: str,
    totals: dict[str, int],
    empty: bool,
    notices: list[str] | None = None,
    clash_count: int = 0,
    usage_html: str | None = None,
    inbox_total: int | None = None,
) -> str:
    total = len(inbox) if inbox_total is None else inbox_total
    since_html = "\n".join(f"<li>{html.escape(line)}</li>" for line in since)
    blocked_html = "\n".join(f"<li>{html.escape(line)}</li>" for line in blocked)
    inbox_html = "\n".join(f"<li>{html.escape(line)}</li>" for line in inbox)
    body = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>Second Brain</title>",
        "<style>",
        "body { font: 16px/1.5 system-ui, sans-serif; margin: 2rem auto; max-width: 40rem; }",
        "li { margin: 0.25rem 0; }",
        ".open-time { font-size: 0.85em; color: #555; }",
        "</style>",
        "</head>",
        "<body>",
        "<h1>Second Brain</h1>",
        f'<p id="brief-date">{html.escape(date)}</p>',
    ]
    if notices:
        notice_html = "".join(f"<li>{html.escape(line)}</li>" for line in notices)
        body.append(f'<ul id="attention">{notice_html}</ul>')
    if clash_count:
        body.append(f'<p id="clashes">Inbox clashes: {clash_count}</p>')
    body.append(f'<p id="next-hour">{html.escape(action)}</p>')
    if usage_html:
        body.append(usage_html)
    body.extend([
        f'<ul id="since">\n{since_html}\n</ul>',
        f'<ul id="blocked">\n{blocked_html}\n</ul>',
        f'<ul id="inbox">\n{inbox_html}\n</ul>',
        f'<p id="inbox-count">Inbox: {len(inbox)} open of {total}</p>',
    ])
    if empty:
        body.append('<p id="empty">The registry is empty.</p>')
    else:
        working = [item for item in items if item.id == focus or item.fields.get("weekly") == "yes"]
        queued = [item for item in items if item not in working and item.fields.get("status") == "active"]
        body.append('<h2>Working set</h2><ul id="active">')
        body.extend(_rows(working if working else items, focus, "active"))
        body.append("</ul>")
        if working and queued:
            body.append(_details("queue", "Active queue", len(queued), _rows(queued, focus, "active"), False))
        body.append(_details("waiting", "Waiting", totals["waiting"], _rows(items, focus, "waiting"), True))
        body.append(_details("someday", "Someday", totals["someday"], _rows(items, focus, "someday"), True))
        body.append(_details("done", "Done", totals["done"], _rows(items, focus, "done"), False))
        needs = _rows(items, focus, None)
        if needs:
            body.append('<section id="needs-fix"><h2>Needs a fix</h2><ul>')
            body.extend(needs)
            body.append("</ul></section>")
    body.extend(["</body>", "</html>", ""])
    return "\n".join(body)


def write_board(root: Path, today: str) -> int:
    root = Path(root)
    html_path = root / "board" / "index.html"
    registry_path = root / "REGISTRY.md"
    if not registry_path.is_file():
        print("unreadable registry: missing")
        return 1
    try:
        doc = parse_registry(registry_path.read_text(encoding="utf-8"))
    except RegistryParseError as exc:
        print(f"unreadable registry: {exc.report}")
        return 1
    inbox_path = root / "INBOX.md"
    inbox = inbox_items(inbox_path.read_text(encoding="utf-8")) if inbox_path.is_file() else []
    shown = open_lines(inbox, doc.items)
    latest = latest_brief_path(root / "reviews" / "daily")
    if latest is None:
        date, action, since, notices, clash_count = ("No brief yet.", "No brief yet.", [], [], 0)
    else:
        date, action, since, notices, clash_count = _brief_view(latest.read_text(encoding="utf-8"))
    blocked = blocked_lines(doc.items, today)
    page = render_board(
        date,
        action,
        since,
        [line[2:] for line in blocked],
        shown,
        doc.items,
        doc.focus,
        counts(doc.items),
        empty=not doc.items,
        notices=notices,
        clash_count=clash_count,
        usage_html=_usage_section(root, today),
        inbox_total=len(inbox),
    )
    freshness = f"Board generated: {html.escape(today)}. Brief: {html.escape(date)}."
    if date != today:
        freshness += " Brief is not current; next-hour recommendation may be stale."
    page = page.replace("<h1>Second Brain</h1>", f'<h1>Second Brain</h1><p id="freshness">{freshness}</p>')
    _write(html_path, page)
    return 0


def _usage_section(root: Path, today: str) -> str | None:
    path = root / "reviews" / "usage" / "latest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        week = data["week"]
        human = _duration(data["human_ms"])
        idle = _duration(data.get("idle_ms"))
        prompting = _duration(data.get("prompting_ms"))
        cursor = _duration(data.get("cursor_busy_ms"))
        claude = _duration(data.get("claude_busy_ms"))
        cursor_open = _duration(data.get("cursor_open_ms"))
        claude_open = _duration(data.get("claude_open_ms"))
        tokens = data["tokens"]
        token_line = (
            f"Tokens: {tokens['input']} in / {tokens['output']} out "
            f"({data['token_sessions']}/{data['total_sessions']} sessions)"
        )
    except (OSError, ValueError, TypeError, KeyError):
        return None
    label = html.escape(week)
    heading = f"This week ({label})"
    if not _week_is_current(week, today):
        heading = f"Usage: week {label} (stale)"
    return (
        f'<section id="usage"><h2>{heading}</h2>'
        f"<p>Human: {html.escape(human)} "
        f'<span class="open-time">prompting {html.escape(prompting)}; idle {html.escape(idle)}</span></p>'
        f"<p>Cursor busy: {html.escape(cursor)} "
        f'<span class="open-time">open {html.escape(cursor_open)}</span></p>'
        f"<p>Claude busy: {html.escape(claude)} "
        f'<span class="open-time">open {html.escape(claude_open)}</span></p>'
        f"<p>{html.escape(token_line)}</p>"
        f"<p>Unattributed: {int(data.get('unattributed') or 0)}; "
        f"orphans: {int(data.get('orphans') or 0)}</p>"
        "</section>"
    )


def _week_is_current(week: str, today: str) -> bool:
    day = date.fromisoformat(today)
    iso = day.isocalendar()
    current = {f"{iso.year}-W{iso.week:02d}"}
    if day.isoweekday() == 1:
        previous = (day - timedelta(days=7)).isocalendar()
        current.add(f"{previous.year}-W{previous.week:02d}")
    return week in current


def _duration(value) -> str:
    if value is None:
        return "unknown"
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return "unknown"
    if ms < 60_000:
        return "<1m"
    minutes = ms // 60_000
    hours, minutes = divmod(minutes, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"
