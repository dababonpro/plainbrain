"""Guided researcher: a read-only inventory of one selected knowledge folder that proposes changes for review.

It reads only the folder it is given, never edits it, and skips staff cards, templates and logs. Each finding is a
proposal in a fixed format: what was found, why it may help, the source and its date, related notes, the proposed
action, and a confidence. The person decides each one; nothing is applied.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from scripts.model import valid_date

SKIP_DIRS = {"team"}
SKIP_FILES = {"TEMPLATE.md", "LOG.md", "README.md", "INDEX.md"}
REQUIRED_FIELDS = ("type", "recorded", "source", "status")
STALE_DAYS = 30
WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")


def _frontmatter(text: str) -> dict[str, str]:
    """Key: value lines before the first ## heading, as the other scripts read them."""
    fields: dict[str, str] = {}
    for line in text.split("\n## ", 1)[0].splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if m:
            fields[m.group(1)] = m.group(2).strip()
    return fields


def _notes(source: Path) -> list[Path]:
    found = []
    for p in sorted(source.rglob("*.md")):
        rel = p.relative_to(source)
        if SKIP_DIRS & set(rel.parts[:-1]) or p.name in SKIP_FILES:
            continue
        found.append(p)
    return found


def _links(text: str) -> list[str]:
    """Wikilinks outside code, so a link written as an example in backticks is not checked."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)
    return [t.strip() for t in WIKILINK.findall(text)]


def _link_targets(vault: Path) -> set[str]:
    """Names a wikilink can resolve to in the vault: a note's name, or its path from the vault root. Only file names
    are listed here; no file outside the source is opened."""
    targets = set()
    for p in vault.rglob("*.md"):
        targets.add(p.stem)
        targets.add(p.relative_to(vault).with_suffix("").as_posix())
    return targets


def inventory(source: Path, today: str, vault: Path | None = None) -> tuple[list[dict], dict]:
    notes = _notes(source)
    names = _link_targets(vault or source)
    texts = {p: p.read_text(encoding="utf-8", errors="replace") for p in notes}
    inbound: dict[str, set[str]] = {p.stem: set() for p in notes}
    for p, text in texts.items():
        for target in _links(text):
            if target in inbound and target != p.stem:
                inbound[target].add(p.stem)

    proposals: list[dict] = []
    for p, text in texts.items():
        rel = p.relative_to(source).as_posix()
        fm = _frontmatter(text)
        recorded = fm.get("recorded", "")
        base = {"note": rel, "recorded": recorded or "not recorded", "source": fm.get("source", "") or "not recorded"}
        if fm.get("status") == "superseded":
            continue

        missing = [f for f in REQUIRED_FIELDS if not fm.get(f)]
        if missing:
            proposals.append({**base, "kind": "metadata", "confidence": "high",
                              "found": f"No {', '.join(missing)} in the frontmatter.",
                              "why": "A reusable entry needs its source, date and status so a reader can judge how far to trust it.",
                              "action": f"Add {', '.join(missing)}, from the note's history or from the owner."})

        broken = sorted({t for t in _links(text) if t not in names})
        if broken:
            proposals.append({**base, "kind": "link", "confidence": "high",
                              "found": "Links to notes that do not exist: " + ", ".join(f"[[{b}]]" for b in broken) + ".",
                              "why": "A broken link hides the context it was meant to point to.",
                              "action": "Point each link at the right note, or remove it if the note was never written."})

        if "## Limits" not in text and fm.get("type") in ("reference", "decision", "procedure", "lesson"):
            proposals.append({**base, "kind": "limits", "confidence": "medium",
                              "found": "No Limits section.",
                              "why": "Limits say what could make the note wrong, so it is not trusted past its date.",
                              "action": "Add a short Limits section: what could make this obsolete, and when to recheck."})

        if not inbound.get(p.stem) and not fm.get("related_items"):
            proposals.append({**base, "kind": "orphan", "confidence": "low",
                              "found": "No other note in this folder links here, and it names no registry item. Links "
                                       "from outside the folder, such as the registry, skills or instruction files, "
                                       "were not checked.",
                              "why": "A note nothing points to is only found by search, and is easy to forget.",
                              "action": "Link it from the note it belongs with, or name the registry item it serves."})

        review_on = fm.get("review_on", "")
        if (
            valid_date(recorded)
            and (date.fromisoformat(today) - date.fromisoformat(recorded)).days > STALE_DAYS
            and not (valid_date(review_on) and review_on >= today)
        ):
            age = (date.fromisoformat(today) - date.fromisoformat(recorded)).days
            proposals.append({**base, "kind": "review", "confidence": "low",
                              "found": f"Recorded {age} days ago, with no later review date.",
                              "why": "Facts drift; a dated review keeps the note honest.",
                              "action": "Reread it. Mark it current with a review date, update it, or mark it superseded."})

    order = {"metadata": 0, "link": 1, "limits": 2, "orphan": 3, "review": 4}
    proposals.sort(key=lambda x: (order[x["kind"]], x["note"]))
    for i, prop in enumerate(proposals, 1):
        prop["id"] = f"P-{i:02d}"
    stats = {"read": len(notes), "skipped_dirs": sorted(SKIP_DIRS), "skipped_files": sorted(SKIP_FILES)}
    return proposals, stats


def render(source_label: str, today: str, proposals: list[dict], stats: dict) -> str:
    lines = [
        f"# Research Proposals: {source_label}, {today}",
        "",
        f"Read-only inventory of `{source_label}`. {stats['read']} notes read. Skipped folders: "
        f"{', '.join(stats['skipped_dirs'])}. Skipped files: {', '.join(stats['skipped_files'])}. Nothing was edited, "
        "and no other folder or service was read.",
        "",
        "Each proposal is a suggestion. Decide each one: accept, edit or reject. Nothing is applied until you do.",
        "",
        f"{len(proposals)} proposals.",
        "",
    ]
    for p in proposals:
        lines += [
            f"## {p['id']} {p['kind'].capitalize()}: {p['note']}",
            "",
            f"- **Found:** {p['found']}",
            f"- **Why it may help:** {p['why']}",
            f"- **Source and date:** `{p['note']}`, recorded {p['recorded']}, from {p['source']}",
            f"- **Proposed action:** {p['action']}",
            f"- **Confidence:** {p['confidence']}",
            "- **Decision:**",
            "",
        ]
    return "\n".join(lines)


def write_research(root: Path, today: str, source: str) -> Path:
    if not valid_date(today):
        raise ValueError("today must be YYYY-MM-DD")
    src = (root / source).resolve()
    if not src.is_dir() or root.resolve() not in src.parents and src != root.resolve():
        raise ValueError("source must be a folder inside the root")
    proposals, stats = inventory(src, today, root.resolve())
    slug = source.strip("/\\").replace("/", "-").replace("\\", "-") or "root"
    out = root / "reviews" / "research" / f"{today}-{slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(source, today, proposals, stats), encoding="utf-8")
    return out
