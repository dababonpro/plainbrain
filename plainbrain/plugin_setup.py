"""Create the owner's Plainbrain folder from the bundled or checkout template, and record where it is.

    plainbrain setup --to "C:/Users/you/Documents/my-plainbrain"

It copies the data-only template files into a new or empty folder, then writes that folder's path to `.plainbrain` in
the owner's home folder so the inbox guard and MCP server can find it. It never overwrites: a folder that already holds
files is refused, unless it is already a Plainbrain folder and `--adopt` is given, in which case nothing is copied and
only the path is recorded. No network is used.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from plainbrain import global_hooks  # noqa: E402
from plainbrain.assets import assets_dir  # noqa: E402
from plainbrain.home import MARKER_NAME, pointer_path, recorded_folder  # noqa: E402

DATA_COPY = ("AGENTS.md", "CLAUDE.md", "LICENSE", "LICENSE-docs", "templates", "knowledge", "views")
SKILL_DIRS = (".claude/skills", ".agents/skills")
DATA_GITIGNORE = ".obsidian/\n.env\n*.lock\nboard/\n"
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", "plugin_setup.py")


def is_plainbrain(folder: Path) -> bool:
    if not (folder / "AGENTS.md").is_file():
        return False
    return (
        (folder / MARKER_NAME).is_file()
        or (folder / "scripts" / "brain.py").is_file()
        or ((folder / "REGISTRY.md").is_file() and (folder / "INBOX.md").is_file())
    )


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def _write_project_hooks(target: Path, guard_cmd: str) -> None:
    _write_json(target / ".claude" / "settings.json", {
        "hooks": {
            "PreToolUse": [{
                "matcher": "Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell",
                "hooks": [{"type": "command", "command": guard_cmd, "timeout": 5}],
            }]
        }
    })
    _write_json(target / ".cursor" / "hooks.json", {
        "version": 1,
        "hooks": {
            "preToolUse": [{
                "command": guard_cmd,
                "matcher": "Write|StrReplace|Delete|EditNotebook",
                "timeout": 5,
            }],
            "beforeShellExecution": [{
                "command": guard_cmd,
                "matcher": "INBOX\\.md|REGISTRY\\.md",
                "timeout": 5,
            }],
        },
    })
    _write_json(target / ".codex" / "hooks.json", {
        "description": "Plainbrain: keep the inbox append-only. Trust this hook once in Settings > Hooks, or /hooks in the terminal.",
        "hooks": {
            "PreToolUse": [{
                "matcher": "^(Bash|apply_patch|Edit|Write)$",
                "hooks": [{
                    "type": "command",
                    "command": f"{guard_cmd} --codex",
                    "statusMessage": "Checking the inbox rule",
                    "timeout": 10,
                }],
            }]
        },
    })
    _write_json(target / ".agents" / "hooks.json", {
        "plainbrain-inbox-guard": {
            "PreToolUse": [{
                "matcher": "*",
                "hooks": [{"type": "command", "command": guard_cmd, "timeout": 10}],
            }]
        }
    })


def set_up(
    target: Path,
    adopt: bool = False,
    source: Path | None = None,
    mode: str | None = None,
    temp_root: Path | None = None,
) -> str:
    source = (source or assets_dir()).resolve()
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

    resolved_mode = mode or "plugin"
    previous = recorded_folder()
    copied = 0
    hook_warning = None

    if not holds_files:
        target.mkdir(parents=True, exist_ok=True)
        for name in DATA_COPY:
            item = source / name
            if item.is_dir():
                shutil.copytree(item, target / name, ignore=SKIP)
                copied += 1
            elif item.is_file():
                shutil.copy2(item, target / name)
                copied += 1
        for rel in SKILL_DIRS:
            item = source / rel
            if item.is_dir():
                (target / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(item, target / rel, ignore=SKIP)
                copied += 1
        gemini_src = source / ".gemini" / "settings.json"
        if gemini_src.is_file():
            (target / ".gemini").mkdir(parents=True, exist_ok=True)
            shutil.copy2(gemini_src, target / ".gemini" / "settings.json")
            copied += 1
        (target / MARKER_NAME).write_text("", encoding="utf-8", newline="\n")
        (target / ".gitignore").write_text(DATA_GITIGNORE, encoding="utf-8", newline="\n")
        if resolved_mode == "package":
            try:
                guard_cmd = global_hooks.resolve_hook_command("guard", target, temp_root=temp_root)
            except ValueError as exc:
                hook_warning = str(exc)
            else:
                _write_project_hooks(target, guard_cmd)

    pointer_path().write_text(target.as_posix() + "\n", encoding="utf-8")
    what = f"copied {copied} template entries into" if copied else "kept the files already in"
    parts = [f"Plainbrain folder: {target.as_posix()} ({what} it). Recorded in {pointer_path().as_posix()}."]
    if previous is not None and previous.resolve() != target.resolve():
        parts.append(f"Note: active folder changed from {previous.resolve().as_posix()} to {target.as_posix()}.")
    if hook_warning:
        parts.append(f"Warning: project hooks were skipped ({hook_warning})")
    return " ".join(parts)


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
