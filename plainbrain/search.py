"""Ranked keyword search over the registry, the inbox, knowledge notes, and the archive.

Everything runs locally. No embeddings and no API calls: each file is cut into chunks
(a registry item, an inbox line, a note section), and chunks are ranked by how many of
the query's words they hold, weighted so that rare words count more.
"""
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

_WORD = re.compile(r"[a-z0-9]+(?:[._/-][a-z0-9]+)*")
_HEADING = re.compile(r"^#{1,3} ")
_ITEM = re.compile(r"^## ")


@dataclass
class Chunk:
    path: str
    title: str
    lines: list[tuple[int, str]]
    terms: dict[str, int] = field(default_factory=dict)

    @property
    def line(self) -> int:
        return self.lines[0][0]

    @property
    def text(self) -> str:
        return "\n".join(text for _number, text in self.lines)


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def terms(text: str) -> list[str]:
    found = []
    for word in _WORD.findall(text.casefold()):
        found.append(_stem(word))
        parts = re.split(r"[._/-]", word)
        if len(parts) > 1:
            found.extend(_stem(part) for part in parts if part)
    return found


def _count(chunk: Chunk) -> Chunk:
    for term in terms(chunk.title + "\n" + chunk.text):
        chunk.terms[term] = chunk.terms.get(term, 0) + 1
    return chunk


def _split(rel: str, text: str, heading: re.Pattern, default_title: str) -> list[Chunk]:
    """One chunk per heading. The heading line is the chunk's first line."""
    chunks: list[Chunk] = []
    current = Chunk(rel, default_title, [])
    for number, line in enumerate(text.splitlines(), 1):
        if heading.match(line):
            chunks.append(current)
            current = Chunk(rel, line.lstrip("#").strip(), [(number, line)])
        else:
            current.lines.append((number, line))
    chunks.append(current)
    return [chunk for chunk in chunks if chunk.lines and chunk.text.strip()]


def _inbox(rel: str, text: str) -> list[Chunk]:
    return [
        Chunk(rel, "inbox", [(number, line)])
        for number, line in enumerate(text.splitlines(), 1)
        if line.startswith(("- ", "* ")) and line[2:].strip()
    ]


def build_index(root: Path) -> list[Chunk]:
    root = Path(root)
    chunks: list[Chunk] = []
    registry = root / "REGISTRY.md"
    if registry.is_file():
        chunks += _split("REGISTRY.md", registry.read_text(encoding="utf-8"), _ITEM, "registry")
    inbox = root / "INBOX.md"
    if inbox.is_file():
        chunks += _inbox("INBOX.md", inbox.read_text(encoding="utf-8"))
    for folder in ("knowledge", "archive"):
        base = root / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            rel = path.relative_to(root).as_posix()
            if rel == "knowledge/LOG.md":
                continue
            chunks += _split(rel, path.read_text(encoding="utf-8", errors="replace"), _HEADING, path.stem)
    return [_count(chunk) for chunk in chunks]


def _snippet(chunk: Chunk, wanted: set[str], width: int = 240) -> tuple[int, str]:
    best_number, best_text, best_hits = chunk.line, chunk.title, 0
    for number, line in chunk.lines:
        hits = len(wanted & set(terms(line)))
        if hits > best_hits:
            best_number, best_text, best_hits = number, line.strip(), hits
    return best_number, best_text[:width]


def search(root: Path, query: str, limit: int = 10) -> list[dict]:
    """Best chunks first. A chunk must hold at least one query word."""
    wanted = list(dict.fromkeys(terms(query)))
    if not wanted:
        return []
    chunks = build_index(root)
    total = len(chunks) or 1
    df = {term: sum(1 for chunk in chunks if term in chunk.terms) for term in wanted}
    phrase = query.casefold().strip()
    scored = []
    for chunk in chunks:
        hit = [term for term in wanted if term in chunk.terms]
        if not hit:
            continue
        length = sum(chunk.terms.values()) or 1
        score = 0.0
        for term in hit:
            tf = chunk.terms[term]
            idf = math.log(1 + total / df[term])
            score += idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * length / 80))
        score *= 1 + len(hit) / len(wanted)
        if len(hit) == len(wanted):
            score *= 1.5
        if phrase and phrase in (chunk.title + "\n" + chunk.text).casefold():
            score *= 1.5
        scored.append((score, chunk))
    scored.sort(key=lambda pair: (-pair[0], pair[1].path, pair[1].line))
    results = []
    for score, chunk in scored[:limit]:
        line, text = _snippet(chunk, set(wanted))
        results.append({"path": chunk.path, "line": line, "title": chunk.title,
                        "snippet": text, "score": round(score, 2)})
    return results
