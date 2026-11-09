"""The inbox guard protects this folder's inbox wherever the folder is installed."""
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
