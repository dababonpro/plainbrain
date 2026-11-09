"""Command line for Plainbrain.

    python scripts/brain.py init --root .
    python scripts/brain.py capture --root . --repo my-website --text "one sentence"
    python scripts/brain.py brief --root .

Every command reads and writes plain Markdown under --root. Nothing leaves the machine.
"""
import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.board import write_board
from scripts.brief import write_brief
from scripts.capture import CaptureError, capture_line, drop_lines, repo_view
from scripts.ingest import log_pairs, write_ingest
from scripts.model import valid_date
from scripts.research import write_research
from scripts.review import search_knowledge, write_review
from scripts.rollup import write_rollup

STARTING_FILES = {
    "REGISTRY.md": """# Registry

focus:

## set-up-second-brain
title: Set up my second brain
area: Personal
kind: project
status: active
next: Capture three things on your mind with the capture command, then run the brief.
blocked_on:
follow_up:
pointer:
opened: {today}
updated: {today}
outcome:
notes: Example item, linked from knowledge/set-up-my-second-brain.md. Replace it with your own.
""",
    "INBOX.md": """# Inbox

Raw capture goes here. Do not organise while capturing. Use the capture command, so lines land under Brain Dump.

## Brain Dump
""",
    "CONTEXT.md": """# Context

Stable context the brief and the weekly review read. Keep it short and current.

## Operating preferences

- Prefer clear next actions over long task lists.
- Keep the system simple until complexity proves necessary.

## Roles and areas

areas: {areas}
capacity: Unknown
""",
}


def init(root: Path, areas: str) -> int:
    today = date.today().isoformat()
    existing = [name for name in STARTING_FILES if (root / name).exists()]
    if existing:
        print("already set up, nothing changed: " + ", ".join(existing), file=sys.stderr)
        return 1
    for name, text in STARTING_FILES.items():
        (root / name).write_text(text.format(today=today, areas=areas), encoding="utf-8", newline="\n")
        print(f"wrote {name}")
    (root / "knowledge").mkdir(exist_ok=True)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="brain.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="create the registry, inbox and context files")
    p.add_argument("--root", required=True)
    p.add_argument("--areas", default="Work, Personal")
    for name in ("brief", "board", "review", "inbox", "ingest"):
        p = sub.add_parser(name)
        p.add_argument("--root", required=True)
        p.add_argument("--today")
    p = sub.add_parser("capture")
    p.add_argument("--root", required=True)
    p.add_argument("--repo", required=True, help="the folder or project the line comes from")
    p.add_argument("--text", required=True)
    p.add_argument("--today")
    p = sub.add_parser("for-repo")
    p.add_argument("--root", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--today")
    p = sub.add_parser("inbox-drop")
    p.add_argument("--root", required=True)
    p.add_argument("--line", action="append")
    p.add_argument("--contains", action="append")
    p = sub.add_parser("ingest-log")
    p.add_argument("--root", required=True)
    p.add_argument("--today")
    p.add_argument("--line")
    p.add_argument("--contains")
    p.add_argument("--page", action="append", required=True)
    p.add_argument("--outcome", required=True, choices=("updated", "unchanged", "rejected"))
    p = sub.add_parser("search")
    p.add_argument("--root", required=True)
    p.add_argument("--query", required=True)
    p = sub.add_parser("research")
    p.add_argument("--root", required=True)
    p.add_argument("--source", required=True, help="one folder under the root, read only")
    p.add_argument("--today")
    args = parser.parse_args(argv)

    root = Path(args.root)
    if args.cmd == "init":
        return init(root, args.areas)
    if args.cmd == "search":
        return search_knowledge(root, args.query)
    today = getattr(args, "today", None) or date.today().isoformat()
    if not valid_date(today):
        parser.error("--today must be a real calendar date in YYYY-MM-DD format")
    try:
        if args.cmd == "capture":
            print(capture_line(root, args.repo, args.text, today))
            return 0
        if args.cmd == "for-repo":
            print(repo_view(root, args.repo, today))
            return 0
        if args.cmd == "inbox-drop":
            for body in drop_lines(root, args.line, args.contains):
                print(f"dropped: {body}")
            return 0
        if args.cmd == "ingest-log":
            for message in log_pairs(root, today, args.page, args.outcome, args.line, args.contains):
                print(message)
            return 0
    except CaptureError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.cmd == "research":
        try:
            print(f"wrote {write_research(root, today, args.source)}")
        except ValueError as exc:
            parser.error(str(exc))
        return 0
    return {"brief": write_brief, "board": write_board, "review": write_review, "inbox": write_rollup,
            "ingest": write_ingest}[args.cmd](root, today)


if __name__ == "__main__":
    sys.exit(main())
