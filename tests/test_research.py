from pathlib import Path

from scripts.research import inventory, write_research

NOTE = """---
type: reference
recorded: 2026-11-01
source: Jane
related_items:
related_notes:
  - "[[b]]"
status: current
---

# A

## Limits
None known.
"""


def _write(folder: Path, name: str, text: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")


def test_clean_notes_raise_no_structural_proposals(tmp_path):
    src = tmp_path / "knowledge"
    _write(src, "a.md", NOTE)
    _write(src, "b.md", NOTE.replace("[[b]]", "[[a]]"))
    proposals, stats = inventory(src, "2026-11-08")
    assert stats["read"] == 2
    assert proposals == []


def test_finds_missing_fields_broken_links_missing_limits_orphans_and_age(tmp_path):
    src = tmp_path / "knowledge"
    _write(src, "a.md", NOTE.replace("source: Jane", "source:").replace("[[b]]", "[[gone]]")
           .replace("## Limits\nNone known.\n", "").replace("recorded: 2026-11-01", "recorded: 2026-09-01"))
    kinds = {p["kind"] for p in inventory(src, "2026-11-08")[0]}
    assert kinds == {"metadata", "link", "limits", "orphan", "review"}


def test_skips_staff_cards_templates_and_superseded_notes(tmp_path):
    src = tmp_path / "knowledge"
    _write(src / "team", "person.md", "no frontmatter at all")
    _write(src, "TEMPLATE.md", "no frontmatter")
    _write(src, "old.md", NOTE.replace("status: current", "status: superseded").replace("source: Jane", "source:"))
    proposals, stats = inventory(src, "2026-11-08")
    assert stats["read"] == 1
    assert proposals == []


def test_write_research_reads_only_and_refuses_paths_outside_root(tmp_path):
    src = tmp_path / "knowledge"
    _write(src, "a.md", NOTE.replace("[[b]]", "[[gone]]"))
    before = (src / "a.md").read_text(encoding="utf-8")
    out = write_research(tmp_path, "2026-11-08", "knowledge")
    assert out == tmp_path / "reviews" / "research" / "2026-11-08-knowledge.md"
    assert "P-01" in out.read_text(encoding="utf-8")
    assert (src / "a.md").read_text(encoding="utf-8") == before
    try:
        write_research(tmp_path / "knowledge", "2026-11-08", "..")
    except ValueError:
        pass
    else:
        raise AssertionError("a source outside the root must be refused")


def test_links_in_code_and_vault_root_links_are_not_broken(tmp_path):
    src = tmp_path / "knowledge"
    _write(tmp_path, "AGENTS.md", "rules")
    _write(src, "README.md", "readme")
    links = '  - "[[AGENTS]]"\n  - "[[knowledge/README]]"'
    _write(src, "a.md", NOTE.replace('  - "[[b]]"', links) + "\nUse `[[wikilinks]]` here.\n")
    _write(src, "b.md", NOTE.replace("[[b]]", "[[a]]"))
    kinds = [p["kind"] for p in inventory(src, "2026-11-08", tmp_path)[0]]
    assert "link" not in kinds


def test_future_review_on_suppresses_stale_age_proposal_until_due(tmp_path):
    src = tmp_path / "knowledge"
    old_with_review = NOTE.replace("recorded: 2026-11-01", "recorded: 2026-09-01\nreview_on: 2026-12-01")
    _write(src, "a.md", old_with_review)
    _write(src, "b.md", NOTE.replace("[[b]]", "[[a]]"))
    assert [p["kind"] for p in inventory(src, "2026-11-08")[0]] == []
    assert [p["kind"] for p in inventory(src, "2026-12-02")[0]] == ["review", "review"]
