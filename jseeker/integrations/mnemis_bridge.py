"""MNEMIS bridge — Pattern memory storage for jSeeker (Phase 3+).

Stores successful resume patterns in MNEMIS PROJECT tier.
Promotes proven patterns to GAIA tier for cross-project reuse.
"""

from __future__ import annotations

from typing import Optional


def store_pattern(
    pattern_type: str,
    pattern_data: dict,
    tier: str = "PROJECT",
) -> Optional[str]:
    """Store a resume pattern in MNEMIS memory.

    Args:
        pattern_type: e.g., "bullet_style", "summary_format", "keyword_match"
        pattern_data: The pattern content.
        tier: Memory tier ("PROJECT" or "GAIA").

    Returns:
        Pattern ID if stored, None if MNEMIS unavailable.
    """
    try:
        from rag_intelligence.memory import MnemisClient
        client = MnemisClient()
        return client.store(
            component="jseeker",
            pattern_type=pattern_type,
            data=pattern_data,
            tier=tier,
        )
    except ImportError:
        return None


def recall_patterns(
    pattern_type: str,
    limit: int = 5,
) -> list[dict]:
    """Recall stored patterns from MNEMIS.

    Returns:
        List of pattern dicts, empty if MNEMIS unavailable.
    """
    try:
        from rag_intelligence.memory import MnemisClient
        client = MnemisClient()
        return client.recall(
            component="jseeker",
            pattern_type=pattern_type,
            limit=limit,
        )
    except ImportError:
        return []
