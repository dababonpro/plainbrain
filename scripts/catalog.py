"""Read-only scan of project folders; writes a pointer index, never touches the repos or the registry."""
import json
import re
import subprocess
from datetime import date
from pathlib import Path

from scripts.model import parse_registry, RegistryParseError

ACTIVE_DAYS = 90
CREDENTIALS_RE = re.compile(r"(https?://)[^/@\s]+@")
BADGE_RE = re.compile(r"^(\[!\[|!\[|<)")
SKIP_PREFIXES = ("#", "---", "|", "=", "-", "*", ">", "+", "[", "**")
SETUP_RE = re.compile(r"^(install|run|first,|to (build|run|install|start)|clone|setup|use |\$|\d+[.)] |[a-z_]+: "
                      r"|(kubectl|gradle|npm|yarn|pnpm|docker|git|pip|python|cd) )", re.I)
PLAIN_RE = re.compile(r"\*\*|`")
CARD_FIELDS = ("summary", "role", "track")
NOT_OURS = ("transferred", "retired")
UNFLAGGED = ("no", "ongoing")

JS_FRAMEWORKS = (("next", "Next.js"), ("astro", "Astro"), ("react-native", "React Native"), ("expo", "Expo"),
                 ("@nestjs/core", "NestJS"), ("nuxt", "Nuxt"), ("vue", "Vue"), ("svelte", "Svelte"),
                 ("express", "Express"), ("fastify", "Fastify"), ("electron", "Electron"), ("react", "React"))
PY_FRAMEWORKS = (("django", "Django"), ("fastapi", "FastAPI"), ("flask", "Flask"))
MARKERS = (("Gemfile", "Ruby"), ("go.mod", "Go"), ("composer.json", "PHP"), ("Cargo.toml", "Rust"),
           ("pubspec.yaml", "Flutter"), ("Chart.yaml", "Helm"), ("wp-config.php", "WordPress"),
           ("wp-content", "WordPress"), ("Dockerfile", "Docker"))


def _git(path: Path, *args: str) -> str:
    try:
        # stdin is closed so git never reads the caller's stdin (the MCP server's message pipe).
        out = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=20, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def remote_url(path: Path) -> str:
    """Origin URL with any embedded credentials removed."""
    return CREDENTIALS_RE.sub(r"\1", _git(path, "config", "--get", "remote.origin.url"))


def detect_stack(path: Path) -> list[str]:
    stack: list[str] = []
    package = path / "package.json"
    if package.is_file():
        try:
            data = json.loads(package.read_text(encoding="utf-8"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        except (ValueError, OSError, AttributeError):
            deps = {}
        stack.append("TypeScript" if "typescript" in deps or (path / "tsconfig.json").exists() else "Node")
        stack += [label for key, label in JS_FRAMEWORKS if key in deps][:2]
    py_files = [path / n for n in ("pyproject.toml", "requirements.txt", "setup.py") if (path / n).is_file()]
    if py_files:
        stack.append("Python")
        text = " ".join(p.read_text(encoding="utf-8", errors="replace").lower() for p in py_files)
        stack += [label for key, label in PY_FRAMEWORKS if key in text]
    if (path / "Gemfile").is_file() and "rails" in (path / "Gemfile").read_text(encoding="utf-8", errors="replace"):
        stack.append("Rails")
    for marker, label in MARKERS:
        if (path / marker).exists() and label not in stack:
            stack.append(label)
    if any(path.glob("*.tf")) and "Terraform" not in stack:
        stack.append("Terraform")
    if any(path.glob("*.xcodeproj")) or any(path.glob("*.xcworkspace")):
        stack.append("iOS")
    return stack


def describe(path: Path) -> str:
    """First prose line of the README, else the package.json description."""
    for name in ("README.md", "readme.md", "README.MD", "Readme.md", "README"):
        readme = path / name
        if readme.is_file():
            text = readme.read_text(encoding="utf-8-sig", errors="replace")
            if text.startswith("---"):
                text = text.split("\n---", 2)[-1]
            in_code = False
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("```"):
                    in_code = not in_code
                    continue
                if not in_code and _prose(line):
                    return _clip(PLAIN_RE.sub("", line))
            break
    package = path / "package.json"
    if package.is_file():
        try:
            return _clip(json.loads(package.read_text(encoding="utf-8")).get("description", "") or "")
        except (ValueError, OSError, AttributeError):
            pass
    return ""


def _prose(line: str) -> bool:
    """A sentence about the project, not a heading, list, badge, quote, setup step, or link line."""
    if not line or line.startswith(SKIP_PREFIXES) or BADGE_RE.match(line) or "<a " in line:
        return False
    if line.endswith(":") or SETUP_RE.match(line):
        return False
    return len(re.findall(r"[A-Za-z]{2,}", line)) >= 4


def _clip(text: str, limit: int = 110) -> str:
    text = text.replace("|", "/")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _row(path: Path, name: str, today: str) -> dict:
    is_git = (path / ".git").exists()
    last = _git(path, "log", "-1", "--format=%cs") if is_git else ""
    age = (date.fromisoformat(today) - date.fromisoformat(last)).days if last else None
    return {"name": name, "card": path.name, "path": str(path), "git": is_git, "last": last,
            "active": age is not None and age <= ACTIVE_DAYS, "remote": remote_url(path) if is_git else "",
            "stack": detect_stack(path), "about": describe(path)}


def _subdirs(folder: Path) -> list[Path]:
    return sorted((p for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".")),
                  key=lambda p: p.name.lower())


def scan(folder: Path, today: str) -> list[dict]:
    """One row per repo. A folder with no commits of its own that holds repos is listed as parent/child."""
    rows = []
    for path in _subdirs(folder):
        row = _row(path, path.name, today)
        children = [c for c in _subdirs(path) if (c / ".git").exists()] if not row["last"] else []
        if children:
            rows += [_row(c, f"{path.name}/{c.name}", today) for c in children]
        else:
            rows.append(row)
    return rows


def read_card(root: Path, card: str) -> dict[str, str]:
    """Header fields (summary, role, track) from knowledge/projects/<card>.md, if the card exists."""
    path = root / "knowledge" / "projects" / f"{card}.md"
    if not path.is_file():
        return {}
    fields = {"file": path.name}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("## "):
            break
        key, sep, value = line.partition(":")
        if sep and key.strip() in CARD_FIELDS:
            fields[key.strip()] = value.strip()
    return fields


def registry_pointers(root: Path) -> dict[str, list[str]]:
    registry = root / "REGISTRY.md"
    if not registry.exists():
        return {}
    try:
        doc = parse_registry(registry.read_text(encoding="utf-8"))
    except RegistryParseError:
        return {}
    pointers: dict[str, list[str]] = {}
    for item in doc.items:
        pointer = item.fields.get("pointer", "").strip().rstrip("\\/")
        if pointer and item.fields.get("status") != "done":
            pointers.setdefault(pointer.lower(), []).append(item.id)
    return pointers


def linked_items(pointers: dict[str, list[str]], path: str) -> list[str]:
    """Open registry ids whose pointer is this repo or a folder containing it."""
    path = path.lower()
    return [i for p, ids in pointers.items() if path == p or path.startswith(p + "\\") or path.startswith(p + "/")
            for i in ids]


def _ids(ids: list[str]) -> str:
    return "-" if not ids else ", ".join(ids[:3]) + (f" +{len(ids) - 3} more" if len(ids) > 3 else "")


def catalog_report(sources: list[tuple[str, Path]], root: Path, today: str) -> str:
    pointers = registry_pointers(root)
    lines = ["# Project catalog", "",
             f"Generated {today} by `python scripts/brain.py catalog`. Read-only pointers; rerun to refresh.",
             f"Active means a commit within {ACTIVE_DAYS} days. Commitments stay in REGISTRY.md.",
             "Project cards live beside this file as `<repo-name>.md`; a card's summary, role, and track override the README guess.",
             ""]
    gaps = []
    for area, folder in sources:
        rows = scan(folder, today)
        for r in rows:
            r["info"] = read_card(root, r["card"])
            r["ids"] = linked_items(pointers, r["path"])
        not_ours = [r for r in rows if r["info"].get("role") in NOT_OURS]
        active = [r for r in rows if r["active"] and r not in not_ours]
        dormant = [r for r in rows if not r["active"] and r not in not_ours]
        gaps += [(area, r) for r in active if not r["ids"] and r["info"].get("track") not in UNFLAGGED]
        lines += [f"## {area}: `{folder}`", "",
                  f"{len(active)} active, {len(dormant)} dormant or not tracked, {len(not_ours)} no longer ours.", "",
                  "### Active", "", "| Repo | Last commit | Role | Stack | About | Remote | Registry |",
                  "|---|---|---|---|---|---|---|"]
        for r in sorted(active, key=lambda r: r["last"], reverse=True):
            info = r["info"]
            name = f"[{r['name']}]({info['file']})" if info else r["name"]
            about = _clip(info.get("summary") or r["about"]) or "-"
            lines.append(f"| {name} | {r['last']} | {info.get('role') or '-'} | {', '.join(r['stack']) or '-'}"
                         f" | {about} | {r['remote'] or '-'} | {_ids(r['ids'])} |")
        if not_ours:
            lines += ["", "### No longer ours", ""]
            for r in not_ours:
                summary = r["info"].get("summary") or r["about"]
                lines.append(f"- [{r['name']}]({r['info']['file']}) ({r['info']['role']}){' - ' + summary if summary else ''}")
        lines += ["", "### Dormant", ""]
        for r in sorted(dormant, key=lambda r: r["name"].lower()):
            when = r["last"] or ("no commits" if r["git"] else "not a git repo")
            about = r["info"].get("summary") or r["about"]
            lines.append(f"- {r['name']} ({when}){' - ' + about if about else ''}")
        lines.append("")
    lines += ["## Registry coverage", "",
              "Active repos with no open registry item. For each, decide in a Second Brain session: capture a commitment,"
              " set `track: ongoing` on its card (a steady stream of tickets; each one you own becomes its own registry"
              " task), or set `track: no` (maintenance only, nothing owed).", ""]
    for area, r in gaps:
        subjects = _git(Path(r["path"]), "log", "-3", "--format=%s").splitlines()
        recent = "; ".join(f'"{_clip(s, 70)}"' for s in subjects)
        lines.append(f"- {area} / {r['name']} (last {r['last']}){' - recent: ' + recent if recent else ''}")
    if not gaps:
        lines.append("- None.")
    lines.append("")
    return "\n".join(lines)


def write_catalog(root: Path, sources: list[tuple[str, Path]], today: str) -> int:
    missing = [str(folder) for _, folder in sources if not folder.is_dir()]
    if missing:
        print(f"missing folder: {', '.join(missing)}")
        return 1
    path = root / "knowledge" / "projects" / "INDEX.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(catalog_report(sources, root, today), encoding="utf-8")
    print(f"wrote {path.relative_to(root)}")
    return 0
