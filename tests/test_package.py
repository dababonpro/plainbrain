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
    import json
    import re
    import plainbrain
    from plainbrain.assets import assets_dir

    plugin_manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert plainbrain.__version__ == plugin_manifest["version"]
    assert marketplace["plugins"][0]["version"] == plainbrain.__version__
    first_heading = next(
        line for line in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("## ")
    )
    assert re.match(rf"^## {re.escape(plainbrain.__version__)},", first_heading), first_heading
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


def test_data_only_setup_folder_runs_cli_init_without_root(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    from plainbrain import plugin_setup
    target = tmp_path / "my-plainbrain"
    plugin_setup.set_up(target)
    assert (target / ".plainbrain-folder").is_file()
    assert not (target / "plainbrain").exists()
    assert not (target / "scripts").exists()

    env = {**_clean_env(), "PYTHONPATH": str(ROOT), "HOME": str(fake_home), "USERPROFILE": str(fake_home)}
    done = subprocess.run(
        [sys.executable, "-m", "plainbrain.cli", "init"],
        cwd=str(target), env=env, capture_output=True, text=True, timeout=30,
    )
    assert done.returncode == 0, done.stderr
    assert (target / "REGISTRY.md").is_file() and (target / "INBOX.md").is_file()


def test_pyproject_declares_core_stdlib_mcp_extra_scripts_and_existing_assets():
    import tomllib

    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    proj = data["project"]
    assert proj["name"] == "plainbrain"
    assert proj["requires-python"] == ">=3.11"
    assert proj.get("dependencies", []) == []
    assert proj["optional-dependencies"]["mcp"] == ["mcp>=1.30,<2"]
    assert proj["scripts"] == {
        "plainbrain": "plainbrain.cli:main",
        "plainbrain-mcp": "plainbrain.mcp_server:main",
        "plainbrain-guard": "plainbrain.inbox_guard:main",
        "plainbrain-nudge": "plainbrain.capture_nudge:main",
    }
    force_include = data["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert force_include
    for src in force_include:
        assert (ROOT / src).exists(), f"missing force-include source: {src}"


def test_sdist_names_its_contents_and_covers_every_wheel_source():
    import tomllib

    targets = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"]
    include = targets.get("sdist", {}).get("include", [])
    # Without a list, a source archive packs every file .gitignore does not exclude, untracked ones too.
    assert include and all(entry.startswith("/") for entry in include)
    assert "/plainbrain" in include and "/README.md" in include
    for src in targets["wheel"]["force-include"]:
        assert f"/{src}" in include, f"wheel source missing from the sdist: {src}"
    for kept_out in ("/docs", "/tests", "/scripts", "/.claude", "/.claude-plugin"):
        assert kept_out not in include


@pytest.mark.skipif(subprocess.run(["git", "--version"], capture_output=True).returncode != 0, reason="no git")
def test_build_output_rules_do_not_hide_an_owners_folders():
    def ignored(path: str) -> bool:
        done = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=str(ROOT), capture_output=True)
        return done.returncode == 0

    assert ignored("dist/plainbrain.whl") and ignored("build/lib/x.py")
    for path in ("knowledge/build/note.md", "knowledge/dist/note.md", "projects/dist/plan.md"):
        assert not ignored(path), f"{path} would drop out of the owner's backup"
