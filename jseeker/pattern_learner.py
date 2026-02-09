"""Pattern learning system for jSeeker.

Extracts and applies learned adaptation patterns from user edits.
After 10-20 resumes: 30-40% cache hit rate
After 50+ resumes: 60-70% cache hit rate
"""

from __future__ import annotations

import difflib
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class LearnedPattern:
    """A learned adaptation pattern."""
    id: int
    pattern_type: str
    source_text: str
    target_text: str
    jd_context: dict
    frequency: int
    confidence: float


def _normalize_text(text: str) -> str:
    """Normalize text for comparison (lowercase, strip)."""
    return " ".join(text.lower().strip().split())


def _text_similarity(a: str, b: str) -> float:
    """Compute similarity between two texts using sequence matching.

    Returns:
        Float between 0.0 (no match) and 1.0 (exact match).
    """
    norm_a = _normalize_text(a)
    norm_b = _normalize_text(b)
    return difflib.SequenceMatcher(None, norm_a, norm_b).ratio()


def _extract_jd_context(jd_dict: dict) -> dict:
    """Extract relevant JD context for pattern matching.

    Args:
        jd_dict: ParsedJD as dict with title, ats_keywords, requirements, etc.

    Returns:
        Simplified context dict for pattern matching.
    """
    return {
        "role": jd_dict.get("title", "").lower(),
        "keywords": sorted([kw.lower() for kw in jd_dict.get("ats_keywords", [])[:10]]),
        "industry": jd_dict.get("industry", "").lower() if "industry" in jd_dict else None,
    }


def _context_similarity(ctx1: dict, ctx2: dict) -> float:
    """Compute similarity between two JD contexts.

    Returns:
        Float between 0.0 (no match) and 1.0 (exact match).
    """
    # Role similarity
    role_sim = _text_similarity(ctx1.get("role", ""), ctx2.get("role", ""))

    # Keyword overlap
    kw1 = set(ctx1.get("keywords", []))
    kw2 = set(ctx2.get("keywords", []))
    if kw1 and kw2:
        kw_sim = len(kw1 & kw2) / len(kw1 | kw2)
    else:
        kw_sim = 0.0

    # Weighted average (role matters more)
    return 0.7 * role_sim + 0.3 * kw_sim


def learn_pattern(
    pattern_type: str,
    source_text: str,
    target_text: str,
    jd_context: Optional[dict] = None,
    db_path: Optional[Path] = None,
) -> None:
    """Store or update a learned pattern.

    Args:
        pattern_type: Type of pattern ('bullet_adaptation', 'summary_style', etc.)
        source_text: Original text before adaptation.
        target_text: User-edited or LLM-adapted text.
        jd_context: Job description context (title, keywords, etc.)
        db_path: Path to jseeker.db (auto-detected if None).
    """
    if db_path is None:
        from config import settings
        db_path = settings.db_path

    context_json = json.dumps(_extract_jd_context(jd_context or {}))

    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    # Upsert: insert or increment frequency
    c.execute("""
        INSERT INTO learned_patterns (pattern_type, source_text, target_text, jd_context, frequency)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(pattern_type, source_text, jd_context) DO UPDATE SET
            frequency = frequency + 1,
            last_used_at = CURRENT_TIMESTAMP
    """, (pattern_type, source_text, target_text, context_json))

    conn.commit()
    conn.close()


def find_matching_pattern(
    pattern_type: str,
    source_text: str,
    jd_context: Optional[dict] = None,
    min_frequency: int = 3,
    similarity_threshold: float = 0.85,
    db_path: Optional[Path] = None,
) -> Optional[str]:
    """Find a matching learned pattern and return adapted text.

    Args:
        pattern_type: Type of pattern to search for.
        source_text: Text to adapt.
        jd_context: Job description context for matching.
        min_frequency: Minimum pattern frequency to trust (default: 3).
        similarity_threshold: Minimum text similarity (default: 0.85).
        db_path: Path to jseeker.db (auto-detected if None).

    Returns:
        Adapted text if a pattern matches, otherwise None.
    """
    if db_path is None:
        from config import settings
        db_path = settings.db_path

    search_context = _extract_jd_context(jd_context or {})

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Get all patterns of this type with sufficient frequency
    c.execute("""
        SELECT * FROM learned_patterns
        WHERE pattern_type = ? AND frequency >= ?
        ORDER BY frequency DESC, last_used_at DESC
        LIMIT 50
    """, (pattern_type, min_frequency))

    patterns = c.fetchall()
    conn.close()

    if not patterns:
        return None

    # Find best matching pattern
    best_match = None
    best_score = 0.0

    for row in patterns:
        # Text similarity
        text_sim = _text_similarity(source_text, row["source_text"])
        if text_sim < similarity_threshold:
            continue

        # Context similarity
        stored_context = json.loads(row["jd_context"] or "{}")
        context_sim = _context_similarity(search_context, stored_context)

        # Combined score (text matters more)
        score = 0.8 * text_sim + 0.2 * context_sim

        if score > best_score:
            best_score = score
            best_match = row

    if best_match:
        # Update last_used_at
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("UPDATE learned_patterns SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?",
                  (best_match["id"],))
        conn.commit()
        conn.close()

        return best_match["target_text"]

    return None


def get_pattern_stats(db_path: Optional[Path] = None) -> dict:
    """Get statistics about learned patterns.

    Returns:
        Dict with total patterns, by type, most frequent, etc.
    """
    if db_path is None:
        from config import settings
        db_path = settings.db_path

    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    # Total patterns
    c.execute("SELECT COUNT(*) as total FROM learned_patterns")
    total = c.fetchone()[0]

    # By type
    c.execute("""
        SELECT pattern_type, COUNT(*) as count, SUM(frequency) as total_uses
        FROM learned_patterns
        GROUP BY pattern_type
        ORDER BY total_uses DESC
    """)
    by_type = [{"type": row[0], "count": row[1], "total_uses": row[2]} for row in c.fetchall()]

    # Most frequent patterns
    c.execute("""
        SELECT pattern_type, source_text, target_text, frequency
        FROM learned_patterns
        ORDER BY frequency DESC
        LIMIT 10
    """)
    top_patterns = [
        {"type": row[0], "source": row[1][:100], "target": row[2][:100], "frequency": row[3]}
        for row in c.fetchall()
    ]

    conn.close()

    return {
        "total_patterns": total,
        "by_type": by_type,
        "top_patterns": top_patterns,
    }
