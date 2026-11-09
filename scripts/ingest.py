"""Read-only routing of inbox lines to the pages they touch; never edits INBOX.md, the registry, or a note."""
import hashlib
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from scripts.capture import CaptureError, _pick, check_root, inbox_lock
from scripts.model import Item, RegistryParseError, inbox_items, parse_registry, valid_date
from scripts.rollup import _FROM, _TICKET, _names_id, _open_items

_HEADER = re.compile(r"^([a-z_]+):\s*(.*)$")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_SKIP = {"README.md", "TEMPLATE.md", "INDEX.md", "LOG.md"}
_LOG = re.compile(r"^- \d{4}-\d{2}-\d{2} \| ([0-9a-f]{8}) \| (\S+) \| \w+\s*$")
OUTCOMES = ("updated", "unchanged", "rejected")
LOG_HEADER = (
    "# Ingest log\n\n"
    "One line per inbox line and page reviewed in an ingest session: date | line hash | page | outcome.\n"
    "Written by `python scripts/brain.py ingest-log`; the ingest report skips pairs listed here.\n\n"
)


@dataclass
class Page:
    path: str
    card: bool
    title: str
    fields: dict[str, str]
    text: str
    aliases: list[str] = field(default_factory=list)

    @property
    def stem(self) -> str:
        return Path(self.path).stem

    @property
    def body(self) -> str:
        """Text from the first ## heading; header fields such as source are provenance, not topic."""
        found = re.search(r"^## ", self.text, re.MULTILINE)
        return self.text[found.start():] if found else ""


def _words(term: str, flags: int = re.IGNORECASE) -> re.Pattern:
    return re.compile(rf"(?<![A-Za-z0-9-]){re.escape(term)}(?![A-Za-z0-9-])", flags)


def _list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _path_key(value: str) -> str:
    return value.strip().strip("'\"").replace("/", "\\").rstrip("\\").casefold()


def read_page(root: Path, path: Path) -> Page:
    text = path.read_text(encoding="utf-8")
    fields: dict[str, str] = {}
    title = ""
    for line in text.splitlines():
        if line.startswith("## "):
            break
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        found = _HEADER.match(line)
        if found:
            fields.setdefault(found.group(1), found.group(2).strip())
    rel = path.relative_to(root).as_posix()
    return Page(rel, rel.startswith("knowledge/projects/"), title, fields, text, _list(fields.get("aliases", "")))


def pages(root: Path) -> list[Page]:
    """Notes and project cards that ingest may route to. Staff cards, templates, and superseded pages are left out."""
    root = Path(root)
    found: list[Page] = []
    for folder in (root / "knowledge", root / "knowledge" / "projects"):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md")):
            if path.name in _SKIP:
                continue
            page = read_page(root, path)
            if page.fields.get("status", "").strip() == "superseded":
                continue
            found.append(page)
    return found


def drop_command(line: str) -> str:
    """The inbox-drop command for a line, quoted for a POSIX shell (Git Bash) when double quotes would break."""
    quoted = f'"{line}"' if not re.search(r'["$`\\]', line) else shlex.quote(line)
    return f"python scripts/brain.py inbox-drop --root . --line {quoted}"


def line_hash(line: str) -> str:
    return hashlib.sha1(line.encode("utf-8")).hexdigest()[:8]


def read_log(root: Path) -> set[tuple[str, str]]:
    """(line hash, page) pairs already reviewed in an ingest session."""
    path = Path(root) / "knowledge" / "LOG.md"
    if not path.is_file():
        return set()
    pairs = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        found = _LOG.match(line)
        if found:
            pairs.add((found.group(1), found.group(2)))
    return pairs


def _items_for(line: str, open_items: list[Item]) -> dict[str, list[str]]:
    """R1 and R2: open registry ids the line reaches, with reasons."""
    reached: dict[str, list[str]] = {}
    tickets = set(_TICKET.findall(line))
    for item in open_items:
        if _names_id(line, item.id):
            reached.setdefault(item.id, []).append(f"names {item.id}")
        blob = " ".join(item.fields.get(key, "") for key in ("title", "next", "notes"))
        for key in sorted(tickets & set(_TICKET.findall(blob))):
            reached.setdefault(item.id, []).append(f"{key} is in {item.id}")
    return reached


def route(line: str, open_items: list[Item], all_pages: list[Page]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """(registry ids, page paths), each mapped to the reasons the line reaches it."""
    found = _FROM.search(line)
    source = found.group(1).strip() if found else ""
    line = line[:found.start()] if found else line
    items = _items_for(line, open_items)
    by_id = {item.id: item for item in open_items}
    reached: dict[str, list[str]] = {}

    def add(page: Page, reason: str) -> None:
        reasons = reached.setdefault(page.path, [])
        if reason not in reasons:
            reasons.append(reason)

    for item_id in items:
        item = by_id[item_id]
        note = item.fields.get("knowledge", "").strip().replace("\\", "/")
        pointer = _path_key(item.fields.get("pointer", ""))
        for page in all_pages:
            if note and page.path == note:
                add(page, f"via {item_id}")
            repo = _path_key(page.fields.get("repo", ""))
            if pointer and page.card and pointer in (repo, repo.rsplit("\\", 1)[-1]):
                add(page, f"via {item_id}")
            if item_id in _list(page.fields.get("related_items", "")):
                add(page, f"via {item_id}")
    tickets = sorted(set(_TICKET.findall(line)))
    for page in all_pages:
        for key in tickets:
            if _words(key, 0).search(page.body):
                add(page, f"{key} appears here")
        aliases = [a for a in page.aliases if _words(a).search(line)]
        if page.card:
            folder = _path_key(page.fields.get("repo", "")).rsplit("\\", 1)[-1]
            if source and source.casefold() in {folder} | {a.casefold() for a in page.aliases}:
                add(page, f"from {source}")
            if _words(page.stem).search(line):
                add(page, f"names {page.stem}")
        elif page.title and _words(page.title, 0).search(line):
            add(page, f'names "{page.title}"')
        for alias in aliases:
            add(page, f'names "{alias}"')
    return items, reached


def _now_date(page: Page) -> tuple[str, str]:
    """Newest date written in a card's ## Now section, else its recorded header."""
    found = re.search(r"^## Now\s*$(.*?)(?=^## |\Z)", page.text, re.MULTILINE | re.DOTALL)
    dates = sorted(_DATE.findall(found.group(1))) if found else []
    if dates:
        return dates[-1], "## Now"
    return page.fields.get("recorded", "").strip(), "recorded"


def build(lines: list[str], items: list[Item], all_pages: list[Page], logged: set[tuple[str, str]]) -> dict:
    open_items = _open_items(items)
    by_path = {page.path: page for page in all_pages}
    report = {"lines": len(lines), "to_page": 0, "registry_only": {}, "no_page": {},
              "pages": {}, "done": [], "logged": 0, "items": {item.id: item for item in open_items}}
    for line in lines:
        found = _FROM.search(line)
        date = found.group(2) if found else ""
        reached_items, reached = route(line, open_items, all_pages)
        if not reached:
            if reached_items:
                for item_id in reached_items:
                    report["registry_only"].setdefault(item_id, []).append(line)
            else:
                source = found.group(1).strip() if found else "no source"
                report["no_page"].setdefault(source, []).append(line)
            continue
        report["to_page"] += 1
        digest = line_hash(line)
        pending = {path: why for path, why in reached.items() if (digest, path) not in logged}
        report["logged"] += len(reached) - len(pending)
        if not pending:
            report["done"].append(line)
        for path, why in pending.items():
            report["pages"].setdefault(path, {"page": by_path[path], "lines": []})["lines"].append(
                {"text": line, "date": date, "why": why})
    return report


def render(today: str, report: dict, registry_note: str = "") -> str:
    total, to_page = report["lines"], report["to_page"]
    only = len({line for lines in report["registry_only"].values() for line in lines})
    nothing = sum(len(lines) for lines in report["no_page"].values())
    out = [f"# Ingest {today}", ""]
    if registry_note:
        out.extend([registry_note, ""])
    out.append(f"{total} lines. {to_page} reach at least one page, {only} reach only a registry item, {nothing} reach nothing.")
    out.append(f"{len(report['pages'])} pages to update. {report['logged']} pairs already logged.")
    out.extend(["Proposals only: write a page after the owner accepts the edit.", "", "## By page", ""])
    entries = list(report["pages"].values())
    for entry in entries:
        entry["lines"].sort(key=lambda l: l["date"], reverse=True)
    entries.sort(key=lambda e: e["page"].path)
    entries.sort(key=lambda e: e["lines"][0]["date"], reverse=True)
    if not entries:
        out.extend(["Nothing to update.", ""])
    for entry in entries:
        page = entry["page"]
        out.extend([f"### {page.path}", ""])
        if page.card:
            when, where = _now_date(page)
            out.append(f"`## Now` date: {when or 'unknown'} ({where}). Newest line routed here: {entry['lines'][0]['date'] or 'undated'}.")
            out.append("")
        for line in entry["lines"]:
            out.append(f"- {line['text']} [{'; '.join(line['why'])}]")
        out.append("")
    out.extend(["## Registry only", ""])
    if not report["registry_only"]:
        out.extend(["None.", ""])
    for item_id in sorted(report["registry_only"]):
        lines = report["registry_only"][item_id]
        item = report["items"][item_id]
        out.append(f"### {item_id} ({len(lines)} line{'' if len(lines) == 1 else 's'})")
        out.append(f"Registry: {item.fields.get('status', '').strip()}. Next: {item.fields.get('next', '').strip()}")
        out.append("")
        out.extend(f"- {line}" for line in lines)
        out.append("")
    out.extend(["## No page", ""])
    if not report["no_page"]:
        out.extend(["None.", ""])
    for source, lines in sorted(report["no_page"].items(), key=lambda kv: (-len(kv[1]), kv[0].casefold())):
        out.append(f"### {source} ({len(lines)} line{'' if len(lines) == 1 else 's'})")
        out.append("No page's repo, title, or aliases match. Add an alias to a card or note, or leave these to triage.")
        out.append("")
        out.extend(f"- {line}" for line in lines)
        out.append("")
    out.extend(["## Done, ready to drop", ""])
    if not report["done"]:
        out.extend(["None.", ""])
    for line in report["done"]:
        out.append(f"- {drop_command(line)}")
    if report["done"]:
        out.append("")
    return "\n".join(out)


def write_ingest(root: Path, today: str) -> int:
    root = Path(root)
    inbox = root / "INBOX.md"
    lines = inbox_items(inbox.read_text(encoding="utf-8")) if inbox.is_file() else []
    items: list[Item] = []
    note = ""
    registry = root / "REGISTRY.md"
    if registry.is_file():
        try:
            items = parse_registry(registry.read_text(encoding="utf-8")).items
        except RegistryParseError as exc:
            note = f"Registry unreadable ({exc}); registry rules were skipped."
    report = build(lines, items, pages(root), read_log(root))
    path = root / "reviews" / "ingest" / f"{today}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(today, report, note))
    print(path)
    return 0


def log_pairs(root: Path, today: str, pages_given: list[str], outcome: str,
              exact: str | None = None, contains: str | None = None) -> list[str]:
    """Record reviewed (line, page) pairs in knowledge/LOG.md. Returns the messages to print."""
    if not valid_date(today):
        raise CaptureError("today must be YYYY-MM-DD")
    if outcome not in OUTCOMES:
        raise CaptureError(f"outcome must be one of {', '.join(OUTCOMES)}")
    if (exact is None) == (contains is None):
        raise CaptureError("name the line with exactly one of --line or --contains")
    root = check_root(root)
    all_pages = pages(root)
    known = {page.path for page in all_pages}
    wanted = []
    for given in pages_given:
        path = given.strip().replace("\\", "/").removeprefix("./")
        if path not in known:
            raise CaptureError(f"{given} is not an ingest page (a note or card under knowledge/, not a template or staff card)")
        wanted.append(path)
    inbox = root / "INBOX.md"
    bodies = inbox_items(inbox.read_text(encoding="utf-8")) if inbox.is_file() else []
    line = bodies[_pick(bodies, set(), exact, contains)]
    digest = line_hash(line)
    log = root / "knowledge" / "LOG.md"
    messages = []
    with inbox_lock(root):
        logged = read_log(root)
        text = log.read_text(encoding="utf-8") if log.is_file() else LOG_HEADER
        for path in wanted:
            if (digest, path) in logged:
                messages.append(f"already logged: {path}")
                continue
            if not text.endswith("\n"):
                text += "\n"
            text += f"- {today} | {digest} | {path} | {outcome}\n"
            logged.add((digest, path))
            messages.append(f"logged: {path} {outcome}")
        log.write_text(text, encoding="utf-8", newline="\n")
    items: list[Item] = []
    registry = root / "REGISTRY.md"
    if registry.is_file():
        try:
            items = parse_registry(registry.read_text(encoding="utf-8")).items
        except RegistryParseError:
            items = []
    _, reached = route(line, _open_items(items), all_pages)
    left = sorted(path for path in reached if (digest, path) not in logged)
    if left:
        messages.append("still to review: " + ", ".join(left))
    else:
        messages.append(f"ready to drop after acceptance: {drop_command(line)}")
    return messages
