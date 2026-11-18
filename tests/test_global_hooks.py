"""`hooks install` adds Plainbrain's hooks to each agent's user-level file without disturbing anything else."""
import json
from pathlib import Path

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
