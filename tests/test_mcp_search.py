from pathlib import Path

import pytest

from scripts.search import search

mcp = pytest.importorskip("mcp")

from scripts import mcp_server  # noqa: E402

REGISTRY = """# Registry

focus: chat-password

## chat-password
title: Rotate the Google Chat bot password
area: Work
status: active
next: Rotate the password and update the secret.
pointer: C:\\Projects\\my-website
updated: 2026-10-09

## old-thing
title: Old thing
area: Personal
status: done
next:
pointer:
updated: 2026-10-01
"""

INBOX = """# Inbox

## Triage Rules

- Action: a concrete next step.

## Brain Dump

- robots.txt launch is waiting on DNS (from site, 2026-10-20)
- unrelated note about lunch (from site, 2026-10-21)
"""


@pytest.fixture
def root(tmp_path, monkeypatch):
    (tmp_path / "REGISTRY.md").write_text(REGISTRY, encoding="utf-8")
    (tmp_path / "INBOX.md").write_text(INBOX, encoding="utf-8")
    notes = tmp_path / "knowledge"
    notes.mkdir()
    (notes / "seo.md").write_text("# SEO\n\n## Launch\nCopy robots.txt.launch over robots.txt at launch.\n",
                                  encoding="utf-8")
    monkeypatch.setattr(mcp_server, "ROOT", tmp_path)
    return tmp_path


def test_search_ranks_items_lines_and_notes_with_line_numbers(root):
    found = search(root, "robots.txt launch")
    paths = [result["path"] for result in found]
    assert "INBOX.md" in paths and "knowledge/seo.md" in paths
    note = next(result for result in found if result["path"] == "knowledge/seo.md")
    assert note["line"] == 4 and note["title"] == "Launch"
    item = search(root, "chat password")[0]
    assert item["path"] == "REGISTRY.md" and item["title"] == "chat-password"
    assert search(root, "zzzz nothing") == []
    assert search(root, "   ") == []


def test_search_stems_simple_word_forms(root):
    assert search(root, "rotating passwords")[0]["title"] == "chat-password"


def test_tools_read_without_writing(root):
    before = {path: path.read_text(encoding="utf-8") for path in (root / "REGISTRY.md", root / "INBOX.md")}
    assert "next: Rotate the password" in mcp_server.registry_item("chat-password")
    assert mcp_server.registry_item("missing") == "No registry item missing."
    active = mcp_server.open_items()
    assert [item["id"] for item in active] == ["chat-password"] and active[0]["focus"]
    assert mcp_server.open_items(area="Personal", status="") == []
    assert [item["id"] for item in mcp_server.open_items(status="done")] == ["old-thing"]
    assert "chat-password" in mcp_server.for_repo("my-website")
    assert mcp_server.latest_brief() == "No brief yet."
    assert mcp_server.search("lunch")[0]["path"] == "INBOX.md"
    assert {path: path.read_text(encoding="utf-8") for path in before} == before


def test_capture_tool_appends_and_reports_refusals(root):
    line = mcp_server.capture("site", "DNS cut over; left: submit the sitemap")
    assert line.startswith("- DNS cut over; left: submit the sitemap (from site, ")
    text = (root / "INBOX.md").read_text(encoding="utf-8")
    assert text.startswith(INBOX) and text.rstrip().endswith(line)
    assert mcp_server.capture("site", "two\nlines").startswith("Not captured:")
    assert mcp_server.capture("bad repo name", "x").startswith("Not captured:")
