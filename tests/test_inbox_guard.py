"""The inbox guard protects this folder's inbox wherever the folder is installed."""
import importlib.util
from pathlib import Path

from plainbrain import home
from scripts import inbox_guard
from scripts.inbox_guard import decide

INBOX = str(inbox_guard.INBOX)
HERE = str(inbox_guard.INBOX.parent)


def _deny(result):
    return result.get("permission") == "deny" or result.get("decision") == "deny" or (
        result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny")


def _claude(tool, tool_input, cwd=HERE):
    return decide({"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": cwd, "tool_input": tool_input})


def test_denies_writes_to_this_inbox():
    assert _deny(_claude("Write", {"file_path": INBOX, "content": "x"}))
    assert _deny(_claude("Edit", {"file_path": INBOX, "old_string": "a", "new_string": "b"}))


def test_allows_reading_this_inbox():
    assert not _deny(_claude("Read", {"file_path": INBOX}))


def test_denies_shell_rewrites_run_in_this_folder():
    assert _deny(_claude("Bash", {"command": "echo x > INBOX.md"}))
    assert _deny(_claude("Bash", {"command": "sed -i 's/a/b/' INBOX.md"}))


def test_denies_powershell_dotnet_and_new_item_rewrites():
    for command in (
        f'[IO.File]::WriteAllText("{INBOX}", "")',
        '[System.IO.File]::WriteAllLines("INBOX.md", $lines)',
        '$w = New-Object System.IO.StreamWriter("INBOX.md"); $w.Close()',
        "New-Item INBOX.md -Force",
        "ni INBOX.md -Force",
        "perl -pi -e 's/a/b/' INBOX.md",
    ):
        assert _deny(_claude("PowerShell", {"command": command})), command


def test_allows_powershell_reads_of_this_inbox():
    for command in ("Get-Content INBOX.md", '[IO.File]::ReadAllText("INBOX.md")', "Select-String -Path INBOX.md -Pattern x"):
        assert not _deny(_claude("PowerShell", {"command": command})), command


def test_allows_a_lone_capture_command():
    command = 'python scripts/brain.py capture --root . --repo demo --text "hello"'
    assert not _deny(_claude("Bash", {"command": command}))


def test_ignores_an_inbox_in_another_folder(tmp_path):
    other = tmp_path / "elsewhere" / "INBOX.md"
    assert not _deny(_claude("Write", {"file_path": str(other), "content": "x"}, cwd=str(other.parent)))


# Codex: shell calls arrive as Bash, file edits as apply_patch text with file headers.
def _patch(*headers):
    body = "\n".join(f"*** {h}" for h in headers)
    return "*** Begin Patch\n" + body + "\n@@\n-old\n+new\n*** End Patch"


def test_codex_denies_a_patch_to_this_inbox():
    assert _deny(_claude("apply_patch", {"command": _patch("Update File: INBOX.md")}))
    assert _deny(_claude("apply_patch", {"command": _patch(f"Update File: {INBOX}")}))
    assert _deny(_claude("apply_patch", {"command": _patch("Delete File: INBOX.md")}))
    assert _deny(_claude("apply_patch", {"command": _patch("Update File: notes.md", "Move to: INBOX.md")}))


def test_codex_allows_patches_to_other_files():
    assert not _deny(_claude("apply_patch", {"command": _patch("Update File: knowledge/para-method.md")}))
    assert not _deny(_claude("apply_patch", {"command": _patch("Add File: knowledge/new-note.md")}))


def test_codex_shell_rules_match_claude():
    assert _deny(_claude("Bash", {"command": "Set-Content INBOX.md reset"}))
    assert not _deny(_claude("Bash", {"command": "python scripts/brain.py capture --root . --repo demo --text hi"}))


# Antigravity: toolCall.name and toolCall.args in, a decision of allow or deny out.
def _antigravity(name, args):
    return decide({"toolCall": {"name": name, "args": args}, "workspacePaths": [HERE], "stepIdx": 0})


def test_antigravity_denies_file_tools_on_this_inbox():
    assert _antigravity("write_to_file", {"TargetFile": INBOX, "CodeContent": "x"}) == {
        "decision": "deny", "reason": inbox_guard.REASON}
    assert _deny(_antigravity("replace_file_content", {"TargetFile": INBOX}))
    assert _deny(_antigravity("multi_replace_file_content", {"TargetFile": INBOX}))


def test_antigravity_denies_shell_rewrites():
    assert _deny(_antigravity("run_command", {"CommandLine": "echo x > INBOX.md", "Cwd": HERE}))


def test_antigravity_allows_reads_capture_and_other_files():
    assert _antigravity("view_file", {"AbsolutePath": INBOX}) == {"decision": "allow"}
    command = "python scripts/brain.py capture --root . --repo demo --text hi"
    assert not _deny(_antigravity("run_command", {"CommandLine": command, "Cwd": HERE}))
    assert not _deny(_antigravity("write_to_file", {"TargetFile": HERE + "/knowledge/note.md"}))


def test_antigravity_other_tool_names():
    # Some Antigravity versions name the file tools write_file and edit_file, and the shell run_shell_command.
    assert _deny(_antigravity("write_file", {"path": INBOX, "content": "x"}))
    assert _deny(_antigravity("edit_file", {"file_path": INBOX}))
    assert _deny(_antigravity("run_shell_command", {"command": "echo x > INBOX.md"}))
    assert not _deny(_antigravity("edit_file", {"file_path": HERE + "/knowledge/note.md"}))


def test_packaged_cli_capture_and_registry_commands_are_allowed():
    allowed = (
        'plainbrain capture --repo app --today 2026-11-18 --text "Update INBOX.md note"',
        'plainbrain inbox-drop --line "x"',
        'plainbrain registry update --id a --set "next=y"',
        '"/home/me/.venv/bin/plainbrain" capture --repo app --text "Update INBOX.md"',
        '"C:/Users/My Name/.venv/Scripts/plainbrain.exe" capture --repo app --text "Update INBOX.md"',
        '/usr/local/bin/plainbrain capture --repo app --text "Update INBOX.md"',
        "'/home/me/.venv/bin/plainbrain' capture --repo app --text \"fixed > INBOX.md\"",
        'plainbrain capture --repo app --text "fixed echo x > INBOX.md"',
        'plainbrain registry update --id a --set "next=fix > REGISTRY.md"',
    )
    for command in allowed:
        assert inbox_guard._own_command(command), command
        assert _claude("Bash", {"command": command}) == {}, command

    denied = (
        'plainbrain capture --repo app --text "ok" && echo x > INBOX.md',
        '"/home/me/.venv/bin/plainbrain" capture --repo app --text "ok" && echo x > INBOX.md',
        '"/home/me/bin/myplainbrain" capture --repo app --text "ok" && echo x > INBOX.md',
    )
    for command in denied:
        assert not inbox_guard._own_command(command), command
        assert _deny(_claude("Bash", {"command": command})), command


def _load_fresh_inbox_guard():
    spec = importlib.util.spec_from_file_location("_test_inbox_guard_packaged", inbox_guard.__file__)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_packaged_guard_uses_pointer_ignores_cwd_and_bare_filename(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    folder = tmp_path / "my-brain"
    folder.mkdir()
    (fake_home / ".plainbrain").write_text(folder.as_posix() + "\n", encoding="utf-8")

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("BRAIN_ROOT", raising=False)
    monkeypatch.setattr(home, "is_packaged", lambda: True)

    mod = _load_fresh_inbox_guard()

    # Full path to recorded folder's INBOX.md is denied with packaged CLI hint.
    denied = mod.decide({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "cwd": str(folder),
        "tool_input": {"file_path": str(folder / "INBOX.md"), "content": "x"},
    })
    assert _deny(denied)
    reason = denied["hookSpecificOutput"]["permissionDecisionReason"]
    assert "plainbrain capture" in reason and "plainbrain inbox-drop" in reason
    assert "brain.py" not in reason

    # Full path to recorded folder's REGISTRY.md asks with packaged CLI hint.
    asked = mod.decide({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "cwd": str(folder),
        "tool_input": {"file_path": str(folder / "REGISTRY.md"), "content": "x"},
    })
    assert asked["hookSpecificOutput"]["permissionDecision"] == "ask"
    reg_reason = asked["hookSpecificOutput"]["permissionDecisionReason"]
    assert "plainbrain registry" in reg_reason and "brain.py" not in reg_reason

    # Bare INBOX.md / REGISTRY.md with no cwd must NOT be guessed in packaged mode.
    assert not _deny(mod.decide({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "INBOX.md", "content": "x"},
    }))
    assert not _deny(mod.decide({
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo x > INBOX.md"},
    }))
    assert mod.decide({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "REGISTRY.md", "content": "x"},
    }) == {}

    # Unrelated CWD's INBOX.md is allowed (both bare and full path).
    unrelated = tmp_path / "other-project"
    unrelated.mkdir()
    assert not _deny(mod.decide({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "cwd": str(unrelated),
        "tool_input": {"file_path": "INBOX.md", "content": "x"},
    }))
    assert not _deny(mod.decide({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "cwd": str(unrelated),
        "tool_input": {"file_path": str(unrelated / "INBOX.md"), "content": "x"},
    }))

    # BRAIN_ROOT overrides ~/.plainbrain in packaged mode.
    override = tmp_path / "override-brain"
    override.mkdir()
    monkeypatch.setenv("BRAIN_ROOT", str(override))
    mod_override = _load_fresh_inbox_guard()
    assert _deny(mod_override.decide({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "cwd": str(override),
        "tool_input": {"file_path": str(override / "INBOX.md"), "content": "x"},
    }))
    assert not _deny(mod_override.decide({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "cwd": str(folder),
        "tool_input": {"file_path": str(folder / "INBOX.md"), "content": "x"},
    }))
