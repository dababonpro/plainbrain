"""`hooks install` adds Plainbrain's hooks to each agent's user-level file without disturbing anything else."""
import json
import shutil
import sys
from pathlib import Path

import pytest

from plainbrain import home
from scripts import global_hooks
from scripts.brain import main

ROOT = Path(__file__).resolve().parents[1]


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_installs_into_empty_homes(tmp_path):
    lines = global_hooks.install(ROOT, home=tmp_path)
    assert all("added" in line for line in lines), lines
    files = global_hooks.files(tmp_path)
    claude = _read(files["claude"])
    assert "inbox_guard.py" in claude["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "capture_nudge.py" in claude["hooks"]["Stop"][0]["hooks"][0]["command"]
    cursor = _read(files["cursor"])
    assert cursor["version"] == 1 and cursor["hooks"]["beforeShellExecution"][0]["matcher"] == "INBOX\\.md|REGISTRY\\.md"
    antigravity = _read(files["antigravity"])
    assert "plainbrain-inbox-guard" in antigravity
    assert global_hooks.status(ROOT, home=tmp_path) == {"claude": "installed", "cursor": "installed",
                                                         "antigravity": "installed"}


def test_running_twice_changes_nothing(tmp_path):
    global_hooks.install(ROOT, home=tmp_path)
    before = {a: p.read_text(encoding="utf-8") for a, p in global_hooks.files(tmp_path).items()}
    lines = global_hooks.install(ROOT, home=tmp_path)
    assert all("already installed" in line for line in lines)
    assert before == {a: p.read_text(encoding="utf-8") for a, p in global_hooks.files(tmp_path).items()}


def test_keeps_existing_settings_and_saves_a_copy(tmp_path):
    path = global_hooks.files(tmp_path)["claude"]
    path.parent.mkdir(parents=True)
    existing = {"theme": "dark", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other"}]}]}}
    path.write_text(json.dumps(existing), encoding="utf-8")
    global_hooks.install(ROOT, agents=("claude",), home=tmp_path)
    data = _read(path)
    assert data["theme"] == "dark"
    assert data["hooks"]["Stop"][0]["hooks"][0]["command"] == "other" and len(data["hooks"]["Stop"]) == 2
    backups = list(path.parent.glob("settings.json.bak-*"))
    assert len(backups) == 1 and json.loads(backups[0].read_text(encoding="utf-8")) == existing


def test_leaves_an_unreadable_file_alone(tmp_path):
    path = global_hooks.files(tmp_path)["cursor"]
    path.parent.mkdir(parents=True)
    path.write_text("{ not json", encoding="utf-8")
    lines = global_hooks.install(ROOT, agents=("cursor",), home=tmp_path)
    assert "left untouched" in lines[0] and path.read_text(encoding="utf-8") == "{ not json"
    assert global_hooks.status(ROOT, home=tmp_path)["cursor"] == "unreadable"


def test_leaves_a_file_with_a_malformed_hooks_section_alone(tmp_path):
    cases = {
        "claude": {"hooks": None},
        "cursor": {"version": 1, "hooks": {"preToolUse": {"not": "a list"}}},
        "antigravity": {"mine": {"PreToolUse": "oops"}},
    }
    for agent, content in cases.items():
        path = global_hooks.files(tmp_path)[agent]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content), encoding="utf-8")
    lines = global_hooks.install(ROOT, home=tmp_path)
    assert all("not the expected shape" in line for line in lines), lines
    for agent, content in cases.items():
        assert _read(global_hooks.files(tmp_path)[agent]) == content
    assert set(global_hooks.status(ROOT, home=tmp_path).values()) == {"unreadable"}


def test_skips_claude_when_the_plugin_is_enabled(tmp_path):
    path = global_hooks.files(tmp_path)["claude"]
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"enabledPlugins": {"plainbrain@dababonpro": True}}), encoding="utf-8")
    lines = global_hooks.install(ROOT, agents=("claude",), home=tmp_path)
    assert "plugin is enabled" in lines[0] and "hooks" not in _read(path)
    assert global_hooks.status(ROOT, home=tmp_path)["claude"] == "plugin"


def test_dry_run_writes_nothing(tmp_path):
    lines = global_hooks.install(ROOT, home=tmp_path, dry_run=True)
    assert all("would add" in line for line in lines)
    assert not any(p.exists() for p in global_hooks.files(tmp_path).values())


def test_hooks_point_at_this_folder_and_still_block(tmp_path):
    import subprocess
    global_hooks.install(ROOT, agents=("cursor",), home=tmp_path)
    command = _read(global_hooks.files(tmp_path)["cursor"])["hooks"]["preToolUse"][0]["command"]
    assert (ROOT / "scripts" / "inbox_guard.py").as_posix() in command
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": "/somewhere/else",
               "tool_input": {"file_path": str(ROOT / "INBOX.md"), "content": "x"}}
    done = subprocess.run(command, shell=True, input=json.dumps(payload), capture_output=True, text=True)
    assert done.returncode == 2


def test_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert main(["hooks", "install", "--root", str(ROOT), "--agent", "antigravity", "--dry-run"]) == 0
    assert "would add" in capsys.readouterr().out
    assert main(["hooks", "status", "--root", str(ROOT)]) == 0
    assert "antigravity: missing" in capsys.readouterr().out


def test_replaces_stale_plainbrain_hooks_and_keeps_unrelated_and_other_tool_hooks(tmp_path):
    old_pb = tmp_path / "old_pb"
    (old_pb / "scripts").mkdir(parents=True)
    (old_pb / "scripts" / "brain.py").write_text("# legacy plainbrain\n", encoding="utf-8")

    other_tool = tmp_path / "other_tool"
    (other_tool / "scripts").mkdir(parents=True)
    (other_tool / "scripts" / "inbox_guard.py").write_text("# unrelated tool\n", encoding="utf-8")

    old_guard = f'"/old/python" "{(old_pb / "scripts" / "inbox_guard.py").as_posix()}"'
    old_nudge = f'"/old/python" "{(old_pb / "scripts" / "capture_nudge.py").as_posix()}"'
    other_guard = f'"/other/python" "{(other_tool / "scripts" / "inbox_guard.py").as_posix()}"'

    fake_home = tmp_path / "home"
    paths = global_hooks.files(fake_home)
    for p in paths.values():
        p.parent.mkdir(parents=True, exist_ok=True)

    paths["claude"].write_text(json.dumps({
        "theme": "dark",
        "hooks": {
            "PreToolUse": [
                {"matcher": "Write|Edit", "hooks": [{"type": "command", "command": old_guard, "timeout": 5}]},
                {"matcher": "Write", "hooks": [{"type": "command", "command": other_guard, "timeout": 5}]},
                {"matcher": "*", "hooks": [{"type": "command", "command": "other-hook", "timeout": 5}]},
            ],
            "Stop": [
                {"hooks": [{"type": "command", "command": old_nudge, "timeout": 10}]},
                {"hooks": [{"type": "command", "command": "other-hook", "timeout": 10}]},
            ],
        },
    }), encoding="utf-8")
    paths["cursor"].write_text(json.dumps({
        "version": 1,
        "hooks": {
            "preToolUse": [
                {"command": old_guard, "matcher": "Write|StrReplace|Delete|EditNotebook", "timeout": 5},
                {"command": other_guard, "matcher": "Write", "timeout": 5},
                {"command": "other-hook", "matcher": "*", "timeout": 5},
            ],
            "beforeShellExecution": [
                {"command": old_guard, "matcher": "INBOX\\.md|REGISTRY\\.md", "timeout": 5},
                {"command": other_guard, "matcher": "INBOX\\.md", "timeout": 5},
                {"command": "other-hook", "matcher": ".*", "timeout": 5},
            ],
        },
    }), encoding="utf-8")
    paths["antigravity"].write_text(json.dumps({
        "plainbrain-inbox-guard": {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": old_guard, "timeout": 10}]},
            ],
        },
        "other-tool-group": {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": other_guard, "timeout": 10}]},
                {"matcher": "*", "hooks": [{"type": "command", "command": "other-hook", "timeout": 10}]},
            ],
        },
    }), encoding="utf-8")

    assert global_hooks.status(ROOT, home=fake_home) == {
        "claude": "stale",
        "cursor": "stale",
        "antigravity": "stale",
    }

    dry_lines = global_hooks.install(ROOT, home=fake_home, dry_run=True)
    assert all("would update" in line for line in dry_lines), dry_lines
    assert not list(paths["claude"].parent.glob("*.bak-*"))

    lines = global_hooks.install(ROOT, home=fake_home)
    assert all("updated" in line for line in lines), lines
    for agent, path in paths.items():
        assert list(path.parent.glob(f"{path.name}.bak-*")), f"missing backup for {agent}"

    expected_guard = global_hooks.resolve_hook_command("guard", ROOT)
    expected_nudge = global_hooks.resolve_hook_command("nudge", ROOT)

    claude = _read(paths["claude"])
    assert claude["theme"] == "dark"
    assert [e["hooks"][0]["command"] for e in claude["hooks"]["PreToolUse"]] == [
        expected_guard, other_guard, "other-hook",
    ]
    assert [e["hooks"][0]["command"] for e in claude["hooks"]["Stop"]] == [
        expected_nudge, "other-hook",
    ]

    cursor = _read(paths["cursor"])
    assert [e["command"] for e in cursor["hooks"]["preToolUse"]] == [
        expected_guard, other_guard, "other-hook",
    ]
    assert [e["command"] for e in cursor["hooks"]["beforeShellExecution"]] == [
        expected_guard, other_guard, "other-hook",
    ]

    antigravity = _read(paths["antigravity"])
    assert antigravity["plainbrain-inbox-guard"]["PreToolUse"][0]["hooks"][0]["command"] == expected_guard
    assert [e["hooks"][0]["command"] for e in antigravity["other-tool-group"]["PreToolUse"]] == [
        other_guard, "other-hook",
    ]

    assert global_hooks.status(ROOT, home=fake_home) == {
        "claude": "installed",
        "cursor": "installed",
        "antigravity": "installed",
    }


def test_other_tool_inbox_guard_alone_is_not_stale_and_untouched(tmp_path):
    other_guard = '"/other/python" "/other-tool/scripts/inbox_guard.py"'
    paths = global_hooks.files(tmp_path)
    for agent in ("claude", "cursor"):
        paths[agent].parent.mkdir(parents=True, exist_ok=True)

    paths["claude"].write_text(json.dumps({
        "hooks": {
            "PreToolUse": [
                {"matcher": "Write", "hooks": [{"type": "command", "command": other_guard, "timeout": 5}]},
            ],
        },
    }), encoding="utf-8")
    paths["cursor"].write_text(json.dumps({
        "version": 1,
        "hooks": {
            "preToolUse": [{"command": other_guard, "matcher": "Write", "timeout": 5}],
            "beforeShellExecution": [{"command": other_guard, "matcher": "INBOX\\.md", "timeout": 5}],
        },
    }), encoding="utf-8")

    st = global_hooks.status(ROOT, home=tmp_path)
    assert st["claude"] == "missing"
    assert st["cursor"] == "missing"

    global_hooks.install(ROOT, home=tmp_path)

    expected_guard = global_hooks.resolve_hook_command("guard", ROOT)
    claude = _read(paths["claude"])
    assert [e["hooks"][0]["command"] for e in claude["hooks"]["PreToolUse"]] == [other_guard, expected_guard]
    cursor = _read(paths["cursor"])
    assert [e["command"] for e in cursor["hooks"]["preToolUse"]] == [other_guard, expected_guard]
    assert [e["command"] for e in cursor["hooks"]["beforeShellExecution"]] == [other_guard, expected_guard]


def test_packaged_hooks_path_venv_and_ephemeral_uvx(tmp_path, monkeypatch):
    temp_root = tmp_path / "sys-temp"
    temp_root.mkdir()
    monkeypatch.setattr(home, "is_packaged", lambda: True)

    # 1. Binary on PATH outside temp/uv-cache resolves to bare binary name.
    path_bin = tmp_path / "bin" / "plainbrain-guard"
    path_bin.parent.mkdir(parents=True)
    path_bin.write_text("", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda name: str(path_bin) if name == "plainbrain-guard" else None)
    assert global_hooks.resolve_hook_command("guard", None, temp_root=temp_root) == "plainbrain-guard"

    # 2. Not on PATH, persistent venv binary beside sys.executable resolves to quoted POSIX path.
    monkeypatch.setattr(shutil, "which", lambda name: None)
    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    venv_python = venv_bin / "python"
    venv_python.write_text("", encoding="utf-8")
    venv_guard = venv_bin / "plainbrain-guard"
    venv_guard.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(venv_python))
    assert global_hooks.resolve_hook_command("guard", None, temp_root=temp_root) == f'"{venv_guard.as_posix()}"'
    # Also verify PLAINBRAIN_TEMP_ROOT env var works when temp_root=None.
    monkeypatch.setenv("PLAINBRAIN_TEMP_ROOT", str(temp_root))
    assert global_hooks.resolve_hook_command("guard", None) == f'"{venv_guard.as_posix()}"'

    # 3a. Ephemeral uv/cache executable raises ValueError and status() returns "ephemeral" without raising.
    uv_python = tmp_path / "uv" / "cache" / "archive-v0" / "bin" / "python"
    uv_python.parent.mkdir(parents=True)
    uv_python.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(uv_python))
    with pytest.raises(ValueError) as exc_info:
        global_hooks.resolve_hook_command("guard", None, temp_root=temp_root)
    msg = str(exc_info.value).lower()
    assert "pipx" in msg and "uv tool install" in msg
    assert global_hooks.status(None, home=tmp_path / "home", temp_root=temp_root) == {
        "claude": "ephemeral",
        "cursor": "ephemeral",
        "antigravity": "ephemeral",
    }

    # 3b. Executable inside temp_root also raises ValueError and status() returns "ephemeral".
    tmp_python = temp_root / "ephemeral-venv" / "bin" / "python"
    tmp_python.parent.mkdir(parents=True)
    tmp_python.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(tmp_python))
    with pytest.raises(ValueError) as exc_info:
        global_hooks.resolve_hook_command("guard", None, temp_root=temp_root)
    msg = str(exc_info.value).lower()
    assert "pipx" in msg and "uv tool install" in msg
    assert global_hooks.status(None, home=tmp_path / "home", temp_root=temp_root) == {
        "claude": "ephemeral",
        "cursor": "ephemeral",
        "antigravity": "ephemeral",
    }


def test_cli_hooks_optional_root_when_packaged(tmp_path, monkeypatch, capsys):
    temp_root = tmp_path / "sys-temp"
    temp_root.mkdir()
    monkeypatch.setenv("PLAINBRAIN_TEMP_ROOT", str(temp_root))
    monkeypatch.setattr(home, "is_packaged", lambda: True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("plainbrain-guard", "plainbrain-nudge"):
        (bin_dir / name).write_text("", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda name: str(bin_dir / name) if (bin_dir / name).is_file() else None)
    assert main(["hooks", "status"]) == 0
    out = capsys.readouterr().out
    assert "claude: missing" in out and "cursor: missing" in out and "antigravity: missing" in out


def test_replaces_stale_packaged_and_recorded_folder_hooks(tmp_path, monkeypatch):
    temp_root = tmp_path / "sys-temp"
    temp_root.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    # Folder with NO scripts/brain.py, recognized ONLY via ~/.plainbrain (Q1 rule b).
    migrated = tmp_path / "migrated_pb"
    migrated.mkdir()
    (fake_home / home.POINTER_NAME).write_text(str(migrated) + "\n", encoding="utf-8")
    legacy_cmd = f'"/old/python" "{(migrated / "scripts" / "inbox_guard.py").as_posix()}"'
    old_venv_cmd = '"/old-venv/bin/plainbrain-guard"'

    monkeypatch.setattr(home, "is_packaged", lambda: True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("plainbrain-guard", "plainbrain-nudge"):
        (bin_dir / name).write_text("", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda name: str(bin_dir / name) if (bin_dir / name).is_file() else None)

    paths = global_hooks.files(fake_home)
    paths["cursor"].parent.mkdir(parents=True, exist_ok=True)
    paths["cursor"].write_text(json.dumps({
        "version": 1,
        "hooks": {
            "preToolUse": [{"command": legacy_cmd, "matcher": "Write", "timeout": 5}],
            "beforeShellExecution": [{"command": old_venv_cmd, "matcher": "INBOX\\.md", "timeout": 5}],
        },
    }), encoding="utf-8")

    assert global_hooks.status(None, home=fake_home, temp_root=temp_root)["cursor"] == "stale"
    lines = global_hooks.install(None, agents=("cursor",), home=fake_home, temp_root=temp_root)
    assert "updated" in lines[0]
    cursor = _read(paths["cursor"])
    assert cursor["hooks"]["preToolUse"][0]["command"] == "plainbrain-guard"
    assert cursor["hooks"]["beforeShellExecution"][0]["command"] == "plainbrain-guard"
    assert global_hooks.status(None, home=fake_home, temp_root=temp_root)["cursor"] == "installed"
