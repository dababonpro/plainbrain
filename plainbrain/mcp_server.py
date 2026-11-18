"""Plainbrain as a local MCP server (stdio). No network, no API keys.

Every tool reads the files in this checkout. The one write is `capture`, which appends a
line to INBOX.md through the same locked, append-only path as `brain.py capture`.
Registry, triage, and brief changes stay in a Plainbrain session.
"""
import os
import sys
from datetime import date
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

from plainbrain.home import NOT_SET_UP, data_root  # noqa: E402

# Left as None so the folder is looked up on every call. A test sets it to a folder of its own.
ROOT = None


def _root() -> Path | None:
    """The owner's folder: BRAIN_ROOT, else (as a Claude plugin) the folder setup recorded, else this checkout.

    Looked up on every call, not once at start. Claude Code starts this server when the session opens, before
    the owner has run setup, so a value read at start would say "no folder yet" for the rest of that session.
    None means a plugin install with no folder: there is nowhere safe to read or write."""
    return ROOT if ROOT is not None else data_root(CODE)

from mcp.server.fastmcp import FastMCP  # noqa: E402

from plainbrain.capture import CaptureError, capture_line, repo_view  # noqa: E402
from plainbrain.model import RegistryParseError, latest_brief_path, parse_registry  # noqa: E402
from plainbrain.search import search as ranked_search  # noqa: E402

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
    root = _root()
    if root is None:
        return None
    path = root / "REGISTRY.md"
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
    root = _root()
    if root is None:
        return NOT_SET_UP
    return repo_view(root, repo, _today())


@server.tool()
def search(query: str, limit: int = 10) -> list[dict]:
    """Ranked search over the registry, inbox, knowledge notes, project cards, and archive.
    Returns path, line, section title, and the best matching line. Use a few distinctive words,
    such as a ticket key, a person, or a repo name."""
    root = _root()
    if root is None:
        return []
    return ranked_search(root, query, max(1, min(limit, 30)))


@server.tool()
def registry_item(item_id: str) -> str:
    """The full registry block for one commitment id, for example website-chat-password."""
    root = _root()
    if root is None:
        return NOT_SET_UP
    path = root / "REGISTRY.md"
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
    root = _root()
    if root is None:
        return NOT_SET_UP
    path = latest_brief_path(root / "reviews" / "daily")
    if path is None:
        return "No brief yet."
    return path.read_text(encoding="utf-8")


@server.tool()
def capture(repo: str, text: str) -> str:
    """Append one sentence to the owner's inbox for tomorrow's brief: what happened and what is left.
    `repo` is the current folder name. Name a registry id first when the fact is about one,
    as in "website-chat-password: rotated; left: update the secret in prod". Returns the line."""
    root = _root()
    if root is None:
        return NOT_SET_UP
    try:
        return capture_line(root, repo, text, _today())
    except CaptureError as exc:
        return f"Not captured: {exc}"


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
