"""Tests for pipeline module."""

import json
from jseeker.pipeline import _write_metadata
from jseeker.models import (
    ParsedJD,
    MatchResult,
    ATSScore,
    TemplateType,
    PipelineResult,
    AdaptedResume,
    PDFValidationResult,
)


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


class TestPipelineResultPDFValidation:
    """Test PipelineResult pdf_validation field."""

    def test_pipeline_result_has_pdf_validation_field(self):
        """PipelineResult should have optional pdf_validation defaulting to None."""
        result = PipelineResult(
            parsed_jd=ParsedJD(raw_text="test", title="Test", company="Test"),
            match_result=MatchResult(template_type=TemplateType.HYBRID),
            adapted_resume=AdaptedResume(),
            ats_score=ATSScore(overall_score=80),
        )
        assert hasattr(result, "pdf_validation")
        assert result.pdf_validation is None

    def test_pipeline_result_with_pdf_validation(self):
        """PipelineResult should accept a PDFValidationResult."""
        validation = PDFValidationResult(
            is_valid=True,
            warnings=["Font not embedded"],
            metadata={"page_count": 2},
        )
        result = PipelineResult(
            parsed_jd=ParsedJD(raw_text="test", title="Test", company="Test"),
            match_result=MatchResult(template_type=TemplateType.HYBRID),
            adapted_resume=AdaptedResume(),
            ats_score=ATSScore(overall_score=80),
            pdf_validation=validation,
        )
        assert result.pdf_validation is not None
        assert result.pdf_validation.is_valid is True
        assert result.pdf_validation.warnings == ["Font not embedded"]
        assert result.pdf_validation.metadata["page_count"] == 2

    def test_pipeline_result_pdf_validation_with_issues(self):
        """PipelineResult should handle pdf_validation with issues."""
        validation = PDFValidationResult(
            is_valid=False,
            issues=["No text layer", "Image-based PDF"],
            error="PDF may not be ATS-parseable",
        )
        result = PipelineResult(
            parsed_jd=ParsedJD(raw_text="test", title="Test", company="Test"),
            match_result=MatchResult(template_type=TemplateType.HYBRID),
            adapted_resume=AdaptedResume(),
            ats_score=ATSScore(overall_score=80),
            pdf_validation=validation,
        )
        assert result.pdf_validation.is_valid is False
        assert len(result.pdf_validation.issues) == 2
