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
    assert [p["kind"] for p in inventory(src, "2026-11-30")[0]] == []
    on_the_day = inventory(src, "2026-12-01")[0]
    assert [(p["note"], p["kind"]) for p in on_the_day] == [("a.md", "review")]
    assert "its review date 2026-12-01 has arrived" in on_the_day[0]["found"]
    assert "move `review_on`" in on_the_day[0]["action"]
    later = inventory(src, "2026-12-02")[0]
    assert [p["kind"] for p in later] == ["review", "review"]
    assert "with no later review date" in later[1]["found"]


def test_unreadable_review_or_decide_date_is_a_metadata_proposal(tmp_path):
    src = tmp_path / "knowledge"
    _write(src, "a.md", NOTE.replace("recorded: 2026-11-01", "recorded: 2026-11-01\nreview_on: 9 Nov 2026"))
    _write(src, "b.md", NOTE.replace("[[b]]", "[[a]]").replace(
        "recorded: 2026-11-01", 'recorded: 2026-11-01\nreview_on: "2026-12-01"\ndecide_by: 2026-11-31'))
    found = [(p["note"], p["kind"], p["found"]) for p in inventory(src, "2026-11-08")[0]]
    assert found == [
        ("a.md", "metadata", "Not a YYYY-MM-DD date: review_on: 9 Nov 2026."),
        ("b.md", "metadata", "Not a YYYY-MM-DD date: decide_by: 2026-11-31."),
    ]


FENCED = NOTE + '\n<untrusted-source src="{src}" fetched="{fetched}">\nThe pump runs   at 40 psi.\n{close}\n'


def _quote_findings(tmp_path, **parts):
    src = tmp_path / "knowledge"
    values = {"src": "raw/page.txt", "fetched": "2026-11-07", "close": "</untrusted-source>", **parts}
    _write(src, "a.md", FENCED.format(**values))
    _write(src, "b.md", NOTE.replace("[[b]]", "[[a]]"))
    _write(src / "raw", "page.txt", "Intro.\nThe pump runs at\n40 psi. More.")
    return [p["found"] for p in inventory(src, "2026-11-08")[0] if p["kind"] == "quote"]


def test_fenced_text_that_matches_its_saved_source_raises_nothing(tmp_path):
    assert _quote_findings(tmp_path) == []


def test_fenced_text_from_a_link_is_not_compared(tmp_path):
    assert _quote_findings(tmp_path, src="https://example.com/page") == []


def test_fence_without_source_date_or_close_is_reported(tmp_path):
    found = _quote_findings(tmp_path, src="", fetched="last week", close="")
    assert len(found) == 1
    assert "no src" in found[0] and "no fetched date" in found[0] and "not closed" in found[0]


def test_fenced_text_missing_from_its_saved_source_is_reported(tmp_path):
    src = tmp_path / "knowledge"
    found = _quote_findings(tmp_path)
    assert found == []
    (src / "raw" / "page.txt").write_text("The pump runs at 60 psi.", encoding="utf-8")
    found = [p["found"] for p in inventory(src, "2026-11-08")[0] if p["kind"] == "quote"]
    assert "is not in raw/page.txt" in found[0]


def test_fence_in_code_and_source_outside_the_folder_are_left_alone(tmp_path):
    src = tmp_path / "knowledge"
    _write(tmp_path, "outside.txt", "nothing alike")
    _write(src, "a.md", NOTE + '\n`<untrusted-source>` is the fence.\n\n```\n<untrusted-source>\nexample\n```\n'
           '\n<!-- <untrusted-source src="link or file" fetched="YYYY-MM-DD"> and </untrusted-source> -->\n'
           '\n<untrusted-source src="../outside.txt" fetched="2026-11-07">\nThe pump.\n</untrusted-source>\n')
    _write(src, "b.md", NOTE.replace("[[b]]", "[[a]]"))
    assert [p for p in inventory(src, "2026-11-08")[0] if p["kind"] == "quote"] == []


def test_unclosed_fence_before_second_fence_and_empty_fence_are_reported(tmp_path):
    src = tmp_path / "knowledge"
    _write(src, "a.md", NOTE
           + '\n<untrusted-source src="https://example.com/1" fetched="2026-11-07">\nFirst quote.\n'
           + '\n<untrusted-source src="raw/page.txt" fetched="2026-11-07">\n   \n</untrusted-source>\n')
    _write(src, "b.md", NOTE.replace("[[b]]", "[[a]]"))
    _write(src / "raw", "page.txt", "Anything.")
    found = [p["found"] for p in inventory(src, "2026-11-08")[0] if p["kind"] == "quote"]
    assert found == ["Outside text that cannot be traced: fence 1 is not closed; fence 2 is empty."]


def test_stale_note_is_one_high_confidence_review(tmp_path):
    src = tmp_path / "knowledge"
    _write(src, "a.md", NOTE.replace("status: current", "status: stale").replace("2026-11-01", "2026-09-01"))
    _write(src, "b.md", NOTE.replace("[[b]]", "[[a]]"))
    reviews = [p for p in inventory(src, "2026-11-08")[0] if p["kind"] == "review"]
    assert len(reviews) == 1
    assert reviews[0]["confidence"] == "high" and "Marked stale" in reviews[0]["found"]
