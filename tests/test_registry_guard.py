"""A direct edit to REGISTRY.md asks the owner first; registry commands and other files pass."""
from scripts import inbox_guard
from scripts.inbox_guard import decide

REGISTRY = str(inbox_guard.REGISTRY)
HERE = str(inbox_guard.INBOX.parent)


def _claude(tool, tool_input, cwd=HERE):
    return decide({"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": cwd, "tool_input": tool_input})


def _decision(result):
    return result.get("hookSpecificOutput", {}).get("permissionDecision") or result.get("permission")


def test_file_edits_to_the_registry_ask():
    assert _decision(_claude("Write", {"file_path": REGISTRY, "content": "x"})) == "ask"
    assert _decision(_claude("Edit", {"file_path": "REGISTRY.md", "old_string": "a", "new_string": "b"})) == "ask"
    patch = "*** Begin Patch\n*** Update File: REGISTRY.md\n@@\n-a\n+b\n*** End Patch"
    assert _decision(_claude("apply_patch", {"command": patch})) == "ask"


def test_the_ask_names_the_registry_command():
    reason = _claude("Write", {"file_path": REGISTRY})["hookSpecificOutput"]["permissionDecisionReason"]
    assert "brain.py" in reason and "registry" in reason


def test_reads_and_registry_commands_pass():
    assert _claude("Read", {"file_path": REGISTRY}) == {}
    command = 'python scripts/brain.py registry update --root . --today 2026-11-17 --id x --set "next=y" --why "ok"'
    assert _claude("Bash", {"command": command}) == {}
    assert _claude("Bash", {"command": "Get-Content REGISTRY.md"}) == {}


def test_shell_rewrites_of_the_registry_ask():
    assert _decision(_claude("Bash", {"command": "echo x > REGISTRY.md"})) == "ask"
    assert _decision(_claude("PowerShell", {"command": "Set-Content REGISTRY.md x"})) == "ask"


def test_inbox_is_still_denied_not_asked():
    assert _decision(_claude("Write", {"file_path": str(inbox_guard.INBOX)})) == "deny"


def test_a_registry_in_another_folder_is_ignored(tmp_path):
    other = tmp_path / "REGISTRY.md"
    assert _claude("Write", {"file_path": str(other)}, cwd=str(tmp_path)) == {}


def _run_hook(payload, *args):
    import json
    import subprocess
    import sys
    from pathlib import Path

    script = Path(inbox_guard.__file__)
    return subprocess.run([sys.executable, str(script), *args], input=json.dumps(payload),
                          capture_output=True, text=True, cwd=HERE)


def test_codex_gets_a_quiet_allow_instead_of_an_unsupported_ask():
    # Codex marks a hook that returns "ask" as failed and shows an error, so its hook passes --codex.
    payload = {"hook_event_name": "PreToolUse", "tool_name": "apply_patch", "cwd": HERE,
               "tool_input": {"command": "*** Begin Patch\n*** Update File: REGISTRY.md\n@@\n-a\n+b\n*** End Patch"}}
    run = _run_hook(payload, "--codex")
    assert run.returncode == 0 and run.stdout == "{}"
    assert '"ask"' in _run_hook(payload).stdout


def test_codex_still_denies_the_inbox():
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": HERE,
               "tool_input": {"file_path": str(inbox_guard.INBOX)}}
    assert _run_hook(payload, "--codex").returncode == 2


def test_the_codex_hook_command_passes_the_flag():
    import json
    from pathlib import Path

    config = json.loads((Path(HERE) / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    command = config["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "'--codex'" in command


def test_cursor_asks_and_antigravity_allows():
    assert decide({"command": "echo x > REGISTRY.md", "cwd": HERE})["permission"] == "ask"
    assert decide({"toolCall": {"name": "write_to_file", "args": {"TargetFile": REGISTRY}}}) == {"decision": "allow"}
