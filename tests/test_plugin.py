"""Plainbrain installed as a Claude plugin: the manifest, the setup script, and finding the owner's folder."""
import json
import os
import struct
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
    assert "plugin-skills" not in plugin_setup.DATA_COPY and ".claude/skills" in plugin_setup.SKILL_DIRS


def test_hook_runs_a_script_inside_the_plugin_with_no_other_variable():
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    command = hooks["PreToolUse"][0]["hooks"][0]["command"]
    # Called through sh, so it runs even where the file's executable bit was lost in a copy.
    assert command == 'sh "${CLAUDE_PLUGIN_ROOT}/hooks/inbox-guard.sh"'
    script = (ROOT / "hooks" / "inbox-guard.sh").read_text(encoding="utf-8")
    assert script.startswith("#!/bin/sh\n") and "${CLAUDE_PLUGIN_ROOT}/scripts/inbox_guard.py" in script
    assert "curl" not in script and "wget" not in script and "pip" not in script


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: folder))
    monkeypatch.setenv("HOME", str(folder))         # `~` is expanded from these, not from Path.home
    monkeypatch.setenv("USERPROFILE", str(folder))
    return folder


def test_setup_copies_the_template_and_records_the_folder(tmp_path, fake_home):
    target = tmp_path / "Documents" / "my-plainbrain"
    message = plugin_setup.set_up(target)
    assert (target / "AGENTS.md").is_file() and (target / "CLAUDE.md").is_file()
    assert (target / ".plainbrain-folder").is_file()
    assert (target / ".claude" / "skills").is_dir() and (target / ".agents" / "skills").is_dir()
    assert (target / "templates").is_dir() and (target / "views" / "Plainbrain.base").is_file()
    assert (target / ".gemini" / "settings.json").is_file()
    assert not (target / "scripts").exists() and not (target / "plainbrain").exists()
    assert not (target / "requirements.txt").exists() and not (target / ".claude" / "settings.json").exists()
    assert not (target / "plugin-skills").exists() and not (target / ".claude-plugin").exists()
    assert not (target / "tests").exists()
    gitignore = (target / ".gitignore").read_text(encoding="utf-8")
    assert "board/" in gitignore and "reviews/" not in gitignore
    assert (fake_home / ".plainbrain").read_text(encoding="utf-8").strip() == target.resolve().as_posix()
    assert "Recorded in" in message and home.recorded_folder() == Path(target.resolve().as_posix())


def test_package_setup_writes_resolved_guard_hooks_and_skips_hooks_on_ephemeral(tmp_path, fake_home, monkeypatch, capsys):
    from plainbrain import cli, global_hooks

    target = tmp_path / "pkg-brain"
    monkeypatch.setattr(global_hooks, "resolve_hook_command", lambda kind, root=None, temp_root=None: "/venv/bin/plainbrain-guard")
    assert cli.main(["setup", "--to", str(target)]) == 0
    out = capsys.readouterr().out
    assert (target / ".plainbrain-folder").is_file()
    assert "/venv/bin/plainbrain-guard" in (target / ".claude" / "settings.json").read_text(encoding="utf-8")
    assert "/venv/bin/plainbrain-guard" in (target / ".cursor" / "hooks.json").read_text(encoding="utf-8")
    assert "/venv/bin/plainbrain-guard --codex" in (target / ".codex" / "hooks.json").read_text(encoding="utf-8")
    assert "/venv/bin/plainbrain-guard" in (target / ".agents" / "hooks.json").read_text(encoding="utf-8")
    assert (fake_home / ".plainbrain").read_text(encoding="utf-8").strip() == target.resolve().as_posix()

    target2 = tmp_path / "uvx-brain"
    def _ephemeral(kind, root=None, temp_root=None):
        raise ValueError("Plainbrain is running from a temporary cache (such as uvx). Install persistently with pipx or uv tool install.")
    monkeypatch.setattr(global_hooks, "resolve_hook_command", _ephemeral)
    assert cli.main(["setup", "--to", str(target2)]) == 0
    out2 = capsys.readouterr().out
    assert "pipx" in out2
    assert (target2 / ".plainbrain-folder").is_file() and (target2 / "AGENTS.md").is_file()
    assert (fake_home / ".plainbrain").read_text(encoding="utf-8").strip() == target2.resolve().as_posix()
    assert not (target2 / ".claude" / "settings.json").exists()
    assert not (target2 / ".cursor").exists()
    assert not (target2 / ".codex").exists()
    assert not (target2 / ".agents" / "hooks.json").exists()


def test_setup_reports_old_and_new_folder_when_pointer_changes(tmp_path, fake_home):
    first = tmp_path / "first-brain"
    second = tmp_path / "second-brain"
    plugin_setup.set_up(first)
    message = plugin_setup.set_up(second)
    assert first.resolve().as_posix() in message
    assert second.resolve().as_posix() in message


def test_adopt_accepts_legacy_and_data_only_folders_without_writing_any_file(tmp_path, fake_home):
    legacy = tmp_path / "legacy"
    (legacy / "scripts").mkdir(parents=True)
    (legacy / "AGENTS.md").write_text("legacy agents", encoding="utf-8")
    (legacy / "scripts" / "brain.py").write_text("# legacy", encoding="utf-8")

    data_only = tmp_path / "data-only"
    data_only.mkdir()
    (data_only / "AGENTS.md").write_text("data agents", encoding="utf-8")
    (data_only / ".plainbrain-folder").write_text("", encoding="utf-8")

    minimal = tmp_path / "minimal"
    minimal.mkdir()
    (minimal / "AGENTS.md").write_text("minimal agents", encoding="utf-8")
    (minimal / "REGISTRY.md").write_text("# Registry\n", encoding="utf-8")
    (minimal / "INBOX.md").write_text("# Inbox\n", encoding="utf-8")

    for folder, expected in (
        (legacy, {"AGENTS.md": "legacy agents", "scripts/brain.py": "# legacy"}),
        (data_only, {"AGENTS.md": "data agents", ".plainbrain-folder": ""}),
        (minimal, {"AGENTS.md": "minimal agents", "REGISTRY.md": "# Registry\n", "INBOX.md": "# Inbox\n"}),
    ):
        msg = plugin_setup.set_up(folder, adopt=True)
        assert "kept the files already in" in msg
        assert (fake_home / ".plainbrain").read_text(encoding="utf-8").strip() == folder.resolve().as_posix()
        actual = {p.relative_to(folder).as_posix(): p.read_text(encoding="utf-8")
                  for p in folder.rglob("*") if p.is_file()}
        assert actual == expected


def test_data_folder_agents_md_needs_no_missing_files(tmp_path, fake_home):
    target = tmp_path / "brain"
    plugin_setup.set_up(target)
    text = (target / "AGENTS.md").read_text(encoding="utf-8")
    for cmd in ("plainbrain brief", "plainbrain board", "plainbrain capture", "plainbrain doctor"):
        assert cmd in text
    assert "python scripts/brain.py" in text
    first_setup = text.split("## First setup", 1)[1].split("## Updating Plainbrain", 1)[0]
    assert "plainbrain init" in first_setup
    assert "requirements.txt" not in first_setup
    assert "scripts/brain.py" not in first_setup


def test_marketplace_manifest_has_unique_name_and_valid_plugin_entry():
    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert marketplace["name"] == "dababonpro-plainbrain"
    assert isinstance(marketplace["owner"], dict) and marketplace["owner"].get("name")
    plugins = marketplace["plugins"]
    assert len(plugins) == 1
    assert plugins[0]["name"] == "plainbrain"
    assert plugins[0]["source"] == "./"


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


def test_a_leading_tilde_in_the_recorded_path_or_the_variable_is_expanded(tmp_path, fake_home, monkeypatch):
    monkeypatch.delenv("BRAIN_ROOT", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "checkout"))
    (fake_home / "brain").mkdir()
    (fake_home / ".plainbrain").write_text("~/brain\n", encoding="utf-8")
    assert home.recorded_folder() == fake_home / "brain"
    assert home.data_root(tmp_path / "checkout") == fake_home / "brain"
    monkeypatch.setenv("BRAIN_ROOT", "~/other")
    assert home.data_root(tmp_path / "checkout") == fake_home / "other"


def _run(code_or_script, env_home, stdin="", plugin=True, extra=None):
    env = {**os.environ, "HOME": str(env_home), "USERPROFILE": str(env_home), "PYTHONPATH": str(ROOT)}
    env.pop("BRAIN_ROOT", None)
    env.update(extra or {})
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


def _bare(tool="Write"):
    """An edit to a bare file name from a tool that did not say which folder it ran in."""
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"file_path": BOX, "content": "x"}})


def test_guard_as_a_plugin_allows_everything_until_there_is_a_folder(tmp_path):
    env_home = tmp_path / "home"
    env_home.mkdir()
    guard = [str(ROOT / "scripts" / "inbox_guard.py")]
    shell = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": f"echo x > {BOX}"}})
    for payload in (_edit(ROOT / BOX), _edit(tmp_path / "elsewhere" / BOX), _bare(), shell):
        assert "deny" not in _run(guard, env_home, payload).stdout, payload           # before setup
    (env_home / ".plainbrain").write_text((tmp_path / "gone").as_posix() + "\n", encoding="utf-8")
    for payload in (_edit(ROOT / BOX), _edit(tmp_path / "gone" / BOX), _bare(), shell):
        assert "deny" not in _run(guard, env_home, payload).stdout, payload           # the recorded folder is gone


def test_guard_as_a_plugin_does_not_guess_when_the_tool_gives_no_folder(tmp_path):
    env_home = tmp_path / "home"
    env_home.mkdir()
    folder = tmp_path / "brain"
    folder.mkdir()
    (env_home / ".plainbrain").write_text(folder.as_posix() + "\n", encoding="utf-8")
    guard = [str(ROOT / "scripts" / "inbox_guard.py")]
    assert "deny" not in _run(guard, env_home, _bare()).stdout           # most likely another project's file
    assert "deny" in _run(guard, env_home, _edit(folder / BOX)).stdout    # the full path is still caught
    assert "deny" in _run(guard, env_home, _bare(), plugin=False).stdout  # in a folder of its own: assume the worst


def test_guard_as_a_plugin_takes_the_named_folder_and_expands_a_tilde(tmp_path):
    env_home = tmp_path / "home"
    (env_home / "brain").mkdir(parents=True)
    named = tmp_path / "named"
    named.mkdir()
    guard = [str(ROOT / "scripts" / "inbox_guard.py")]
    (env_home / ".plainbrain").write_text("~/brain\n", encoding="utf-8")
    assert "deny" in _run(guard, env_home, _edit(env_home / "brain" / BOX)).stdout
    extra = {"BRAIN_ROOT": str(named)}
    assert "deny" in _run(guard, env_home, _edit(named / BOX), extra=extra).stdout
    assert "deny" not in _run(guard, env_home, _edit(env_home / "brain" / BOX), extra=extra).stdout


def test_mcp_server_finds_the_folder_as_soon_as_setup_has_run_in_the_same_session(tmp_path):
    """Claude Code starts the server when the session opens, before the owner has said "Set up Plainbrain"."""
    pytest.importorskip("mcp")
    env_home = tmp_path / "home"
    env_home.mkdir()
    folder = tmp_path / "brain"
    probe = ["-c", "import sys; from pathlib import Path; from scripts import mcp_server as m, plugin_setup\n"
                   "print(m.capture('repo', 'a line')); print(m.search('x')); print(m.latest_brief())\n"
                   "print(m.registry_item('a')); print(m.for_repo('repo')); print(m.open_items())\n"
                   "plugin_setup.set_up(Path(sys.argv[1]))\n"
                   "print(m.latest_brief()); print(m.registry_item('a'))", str(folder)]
    done = _run(probe, env_home)
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert "has no folder yet" in lines[0] and lines[1] == "[]" and "has no folder yet" in lines[2]
    assert "has no folder yet" in lines[3] and "has no folder yet" in lines[4] and lines[5] == "[]"
    assert lines[6] == "No brief yet." and lines[7] == "REGISTRY.md is missing."   # the same process, after setup
    assert not (ROOT / ".not-set-up").exists() and not (env_home / BOX).exists()


def test_the_folder_check_tests_this_folders_guard_even_inside_a_plugin_session(fake_home, monkeypatch):
    from scripts import doctor
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(ROOT))
    monkeypatch.delenv("BRAIN_ROOT", raising=False)
    assert not (fake_home / ".plainbrain").exists()
    assert doctor._blocks([sys.executable, str(doctor.GUARD)])
    (fake_home / "other").mkdir()
    (fake_home / ".plainbrain").write_text((fake_home / "other").as_posix() + "\n", encoding="utf-8")
    assert doctor._blocks([sys.executable, str(doctor.GUARD)])


def test_listing_icon_is_a_square_png_of_an_accepted_size():
    data = (ROOT / ".claude-plugin" / "icon.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    # The directory takes a square PNG of 512 to 2048 px a side, under 2 MB, and only at first submission.
    assert width == height and 512 <= width <= 2048 and len(data) < 2 * 1024 * 1024
