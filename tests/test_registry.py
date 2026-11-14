"""Registry commands change one item, enforce the registry rules, and record each change."""
import pytest

from scripts import registry
from scripts.model import parse_registry
from scripts.registry import RegistryError

TODAY = "2026-11-11"

BASE = """# Registry

focus: dentist-call

## dentist-call
title: Book the dentist
area: Personal
kind: task
status: active
next: Call the clinic and book a cleaning.
blocked_on:
follow_up:
pointer:
opened: 2026-10-08
updated: 2026-10-08
outcome:
notes:

## tax-return
title: File the tax return
area: Personal
kind: project
status: active
next: Collect the receipts.
blocked_on:
follow_up:
pointer:
opened: 2026-10-01
updated: 2026-10-20
outcome:
notes: Accountant is Jane.
"""

WITH_OPTIONAL = BASE.replace("notes: Accountant is Jane.\n",
                             "notes: Accountant is Jane.\nweekly: yes\ndue: 2026-12-01\ndepends_on:\nrequested_on:\nknowledge:\n")


@pytest.fixture
def root(tmp_path):
    (tmp_path / "REGISTRY.md").write_text(BASE, encoding="utf-8", newline="\n")
    return tmp_path


def text(root):
    return (root / "REGISTRY.md").read_bytes().decode("utf-8")


def item(root, item_id):
    return next(i for i in parse_registry(text(root)).items if i.id == item_id)


def block(root, item_id):
    return registry.show(root, item_id)


def log(root):
    return (root / "reviews" / "registry" / "2026-11.md").read_text(encoding="utf-8")


def test_add_writes_a_usable_block_with_defaults(root):
    out = registry.add(root, "renew-passport", registry.parse_sets(["title=Renew the passport", "next=Find the form", "area=Personal"]), TODAY)
    added = item(root, "renew-passport")
    assert added.reason is None
    assert added.fields["status"] == "active" and added.fields["kind"] == "task"
    assert added.fields["opened"] == TODAY and added.fields["updated"] == TODAY
    assert out.startswith("## renew-passport")
    assert "weekly" not in added.fields
    assert text(root).endswith("notes:\n")


def test_add_keeps_the_optional_fields_when_the_registry_uses_them(root):
    (root / "REGISTRY.md").write_text(WITH_OPTIONAL, encoding="utf-8", newline="\n")
    registry.add(root, "renew-passport", {"title": "Renew the passport", "next": "Find the form"}, TODAY)
    assert set(registry.OPTIONAL_FIELDS) <= set(item(root, "renew-passport").fields)


@pytest.mark.parametrize("item_id, sets, message", [
    ("dentist-call", ["title=x", "next=y"], "already exists"),
    ("Bad Id", ["title=x", "next=y"], "lowercase"),
    ("new-one", ["next=y"], "needs title"),
    ("new-one", ["title=x"], "needs next"),
    ("new-one", ["title=x", "next=y", "area=Garden"], "area must be"),
    ("new-one", ["title=x", "next=y", "colour=red"], "unknown field"),
    ("new-one", ["title=x", "next=y", "status=waiting"], "waiting without blocked_on"),
    ("new-one", ["title=x", "next=y", "depends_on=no-such-item"], "not in the registry"),
])
def test_add_refuses_and_changes_nothing(root, item_id, sets, message):
    with pytest.raises(RegistryError, match=message):
        registry.add(root, item_id, registry.parse_sets(sets), TODAY)
    assert text(root) == BASE
    assert not (root / "reviews").exists()


def test_area_list_comes_from_context(root):
    (root / "CONTEXT.md").write_text("# Context\n\nareas: Work, Personal, Garden\n", encoding="utf-8")
    registry.add(root, "prune-roses", registry.parse_sets(["title=Prune", "next=Buy shears", "area=Garden"]), TODAY)
    assert item(root, "prune-roses").fields["area"] == "Garden"


def test_update_changes_only_the_named_item(root):
    before_other = block(root, "tax-return")
    registry.update(root, "dentist-call", registry.parse_sets(["next=Confirm the 3pm slot"]), TODAY, why="said so in chat")
    changed = item(root, "dentist-call")
    assert changed.fields["next"] == "Confirm the 3pm slot" and changed.fields["updated"] == TODAY
    assert block(root, "tax-return") == before_other
    assert 'update dentist-call: next: "Call the clinic and book a cleaning." -> "Confirm the 3pm slot" (why: said so in chat)' in log(root)


def test_update_to_waiting_needs_both_fields(root):
    with pytest.raises(RegistryError, match="waiting without follow_up"):
        registry.update(root, "dentist-call", {"status": "waiting", "blocked_on": "Clinic"}, TODAY)
    assert text(root) == BASE
    registry.update(root, "dentist-call", {"status": "waiting", "blocked_on": "Clinic", "follow_up": "2026-11-20"}, TODAY)
    assert item(root, "dentist-call").reason is None


@pytest.mark.parametrize("sets, message", [
    ({"status": "someday"}, "someday without follow_up"),
    ({"follow_up": "next week"}, "bad follow_up"),
    ({"due": "2026-13-40"}, "bad due"),
    ({"status": "paused"}, "status must be"),
    ({"weekly": "maybe"}, "weekly is yes or empty"),
    ({"kind": "epic"}, "bad kind"),
    ({"next": "Call the clinic and book a cleaning."}, "already has that value"),
    ({}, "nothing to change"),
])
def test_update_refuses_and_changes_nothing(root, sets, message):
    with pytest.raises(RegistryError, match=message):
        registry.update(root, "dentist-call", sets, TODAY)
    assert text(root) == BASE


def test_update_adds_a_field_the_block_does_not_have(root):
    registry.update(root, "dentist-call", {"due": "2026-12-01"}, TODAY)
    assert item(root, "dentist-call").fields["due"] == "2026-12-01"
    assert block(root, "tax-return").startswith("## tax-return")


def test_a_value_is_one_line():
    with pytest.raises(RegistryError, match="one line"):
        registry.parse_sets(["notes=first\n## injected-item"])


def test_done_sets_the_status_and_takes_an_outcome(root):
    registry.done(root, "dentist-call", {"outcome": "nothing to keep"}, TODAY)
    fields = item(root, "dentist-call").fields
    assert fields["status"] == "done" and fields["outcome"] == "nothing to keep"
    assert "done dentist-call" in log(root)


def test_focus_sets_and_clears(root):
    registry.focus(root, "tax-return", TODAY)
    assert parse_registry(text(root)).focus == "tax-return"
    registry.focus(root, None, TODAY)
    assert parse_registry(text(root)).focus == ""
    with pytest.raises(RegistryError, match="no item called"):
        registry.focus(root, "nope", TODAY)


def test_focus_refuses_a_done_item(root):
    registry.done(root, "tax-return", {}, TODAY)
    with pytest.raises(RegistryError, match="is done"):
        registry.focus(root, "tax-return", TODAY)


def test_archive_needs_done_a_record_and_no_focus(root):
    with pytest.raises(RegistryError, match="is not done"):
        registry.archive(root, "tax-return", TODAY)
    registry.done(root, "tax-return", {}, TODAY)
    with pytest.raises(RegistryError, match="no record to keep"):
        registry.archive(root, "tax-return", TODAY)
    registry.done(root, "dentist-call", {"outcome": "nothing to keep"}, TODAY)
    with pytest.raises(RegistryError, match="is the focus"):
        registry.archive(root, "dentist-call", TODAY)
    assert not (root / "archive").exists()


def test_archive_moves_the_block_and_keeps_the_rest(root):
    registry.focus(root, None, TODAY)
    registry.done(root, "dentist-call", {"outcome": "nothing to keep"}, TODAY)
    kept = block(root, "tax-return")
    moved = block(root, "dentist-call")
    registry.archive(root, "dentist-call", TODAY)
    assert [i.id for i in parse_registry(text(root)).items] == ["tax-return"]
    assert block(root, "tax-return") == kept
    archived = (root / "archive" / "2026-11.md").read_text(encoding="utf-8")
    assert archived == f"archived: {TODAY}\n{moved}\n"
    assert "\n\n\n" not in text(root)


def test_archive_accepts_a_knowledge_note_or_a_project_card(root):
    registry.focus(root, None, TODAY)
    (root / "knowledge" / "projects").mkdir(parents=True)
    (root / "knowledge" / "projects" / "home.md").write_text("# Home\n\n## Now\n\n- tax-return: filed.\n\n## Later\n", encoding="utf-8")
    registry.done(root, "tax-return", {}, TODAY)
    registry.archive(root, "tax-return", TODAY)
    assert "tax-return" not in text(root)


def test_archive_of_an_open_item_needs_the_second_confirmation(root):
    registry.archive(root, "tax-return", TODAY, not_done=True)
    assert [i.id for i in parse_registry(text(root)).items] == ["dentist-call"]


def test_keeps_windows_line_endings(root):
    (root / "REGISTRY.md").write_bytes(BASE.replace("\n", "\r\n").encode("utf-8"))
    registry.update(root, "dentist-call", {"next": "Confirm the slot"}, TODAY)
    raw = (root / "REGISTRY.md").read_bytes().decode("utf-8")
    assert "\r\n" in raw and "\n" not in raw.replace("\r\n", "")


def test_an_unreadable_registry_is_left_alone(root):
    broken = BASE.replace("## tax-return", "## Tax Return")
    (root / "REGISTRY.md").write_text(broken, encoding="utf-8", newline="\n")
    with pytest.raises(RegistryError, match="cannot be read"):
        registry.update(root, "dentist-call", {"next": "x"}, TODAY)
    assert text(root) == broken


def _run(root, *words):
    import argparse
    parser = argparse.ArgumentParser()
    registry.add_parser(parser.add_subparsers(dest="cmd", required=True))
    return registry.run(parser.parse_args(["registry", words[0], "--root", str(root), *words[1:]]), TODAY)


def test_command_line(root):
    out = _run(root, "update", "--id", "dentist-call", "--set", "next=Confirm the slot", "--why", "accepted")
    assert "next: Confirm the slot" in out
    with pytest.raises(RegistryError, match="no item called nope"):
        _run(root, "update", "--id", "nope", "--set", "next=x")
    with pytest.raises(RegistryError, match="pass --id to set the focus"):
        _run(root, "focus")
    assert _run(root, "focus", "--clear") == "focus:"
    assert _run(root, "show", "--id", "tax-return").startswith("## tax-return")


def test_moving_a_waiting_item_to_active_or_done_clears_its_waiting_fields(root):
    registry.update(root, "tax-return", {"status": "waiting", "blocked_on": "Jane", "follow_up": "2026-11-20"}, TODAY)
    registry.update(root, "tax-return", {"status": "active"}, TODAY)
    fields = item(root, "tax-return").fields
    assert fields["blocked_on"] == "" and fields["follow_up"] == ""
    assert 'blocked_on: "Jane" -> ""' in log(root)
    registry.update(root, "dentist-call", {"status": "waiting", "blocked_on": "Clinic", "follow_up": "2026-11-20"}, TODAY)
    registry.done(root, "dentist-call", {"outcome": "nothing to keep"}, TODAY)
    fields = item(root, "dentist-call").fields
    assert fields["status"] == "done" and fields["blocked_on"] == "" and fields["follow_up"] == ""


def test_active_with_a_named_blocker_keeps_it(root):
    registry.update(root, "tax-return", {"status": "waiting", "blocked_on": "Jane", "follow_up": "2026-11-20"}, TODAY)
    registry.update(root, "tax-return", {"status": "active", "blocked_on": "Receipts from Jane"}, TODAY)
    fields = item(root, "tax-return").fields
    assert fields["blocked_on"] == "Receipts from Jane" and fields["follow_up"] == ""


def test_a_failed_registry_save_takes_the_archive_copy_back_out(root, monkeypatch):
    registry.focus(root, None, TODAY)
    registry.done(root, "dentist-call", {"outcome": "nothing to keep"}, TODAY)
    before = text(root)

    def locked(*_args):
        raise PermissionError("REGISTRY.md is open in another program")

    monkeypatch.setattr(registry, "_commit", locked)
    with pytest.raises(PermissionError):
        registry.archive(root, "dentist-call", TODAY)
    assert text(root) == before
    assert not (root / "archive" / "2026-11.md").exists()
