"""Doctor reports whether Plainbrain and its inbox guard really work on this machine."""
import os
import subprocess
import sys

import pytest

from scripts import brain, doctor


def _statuses(root):
    return [status for status, _text in doctor.checks(root)]


def test_fails_before_init_and_passes_after(tmp_path, capsys):
    assert doctor.FAIL in _statuses(tmp_path)
    assert doctor.run_doctor(tmp_path) == 1
    assert brain.init(tmp_path, "Work, Personal") == 0
    assert doctor.FAIL not in _statuses(tmp_path)
    assert doctor.run_doctor(tmp_path) == 0
    assert "ok" in capsys.readouterr().out


def test_changes_nothing(tmp_path):
    brain.init(tmp_path, "Work")
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    doctor.run_doctor(tmp_path)
    after = {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    assert before == after


def test_warns_when_python_does_not_start(tmp_path, monkeypatch):
    brain.init(tmp_path, "Work")
    monkeypatch.setattr(doctor, "interpreter", lambda name: None)
    warnings = [text for status, text in doctor.checks(tmp_path) if status == doctor.WARN]
    assert any("Cursor, Codex and Antigravity" in text and "nothing blocks" in text for text in warnings)


def test_a_name_that_is_not_installed_does_not_start():
    assert doctor.interpreter("no-such-python-anywhere") is None


needs_sh = pytest.mark.skipif(doctor.find_sh() is None, reason="no sh on this machine")


@needs_sh
def test_claude_hook_blocks_an_inbox_edit():
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(doctor.HOME)}
    assert doctor._blocks([doctor.find_sh(), "-c", doctor.claude_hook_command()], env=env)


@needs_sh
@pytest.mark.skipif(os.name == "nt", reason="builds a POSIX launcher")
def test_claude_hook_runs_where_only_python3_exists(tmp_path):
    # A machine such as stock macOS or Ubuntu: `python3` is on PATH and `python` is not.
    launcher = tmp_path / "python3"
    launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    launcher.chmod(0o755)
    env = {"PATH": str(tmp_path), "CLAUDE_PROJECT_DIR": str(doctor.HOME)}
    done = subprocess.run([doctor.find_sh(), "-c", doctor.claude_hook_command()], input=doctor._edit(),
                          capture_output=True, text=True, timeout=30, env=env)
    assert done.returncode == 2, done.stderr
