"""Locate Plainbrain's bundled assets (wheel install or source checkout)."""
from pathlib import Path


def assets_dir() -> Path:
    bundled = Path(__file__).resolve().parent / "_assets"
    if (bundled / "AGENTS.md").is_file():
        return bundled
    checkout = Path(__file__).resolve().parents[1]
    if (checkout / "AGENTS.md").is_file():
        return checkout
    raise FileNotFoundError("Plainbrain bundled assets not found")
