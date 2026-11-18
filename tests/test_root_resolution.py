from pathlib import Path
import pytest

from plainbrain import cli, home


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: folder))
    monkeypatch.setenv("HOME", str(folder))
    monkeypatch.setenv("USERPROFILE", str(folder))
    monkeypatch.delenv("BRAIN_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    return folder


def test_cli_root_ignores_decoy_cwd_with_both_registry_and_inbox(tmp_path, fake_home):
    decoy = tmp_path / "other-system"
    decoy.mkdir()
    (decoy / "REGISTRY.md").write_text("# Registry\n", encoding="utf-8")
    (decoy / "INBOX.md").write_text("# Inbox\n", encoding="utf-8")

    real = tmp_path / "real-brain"
    real.mkdir()
    (fake_home / ".plainbrain").write_text(real.as_posix() + "\n", encoding="utf-8")

    assert not home.is_plainbrain_cwd(decoy)
    assert home.resolve_cli_root(None, cwd=decoy) == real


def test_cli_root_accepts_marker_or_legacy_script_and_respects_precedence(tmp_path, fake_home, monkeypatch):
    marker_dir = tmp_path / "marked"
    marker_dir.mkdir()
    (marker_dir / home.MARKER_NAME).write_text("plainbrain\n", encoding="utf-8")

    legacy_dir = tmp_path / "legacy"
    (legacy_dir / "scripts").mkdir(parents=True)
    (legacy_dir / "scripts" / "brain.py").write_text("", encoding="utf-8")

    recorded = tmp_path / "recorded"
    recorded.mkdir()
    (fake_home / ".plainbrain").write_text(recorded.as_posix() + "\n", encoding="utf-8")

    assert home.resolve_cli_root(None, cwd=marker_dir) == marker_dir
    assert home.resolve_cli_root(None, cwd=legacy_dir) == legacy_dir

    env_dir = tmp_path / "from-env"
    monkeypatch.setenv("BRAIN_ROOT", str(env_dir))
    assert home.resolve_cli_root(None, cwd=marker_dir) == env_dir
    assert home.resolve_cli_root(str(tmp_path / "explicit"), cwd=marker_dir) == tmp_path / "explicit"


def test_global_root_never_reads_cwd_when_packaged_or_plugin(tmp_path, fake_home, monkeypatch):
    marked_cwd = tmp_path / "marked-cwd"
    marked_cwd.mkdir()
    (marked_cwd / home.MARKER_NAME).write_text("plainbrain\n", encoding="utf-8")
    monkeypatch.chdir(marked_cwd)

    monkeypatch.setattr(home, "is_packaged", lambda: True)
    assert home.resolve_global_root(tmp_path / "site") is None

    recorded = tmp_path / "recorded"
    recorded.mkdir()
    (fake_home / ".plainbrain").write_text(recorded.as_posix() + "\n", encoding="utf-8")
    assert home.resolve_global_root(tmp_path / "site") == recorded

    env_dir = tmp_path / "from-env"
    monkeypatch.setenv("BRAIN_ROOT", str(env_dir))
    assert home.resolve_global_root(tmp_path / "site") == env_dir


def test_cli_runs_brief_and_registry_without_root_using_pointer_and_errors_when_unset(tmp_path, fake_home, monkeypatch, capsys):
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)

    assert cli.main(["brief", "--today", "2026-11-18"]) == 1
    assert "No Plainbrain folder found" in capsys.readouterr().err

    brain_dir = tmp_path / "my-brain"
    brain_dir.mkdir()
    (fake_home / ".plainbrain").write_text(brain_dir.as_posix() + "\n", encoding="utf-8")
    assert cli.main(["init"]) == 0
    assert cli.main(["brief", "--today", "2026-11-18"]) == 0
    assert cli.main(["registry", "show", "--id", "set-up-second-brain"]) == 0
