import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SHIM_MAP = {
    "board": "board",
    "brain": "cli",
    "brief": "brief",
    "capture": "capture",
    "capture_nudge": "capture_nudge",
    "catalog": "catalog",
    "doctor": "doctor",
    "filelock": "filelock",
    "flow": "flow",
    "global_hooks": "global_hooks",
    "home": "home",
    "impact": "impact",
    "inbox_guard": "inbox_guard",
    "ingest": "ingest",
    "model": "model",
    "plugin_setup": "plugin_setup",
    "recent": "recent",
    "registry": "registry",
    "research": "research",
    "review": "review",
    "rollup": "rollup",
    "search": "search",
    "unshipped": "unshipped",
}


def _clean_env():
    return {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "CLAUDE_PLUGIN_ROOT", "BRAIN_ROOT")}


def test_package_version_and_checkout_assets_dir():
    import plainbrain
    from plainbrain.assets import assets_dir

    assert plainbrain.__version__ == "1.3.0.dev0"
    found = assets_dir()
    assert found == ROOT
    assert (found / "AGENTS.md").is_file()
    assert (found / "templates" / "note.md").is_file()
    assert (found / "views" / "Plainbrain.base").is_file()
    assert (found / ".claude" / "skills").is_dir()
    assert (found / ".agents" / "skills").is_dir()


def test_core_cli_imports_without_mcp():
    probe = (
        "import sys; sys.modules['mcp'] = None; "
        "import plainbrain.cli, plainbrain.inbox_guard, plainbrain.capture_nudge; "
        "assert callable(plainbrain.cli.main); "
        "assert callable(plainbrain.inbox_guard.main); "
        "assert callable(plainbrain.capture_nudge.main)"
    )
    done = subprocess.run([sys.executable, "-c", probe], cwd=str(ROOT), capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_mcp_server_exposes_main_callable():
    pytest.importorskip("mcp")
    from plainbrain import mcp_server

    assert callable(mcp_server.main)


def test_scripts_shims_alias_plainbrain_module_objects():
    for script_name, pkg_name in SHIM_MAP.items():
        s_mod = importlib.import_module(f"scripts.{script_name}")
        p_mod = importlib.import_module(f"plainbrain.{pkg_name}")
        assert s_mod is p_mod, f"scripts.{script_name} is not plainbrain.{pkg_name}"


def test_scripts_mcp_server_shim_aliases_plainbrain_module():
    pytest.importorskip("mcp")
    s_mod = importlib.import_module("scripts.mcp_server")
    p_mod = importlib.import_module("plainbrain.mcp_server")
    assert s_mod is p_mod


def test_runnable_shims_work_from_unrelated_cwd_with_clean_env(tmp_path):
    env = _clean_env()
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "brain.py"), "--help"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=30,
    )
    assert done.returncode == 0 and "usage:" in done.stdout.lower(), done.stderr

    payload = json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "cwd": str(ROOT),
        "tool_input": {"file_path": str(ROOT / "INBOX.md"), "content": "x"},
    })
    guard = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "inbox_guard.py")],
        input=payload, cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=30,
    )
    assert guard.returncode == 2 and "deny" in guard.stdout, (guard.returncode, guard.stdout, guard.stderr)


def test_plugin_setup_folder_runs_init_standalone(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    from plainbrain import plugin_setup
    target = tmp_path / "my-plainbrain"
    plugin_setup.set_up(target)
    assert (target / "plainbrain" / "cli.py").is_file()
    assert not (target / "plainbrain" / "plugin_setup.py").exists()

    done = subprocess.run(
        [sys.executable, str(target / "scripts" / "brain.py"), "init", "--root", str(target)],
        cwd=str(tmp_path), env=_clean_env(), capture_output=True, text=True, timeout=30,
    )
    assert done.returncode == 0, done.stderr
    assert (target / "REGISTRY.md").is_file() and (target / "INBOX.md").is_file()
