from pathlib import Path

import pytest

from scripts.model import (
    RegistryParseError,
    capacity_line,
    counts,
    inbox_items,
    latest_brief_path,
    parse_registry,
    previous_brief_path,
    snapshot_inbox,
)


SAMPLE = """# Registry

focus: dentist-call

## dentist-call
title: Book the dentist
area: Personal
kind: task
status: active
next: Call the clinic
blocked_on:
follow_up:
pointer:
opened: 2026-10-01
updated: 2026-10-08
outcome:
notes:
extra: ignored
"""


def test_parse_sample():
    doc = parse_registry(SAMPLE)
    assert doc.focus == "dentist-call"
    assert doc.items[0].id == "dentist-call"
    assert doc.items[0].reason is None
    assert doc.items[0].fields["title"] == "Book the dentist"
    assert doc.items[0].fields["extra"] == "ignored"


def test_empty_registry():
    doc = parse_registry("# Registry\n\nfocus:\n")
    assert doc.focus == ""
    assert doc.items == []


def test_unusable_reasons():
    text = """# Registry

focus:

## no-title
title:
status: active
next: Call
updated: 2026-10-01

## no-status
title: T
status:
next: Call
updated: 2026-10-01

## no-next
title: T
status: active
next:
updated: 2026-10-01

## no-updated
title: T
status: active
next: Call
updated:

## bad-updated
title: T
status: active
next: Call
updated: 08-10-2026

## bad-status
title: T
status: later
next: Call
updated: 2026-10-01

## bad-follow
title: T
status: active
next: Call
updated: 2026-10-01
follow_up: soon

## dup
title: First
status: active
next: Keep
updated: 2026-10-01

## dup
title:
status:
next:
updated:

## wait-empty
title: T
status: waiting
next: Ask
blocked_on:
updated: 2026-10-01

## someday-empty
title: T
status: someday
next: Revisit
follow_up:
updated: 2026-10-01
"""
    reasons = {item.id: [] for item in parse_registry(text).items}
    for item in parse_registry(text).items:
        reasons[item.id].append(item.reason)
    assert reasons["no-title"] == ["missing title"]
    assert reasons["no-status"] == ["missing status"]
    assert reasons["no-next"] == ["missing next"]
    assert reasons["no-updated"] == ["missing updated"]
    assert reasons["bad-updated"] == ["bad updated"]
    assert reasons["bad-status"] == ["bad status"]
    assert reasons["bad-follow"] == ["bad follow_up"]
    assert reasons["dup"] == [None, "duplicate id"]
    assert reasons["wait-empty"] == ["waiting without blocked_on"]
    assert reasons["someday-empty"] == ["someday without follow_up"]


def test_bad_id():
    with pytest.raises(RegistryParseError) as caught:
        parse_registry("# Registry\n\nfocus:\n\n## BAD_ID\ntitle: Nope\n")
    assert caught.value.report == "BAD_ID"


def test_empty_heading_reports_line():
    text = "# Registry\n\nfocus:\n\n## \ntitle: Nope\n"
    with pytest.raises(RegistryParseError) as caught:
        parse_registry(text)
    assert caught.value.report == "line 5"


def test_bad_field_reports_id():
    text = "# Registry\n\nfocus:\n\n## ok-id\nnot a field\n"
    with pytest.raises(RegistryParseError) as caught:
        parse_registry(text)
    assert caught.value.report == "ok-id"


def test_missing_heading_and_focus():
    with pytest.raises(RegistryParseError) as caught:
        parse_registry("focus:\n\n## ok-id\n")
    assert caught.value.report == "line 1"
    with pytest.raises(RegistryParseError) as caught:
        parse_registry("# Registry\n\n## ok-id\ntitle: X\n")
    assert caught.value.report == "line 1"


def test_inbox_items():
    text = """# Inbox

## Brain Dump

- 
- call the clinic
- second

## Triage Rules

- not an inbox item
"""
    assert inbox_items(text) == ["call the clinic", "second"]


def test_inbox_items_when_brain_dump_is_last():
    text = """# Inbox

## Triage Rules

- Action: not an inbox item

## Brain Dump

- real item
"""
    assert inbox_items(text) == ["real item"]


def test_capacity_line():
    assert capacity_line(None) == "Capacity is unknown."
    assert capacity_line("") == "Capacity is unknown."
    assert capacity_line("capacity: Unknown\n") == "Capacity is unknown."
    assert capacity_line("capacity:\n") == "Capacity is unknown."
    assert capacity_line("# Context\n\ncapacity: short day\n") == "Capacity: short day."


def test_snapshot_and_brief_paths(tmp_path: Path):
    daily = tmp_path / "reviews" / "daily"
    daily.mkdir(parents=True)
    (daily / "2026-10-07.md").write_text(
        "# Brief 2026-10-07\n\nsnapshot:\ninbox: 0\n", encoding="utf-8"
    )
    (daily / "2026-10-08.md").write_text("today\n", encoding="utf-8")
    (daily / "2026-10-09.md").write_text("later\n", encoding="utf-8")
    (daily / "notes.md").write_text("skip\n", encoding="utf-8")
    assert previous_brief_path(daily, "2026-10-08").stem == "2026-10-07"
    assert latest_brief_path(daily).stem == "2026-10-09"
    assert snapshot_inbox((daily / "2026-10-07.md").read_text(encoding="utf-8")) == 0
    assert previous_brief_path(tmp_path / "missing", "2026-10-08") is None


def test_counts_skip_duplicates_and_bad_status():
    text = """# Registry

focus:

## keep
title: Keep
status: active
next: Go
updated: 2026-10-01

## keep
title: Copy
status: active
next: Go
updated: 2026-10-01

## later
title: Later
status: later
next: Go
updated: 2026-10-01

## hold
title: Hold
status: waiting
next: Ask
blocked_on:
updated: 2026-10-01
"""
    assert counts(parse_registry(text).items) == {
        "active": 1,
        "waiting": 1,
        "someday": 0,
        "done": 0,
    }


def test_a_done_item_needs_no_next_action():
    from scripts.model import parse_registry
    doc = parse_registry("# Registry\n\nfocus:\n\n## shipped\ntitle: Shipped\nstatus: done\nnext:\nupdated: 2026-10-20\n\n"
                         "## open\ntitle: Open\nstatus: active\nnext:\nupdated: 2026-10-20\n")
    reasons = {item.id: item.reason for item in doc.items}
    assert reasons == {"shipped": None, "open": "missing next"}


def test_note_head_takes_the_first_value_and_ignores_frontmatter_comments_and_code(tmp_path):
    from scripts.model import note_head, note_paths

    text = (
        "---\n# a yaml comment\nstatus: current\nreview_on: 2026-11-09\n---\n\n"
        "```\n# not the title\nstatus: superseded\n```\n"
        "# The title\nstatus: superseded\nsummary: under the title\n# Second heading\n\n## Section\nreview_on: 2030-01-01\n"
    )
    assert note_head(text) == (
        "The title", {"status": "current", "review_on": "2026-11-09", "summary": "under the title"})
    assert note_head("no heading\n") == ("", {})
    for name in ("a.md", "sub/b.md", "team/c.md", "sub/team/d.md", "TEMPLATE.md", "sub/INDEX.md", "LOG.md", "README.md"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    assert [p.relative_to(tmp_path).as_posix() for p in note_paths(tmp_path)] == ["a.md", "sub/b.md"]
