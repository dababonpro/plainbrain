"""Smoke-test a built Plainbrain wheel in a fresh isolated virtualenv outside the repo."""
from __future__ import annotations

import argparse
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


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed (exit {proc.returncode}): {cmd}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def _verify_core_wheel(wheel: Path, tmp_root: Path, env: dict[str, str]) -> None:
    venv_dir = tmp_root / "venv-core"
    venv.EnvBuilder(with_pip=True).create(str(venv_dir))
    bin_dir, venv_py, ext = _venv_paths(venv_dir)

    _run([str(venv_py), "-m", "pip", "install", "--quiet", "--no-deps", str(wheel)], cwd=tmp_root, env=env)

    for name in CONSOLE_SCRIPTS:
        exe = bin_dir / f"{name}{ext}"
        if not exe.is_file():
            raise AssertionError(f"Expected console script missing: {exe}")

    plainbrain_bin = str(bin_dir / f"plainbrain{ext}")
    data_dir = tmp_root / "data"
    data_dir.mkdir()

    _run([plainbrain_bin, "--help"], cwd=tmp_root, env=env)
    _run([plainbrain_bin, "init", "--root", str(data_dir)], cwd=tmp_root, env=env)
    for fname in ("REGISTRY.md", "INBOX.md", "CONTEXT.md"):
        if not (data_dir / fname).is_file():
            raise AssertionError(f"init did not create {fname} in {data_dir}")

    _run(
        [
            plainbrain_bin,
            "capture",
            "--root",
            str(data_dir),
            "--repo",
            "demo",
            "--today",
            "2026-11-18",
            "--text",
            "Wheel smoke check",
        ],
        cwd=tmp_root,
        env=env,
    )

    _run(
        [plainbrain_bin, "brief", "--root", str(data_dir), "--today", "2026-11-18"],
        cwd=tmp_root,
        env=env,
    )
    brief_path = data_dir / "reviews" / "daily" / "2026-11-18.md"
    if not brief_path.is_file():
        raise AssertionError(f"brief did not create {brief_path}")

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


def _verify_mcp_extra(wheel: Path, tmp_root: Path, env: dict[str, str]) -> None:
    venv_dir = tmp_root / "venv-mcp"
    venv.EnvBuilder(with_pip=True).create(str(venv_dir))
    _, venv_py, _ = _venv_paths(venv_dir)

    _run([str(venv_py), "-m", "pip", "install", "--quiet", f"{wheel}[mcp]"], cwd=tmp_root, env=env)
    _run(
        [str(venv_py), "-c", "from plainbrain import mcp_server; assert callable(mcp_server.main)"],
        cwd=tmp_root,
        env=env,
    )


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
    env = _clean_env()

    with tempfile.TemporaryDirectory(prefix="plainbrain-wheel-smoke-") as td:
        tmp_root = Path(td)
        _verify_core_wheel(wheel, tmp_root, env)
        if args.with_mcp:
            _verify_mcp_extra(wheel, tmp_root, env)

    extras = " (+mcp)" if args.with_mcp else ""
    print(f"Wheel smoke test passed{extras}: {wheel.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
