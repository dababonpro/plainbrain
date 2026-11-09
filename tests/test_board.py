import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
TODAY = "2026-10-08"


def copy_fixture(name: str, tmp_path: Path) -> Path:
    dst = tmp_path / name
    shutil.copytree(FIXTURES / name, dst)
    return dst


def test_board_after_brief(tmp_path: Path):
    from scripts.board import write_board
    from scripts.brief import write_brief

    dst = copy_fixture("first-brief", tmp_path)
    assert write_brief(dst, TODAY) == 0
    assert write_board(dst, TODAY) == 0
    html = (dst / "board" / "index.html").read_text(encoding="utf-8")
    assert "2026-10-08" in html
    assert "Call the clinic and book a cleaning." in html
    assert "No previous brief." in html
    assert "clinic" in html
    assert "2026-10-08" in html
    assert "C:/work/dentist" in html
    active = html.split('id="active"', 1)[1].split("</ul>", 1)[0]
    assert "dentist-call" in active
    assert "later-task" not in active
    assert 'id="queue"' in html
    assert "later-task" in html.split('id="queue"', 1)[1]
    assert '<details id="waiting" open>' in html
    assert '<details id="someday" open>' in html
    assert '<details id="done">' in html
    assert '<details id="done" open>' not in html
    assert "Learn piano" in html
    assert "Pay the bill" in html


def test_board_lists_inbox_lines(tmp_path: Path):
    from scripts.board import write_board
    from scripts.brief import write_brief

    dst = copy_fixture("inbox-triage", tmp_path)
    assert write_brief(dst, TODAY) == 0
    assert write_board(dst, TODAY) == 0
    html = (dst / "board" / "index.html").read_text(encoding="utf-8")
    inbox = html.split('id="inbox"', 1)[1].split("</ul>", 1)[0]
    assert "call the clinic" in inbox


def test_empty_registry_board(tmp_path: Path):
    from scripts.board import write_board
    from scripts.brief import write_brief

    dst = copy_fixture("empty-registry", tmp_path)
    assert write_brief(dst, TODAY) == 0
    assert write_board(dst, TODAY) == 0
    html = (dst / "board" / "index.html").read_text(encoding="utf-8")
    assert "The registry is empty." in html
    assert "Inbox: 0" in html
    assert "No usable next action today." in html
    assert 'id="active"' not in html


def test_board_shows_unusable(tmp_path: Path):
    from scripts.board import write_board
    from scripts.brief import write_brief

    dst = copy_fixture("unusable", tmp_path)
    assert write_brief(dst, TODAY) == 0
    assert write_board(dst, TODAY) == 0
    html = (dst / "board" / "index.html").read_text(encoding="utf-8")
    active = html.split('id="active"', 1)[1].split("</ul>", 1)[0]
    assert "no-title" in active
    assert "missing title" in active
    assert "duplicate id" in active
    needs = html.split('id="needs-fix"', 1)[1]
    assert "bad-status" in needs
    assert "no-status" in needs


def test_board_leaves_existing_html(tmp_path: Path, capsys):
    from scripts.board import write_board

    dst = copy_fixture("board-unreadable", tmp_path)
    assert write_board(dst, TODAY) == 1
    assert capsys.readouterr().out == "unreadable registry: BAD_ID\n"
    assert (dst / "board" / "index.html").read_text(encoding="utf-8") == "SENTINEL\n"


def test_board_missing_registry_creates_nothing(tmp_path: Path, capsys):
    from scripts.board import write_board

    dst = copy_fixture("missing-registry", tmp_path)
    assert write_board(dst, TODAY) == 1
    assert capsys.readouterr().out == "unreadable registry: missing\n"
    assert not (dst / "board" / "index.html").exists()


def test_cli_board(tmp_path: Path):
    dst = copy_fixture("empty-registry", tmp_path)
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "brain.py"), "brief", "--root", str(dst), "--today", TODAY],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "brain.py"), "board", "--root", str(dst), "--today", TODAY],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "The registry is empty." in (dst / "board" / "index.html").read_text(encoding="utf-8")


def test_board_shows_current_usage_summary(tmp_path):
    from scripts.board import write_board
    from scripts.brief import write_brief

    root = copy_fixture("first-brief", tmp_path)
    write_brief(root, TODAY)
    usage = root / "reviews" / "usage"
    usage.mkdir(parents=True)
    (usage / "latest.json").write_text(
        json.dumps(
            {
                "week": "2026-W42",
                "as_of": "2026-10-18",
                "human_ms": 3_600_000,
                "idle_ms": 1_800_000,
                "prompting_ms": 600_000,
                "cursor_busy_ms": 1_800_000,
                "cursor_open_ms": 2_000_000,
                "claude_busy_ms": None,
                "claude_open_ms": None,
                "segments": 1,
                "cursor_failures": 0,
                "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
                "token_sessions": 0,
                "total_sessions": 1,
                "unattributed": 0,
                "orphans": 0,
            }
        ),
        encoding="utf-8",
    )
    assert write_board(root, "2026-10-18") == 0
    page = (root / "board/index.html").read_text(encoding="utf-8")
    assert 'id="usage"' in page
    assert "Human: 1h" in page
    assert "prompting 10m" in page
    assert "idle 30m" in page
    assert "Cursor busy: 30m" in page
    assert "(stale)" not in page.split('id="usage"', 1)[1].split("</section>", 1)[0]


def test_monday_accepts_previous_week_as_current(tmp_path):
    from scripts.board import write_board
    from scripts.brief import write_brief

    root = copy_fixture("first-brief", tmp_path)
    write_brief(root, TODAY)
    usage = root / "reviews" / "usage"
    usage.mkdir(parents=True)
    (usage / "latest.json").write_text(
        json.dumps(
            {
                "week": "2026-W42",
                "as_of": "2026-10-19",
                "human_ms": 0,
                "cursor_busy_ms": None,
                "cursor_open_ms": None,
                "claude_busy_ms": None,
                "claude_open_ms": None,
                "segments": 0,
                "cursor_failures": 0,
                "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
                "token_sessions": 0,
                "total_sessions": 0,
                "unattributed": 0,
                "orphans": 0,
            }
        ),
        encoding="utf-8",
    )
    assert write_board(root, "2026-10-19") == 0
    assert "(stale)" not in (root / "board/index.html").read_text(encoding="utf-8")


def test_board_omits_usage_when_summary_missing_or_unreadable(tmp_path):
    from scripts.board import write_board
    from scripts.brief import write_brief

    root = copy_fixture("first-brief", tmp_path)
    write_brief(root, TODAY)
    assert write_board(root, TODAY) == 0
    assert 'id="usage"' not in (root / "board/index.html").read_text(encoding="utf-8")
    usage = root / "reviews" / "usage"
    usage.mkdir(parents=True)
    (usage / "latest.json").write_text("{bad", encoding="utf-8")
    assert write_board(root, TODAY) == 0
    assert 'id="usage"' not in (root / "board/index.html").read_text(encoding="utf-8")


def test_stale_usage_week_is_labeled(tmp_path):
    from scripts.board import write_board
    from scripts.brief import write_brief

    root = copy_fixture("first-brief", tmp_path)
    write_brief(root, TODAY)
    usage = root / "reviews" / "usage"
    usage.mkdir(parents=True)
    (usage / "latest.json").write_text(
        json.dumps(
            {
                "week": "2026-W40",
                "as_of": "2026-10-01",
                "human_ms": 0,
                "cursor_busy_ms": None,
                "cursor_open_ms": None,
                "claude_busy_ms": None,
                "claude_open_ms": None,
                "segments": 0,
                "cursor_failures": 0,
                "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
                "token_sessions": 0,
                "total_sessions": 0,
                "unattributed": 0,
                "orphans": 0,
            }
        ),
        encoding="utf-8",
    )
    assert write_board(root, "2026-10-18") == 0
    page = (root / "board/index.html").read_text(encoding="utf-8")
    assert "Usage: week 2026-W40 (stale)" in page


def test_agents_refresh():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "python scripts/brain.py board --root . --today YYYY-MM-DD" in text
    assert "Exit code 0: the brief was written and the registry was readable. Run the board command." in text
    assert "unreadable registry:" in text
