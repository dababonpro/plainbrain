"""Plainbrain installed as a Claude plugin: the manifest, the setup script, and finding the owner's folder."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import home, plugin_setup

ROOT = Path(__file__).resolve().parents[1]
BOX = "INBOX.md"


def test_manifest_points_at_files_that_exist_and_stay_inside_the_plugin():
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "plainbrain" and manifest["license"] == "MIT"
    for field in ("description", "version", "author", "homepage", "privacyPolicyUrl", "supportUrl"):
        assert manifest[field], field
    for path in manifest["skills"]:
        assert path.startswith("./") and ".." not in path and (ROOT / path).is_dir(), path
    server = manifest["mcpServers"]["plainbrain"]
    assert server["args"] == ["${CLAUDE_PLUGIN_ROOT}/scripts/mcp_server.py"] and (ROOT / "scripts" / "mcp_server.py").is_file()
    assert "userConfig" not in manifest  # the folder is recorded by setup, not typed into a settings dialog


def test_plugin_skills_have_front_matter_and_the_template_skills_are_listed_once():
    for name in ("setup", "plainbrain"):
        text = (ROOT / "plugin-skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---\nname: " + name + "\n") and "\ndescription: " in text.split("---")[1]
    # Plugin-only skills name the plugin's own folder, so they must not be copied into the owner's folder.
    assert "plugin-skills" not in plugin_setup.COPY and ".claude" in plugin_setup.COPY


def test_hook_runs_a_script_inside_the_plugin_with_no_other_variable():
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    command = hooks["PreToolUse"][0]["hooks"][0]["command"]
    assert command == '"${CLAUDE_PLUGIN_ROOT}"/hooks/inbox-guard.sh'
    script = (ROOT / "hooks" / "inbox-guard.sh").read_text(encoding="utf-8")
    assert script.startswith("#!/bin/sh\n") and "${CLAUDE_PLUGIN_ROOT}/scripts/inbox_guard.py" in script
    assert "curl" not in script and "wget" not in script and "pip" not in script


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: folder))
    return folder


def test_setup_copies_the_template_and_records_the_folder(tmp_path, fake_home):
    target = tmp_path / "Documents" / "my-plainbrain"
    message = plugin_setup.set_up(target)
    assert (target / "AGENTS.md").is_file() and (target / "scripts" / "brain.py").is_file()
    assert (target / ".claude" / "skills").is_dir() and (target / "templates").is_dir()
    assert not (target / "plugin-skills").exists() and not (target / ".claude-plugin").exists()
    assert not (target / "tests").exists() and not (target / "scripts" / "plugin_setup.py").exists()
    assert (fake_home / ".plainbrain").read_text(encoding="utf-8").strip() == target.resolve().as_posix()
    assert "Recorded in" in message and home.recorded_folder() == Path(target.resolve().as_posix())


def test_setup_never_overwrites(tmp_path, fake_home):
    target = tmp_path / "existing"
    target.mkdir()
    (target / "mine.txt").write_text("keep me")
    with pytest.raises(ValueError, match="already holds files"):
        plugin_setup.set_up(target)
    assert (target / "mine.txt").read_text() == "keep me" and not (fake_home / ".plainbrain").exists()
    assert plugin_setup.main(["--to", str(target)]) == 1


def test_setup_adopts_an_existing_plainbrain_folder_without_copying(tmp_path, fake_home):
    target = tmp_path / "older"
    plugin_setup.set_up(target)
    (target / "AGENTS.md").write_text("mine now", encoding="utf-8")
    (fake_home / ".plainbrain").unlink()
    with pytest.raises(ValueError, match="pass --adopt"):
        plugin_setup.set_up(target)
    assert "kept the files already in" in plugin_setup.set_up(target, adopt=True)
    assert (target / "AGENTS.md").read_text(encoding="utf-8") == "mine now"
    assert (fake_home / ".plainbrain").is_file()


def test_setup_refuses_the_plugins_own_folder_and_a_file(tmp_path, fake_home):
    with pytest.raises(ValueError, match="outside the plugin"):
        plugin_setup.set_up(ROOT / "my-plainbrain")
    file = tmp_path / "a.txt"
    file.write_text("x")
    with pytest.raises(ValueError, match="is a file"):
        plugin_setup.set_up(file)


def test_data_root_rules(tmp_path, fake_home, monkeypatch):
    checkout = tmp_path / "checkout"
    monkeypatch.delenv("BRAIN_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    assert home.data_root(checkout) == checkout                 # the owner's own folder: code beside data
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(checkout))
    assert home.data_root(checkout) is None                     # a plugin that was never set up
    folder = tmp_path / "brain"
    folder.mkdir()
    (fake_home / ".plainbrain").write_text(folder.as_posix() + "\n", encoding="utf-8")
    assert home.data_root(checkout) == Path(folder.as_posix())  # a plugin after setup
    folder.rmdir()
    assert home.data_root(checkout) is None                     # the recorded folder was deleted
    monkeypatch.setenv("BRAIN_ROOT", str(tmp_path / "named"))
    assert home.data_root(checkout) == tmp_path / "named"       # an explicit folder always wins


def _run(code_or_script, env_home, stdin="", plugin=True):
    env = {**os.environ, "HOME": str(env_home), "USERPROFILE": str(env_home), "PYTHONPATH": str(ROOT)}
    env.pop("BRAIN_ROOT", None)
    if plugin:
        env["CLAUDE_PLUGIN_ROOT"] = str(ROOT)
    else:
        env.pop("CLAUDE_PLUGIN_ROOT", None)
    return subprocess.run([sys.executable, *code_or_script], input=stdin, capture_output=True, text=True, env=env,
                          cwd=str(ROOT), timeout=60)


def _edit(path):
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(Path(path).parent),
                       "tool_input": {"file_path": str(path), "content": "x"}})


def test_guard_as_a_plugin_protects_the_recorded_folder_not_the_install_folder(tmp_path):
    env_home = tmp_path / "home"
    env_home.mkdir()
    folder = tmp_path / "brain"
    folder.mkdir()
    (env_home / ".plainbrain").write_text(folder.as_posix() + "\n", encoding="utf-8")
    guard = [str(ROOT / "scripts" / "inbox_guard.py")]
    assert "deny" in _run(guard, env_home, _edit(folder / BOX)).stdout
    assert "deny" not in _run(guard, env_home, _edit(folder / "notes.md")).stdout
    assert "deny" not in _run(guard, env_home, _edit(ROOT / BOX)).stdout          # the plugin's copy is not the owner's
    assert "deny" in _run(guard, env_home, _edit(ROOT / BOX), plugin=False).stdout  # in a folder of its own, as before


def test_mcp_server_as_a_plugin_writes_nowhere_until_setup(tmp_path):
    pytest.importorskip("mcp")
    env_home = tmp_path / "home"
    env_home.mkdir()
    probe = ["-c", "from scripts import mcp_server as m; print(m.NOT_SET); print(m.capture('repo', 'a line')); "
                   "print(m.search('x')); print(m.latest_brief())"]
    done = _run(probe, env_home)
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert lines[0] == "True" and "has no folder yet" in lines[1] and lines[2] == "[]" and "has no folder yet" in lines[3]
    assert not (ROOT / ".not-set-up").exists() and not (env_home / BOX).exists()
