"""Read-only impact ledger reports for aggregate initiative outcomes."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from scripts.model import valid_date


def load_ledger(root: Path) -> list[dict]:
    path = root / "knowledge" / "impact" / "ledger.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("initiatives"), list):
        raise ValueError("impact ledger must have schema_version 1 and an initiatives list")
    seen: set[str] = set()
    for entry in data["initiatives"]:
        if not isinstance(entry, dict) or not entry.get("id") or entry["id"] in seen:
            raise ValueError("each impact initiative needs a unique id")
        seen.add(entry["id"])
        for field in ("baseline_date", "check_date"):
            value = entry.get(field, "")
            if value and not valid_date(value):
                raise ValueError(f"{entry['id']}: {field} must be YYYY-MM-DD")
        if entry.get("evidence_class") not in ("unvalidated", "directional", "validated"):
            raise ValueError(f"{entry['id']}: invalid evidence_class")
        if entry.get("status") not in ("planned", "measuring", "complete"):
            raise ValueError(f"{entry['id']}: invalid status")
    return data["initiatives"]


def _baseline(entry: dict) -> str:
    value = entry.get("baseline_value") or "pending"
    period = entry.get("baseline_period") or "period pending"
    return f"{value} ({period}; {entry.get('baseline_date') or 'date pending'})"


def due_lines(root: Path, today: str) -> list[str]:
    entries = load_ledger(root)
    result = []
    for e in entries:
        if e.get("status") == "complete":
            continue
        check = e.get("check_date", "")
        if check and check <= today:
            state = "overdue" if check < today else "due"
            result.append(f"- {e['id']}: {e['metric']} check {state} ({check}); baseline {_baseline(e)}; result {e.get('result') or 'pending'}.")
    return result


def impact_report(root: Path, today: str) -> str:
    entries = load_ledger(root)
    lines = [f"# Impact {today}", "", "Aggregate initiative outcomes; evidence is directional unless marked otherwise.", ""]
    due = due_lines(root, today)
    lines += ["## Checks due", *(due or ["- None."]), "", "## Initiatives"]
    if not entries:
        lines.append("- No initiatives recorded.")
    for e in entries:
        result = e.get("result") or "pending"
        result_date = e.get("result_date") or ""
        lines.append(f"- {e['id']} ({e['status']}): {e['metric']}; baseline {_baseline(e)}; check {e.get('check_date') or 'pending'}; result {result}{f' ({result_date})' if result_date else ''}; evidence {e['evidence_class']}.")
    return "\n".join(lines) + "\n"


def review_impact_lines(root: Path, today: str) -> list[str]:
    entries = load_ledger(root)
    if not entries:
        return ["- No initiatives recorded."]
    lines = []
    for e in entries:
        result = e.get("result") or "not measured"
        direction = e.get("movement") or "movement not established"
        lines.append(f"- {e['id']}: {direction}; {e['metric']}; baseline {_baseline(e)}; result {result}; evidence {e['evidence_class']}; status {e['status']}.")
    return lines
