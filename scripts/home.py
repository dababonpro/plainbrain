"""Where the owner's Plainbrain folder is, for code that may run from somewhere else.

In the owner's own folder the scripts sit beside the data, so the folder is the checkout. Installed as a Claude
plugin, the scripts sit in the plugin's install folder, which is replaced on every update and must never hold the
owner's data. Setup records the owner's folder in one small file in their home folder, and this module reads it.
"""
import os
from pathlib import Path

POINTER_NAME = ".plainbrain"
NOT_SET_UP = ("Plainbrain is installed as a plugin and has no folder yet. Ask the owner to say "
              '"Set up Plainbrain", which creates their folder and records where it is.')


def pointer_path() -> Path:
    return Path.home() / POINTER_NAME


def recorded_folder() -> Path | None:
    """The folder setup recorded, or None when there is none or it no longer exists."""
    try:
        named = pointer_path().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    folder = Path(named).expanduser() if named else None
    return folder if folder and folder.is_dir() else None


def as_plugin() -> bool:
    return bool(os.environ.get("CLAUDE_PLUGIN_ROOT"))


def data_root(checkout: Path) -> Path | None:
    """The folder holding the owner's files: BRAIN_ROOT when set, the recorded folder when running as a plugin,
    else `checkout`. None means a plugin install that has not been set up, so there is nowhere safe to write."""
    named = os.environ.get("BRAIN_ROOT", "").strip()
    if named:
        return Path(named).expanduser()
    if as_plugin():
        return recorded_folder()
    return checkout
