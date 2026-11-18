"""Doctor reports whether Plainbrain and its inbox guard really work on this machine."""
import os
import subprocess
import sys

import pytest

from plainbrain import global_hooks, home
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


def test_doctor_reports_stale_and_ephemeral_global_hooks_without_raising(tmp_path, monkeypatch):
    brain.init(tmp_path, "Work")

    # Case A: stale global hooks -> WARN mentioning "stale" and "hooks install"
    monkeypatch.setattr(
        global_hooks,
        "status",
        lambda *a, **kw: {"claude": "stale", "cursor": "installed", "antigravity": "installed"},
    )
    results = doctor.checks(tmp_path)
    warnings = [text for status, text in results if status == doctor.WARN]
    assert any("stale" in text.lower() and "hooks install" in text.lower() for text in warnings), results

    # Case B: ephemeral global hooks -> WARN mentioning pipx / uv tool install, no exception, no FAIL
    monkeypatch.setattr(
        global_hooks,
        "status",
        lambda *a, **kw: {"claude": "ephemeral", "cursor": "ephemeral", "antigravity": "ephemeral"},
    )
    results = doctor.checks(tmp_path)
    assert all(status != doctor.FAIL for status, _text in results), results
    warnings = [text for status, text in results if status == doctor.WARN]
    assert any("pipx" in text.lower() and "uv tool install" in text.lower() for text in warnings), results


def test_doctor_checks_data_only_folder_in_packaged_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(home, "is_packaged", lambda: True)
    brain.init(tmp_path, "Work")

    seen = []
    real_blocks = doctor._blocks

    def spy_blocks(argv, env=None, target_root=None):
        seen.append((argv, env, target_root))
        return real_blocks(argv, env=env, target_root=target_root)

    monkeypatch.setattr(doctor, "_blocks", spy_blocks)
    results = doctor.checks(tmp_path)
    assert all(status != doctor.FAIL for status, _text in results), results
    assert any(status == doctor.OK and "inbox guard blocks" in text.lower() for status, text in results), results
    assert seen, "expected doctor to run the inbox guard check"
    argv, env, target_root = seen[0]
    assert argv == [sys.executable, "-m", "plainbrain.inbox_guard"]
    assert env is not None and env.get("BRAIN_ROOT") == str(tmp_path)
    assert target_root == tmp_path


def test_doctor_does_not_report_ephemeral_path_binaries_as_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(home, "is_packaged", lambda: True)
    brain.init(tmp_path, "Work")

    temp_root = tmp_path / "sys-temp"
    uv_bin = temp_root / "uv" / "cache" / "bin"
    uv_bin.mkdir(parents=True)
    for name in ("plainbrain-guard", "plainbrain-mcp"):
        (uv_bin / name).write_text("", encoding="utf-8")
    monkeypatch.setenv("PLAINBRAIN_TEMP_ROOT", str(temp_root))
    monkeypatch.setattr(doctor.shutil, "which", lambda name: str(uv_bin / name) if (uv_bin / name).is_file() else None)
    monkeypatch.setattr(global_hooks, "status", lambda *a, **kw: {"claude": "ephemeral", "cursor": "ephemeral", "antigravity": "ephemeral"})

    results = doctor.checks(tmp_path)
    assert not any(status == doctor.OK and "plainbrain-guard is on PATH" in text for status, text in results), results
    assert not any(status == doctor.OK and "plainbrain-mcp is on PATH" in text for status, text in results), results
    assert any(status == doctor.WARN and "plainbrain-guard is not on PATH" in text for status, text in results), results
    assert any(status == doctor.NOTE and "plainbrain-mcp is not on PATH" in text for status, text in results), results
