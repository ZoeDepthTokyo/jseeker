"""Tests for matcher fallback behavior."""

from jseeker.matcher import match_templates
from jseeker.models import ParsedJD, TemplateType


def test_match_templates_uses_local_fallback_when_llm_returns_empty(monkeypatch):
    """If LLM ranking is empty, matcher should still return deterministic fallback rankings."""
    monkeypatch.setattr("jseeker.matcher.llm_relevance_score", lambda parsed_jd: [])

    parsed_jd = ParsedJD(raw_text="JD", ats_keywords=["AI", "Design", "Leadership"])
    results = match_templates(parsed_jd)

    assert len(results) == 3
    assert {r.template_type for r in results} == {
        TemplateType.AI_UX,
        TemplateType.AI_PRODUCT,
        TemplateType.HYBRID,
    }
    assert all("fallback" in r.gap_analysis.lower() for r in results)


def test_match_templates_fallback_handles_no_keywords(monkeypatch):
    """Fallback ranking should still return templates even when JD has no ATS keywords."""
    monkeypatch.setattr("jseeker.matcher.llm_relevance_score", lambda parsed_jd: [])

    parsed_jd = ParsedJD(raw_text="JD without keywords", ats_keywords=[])
    results = match_templates(parsed_jd)

    assert len(results) == 3
    assert all(r.relevance_score == 0.0 for r in results)

