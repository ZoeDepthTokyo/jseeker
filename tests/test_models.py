"""Tests for Pydantic data models."""

from jseeker.models import (
    ParsedJD,
    ATSScore,
    Application,
    TemplateType,
    ResumeStatus,
    ApplicationStatus,
    JobStatus,
    ATSPlatform,
)


class TestEnums:
    def test_template_types(self):
        assert TemplateType.AI_UX.value == "ai_ux"
        assert TemplateType.AI_PRODUCT.value == "ai_product"
        assert TemplateType.HYBRID.value == "hybrid"

    def test_resume_status_values(self):
        assert ResumeStatus.DRAFT.value == "draft"
        assert ResumeStatus.SUBMITTED.value == "submitted"

    def test_application_status_values(self):
        assert ApplicationStatus.NOT_APPLIED.value == "not_applied"
        assert ApplicationStatus.GHOSTED.value == "ghosted"

    def test_job_status_values(self):
        assert JobStatus.ACTIVE.value == "active"
        assert JobStatus.REPOSTED.value == "reposted"

    def test_ats_platform_values(self):
        assert ATSPlatform.GREENHOUSE.value == "greenhouse"
        assert ATSPlatform.UNKNOWN.value == "unknown"


class TestParsedJD:
    def test_create_minimal(self):
        jd = ParsedJD(raw_text="Some JD")
        assert jd.raw_text == "Some JD"
        assert jd.ats_keywords == []

    def test_create_full(self):
        jd = ParsedJD(
            raw_text="Full JD",
            title="Director",
            company="TechCorp",
            ats_keywords=["AI", "UX"],
            detected_ats=ATSPlatform.GREENHOUSE,
        )
        assert jd.title == "Director"
        assert len(jd.ats_keywords) == 2


class TestApplication:
    def test_create_with_defaults(self):
        app = Application(role_title="Designer")
        assert app.resume_status == ResumeStatus.DRAFT
        assert app.application_status == ApplicationStatus.NOT_APPLIED
        assert app.job_status == JobStatus.ACTIVE

    def test_create_with_statuses(self):
        app = Application(
            role_title="Director",
            resume_status=ResumeStatus.EXPORTED,
            application_status=ApplicationStatus.APPLIED,
            job_status=JobStatus.CLOSED,
        )
        assert app.resume_status == ResumeStatus.EXPORTED


class TestATSScore:
    def test_create_score(self):
        score = ATSScore(
            overall_score=85,
            keyword_match_rate=0.82,
            platform=ATSPlatform.GREENHOUSE,
        )
        assert score.overall_score == 85
        assert score.recommended_format == "both"
