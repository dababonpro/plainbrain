"""Create the owner's Plainbrain folder from this plugin's own copy, and record where it is.

    python plugin_setup.py --to "C:/Users/you/Documents/my-plainbrain"

It copies the template files into a new or empty folder, then writes that folder's path to `.plainbrain` in the
owner's home folder so the plugin's inbox guard and MCP server can find it. It never overwrites: a folder that
already holds files is refused, unless it is already a Plainbrain folder and `--adopt` is given, in which case
nothing is copied and only the path is recorded. No network is used.
"""
import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from scripts.home import pointer_path  # noqa: E402

# What a Plainbrain folder is made of. Plugin-only files, tests and repository housekeeping stay behind.
COPY = ("AGENTS.md", "README.md", "CHANGELOG.md", "LICENSE", "LICENSE-docs", "requirements.txt", ".gitignore",
        "scripts", "templates", "knowledge", "views", ".claude", ".agents", ".codex", ".cursor", ".gemini")
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", "plugin_setup.py")


def is_plainbrain(folder: Path) -> bool:
    return (folder / "AGENTS.md").is_file() and (folder / "scripts" / "brain.py").is_file()


def set_up(target: Path, adopt: bool = False, source: Path = HERE) -> str:
    target = target.expanduser().resolve()
    if target == source or source in target.parents:
        raise ValueError("choose a folder outside the plugin's own install folder; that folder is replaced on update")
    if target.exists() and not target.is_dir():
        raise ValueError(f"{target} is a file, not a folder")
    holds_files = target.is_dir() and any(target.iterdir())
    if holds_files and not (adopt and is_plainbrain(target)):
        if is_plainbrain(target):
            raise ValueError(f"{target} is already a Plainbrain folder; pass --adopt to use it as it is")
        raise ValueError(f"{target} already holds files and nothing is ever overwritten; choose a new folder")
    copied = 0
    if not holds_files:
        target.mkdir(parents=True, exist_ok=True)
        for name in COPY:
            item = source / name
            if item.is_dir():
                shutil.copytree(item, target / name, ignore=SKIP)
                copied += 1
            elif item.is_file():
                shutil.copy2(item, target / name)
                copied += 1
    pointer_path().write_text(target.as_posix() + "\n", encoding="utf-8")
    what = f"copied {copied} template entries into" if copied else "kept the files already in"
    return f"Plainbrain folder: {target.as_posix()} ({what} it). Recorded in {pointer_path().as_posix()}."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--to", required=True, help="the folder to create, for example Documents/my-plainbrain")
    parser.add_argument("--adopt", action="store_true", help="use an existing Plainbrain folder without copying")
    args = parser.parse_args(argv)
    try:
        print(set_up(Path(args.to), args.adopt))
    except (OSError, ValueError) as exc:
        print(f"not set up: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
