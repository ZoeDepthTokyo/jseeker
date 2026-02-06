"""PROTEUS Feedback — Edit capture + preference learning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def capture_edit(
    resume_id: int,
    field: str,
    original_value: str,
    new_value: str,
) -> None:
    """Record a user edit event for preference learning."""
    from proteus.tracker import tracker_db

    conn = tracker_db._conn()
    c = conn.cursor()
    c.execute("""INSERT INTO feedback_events
        (resume_id, event_type, field, original_value, new_value)
        VALUES (?, 'edit', ?, ?, ?)""",
        (resume_id, field, original_value, new_value),
    )
    conn.commit()
    conn.close()


def get_edit_history(limit: int = 50) -> list[dict]:
    """Get recent edit events."""
    from proteus.tracker import tracker_db

    conn = tracker_db._conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM feedback_events ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def detect_patterns(min_edits: int = 5) -> list[str]:
    """Detect recurring edit patterns from feedback events.

    Returns list of preference rules (human-readable).
    """
    events = get_edit_history(limit=100)
    if len(events) < min_edits:
        return []

    # Simple pattern detection: count field-level edit frequencies
    field_counts: dict[str, int] = {}
    for event in events:
        field = event.get("field", "unknown")
        field_counts[field] = field_counts.get(field, 0) + 1

    patterns = []
    for field, count in field_counts.items():
        if count >= min_edits:
            patterns.append(
                f"User frequently edits '{field}' — consider adjusting generation for this field."
            )

    return patterns


def save_preferences(rules: list[str]) -> None:
    """Save detected preference rules to preferences.json."""
    from config import settings
    prefs_path = settings.data_dir / "preferences.json"
    prefs_path.parent.mkdir(parents=True, exist_ok=True)

    existing = {}
    if prefs_path.exists():
        existing = json.loads(prefs_path.read_text(encoding="utf-8"))

    existing["rules"] = rules
    prefs_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
