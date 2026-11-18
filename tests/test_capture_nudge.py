"""The capture nudge asks once, at the end of a session, for finished work that was not captured."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import capture_nudge

ROOT = Path(__file__).resolve().parents[1]


def _call(name, args, sidechain=False, kind="assistant"):
    return {"type": kind, "isSidechain": sidechain,
            "message": {"content": [{"type": "tool_use", "id": "x", "name": name, "input": args}]}}


def _shell(command, **kw):
    return _call("Bash", {"command": command}, **kw)


def _transcript(tmp_path, rows, name="t.jsonl"):
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_nudge, "STATE", tmp_path / "state")


@pytest.fixture
def brain(tmp_path):
    folder = tmp_path / "my-plainbrain"
    folder.mkdir()
    return folder


def _payload(path, session="s1", active=False, cwd="/home/me/work/website"):
    return {"hook_event_name": "Stop", "session_id": session, "transcript_path": str(path), "cwd": cwd,
            "stop_hook_active": active}


def test_asks_once_for_an_uncaptured_commit(tmp_path, brain):
    path = _transcript(tmp_path, [_shell("cd /home/me/work/api && git commit -m fix")])
    out = capture_nudge.decide(_payload(path), today="2026-11-18", brain=brain)
    assert out["decision"] == "block"
    assert "git commit in api" in out["reason"]
    assert f'--root "{brain.as_posix()}"' in out["reason"] and "--today 2026-11-18" in out["reason"]
    assert capture_nudge.decide(_payload(path), brain=brain) == {}


def test_folder_names_with_spaces(tmp_path, brain):
    path = _transcript(tmp_path, [_shell('cd "C:\\My Projects\\api" && git commit -m fix')])
    out = capture_nudge.decide(_payload(path, cwd="C:\\My Projects\\web site"), brain=brain)
    assert "git commit in api" in out["reason"]
    assert '--repo "web site"' in out["reason"]


def test_a_capture_after_the_work_clears_it(tmp_path, brain):
    path = _transcript(tmp_path, [
        _shell("git commit -m fix"),
        _shell('python scripts/brain.py capture --root . --repo website --text "fixed the form"'),
    ])
    assert capture_nudge.decide(_payload(path), brain=brain) == {}


def test_the_plugin_mcp_capture_tool_counts(tmp_path, brain):
    path = _transcript(tmp_path, [_shell("gh pr create --title x"),
                                  _call("mcp__plugin_plainbrain_plainbrain__capture", {"text": "y"})])
    assert capture_nudge.decide(_payload(path), brain=brain) == {}
    path = _transcript(tmp_path, [_shell("gh pr create --title x"), _call("mcp__plainbrain__capture", {"text": "y"})],
                       name="u.jsonl")
    assert capture_nudge.decide(_payload(path, session="s2"), brain=brain) == {}


def test_jira_moves_count_for_people_who_do_not_commit(tmp_path, brain):
    path = _transcript(tmp_path, [_call("mcp__atlassian__transitionJiraIssue", {"issueIdOrKey": "TECH-1"})])
    assert "Jira moved: TECH-1" in capture_nudge.decide(_payload(path), brain=brain)["reason"]


def test_a_push_alone_is_not_asked_about(tmp_path, brain):
    path = _transcript(tmp_path, [_shell("git push origin main")])
    assert capture_nudge.decide(_payload(path), brain=brain) == {}


def test_new_work_after_an_answer_asks_again(tmp_path, brain):
    rows = [_shell("git commit -m a")]
    assert capture_nudge.decide(_payload(_transcript(tmp_path, rows)), brain=brain)
    rows.append(_shell("git commit -m b"))
    assert capture_nudge.decide(_payload(_transcript(tmp_path, rows)), brain=brain)


def test_quiet_cases(tmp_path, brain):
    path = _transcript(tmp_path, [_shell("git commit -m x")])
    assert capture_nudge.decide(_payload(path, active=True), brain=brain) == {}
    assert capture_nudge.decide(_payload(tmp_path / "missing.jsonl"), brain=brain) == {}
    sub = _transcript(tmp_path, [_shell("git commit -m sub", sidechain=True)], name="sub.jsonl")
    assert capture_nudge.decide(_payload(sub, session="s3"), brain=brain) == {}


def test_a_plugin_that_is_not_set_up_stays_quiet(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_nudge, "data_root", lambda _checkout: None)
    path = _transcript(tmp_path, [_shell("git commit -m x")])
    assert capture_nudge.decide(_payload(path)) == {}


def test_cli_never_fails():
    for raw in ("", "not json", json.dumps({"stop_hook_active": True})):
        run = subprocess.run([sys.executable, str(ROOT / "scripts" / "capture_nudge.py")], input=raw,
                             capture_output=True, text=True)
        assert run.returncode == 0
        json.loads(run.stdout)
