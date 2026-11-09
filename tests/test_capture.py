from pathlib import Path

import pytest

import threading

from scripts.capture import CaptureError, capture_line, drop_lines, inbox_lock, repo_view
from scripts.model import inbox_items

VALID = """# Inbox

## Triage Rules

- Action: a concrete next step.

## Brain Dump

- old fact (from demo, 2026-10-20)
"""

BROKEN = """# Inbox

keep this sentence

- orphan line (from demo, 2026-10-21)

## Triage Rules

For each captured item, decide whether it is:

- Action: a concrete next step.
"""


def test_capture_appends_without_rewriting_a_valid_file(tmp_path):
    (tmp_path / "INBOX.md").write_text(VALID, encoding="utf-8")
    bullet = capture_line(tmp_path, "robot-ai-geek", "left the sitemap", "2026-10-21")
    text = (tmp_path / "INBOX.md").read_text(encoding="utf-8")
    assert text.startswith(VALID)
    assert text[len(VALID):] == "- left the sitemap (from robot-ai-geek, 2026-10-21)\n"
    assert bullet == "- left the sitemap (from robot-ai-geek, 2026-10-21)"
    assert inbox_items(text)[-1] == "left the sitemap (from robot-ai-geek, 2026-10-21)"


def test_capture_repairs_a_missing_heading_without_dropping_lines(tmp_path):
    (tmp_path / "INBOX.md").write_text(BROKEN, encoding="utf-8")
    capture_line(tmp_path, "demo", "new fact", "2026-10-21")
    text = (tmp_path / "INBOX.md").read_text(encoding="utf-8")
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert headings[-1] == "## Brain Dump"
    assert "keep this sentence" in text
    assert "For each captured item, decide whether it is:" in text
    assert "orphan line (from demo, 2026-10-21)" in text
    assert inbox_items(text)[0] == "orphan line (from demo, 2026-10-21)"
    assert inbox_items(text)[-1] == "new fact (from demo, 2026-10-21)"


def test_capture_creates_a_missing_file(tmp_path):
    (tmp_path / "REGISTRY.md").write_text("# Registry\n\nfocus:\n", encoding="utf-8")
    capture_line(tmp_path, "demo", "first line", "2026-10-21")
    text = (tmp_path / "INBOX.md").read_text(encoding="utf-8")
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert headings[-1] == "## Brain Dump"
    assert inbox_items(text) == ["first line (from demo, 2026-10-21)"]


def test_capture_rejects_empty_multiline_and_a_bad_repo():
    with pytest.raises(CaptureError):
        capture_line(Path("."), "demo", "  ", "2026-10-21")
    with pytest.raises(CaptureError):
        capture_line(Path("."), "demo", "one\ntwo", "2026-10-21")
    with pytest.raises(CaptureError):
        capture_line(Path("."), "bad,repo", "fact", "2026-10-21")
    with pytest.raises(CaptureError):
        capture_line(Path("."), "demo", "fact", "21-10-2026")


def test_shrink_guard_rejects_a_dropped_bullet():
    from scripts.capture import assert_keeps
    with pytest.raises(CaptureError, match="shrink"):
        assert_keeps("- one\n- two\n", "- one\n")


def test_repo_view_names_open_work_newest_line_and_now(tmp_path):
    (tmp_path / "REGISTRY.md").write_text(
        """# Registry

focus:

## demo-task
title: Demo
area: Work
kind: task
status: active
next: Ship the demo.
blocked_on:
follow_up:
pointer: C:\\Projects\\demo-repo
opened: 2026-10-20
updated: 2026-10-20
outcome:
notes:

## other-task
title: Other
area: Work
kind: task
status: active
next: Ignore this.
blocked_on:
follow_up:
pointer: C:\\Projects\\other
opened: 2026-10-20
updated: 2026-10-20
outcome:
notes:

## demo-done
title: Done demo
area: Work
kind: task
status: done
next: Nothing.
blocked_on:
follow_up:
pointer: C:\\Projects\\demo-repo
opened: 2026-10-20
updated: 2026-10-20
outcome:
notes:
""",
        encoding="utf-8",
    )
    (tmp_path / "INBOX.md").write_text(
        "# Inbox\n\n## Brain Dump\n\n"
        "- older (from demo-repo, 2026-10-20)\n"
        "- newest left (from demo-repo, 2026-10-21)\n"
        "- other repo (from other, 2026-10-21)\n",
        encoding="utf-8",
    )
    card = tmp_path / "knowledge" / "projects"
    card.mkdir(parents=True)
    (card / "demo-repo.md").write_text(
        "---\nrepo: 'C:\\Missing\\demo-repo'\n---\n\n# demo-repo\n\n## Now\nLive on v2.\n\n## Limits\nNone.\n",
        encoding="utf-8",
    )
    text = repo_view(tmp_path, "demo-repo", "2026-10-21")
    assert "demo-task" in text
    assert "Ship the demo." in text
    assert "other-task" not in text
    assert "demo-done" not in text
    assert "newest left (from demo-repo, 2026-10-21)" in text
    assert "older (from demo-repo, 2026-10-20)" not in text
    assert "Live on v2." in text
    assert "No checkout" in text


















def test_drop_removes_only_the_named_lines(tmp_path):
    text = VALID + "- second fact (from demo, 2026-10-21)\n- third fact (from other, 2026-10-21)\n"
    (tmp_path / "INBOX.md").write_text(text, encoding="utf-8")
    removed = drop_lines(tmp_path, exact=["- old fact (from demo, 2026-10-20)"], contains=["third fact"])
    assert removed == ["old fact (from demo, 2026-10-20)", "third fact (from other, 2026-10-21)"]
    after = (tmp_path / "INBOX.md").read_text(encoding="utf-8")
    assert inbox_items(after) == ["second fact (from demo, 2026-10-21)"]
    assert "- Action: a concrete next step." in after


def test_drop_writes_nothing_when_a_line_is_missing_or_ambiguous(tmp_path):
    text = VALID + "- second fact (from demo, 2026-10-21)\n"
    (tmp_path / "INBOX.md").write_text(text, encoding="utf-8")
    with pytest.raises(CaptureError):
        drop_lines(tmp_path, exact=["old fact (from demo, 2026-10-20)", "not there"])
    with pytest.raises(CaptureError):
        drop_lines(tmp_path, contains=["fact"])
    with pytest.raises(CaptureError):
        drop_lines(tmp_path, contains=["Action: a concrete"])
    assert (tmp_path / "INBOX.md").read_text(encoding="utf-8") == text


def test_concurrent_captures_keep_every_line(tmp_path):
    (tmp_path / "INBOX.md").write_text(VALID, encoding="utf-8")
    errors = []

    def write(n):
        try:
            capture_line(tmp_path, "demo", f"fact {n}", "2026-10-21")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(n,)) for n in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    items = inbox_items((tmp_path / "INBOX.md").read_text(encoding="utf-8"))
    assert sorted(items[1:]) == sorted(f"fact {n} (from demo, 2026-10-21)" for n in range(12))
    assert not (tmp_path / "INBOX.md.lock").exists()


def test_a_held_lock_blocks_then_a_stale_lock_is_cleared(tmp_path, monkeypatch):
    import scripts.capture as capture
    (tmp_path / "INBOX.md").write_text(VALID, encoding="utf-8")
    monkeypatch.setattr(capture, "LOCK_WAIT_SECONDS", 0.2)
    with inbox_lock(tmp_path):
        with pytest.raises(CaptureError):
            capture_line(tmp_path, "demo", "blocked", "2026-10-21")
    lock = tmp_path / "INBOX.md.lock"
    lock.write_text("1", encoding="utf-8")
    monkeypatch.setattr(capture, "LOCK_STALE_SECONDS", 0.0)
    capture_line(tmp_path, "demo", "after stale", "2026-10-21")
    assert "after stale (from demo, 2026-10-21)" in inbox_items((tmp_path / "INBOX.md").read_text(encoding="utf-8"))


def test_capture_refuses_a_root_that_is_not_plainbrain(tmp_path):
    missing = tmp_path / "Plainbrain"
    with pytest.raises(CaptureError):
        capture_line(missing, "demo", "lost line", "2026-10-21")
    assert not missing.exists()
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(CaptureError):
        capture_line(empty, "demo", "lost line", "2026-10-21")
    assert not (empty / "INBOX.md").exists()
    with pytest.raises(CaptureError, match="drive-relative"):
        capture_line(Path("C:Plainbrain"), "demo", "lost line", "2026-10-21")
    with pytest.raises(CaptureError):
        drop_lines(missing, contains=["x"])


