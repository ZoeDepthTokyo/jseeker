"""Tests for ATS scorer module."""

import pytest
from proteus.ats_scorer import recommend_format, local_format_score
from proteus.models import ATSPlatform, AdaptedResume, ContactInfo


class TestRecommendFormat:
    """Test format recommendation logic."""

    def test_workday_recommends_docx(self):
        result = recommend_format(ATSPlatform.WORKDAY)
        assert result["primary"] == "docx"

    def test_greenhouse_recommends_pdf(self):
        result = recommend_format(ATSPlatform.GREENHOUSE)
        assert result["primary"] == "pdf"

    def test_lever_recommends_pdf(self):
        result = recommend_format(ATSPlatform.LEVER)
        assert result["primary"] == "pdf"

    def test_icims_recommends_docx(self):
        result = recommend_format(ATSPlatform.ICIMS)
        assert result["primary"] == "docx"

    def test_taleo_recommends_docx(self):
        result = recommend_format(ATSPlatform.TALEO)
        assert result["primary"] == "docx"

    def test_ashby_recommends_pdf(self):
        result = recommend_format(ATSPlatform.ASHBY)
        assert result["primary"] == "pdf"

    def test_unknown_recommends_both(self):
        result = recommend_format(ATSPlatform.UNKNOWN)
        assert result["primary"] == "both"


class TestLocalFormatScore:
    """Test local format scoring (no LLM)."""

    def test_complete_resume_scores_high(self):
        adapted = AdaptedResume(
            summary="A strong leader with 15+ years experience improving retention by 45%",
            experience_blocks=[
                {
                    "company": "Toyota",
                    "role": "Director",
                    "start": "2020",
                    "end": "2025",
                    "bullets": [
                        "Increased retention from 12% to 45% across 10M+ vehicles",
                        "Reduced iteration cycles by 50%",
                        "Led a team of 25+ designers",
                    ],
                }
            ],
            skills_ordered=[{"category": "AI", "skills": ["AI UX"]}],
            contact=ContactInfo(full_name="Test User"),
            education=[],
        )
        result = local_format_score(adapted, ATSPlatform.GREENHOUSE)
        assert result["format_score"] >= 80

    def test_missing_skills_penalized(self):
        adapted = AdaptedResume(
            summary="A leader",
            experience_blocks=[{"bullets": ["Did stuff"]}],
            skills_ordered=[],
            contact=ContactInfo(full_name="Test User"),
        )
        result = local_format_score(adapted, ATSPlatform.WORKDAY)
        assert result["format_score"] < 100
        assert any("skills" in w.lower() for w in result["warnings"])
