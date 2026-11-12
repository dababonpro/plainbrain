"""`recent` shows the owner's recent work for proposing commitments. It reads and prints, and hides keys."""
import json
import os
import subprocess
import time

import pytest

from scripts import brain, recent


def _session(folder, name, entries, age_days=1):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))
    return path


def _user(text, cwd="C:/Projects/my-website", **extra):
    return {"type": "user", "cwd": cwd, "message": {"role": "user", "content": text}, **extra}


def test_scrub_hides_keys_passwords_and_email_and_shortens():
    line = recent.scrub("deploy with token = abc123def456 and sk-abcdefghijklmnopqrstuv\n mail jane@example.com now")
    assert "abc123def456" not in line and "sk-abcdef" not in line and "jane@example.com" not in line
    assert line.count("[hidden]") == 3 and "\n" not in line
    assert recent.scrub("x" * 500).endswith("...") and len(recent.scrub("x" * 500)) <= recent.PROMPT_CHARS + 3


def test_printable_survives_a_terminal_without_emoji():
    assert recent.printable("ship it 🚀 日本", "cp1252") == "ship it ? ??"
    assert recent.printable("plain", None) == "plain"


def test_sessions_show_the_first_typed_request_per_folder(tmp_path):
    projects = tmp_path / "projects"
    _session(projects / "a", "one.jsonl", [
        {"type": "summary", "summary": "ignored"},
        _user("<command-name>/clear</command-name>"),
        _user("reminder", isMeta=True),
        _user([{"type": "tool_result", "content": "output"}]),
        _user("Fix the checkout bug before Friday"),
        _user("a later request"),
    ])
    _session(projects / "a", "two.jsonl", [_user([{"type": "text", "text": "Add a pricing page"}])], age_days=2)
    _session(projects / "b", "old.jsonl", [_user("Ancient work", cwd="C:/Projects/old-thing")], age_days=40)
    lines = recent.session_lines(tmp_path)
    assert lines[0].startswith("Folder: my-website (2 sessions, latest ")
    assert lines[1:] == ["- Fix the checkout bug before Friday", "- Add a pricing page"]


def test_sessions_report_when_there_are_none(tmp_path):
    assert recent.session_lines(tmp_path) == ["No Claude Code sessions found on this machine."]
    (tmp_path / "projects").mkdir()
    assert recent.session_lines(tmp_path) == [f"No Claude Code sessions in the last {recent.DAYS} days."]


def test_a_broken_session_file_is_skipped(tmp_path):
    folder = tmp_path / "projects" / "a"
    folder.mkdir(parents=True)
    (folder / "bad.jsonl").write_text("not json\n[1, 2]\n", encoding="utf-8")
    assert recent.session_lines(tmp_path) == [f"No Claude Code sessions in the last {recent.DAYS} days."]


def _git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


@pytest.mark.skipif(subprocess.run(["git", "--version"], capture_output=True).returncode != 0, reason="no git")
def test_folder_shows_commits_and_uncommitted_files(tmp_path):
    repo = tmp_path / "my-website"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "a.txt").write_text("one", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "Add the pricing page")
    (repo / "b.txt").write_text("two", encoding="utf-8")
    lines = recent.folder_lines(repo)
    assert lines[0] == "Folder: my-website"
    assert "Commits in the last 14 days: 1" in lines
    assert any(line.endswith("Add the pricing page") for line in lines)
    assert "Uncommitted files: 1" in lines and "- ?? b.txt" in lines


def test_a_folder_without_git_lists_recent_files(tmp_path):
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    lines = recent.folder_lines(tmp_path)
    assert lines[1].startswith("Not a git folder.") and "notes.txt" in lines[1]
    assert recent.folder_lines(tmp_path / "missing") == [f"{tmp_path / 'missing'}: not a folder."]


def test_command_reads_only_and_says_so(tmp_path, capsys):
    _session(tmp_path / "home" / "projects" / "a", "one.jsonl", [_user("Fix the checkout bug")])
    before = sorted(p.as_posix() for p in tmp_path.rglob("*"))
    assert brain.main(["recent", "--claude-sessions", "--claude-home", str(tmp_path / "home")]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Read only. Nothing was written.") and "- Fix the checkout bug" in out
    assert sorted(p.as_posix() for p in tmp_path.rglob("*")) == before
    assert brain.main(["recent"]) == 0
    assert "Name a folder" in capsys.readouterr().out
