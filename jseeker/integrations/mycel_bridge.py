"""MYCEL bridge — LLM client via GAIA MYCEL infrastructure.

Falls back to direct Anthropic SDK if MYCEL is not available.
"""

from __future__ import annotations

from typing import Optional


def get_llm_client(provider: str = "anthropic") -> Optional[object]:
    """Try to get LLM client from MYCEL, fall back to direct SDK."""
    try:
        from rag_intelligence.llm import create_llm_client
        return create_llm_client(provider=provider)
    except ImportError:
        return None
