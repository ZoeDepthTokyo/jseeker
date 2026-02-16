"""jSeeker Feedback — Edit capture + preference learning."""

from __future__ import annotations

import json
from typing import Optional


def capture_edit(
    resume_id: int,
    field: str,
    original_value: str,
    new_value: str,
    jd_context: Optional[dict] = None,
) -> None:
    """Record a user edit event and learn adaptation pattern.

    Args:
        resume_id: Resume ID being edited.
        field: Field name (e.g., 'summary', 'experience_bullet_0').
        original_value: Original generated value.
        new_value: User-edited value.
        jd_context: Optional JD context (ParsedJD as dict) for pattern learning.
    """
    from jseeker.tracker import tracker_db

    # Record edit event
    conn = tracker_db._conn()
    c = conn.cursor()
    c.execute(
        """INSERT INTO feedback_events
        (resume_id, event_type, field, original_value, new_value)
        VALUES (?, 'edit', ?, ?, ?)""",
        (resume_id, field, original_value, new_value),
    )
    conn.commit()
    conn.close()

    # Learn pattern for content-level fields
    _learn_from_edit(field, original_value, new_value, jd_context)


def _learn_from_edit(
    field: str,
    original: str,
    edited: str,
    jd_context: Optional[dict],
) -> None:
    """Extract and store adaptation pattern from user edit."""
    if not original or not edited or original == edited:
        return

    # Classify edit type
    pattern_type = _classify_edit_type(field)
    if not pattern_type:
        return  # Not a learnable field

    # Store pattern
    from jseeker.pattern_learner import learn_pattern

    learn_pattern(
        pattern_type=pattern_type,
        source_text=original,
        target_text=edited,
        jd_context=jd_context,
    )


def _classify_edit_type(field: str) -> Optional[str]:
    """Map field name to pattern type for learning.

    Returns:
        Pattern type string or None if field is not learnable.
    """
    field_lower = field.lower()

    if "summary" in field_lower:
        return "summary_adaptation"
    elif "bullet" in field_lower or "experience" in field_lower:
        return "bullet_adaptation"
    elif "skill" in field_lower:
        return "skill_adaptation"
    else:
        return None  # Not a learnable field (e.g., contact info)


def get_edit_history(limit: int = 50) -> list[dict]:
    """Get recent edit events."""
    from jseeker.tracker import tracker_db

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
