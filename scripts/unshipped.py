"""Read-only scan for local work that never reached a remote; never fetches, pushes, or changes the repos."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from scripts.catalog import _git, _subdirs
from scripts.model import DATE_RE

SEP = "\x1f"
SUMMARY = "## Summary"
OLDER = "## Older local work"
RECENT_DAYS = 30
WORKERS = 8  # git calls wait on disk, so threads overlap them; 113 repos went from about 110 s to 46 s


def _count(text: str) -> int:
    return int(text) if text.isdigit() else 0


def _repos(folder: Path) -> list[tuple[str, Path]]:
    """Git repos directly under folder; a folder with no .git that holds repos is listed as parent/child."""
    found = []
    if not folder.is_dir():
        return found
    for path in _subdirs(folder):
        if (path / ".git").exists():
            found.append((path.name, path))
        else:
            found += [(f"{path.name}/{c.name}", c) for c in _subdirs(path) if (c / ".git").exists()]
    return found


def _branches(repo: Path) -> list[dict]:
    """Local branches with commits that no remote-tracking ref holds."""
    fmt = SEP.join(("%(refname:short)", "%(upstream:short)", "%(upstream:track)"))
    rows = []
    for line in _git(repo, "for-each-ref", f"--format={fmt}", "refs/heads").splitlines():
        parts = (line.split(SEP) + ["", ""])[:3]
        branch, upstream, track = (part.strip() for part in parts)
        if not branch:
            continue
        gone = "gone" in track
        if upstream and not gone:
            span, kind = [f"{upstream}..{branch}"], "ahead"
        else:
            span, kind = [branch, "--not", "--remotes"], "no upstream" if not upstream else "upstream gone"
        ahead = _count(_git(repo, "rev-list", "--count", *span))
        if ahead == 0:
            continue
        oldest = _git(repo, "log", "--format=%as", "--reverse", *span).splitlines()
        rows.append({"branch": branch, "commits": ahead, "kind": kind, "since": oldest[0] if oldest else ""})
    return rows


def _dirty(path: Path) -> tuple[int, int]:
    """(changed tracked files, untracked files) in one working tree."""
    changed = untracked = 0
    for line in _git(path, "status", "--porcelain").splitlines():
        if line.startswith("??"):
            untracked += 1
        elif line.strip():
            changed += 1
    return changed, untracked


def _worktrees(repo: Path) -> list[Path]:
    paths = [Path(line[9:]) for line in _git(repo, "worktree", "list", "--porcelain").splitlines()
             if line.startswith("worktree ")]
    return paths or [repo]


def scan_repo(name: str, repo: Path) -> dict:
    trees = []
    for tree in _worktrees(repo):
        if not tree.is_dir():
            continue
        changed, untracked = _dirty(tree)
        if changed or untracked:
            same = tree.resolve() == repo.resolve()
            trees.append({"path": "" if same else str(tree), "changed": changed, "untracked": untracked})
    remote = bool(_git(repo, "remote"))
    branches = _branches(repo)
    unpushed = _count(_git(repo, "rev-list", "--count", "--branches", "--not", "--remotes")) if branches else 0
    last = _git(repo, "log", "-1", "--all", "--format=%as")
    return {"name": name, "remote": remote, "branches": branches, "unpushed": unpushed, "trees": trees,
            "last": last,
            "stashes": len(_git(repo, "stash", "list").splitlines())}


def _has_work(row: dict) -> bool:
    return bool(row["branches"] or row["trees"] or row["stashes"])


def summary_line(row: dict) -> str:
    parts = []
    commits = row["unpushed"]
    if commits:
        since = min((b["since"] for b in row["branches"] if b["since"]), default="")
        word = "commit" if commits == 1 else "commits"
        where = "no remote" if not row["remote"] else f"{len(row['branches'])} branch" + (
            "" if len(row["branches"]) == 1 else "es")
        parts.append(f"{commits} unpushed {word} on {where}" + (f" since {since}" if since else ""))
    elif row["branches"]:
        # Ahead of its own upstream, but every commit is already on another remote branch: not unpushed, still unmerged.
        count = len(row["branches"])
        parts.append(f"{count} branch{'' if count == 1 else 'es'} ahead of upstream, commits already on a remote")
    changed = sum(t["changed"] for t in row["trees"])
    untracked = sum(t["untracked"] for t in row["trees"])
    if changed:
        parts.append(f"{changed} uncommitted file" + ("" if changed == 1 else "s"))
    if untracked:
        parts.append(f"{untracked} untracked")
    if row["stashes"]:
        parts.append(f"{row['stashes']} stash" + ("" if row["stashes"] == 1 else "es"))
    return f"- {row['area']}/{row['name']}: " + ", ".join(parts)


def _days(day: str, today: str) -> int:
    try:
        return (date.fromisoformat(today) - date.fromisoformat(day)).days
    except ValueError:
        return 10 ** 6


def is_recent(row: dict, today: str) -> bool:
    """Work worth a nudge: a commit on any branch, or an unpushed one, within RECENT_DAYS."""
    since = min((b["since"] for b in row["branches"] if b["since"]), default="")
    return _days(row["last"], today) <= RECENT_DAYS or (since != "" and _days(since, today) <= RECENT_DAYS)


def render(today: str, rows: list[dict], scanned: int) -> str:
    work = [r for r in rows if _has_work(r)]
    recent = [r for r in work if is_recent(r, today)]
    older = [r for r in work if not is_recent(r, today)]
    lines = [f"# Unshipped {today}", "",
             f"{len(recent)} active repos hold work that is not on a remote; {len(older)} quieter repos hold "
             f"older local work. {scanned} repos scanned. Remote refs are as of each repo's last fetch.",
             "", SUMMARY]
    lines += [summary_line(r) for r in recent] or ["- Nothing unshipped."]
    lines += ["", OLDER, f"No commit in the last {RECENT_DAYS} days. Clean up when convenient."]
    lines += [summary_line(r) + (f" (last commit {r['last']})" if r["last"] else "") for r in older] or ["- None."]
    lines.append("")
    for row in recent:
        lines += [f"## {row['area']}/{row['name']}", ""]
        for b in row["branches"]:
            since = f", oldest {b['since']}" if b["since"] else ""
            lines.append(f"- branch {b['branch']}: {b['commits']} commit(s), {b['kind']}{since}")
        for t in row["trees"]:
            where = f" ({t['path']})" if t["path"] else ""
            lines.append(f"- working tree{where}: {t['changed']} changed, {t['untracked']} untracked")
        if row["stashes"]:
            lines.append(f"- {row['stashes']} stash entr" + ("y" if row["stashes"] == 1 else "ies"))
        lines.append("")
    lines += ["## Scanned", ""]
    lines += [f"- {row['area']}/{row['name']}" for row in rows]
    lines.append("")
    return "\n".join(lines)


def write_unshipped(root: Path, sources: list[tuple[str, Path]], today: str) -> int:
    jobs = [(area, name, repo) for area, folder in sources for name, repo in _repos(folder)]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        rows = list(pool.map(lambda job: {**scan_repo(job[1], job[2]), "area": job[0]}, jobs))  # map keeps job order
    scanned = len(jobs)
    path = Path(root) / "reviews" / "unshipped" / f"{today}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(today, rows, scanned))
    print(path)
    return 0


def latest_summary(root: Path, today: str) -> tuple[str, list[str]] | None:
    """Newest unshipped report on or before today: (its date, its summary lines)."""
    folder = Path(root) / "reviews" / "unshipped"
    if not folder.is_dir():
        return None
    stems = [p.stem for p in folder.glob("*.md") if DATE_RE.fullmatch(p.stem) and p.stem <= today]
    if not stems:
        return None
    stem = max(stems)
    text = (folder / f"{stem}.md").read_text(encoding="utf-8")
    body = text.split(f"\n{SUMMARY}\n", 1)[-1] if f"\n{SUMMARY}\n" in text else ""
    lines = []
    for line in body.splitlines():
        if not line.startswith("- "):
            break
        lines.append(line)
    return stem, [l for l in lines if l != "- Nothing unshipped."]

