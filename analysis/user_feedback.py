from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEEDBACK_PATH = REPO_ROOT / "analysis" / "results" / "user_feedback.jsonl"
FEEDBACK_FIELDS = ("clarity", "usefulness", "actionability", "overwhelm_reduction")


def append_feedback_entry(entry: dict, path: Path = DEFAULT_FEEDBACK_PATH) -> dict:
    payload = dict(entry)
    payload.setdefault("submitted_at", datetime.now(timezone.utc).isoformat())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    return payload


def load_feedback_entries(path: Path = DEFAULT_FEEDBACK_PATH) -> list[dict]:
    if not path.exists():
        return []

    entries: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            cleaned = line.strip()
            if not cleaned:
                continue
            entries.append(json.loads(cleaned))
    return entries


def summarize_feedback(entries: list[dict]) -> dict:
    summary = {
        "count": len(entries),
        "averages": {},
        "by_level": {},
        "recent_notes": [],
    }
    if not entries:
        return summary

    for field in FEEDBACK_FIELDS:
        numeric_values = [float(entry[field]) for entry in entries if field in entry]
        if numeric_values:
            summary["averages"][field] = round(sum(numeric_values) / len(numeric_values), 2)

    level_counts: dict[str, int] = {}
    for entry in entries:
        level_key = str(entry.get("level_key", "unknown"))
        level_counts[level_key] = level_counts.get(level_key, 0) + 1
    summary["by_level"] = level_counts

    noted_entries = [entry for entry in entries if str(entry.get("notes", "")).strip()]
    noted_entries.sort(key=lambda entry: entry.get("submitted_at", ""), reverse=True)
    summary["recent_notes"] = [
        {
            "submitted_at": entry.get("submitted_at", ""),
            "level_key": entry.get("level_key", ""),
            "notes": str(entry.get("notes", "")).strip(),
        }
        for entry in noted_entries[:5]
    ]
    return summary
