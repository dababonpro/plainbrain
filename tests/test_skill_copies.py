"""Claude Code reads skills from .claude/skills and the other agents from .agents/skills. Both must hold the same files."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = (ROOT / ".claude" / "skills", ROOT / ".agents" / "skills")


def _files(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def test_both_skill_folders_hold_the_same_skills():
    claude, agents = (_files(folder) for folder in COPIES)
    assert claude, ".claude/skills is empty"
    assert sorted(claude) == sorted(agents)
    drifted = [name for name in claude if claude[name] != agents[name]]
    assert not drifted, f"edit both copies: {drifted}"
