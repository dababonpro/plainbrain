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
