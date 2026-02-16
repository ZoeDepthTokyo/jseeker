"""Pattern learning system for jSeeker.

Extracts and applies learned adaptation patterns from user edits.
After 10-20 resumes: 30-40% cache hit rate
After 50+ resumes: 60-70% cache hit rate
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


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
        "role": (jd_dict.get("title") or "").lower(),
        "keywords": sorted([(kw or "").lower() for kw in jd_dict.get("ats_keywords", [])[:10]]),
        "industry": (jd_dict.get("industry") or "").lower() if jd_dict.get("industry") else None,
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

    pattern_id = c.lastrowid
    conn.commit()
    conn.close()

    logger.info(f"learn_pattern | type={pattern_type} | pattern_id={pattern_id} | source_len={len(source_text)} | target_len={len(target_text)}")


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
        logger.debug(f"find_matching_pattern | type={pattern_type} | no patterns with min_frequency={min_frequency}")
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

        logger.info(f"find_matching_pattern | type={pattern_type} | MATCH | pattern_id={best_match['id']} | score={best_score:.2f}")
        return best_match["target_text"]

    logger.debug(f"find_matching_pattern | type={pattern_type} | no match above threshold={similarity_threshold}")
    return None


def _classify_domain(role: str, keywords: list) -> str:
    """Classify a JD role + keywords into a broad domain category."""
    text = f"{role} {' '.join(keywords)}".lower()

    domain_signals = {
        "UX / Design": ["ux", "user experience", "user research", "design system", "ui design",
                        "interaction design", "usability", "figma", "sketch"],
        "Product": ["product manager", "product owner", "product lead", "product director",
                    "product strategy", "roadmap", "stakeholder"],
        "Engineering": ["software engineer", "developer", "backend", "frontend", "full stack",
                        "fullstack", "sre", "devops", "infrastructure"],
        "Data / ML": ["data scientist", "data engineer", "machine learning", "ai engineer",
                      "deep learning", "nlp", "tensorflow", "pytorch", "analytics"],
        "Leadership": ["director", "vp", "head of", "chief", "c-level", "executive",
                       "strategic oversight", "cross-functional leadership"],
    }

    matches = {}
    for domain, signals in domain_signals.items():
        score = sum(1 for s in signals if s in text)
        if score > 0:
            matches[domain] = score

    if not matches:
        return "General"

    # Return top match; if Leadership ties with a specialty, combine them
    sorted_domains = sorted(matches.items(), key=lambda x: x[1], reverse=True)
    top = sorted_domains[0][0]
    if len(sorted_domains) > 1 and top == "Leadership":
        return f"{sorted_domains[1][0]} / {top}"
    return top


def get_pattern_stats(db_path: Optional[Path] = None) -> dict:
    """Get statistics about learned patterns.

    Returns:
        Dict with total patterns, by type, most frequent, cache hit rate, cost savings, etc.
    """
    if db_path is None:
        from config import settings
        db_path = settings.db_path

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
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

    # Most frequent patterns (for display)
    c.execute("""
        SELECT id, pattern_type, source_text, target_text, jd_context, frequency, confidence
        FROM learned_patterns
        ORDER BY frequency DESC
        LIMIT 10
    """)
    top_patterns = []
    for row in c.fetchall():
        context = json.loads(row["jd_context"] or "{}")
        role = context.get("role", "N/A")
        keywords = context.get("keywords", [])
        domain = _classify_domain(role, keywords)
        top_patterns.append({
            "id": row["id"],
            "type": row["pattern_type"],
            "source": row["source_text"][:100],
            "target": row["target_text"][:100],
            "frequency": row["frequency"],
            "confidence": row["confidence"],
            "context": role,
            "domain": domain,
        })

    # Calculate cache hit rate
    total_uses = sum(item["total_uses"] for item in by_type)
    total_opportunities = total_uses if total_uses > 0 else 1

    # Patterns with frequency >= 3 are trusted and used
    c.execute("SELECT COALESCE(SUM(frequency), 0) FROM learned_patterns WHERE frequency >= 3")
    cache_hits = c.fetchone()[0]
    hit_rate = (cache_hits / total_opportunities * 100) if total_opportunities > 0 else 0.0

    # Estimate cost savings (each cache hit saves ~$0.01 in Sonnet calls)
    cost_saved = cache_hits * 0.01

    conn.close()

    return {
        "total_patterns": total,
        "by_type": by_type,
        "top_patterns": top_patterns,
        "cache_hit_rate": round(hit_rate, 1),
        "cost_saved": round(cost_saved, 2),
        "total_uses": total_uses,
    }


def analyze_batch_patterns(completed_jobs: list, db_path: Optional[Path] = None) -> dict:
    """Analyze patterns from a batch of completed jobs.

    This is called during the learning pause between batch segments to extract
    insights from the completed resumes that can be applied to the next segment.

    Args:
        completed_jobs: List of BatchJob objects with status=COMPLETED
        db_path: Path to jseeker.db (auto-detected if None)

    Returns:
        Dict with analysis insights (pattern_count, common_roles, etc.)
    """
    if db_path is None:
        from config import settings
        db_path = settings.db_path

    if not completed_jobs:
        return {"pattern_count": 0, "message": "No completed jobs to analyze"}

    logger.info(f"analyze_batch_patterns | analyzing {len(completed_jobs)} completed jobs")

    # Extract patterns from job results
    roles = []
    companies = []
    ats_scores = []

    for job in completed_jobs:
        if job.result:
            if job.result.get("role"):
                roles.append(job.result["role"])
            if job.result.get("company"):
                companies.append(job.result["company"])
            if job.result.get("ats_score"):
                ats_scores.append(job.result["ats_score"])

    # Calculate insights
    avg_ats = sum(ats_scores) / len(ats_scores) if ats_scores else 0
    unique_roles = len(set(roles))
    unique_companies = len(set(companies))

    # Get current pattern stats from DB
    stats = get_pattern_stats(db_path)

    insights = {
        "pattern_count": stats["total_patterns"],
        "jobs_analyzed": len(completed_jobs),
        "unique_roles": unique_roles,
        "unique_companies": unique_companies,
        "avg_ats_score": round(avg_ats, 1),
        "cache_hit_rate": stats["cache_hit_rate"],
        "message": f"Analyzed {len(completed_jobs)} resumes. Pattern library: {stats['total_patterns']} patterns, {stats['cache_hit_rate']}% cache hit rate."
    }

    logger.info(f"analyze_batch_patterns | complete | {insights['message']}")
    return insights
