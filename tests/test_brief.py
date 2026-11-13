import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
TODAY = "2026-10-08"


def copy_fixture(name: str, tmp_path: Path) -> Path:
    dst = tmp_path / name
    shutil.copytree(FIXTURES / name, dst)
    return dst


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("first-brief", 0),
        ("inbox-triage", 0),
        ("focus-blocked", 0),
        ("missing-focus", 0),
        ("due-follow", 0),
        ("closed-only", 0),
        ("oldest", 0),
        ("capacity", 0),
        ("missing-inbox", 0),
        ("missing-context", 0),
        ("unusable", 0),
        ("missing-registry", 2),
    ],
)
def test_brief_matches_expected(name: str, code: int, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    from scripts.brief import write_brief

    src = FIXTURES / name
    dst = copy_fixture(name, tmp_path)
    registry = dst / "REGISTRY.md"
    before = registry.read_bytes() if registry.exists() else None
    assert write_brief(dst, TODAY) == code
    assert capsys.readouterr().out == ""
    actual = (dst / "reviews" / "daily" / f"{TODAY}.md").read_text(encoding="utf-8")
    dashboard = (dst / "DASHBOARD.md").read_text(encoding="utf-8")
    assert actual == (src / "expected-brief.md").read_text(encoding="utf-8")
    assert dashboard == (src / "expected-dashboard.md").read_text(encoding="utf-8")
    if before is None:
        assert not registry.exists()
    else:
        assert registry.read_bytes() == before


def test_same_day_replace(tmp_path: Path):
    from scripts.brief import write_brief

    dst = copy_fixture("inbox-triage", tmp_path)
    assert write_brief(dst, TODAY) == 0
    brief = dst / "reviews" / "daily" / f"{TODAY}.md"
    dashboard = dst / "DASHBOARD.md"
    brief.write_text("SENTINEL", encoding="utf-8")
    dashboard.write_text("SENTINEL", encoding="utf-8")
    assert write_brief(dst, TODAY) == 0
    expected = FIXTURES / "inbox-triage"
    assert brief.read_text(encoding="utf-8") == (expected / "expected-brief.md").read_text(encoding="utf-8")
    assert dashboard.read_text(encoding="utf-8") == (expected / "expected-dashboard.md").read_text(encoding="utf-8")


def test_unreadable_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    from scripts.brief import write_brief

    dst = copy_fixture("unreadable", tmp_path)
    assert write_brief(dst, TODAY) == 1
    assert capsys.readouterr().out == "unreadable registry: BAD_ID\n"
    assert not (dst / "reviews" / "daily" / f"{TODAY}.md").exists()
    assert (dst / "DASHBOARD.md").read_text(encoding="utf-8") == "SENTINEL\n"
    assert (dst / "reviews" / "daily" / "2026-10-07.md").read_text(encoding="utf-8") == "keep\n"


def test_cli_brief(tmp_path: Path):
    dst = copy_fixture("first-brief", tmp_path)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "brain.py"), "brief", "--root", str(dst), "--today", TODAY],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Call the clinic and book a cleaning." in (dst / "DASHBOARD.md").read_text(encoding="utf-8")


def _due_item(item_id, due, status="active"):
    extra = "blocked_on: Sam\nfollow_up: 2026-12-20\n" if status == "waiting" else "blocked_on:\nfollow_up:\n"
    return (f"## {item_id}\ntitle: Title of {item_id}\narea: Work\nkind: task\nstatus: {status}\nnext: Do it.\n"
            f"{extra}pointer:\nopened: 2026-11-01\nupdated: 2026-11-01\noutcome:\nnotes:\ndue: {due}\n")


def test_deadlines_lists_what_is_due_within_a_week_soonest_first(tmp_path):
    from scripts.brief import deadline_lines, write_brief
    from scripts.model import parse_registry
    text = "# Registry\n\nfocus:\n\n" + "\n".join([
        _due_item("far-away", "2026-12-25"), _due_item("this-week", "2026-11-14"), _due_item("late", "2026-11-09"),
        _due_item("today-item", "2026-11-11", "waiting"), _due_item("finished", "2026-11-10", "done"),
        _due_item("no-date", ""),
    ])
    assert deadline_lines(parse_registry(text).items, "2026-11-11") == [
        "- late: Title of late (due 2026-11-09, 2 days overdue)",
        "- today-item: Title of today-item (due 2026-11-11, today)",
        "- this-week: Title of this-week (due 2026-11-14, in 3 days)",
    ]
    (tmp_path / "REGISTRY.md").write_text(text, encoding="utf-8")
    assert write_brief(tmp_path, "2026-11-11") == 0
    brief = (tmp_path / "reviews" / "daily" / "2026-11-11.md").read_text(encoding="utf-8")
    assert "## Deadlines\n- late: Title of late (due 2026-11-09, 2 days overdue)\n" in brief
    assert "far-away" not in brief.split("## Deadlines")[1].split("##")[0]


def test_no_deadlines_section_without_a_due_date_and_the_snapshot_is_explained(tmp_path):
    from scripts.brief import write_brief
    from scripts.model import snapshot_inbox
    (tmp_path / "REGISTRY.md").write_text("# Registry\n\nfocus:\n\n" + _due_item("no-date", ""), encoding="utf-8")
    assert write_brief(tmp_path, "2026-11-11") == 0
    brief = (tmp_path / "reviews" / "daily" / "2026-11-11.md").read_text(encoding="utf-8")
    assert "## Deadlines" not in brief
    assert "## Decisions due" not in brief
    assert "## For the next brief\nThe next brief compares itself against these lines." in brief
    assert snapshot_inbox(brief) == 0


def test_decisions_due_lists_due_and_overdue_reviews_and_open_decisions_with_conditions(tmp_path):
    from scripts.brief import decision_lines, write_brief

    (tmp_path / "REGISTRY.md").write_text("# Registry\n\nfocus:\n\n" + _due_item("no-date", ""), encoding="utf-8")
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "tier-rule.md").write_text(
        "---\ntype: decision\nrecorded: 2026-10-16\nsource: Jane\n"
        "expected: Hot-lead response time drops below 2 hours\n"
        "breaks_if: Uncalled hot leads rise above 10%\n"
        "review_on: 2026-11-09\nstatus: current\n---\n\n# LinkedIn Lead Ads moved to hot tier\n\n## Limits\nNone.\n",
        encoding="utf-8",
    )
    (knowledge / "locale-choice.md").write_text(
        "---\ntype: decision\nrecorded: 2026-11-01\nsource: Jane\n"
        "decide_by: 2026-11-11\nstatus: current\n---\n\n# Choose PT-BR or PT-PT\n\n## Limits\nNone.\n",
        encoding="utf-8",
    )
    (knowledge / "future-review.md").write_text(
        "---\ntype: decision\nrecorded: 2026-11-01\nsource: Jane\n"
        "review_on: 2026-12-01\nstatus: current\n---\n\n# Future check\n\n## Limits\nNone.\n",
        encoding="utf-8",
    )
    (knowledge / "retired.md").write_text(
        "---\ntype: decision\nrecorded: 2026-10-01\nsource: Jane\n"
        "review_on: 2026-11-01\nstatus: superseded\n---\n\n# Retired decision\n\n## Limits\nNone.\n",
        encoding="utf-8",
    )
    expected = [
        "- tier-rule: LinkedIn Lead Ads moved to hot tier (review 2026-11-09, 2 days overdue)"
        " — expected: Hot-lead response time drops below 2 hours — breaks if: Uncalled hot leads rise above 10%",
        "- locale-choice: Choose PT-BR or PT-PT (decide by 2026-11-11, today)",
    ]
    assert decision_lines(tmp_path, "2026-11-11") == expected
    assert write_brief(tmp_path, "2026-11-11") == 0
    brief = (tmp_path / "reviews" / "daily" / "2026-11-11.md").read_text(encoding="utf-8")
    assert "## Decisions due\n" + "\n".join(expected) + "\n" in brief
    assert "future-review" not in brief
    assert "retired" not in brief


def _note(folder, name, head, title="Title", body=""):
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{head}status: current\n---\n\n# {title}\n{body}\n## Limits\nNone.\n", encoding="utf-8")


def test_decisions_due_reports_an_unreadable_date_and_accepts_a_quoted_one(tmp_path):
    from scripts.brief import decision_lines

    knowledge = tmp_path / "knowledge"
    _note(knowledge, "quoted.md", 'review_on: "2026-11-10"\n', "Quoted date")
    _note(knowledge, "comment.md", "review_on: 2026-11-09 # check leads\n", "Trailing comment")
    _note(knowledge, "impossible.md", "decide_by: 2026-11-31\n", "Impossible date")
    _note(knowledge, "empty.md", "review_on:\ndecide_by:\n", "No dates")
    assert decision_lines(tmp_path, "2026-11-11") == [
        "- comment: Trailing comment (review_on is not a YYYY-MM-DD date: 2026-11-09 # check leads; no reminder "
        "until it is fixed)",
        "- impossible: Impossible date (decide_by is not a YYYY-MM-DD date: 2026-11-31; no reminder until it is fixed)",
        "- quoted: Quoted date (review 2026-11-10, 1 day overdue)",
    ]


def test_decisions_due_skips_staff_cards_and_templates_and_lists_any_note_type_and_both_dates(tmp_path):
    from scripts.brief import decision_lines

    knowledge = tmp_path / "knowledge"
    for name in ("team/ana.md", "TEMPLATE.md", "LOG.md", "README.md", "INDEX.md", "projects/TEMPLATE.md"):
        _note(knowledge, name, "review_on: 2026-11-01\n", "Skipped")
    _note(knowledge, "projects/site.md", "type: reference\nreview_on: 2026-11-11\n", "Site card")
    _note(knowledge, "both.md", "type: decision\ndecide_by: 2026-11-08\nreview_on: 2026-11-10\n", "Both dates")
    assert decision_lines(tmp_path, "2026-11-11") == [
        "- both: Both dates (decide by 2026-11-08, 3 days overdue)",
        "- both: Both dates (review 2026-11-10, 1 day overdue)",
        "- projects/site: Site card (review 2026-11-11, today)",
    ]


def test_decisions_due_reads_the_frontmatter_not_lines_in_the_body(tmp_path):
    from scripts.brief import decision_lines

    knowledge = tmp_path / "knowledge"
    body = "\nstatus: superseded\nreview_on: 2027-01-01\n\n```\n# a shell comment\nexpected: from the code block\n```\n"
    _note(knowledge, "intro.md", "expected: >\nbreaks_if: Leads drop\nreview_on: 2026-11-11\n", "Real title", body)
    assert decision_lines(tmp_path, "2026-11-11") == [
        "- intro: Real title (review 2026-11-11, today) — breaks if: Leads drop",
    ]


def test_dashboard_counts_decisions_due(tmp_path):
    from scripts.brief import write_brief

    (tmp_path / "REGISTRY.md").write_text("# Registry\n\nfocus:\n\n" + _due_item("no-date", ""), encoding="utf-8")
    assert write_brief(tmp_path, "2026-11-10") == 0
    assert "Decisions due" not in (tmp_path / "DASHBOARD.md").read_text(encoding="utf-8")
    _note(tmp_path / "knowledge", "one.md", "review_on: 2026-11-11\n")
    _note(tmp_path / "knowledge", "two.md", "decide_by: 2026-11-01\n")
    assert write_brief(tmp_path, "2026-11-11") == 0
    assert "Decisions due: 2. See the brief.\n" in (tmp_path / "DASHBOARD.md").read_text(encoding="utf-8")
