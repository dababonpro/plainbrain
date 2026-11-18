"""Smoke-test a built Plainbrain wheel in a fresh isolated virtualenv outside the repo."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

CONSOLE_SCRIPTS = (
    "plainbrain",
    "plainbrain-mcp",
    "plainbrain-guard",
    "plainbrain-nudge",
)

REQUIRED_ASSETS = (
    "AGENTS.md",
    "templates/note.md",
    "views/Plainbrain.base",
    ".claude/skills/note-creation/SKILL.md",
    ".agents/skills/note-creation/SKILL.md",
)


def _resolve_wheel(target: Path) -> Path:
    if target.is_dir():
        wheels = sorted(target.glob("*.whl"))
        if not wheels:
            raise ValueError(f"No .whl files found in directory: {target}")
        if len(wheels) > 1:
            names = ", ".join(w.name for w in wheels)
            raise ValueError(f"Expected a single .whl in {target}, found {len(wheels)}: {names}")
        return wheels[0].resolve()
    if target.is_file() and target.suffix == ".whl":
        return target.resolve()
    raise ValueError(f"Target must be an existing .whl file or directory containing one: {target}")


def _clean_env() -> dict[str, str]:
    return {
        k: v
        for k, v in os.environ.items()
        if k not in ("PYTHONPATH", "CLAUDE_PLUGIN_ROOT", "BRAIN_ROOT")
    }


def _venv_paths(venv_dir: Path) -> tuple[Path, Path, str]:
    if os.name == "nt":
        bin_dir = venv_dir / "Scripts"
        ext = ".exe"
    else:
        bin_dir = venv_dir / "bin"
        ext = ""
    return bin_dir, bin_dir / f"python{ext}", ext


def _run(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int = 60,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed (exit {proc.returncode}): {cmd}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def _create_venv(venv_dir: Path) -> None:
    venv.EnvBuilder(with_pip=True, symlinks=os.name != "nt").create(str(venv_dir))


def _verify_core_wheel(
    wheel: Path,
    tmp_root: Path,
    env: dict[str, str],
    fake_home: Path,
) -> tuple[Path, Path]:
    venv_dir = tmp_root / "venv-core"
    _create_venv(venv_dir)
    bin_dir, venv_py, ext = _venv_paths(venv_dir)

    _run(
        [str(venv_py), "-m", "pip", "install", "--quiet", "--no-deps", str(wheel)],
        cwd=tmp_root,
        env=env,
        timeout=300,
    )

    for name in CONSOLE_SCRIPTS:
        exe = bin_dir / f"{name}{ext}"
        if not exe.is_file():
            raise AssertionError(f"Expected console script missing: {exe}")

    plainbrain_bin = str(bin_dir / f"plainbrain{ext}")
    guard_bin = str(bin_dir / f"plainbrain-guard{ext}")
    data_dir = tmp_root / "data"
    decoy_dir = tmp_root / "decoy"
    decoy_dir.mkdir()
    (decoy_dir / "REGISTRY.md").write_text("# Registry\n\nfocus:\n", encoding="utf-8")
    (decoy_dir / "INBOX.md").write_text("# Inbox\n\n## Brain Dump\n", encoding="utf-8")

    _run([plainbrain_bin, "--help"], cwd=tmp_root, env=env)
    _run([plainbrain_bin, "setup", "--to", str(data_dir)], cwd=tmp_root, env=env)

    if not (data_dir / ".plainbrain-folder").is_file():
        raise AssertionError(f"setup did not create .plainbrain-folder in {data_dir}")
    gitignore_text = (data_dir / ".gitignore").read_text(encoding="utf-8")
    if "board/" not in gitignore_text or "reviews/" in gitignore_text:
        raise AssertionError(f"Unexpected .gitignore contents in {data_dir}: {gitignore_text!r}")
    if (data_dir / "scripts").exists() or (data_dir / "plainbrain").exists():
        raise AssertionError(f"setup copied code into data folder {data_dir}")
    claude_settings = data_dir / ".claude" / "settings.json"
    if not claude_settings.is_file():
        raise AssertionError(f"setup did not create {claude_settings}")
    if "plainbrain-guard" not in claude_settings.read_text(encoding="utf-8"):
        raise AssertionError(f"Claude settings missing resolved guard command: {claude_settings}")
    home_pointer = fake_home / ".plainbrain"
    if not home_pointer.is_file():
        raise AssertionError(f"setup did not write pointer file {home_pointer}")
    recorded = Path(home_pointer.read_text(encoding="utf-8").strip()).resolve()
    if recorded != data_dir.resolve():
        raise AssertionError(f"Pointer {home_pointer} recorded {recorded}, expected {data_dir.resolve()}")

    _run([plainbrain_bin, "init"], cwd=data_dir, env=env)
    for fname in ("REGISTRY.md", "INBOX.md", "CONTEXT.md"):
        if not (data_dir / fname).is_file():
            raise AssertionError(f"init did not create {fname} in {data_dir}")

    _run(
        [
            plainbrain_bin,
            "capture",
            "--repo",
            "demo",
            "--today",
            "2026-11-18",
            "--text",
            "Wheel smoke check",
        ],
        cwd=decoy_dir,
        env=env,
    )
    if "Wheel smoke check" not in (data_dir / "INBOX.md").read_text(encoding="utf-8"):
        raise AssertionError("capture did not write to data/INBOX.md")
    if "Wheel smoke check" in (decoy_dir / "INBOX.md").read_text(encoding="utf-8"):
        raise AssertionError("capture leaked into decoy/INBOX.md")

    _run([plainbrain_bin, "brief", "--today", "2026-11-18"], cwd=decoy_dir, env=env)
    brief_path = data_dir / "reviews" / "daily" / "2026-11-18.md"
    if not brief_path.is_file():
        raise AssertionError(f"brief did not create {brief_path}")

    _run([plainbrain_bin, "doctor", "--today", "2026-11-18"], cwd=data_dir, env=env)
    _run([plainbrain_bin, "doctor", "--today", "2026-11-18"], cwd=decoy_dir, env=env)

    deny_payload = json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "cwd": str(decoy_dir),
        "tool_input": {"file_path": str(data_dir / "INBOX.md"), "content": "x"},
    })
    deny_proc = _run([guard_bin], cwd=decoy_dir, env=env, input_text=deny_payload, check=False)
    deny_output = f"{deny_proc.stdout}\n{deny_proc.stderr}"
    if deny_proc.returncode != 2 or "deny" not in deny_output or "plainbrain capture" not in deny_output:
        raise AssertionError(
            f"Expected guard deny (exit 2) for data/INBOX.md, got {deny_proc.returncode}: {deny_output}"
        )

    allow_payload = json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "INBOX.md", "content": "x"},
    })
    allow_proc = _run([guard_bin], cwd=decoy_dir, env=env, input_text=allow_payload, check=False)
    allow_output = f"{allow_proc.stdout}\n{allow_proc.stderr}"
    if allow_proc.returncode != 0 or "deny" in allow_output:
        raise AssertionError(
            f"Expected guard allow (exit 0) for bare INBOX.md without cwd, got {allow_proc.returncode}: {allow_output}"
        )

    ephemeral_env = {**env, "PLAINBRAIN_TEMP_ROOT": str(tmp_root)}
    eph_proc = _run([plainbrain_bin, "doctor", "--today", "2026-11-18"], cwd=data_dir, env=ephemeral_env)
    eph_out = eph_proc.stdout.lower()
    if "warn" not in eph_out or ("pipx" not in eph_out and "uv tool install" not in eph_out):
        raise AssertionError(f"Expected ephemeral doctor warning mentioning pipx/uv tool install, got:\n{eph_proc.stdout}")

    assets_check = (
        "from pathlib import Path; "
        "import plainbrain.assets as a; "
        "d = a.assets_dir().resolve(); "
        f"venv = Path({str(venv_dir.resolve())!r}).resolve(); "
        "assert venv in d.parents, f'assets_dir outside venv: {d}'; "
        "assert d.name == '_assets' and d.parent.name == 'plainbrain', f'unexpected assets_dir: {d}'; "
        "assert 'site-packages' in d.parts, f'assets_dir not in site-packages: {d}'; "
        f"req = {list(REQUIRED_ASSETS)!r}; "
        "missing = [r for r in req if not (d / r).is_file()]; "
        "assert not missing, f'missing bundled assets: {missing}'; "
        "print(d)"
    )
    _run([str(venv_py), "-c", assets_check], cwd=tmp_root, env=env)
    return data_dir, decoy_dir


def _verify_mcp_extra(
    wheel: Path,
    tmp_root: Path,
    env: dict[str, str],
    data_dir: Path,
    decoy_dir: Path,
) -> None:
    venv_dir = tmp_root / "venv-mcp"
    _create_venv(venv_dir)
    _, venv_py, _ = _venv_paths(venv_dir)

    _run(
        [str(venv_py), "-m", "pip", "install", "--quiet", f"{wheel}[mcp]"],
        cwd=tmp_root,
        env=env,
        timeout=300,
    )
    mcp_check = (
        "from pathlib import Path; "
        "from plainbrain import mcp_server; "
        "assert callable(mcp_server.main); "
        f"expected = Path({str(data_dir.resolve())!r}).resolve(); "
        "root = mcp_server._root(); "
        "assert root is not None and root.resolve() == expected, f'unexpected _root(): {root}'; "
        "items = mcp_server.open_items(); "
        "assert items, f'expected active items, got: {items}'; "
        "brief = mcp_server.latest_brief(); "
        "assert '2026-11-18' in brief, f'unexpected latest_brief(): {brief[:120]}'; "
        "line = mcp_server.capture('demo', 'MCP wheel check'); "
        "assert 'MCP wheel check' in line, f'unexpected capture(): {line}'; "
        "assert 'MCP wheel check' in (expected / 'INBOX.md').read_text(encoding='utf-8')"
    )
    _run([str(venv_py), "-c", mcp_check], cwd=decoy_dir, env=env)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test a built Plainbrain wheel.")
    parser.add_argument("target", help="Path to a .whl file or a directory containing one .whl.")
    parser.add_argument(
        "--with-mcp",
        action="store_true",
        help="Also verify installing <wheel>[mcp] and importing plainbrain.mcp_server.main.",
    )
    args = parser.parse_args(argv)

    wheel = _resolve_wheel(Path(args.target))
    base_env = _clean_env()

    with tempfile.TemporaryDirectory(prefix="plainbrain-wheel-smoke-") as td:
        tmp_root = Path(td)
        fake_home = tmp_root / "home"
        fake_home.mkdir()
        ephemeral_dir = tmp_root / "ephemeral-temp"
        ephemeral_dir.mkdir()
        env = {
            **base_env,
            "HOME": str(fake_home),
            "USERPROFILE": str(fake_home),
            "PLAINBRAIN_TEMP_ROOT": str(ephemeral_dir),
        }
        data_dir, decoy_dir = _verify_core_wheel(wheel, tmp_root, env, fake_home)
        if args.with_mcp:
            _verify_mcp_extra(wheel, tmp_root, env, data_dir, decoy_dir)

    extras = " (+mcp)" if args.with_mcp else ""
    print(f"Wheel smoke test passed{extras}: {wheel.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
