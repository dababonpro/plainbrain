"""The inbox guard protects this folder's inbox wherever the folder is installed."""
from scripts import inbox_guard
from scripts.inbox_guard import decide

INBOX = str(inbox_guard.INBOX)
HERE = str(inbox_guard.INBOX.parent)


def _deny(result):
    return result.get("permission") == "deny" or (
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
