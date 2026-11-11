"""Init creates the owner's files once, with the example commitment or without it."""
from scripts import brain, registry
from scripts.brief import write_brief
from scripts.model import capacity_line, parse_registry

TODAY = "2026-11-11"


def _registry(root):
    return parse_registry((root / "REGISTRY.md").read_text(encoding="utf-8"))


def test_init_writes_one_example_by_default(tmp_path):
    assert brain.init(tmp_path, "Work, Personal") == 0
    assert [item.id for item in _registry(tmp_path).items] == ["set-up-second-brain"]
    assert capacity_line((tmp_path / "CONTEXT.md").read_text(encoding="utf-8")) == "Capacity is unknown."


def test_init_without_the_example_takes_real_commitments(tmp_path):
    assert brain.init(tmp_path, "Work, Home", "about 2 hours a day", example=False) == 0
    assert _registry(tmp_path).items == []
    registry.add(tmp_path, "renew-passport",
                 {"title": "Renew my passport", "next": "Book the appointment online", "area": "Home"}, TODAY)
    registry.focus(tmp_path, "renew-passport", TODAY)
    assert write_brief(tmp_path, TODAY) == 0
    brief = (tmp_path / "reviews" / "daily" / f"{TODAY}.md").read_text(encoding="utf-8")
    assert "Do this: Book the appointment online" in brief
    assert "Capacity: about 2 hours a day." in brief
    assert "set-up-second-brain" not in brief


def test_init_changes_nothing_when_the_files_exist(tmp_path):
    brain.init(tmp_path, "Work")
    before = (tmp_path / "REGISTRY.md").read_bytes()
    assert brain.init(tmp_path, "Home", example=False) == 1
    assert (tmp_path / "REGISTRY.md").read_bytes() == before


def test_a_value_with_a_line_break_stays_on_one_line(tmp_path):
    brain.init(tmp_path, "Work,\nHome", "2 hours\ncapacity: lots")
    context = (tmp_path / "CONTEXT.md").read_text(encoding="utf-8")
    assert "areas: Work, Home\n" in context
    assert context.count("\ncapacity:") == 1


def test_command_line_flags(tmp_path):
    assert brain.main(["init", "--root", str(tmp_path), "--areas", "Work, Home", "--capacity", "1 hour", "--no-example"]) == 0
    assert _registry(tmp_path).items == []
    assert "areas: Work, Home" in (tmp_path / "CONTEXT.md").read_text(encoding="utf-8")
