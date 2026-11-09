"""Plainbrain as a local MCP server (stdio). No network, no API keys.

Every tool reads the files in this checkout. The one write is `capture`, which appends a
line to INBOX.md through the same locked, append-only path as `brain.py capture`.
Registry, triage, and brief changes stay in a Plainbrain session.
"""
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(os.environ.get("BRAIN_ROOT") or Path(__file__).resolve().parents[1])
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from scripts.capture import CaptureError, capture_line, repo_view  # noqa: E402
from scripts.model import RegistryParseError, latest_brief_path, parse_registry  # noqa: E402
from scripts.search import search as ranked_search  # noqa: E402

INSTRUCTIONS = (
    "Plainbrain is the owner's command system: REGISTRY.md is the only list of their commitments, "
    "INBOX.md holds raw capture, knowledge/ holds notes and project cards. "
    "Start work in a repo with for_repo to see what the owner already owes there. "
    "Use search before asking the owner about a past decision, person, or ticket. "
    "At the end of a session, call capture once per fact worth tomorrow's brief: one sentence "
    "on what happened and what is left. Never capture a transcript. capture is the only write; "
    "registry changes, triage, and briefs happen in a Plainbrain session."
)

server = FastMCP("plainbrain", instructions=INSTRUCTIONS)


def _today() -> str:
    return date.today().isoformat()


def _registry():
    path = ROOT / "REGISTRY.md"
    if not path.is_file():
        return None
    try:
        return parse_registry(path.read_text(encoding="utf-8"))
    except RegistryParseError:
        return None


@server.tool()
def for_repo(repo: str) -> str:
    """What the owner owes in one repo: open registry items pointing at it, the newest inbox line
    from it, its project card's Now section, and unpushed local work. `repo` is the folder name,
    for example my-website."""
    return repo_view(ROOT, repo, _today())


@server.tool()
def search(query: str, limit: int = 10) -> list[dict]:
    """Ranked search over the registry, inbox, knowledge notes, project cards, and archive.
    Returns path, line, section title, and the best matching line. Use a few distinctive words,
    such as a ticket key, a person, or a repo name."""
    return ranked_search(ROOT, query, max(1, min(limit, 30)))


@server.tool()
def registry_item(item_id: str) -> str:
    """The full registry block for one commitment id, for example website-chat-password."""
    path = ROOT / "REGISTRY.md"
    if not path.is_file():
        return "REGISTRY.md is missing."
    lines = path.read_text(encoding="utf-8").splitlines()
    wanted = f"## {item_id.strip()}"
    for index, line in enumerate(lines):
        if line.strip() == wanted:
            block = [line]
            for rest in lines[index + 1:]:
                if rest.startswith("## "):
                    break
                block.append(rest)
            return "\n".join(block).strip()
    return f"No registry item {item_id}."


@server.tool()
def open_items(area: str = "", status: str = "active") -> list[dict]:
    """Registry items with one status (active, waiting, someday, or done; empty for every open
    status), optionally in one area (Work or Personal). Each has id, title, status, next,
    pointer, and updated."""
    doc = _registry()
    if doc is None:
        return []
    found = []
    for item in doc.items:
        fields = item.fields
        item_status = fields.get("status", "").strip()
        if status and item_status != status.strip():
            continue
        if not status and item_status == "done":
            continue
        if area and fields.get("area", "").strip().casefold() != area.strip().casefold():
            continue
        found.append({
            "id": item.id,
            "title": fields.get("title", "").strip(),
            "status": item_status,
            "next": fields.get("next", "").strip(),
            "pointer": fields.get("pointer", "").strip(),
            "updated": fields.get("updated", "").strip(),
            "focus": item.id == doc.focus,
        })
    return found


@server.tool()
def latest_brief() -> str:
    """Today's brief if it exists, else the newest one, with its date in the first line."""
    path = latest_brief_path(ROOT / "reviews" / "daily")
    if path is None:
        return "No brief yet."
    return path.read_text(encoding="utf-8")


@server.tool()
def capture(repo: str, text: str) -> str:
    """Append one sentence to the owner's inbox for tomorrow's brief: what happened and what is left.
    `repo` is the current folder name. Name a registry id first when the fact is about one,
    as in "website-chat-password: rotated; left: update the secret in prod". Returns the line."""
    try:
        return capture_line(ROOT, repo, text, _today())
    except CaptureError as exc:
        return f"Not captured: {exc}"


if __name__ == "__main__":
    server.run()
