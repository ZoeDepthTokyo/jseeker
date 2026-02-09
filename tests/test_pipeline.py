"""Tests for pipeline module."""

import json
import pytest
from pathlib import Path
from jseeker.pipeline import _write_metadata
from jseeker.models import ParsedJD, MatchResult, ATSScore, TemplateType, ATSPlatform


class TestWriteMetadata:
    """Test metadata file writing."""

    def test_write_metadata_creates_file(self, tmp_path):
        """Test that metadata.json is created."""
        output_folder = tmp_path / "output"
        output_folder.mkdir()

        parsed_jd = ParsedJD(
            raw_text="test JD",
            title="Director of Product",
            company="TestCorp",
            language="en",
            market="us",
        )
        match_result = MatchResult(
            template_type=TemplateType.AI_UX,
            relevance_score=0.85,
        )
        ats_score = ATSScore(
            overall_score=87,
            matched_keywords=["python", "design", "leadership"],
            missing_keywords=["golang"],
        )

        _write_metadata(output_folder, parsed_jd, match_result, ats_score, 0.05)

        metadata_path = output_folder / "metadata.json"
        assert metadata_path.exists()

    def test_write_metadata_content(self, tmp_path):
        """Test that metadata.json contains correct fields."""
        output_folder = tmp_path / "output"
        output_folder.mkdir()

        parsed_jd = ParsedJD(
            raw_text="test JD",
            title="Director of Product",
            company="TestCorp",
            language="es",
            market="mx",
        )
        match_result = MatchResult(
            template_type=TemplateType.AI_PRODUCT,
            relevance_score=0.92,
        )
        ats_score = ATSScore(
            overall_score=95,
            matched_keywords=["python", "design"],
            missing_keywords=["golang"],
        )

        _write_metadata(output_folder, parsed_jd, match_result, ats_score, 0.07)

        metadata_path = output_folder / "metadata.json"
        content = json.loads(metadata_path.read_text(encoding="utf-8"))

        # Verify all required fields
        assert content["title"] == "Director of Product"
        assert content["company"] == "TestCorp"
        assert content["ats_score"] == 95
        assert content["template"] == "ai_product"
        assert content["cost_usd"] == 0.07
        assert content["language"] == "es"
        assert content["market"] == "mx"
        assert "timestamp" in content
        assert content["relevance_score"] == 0.92

    def test_write_metadata_keywords(self, tmp_path):
        """Test that keywords are present and truncated."""
        output_folder = tmp_path / "output"
        output_folder.mkdir()

        # Create long lists of keywords
        matched = [f"keyword_{i}" for i in range(30)]
        missing = [f"missing_{i}" for i in range(15)]

        parsed_jd = ParsedJD(
            raw_text="test JD",
            title="Test Role",
            company="TestCorp",
        )
        match_result = MatchResult(template_type=TemplateType.HYBRID)
        ats_score = ATSScore(
            overall_score=80,
            matched_keywords=matched,
            missing_keywords=missing,
        )

        _write_metadata(output_folder, parsed_jd, match_result, ats_score, 0.03)

        metadata_path = output_folder / "metadata.json"
        content = json.loads(metadata_path.read_text(encoding="utf-8"))

        # Verify arrays exist
        assert "matched_keywords" in content
        assert "missing_keywords" in content

        # Verify truncation (max 20 matched, 10 missing)
        assert len(content["matched_keywords"]) == 20
        assert len(content["missing_keywords"]) == 10
