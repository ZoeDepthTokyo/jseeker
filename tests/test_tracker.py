"""Tests for tracker module."""

import pytest
from pathlib import Path
from jseeker.tracker import TrackerDB
from jseeker.models import (
    Application, Company, Resume, APICost, JobDiscovery,
    ResumeStatus, ApplicationStatus, JobStatus, DiscoveryStatus,
    PipelineResult, ParsedJD, MatchResult, AdaptedResume, ATSScore,
    ContactInfo, TemplateType, ATSPlatform,
)


class TestTrackerDB:
    """Test SQLite CRUD operations."""

    def test_init_creates_tables(self, tmp_db):
        db = TrackerDB(tmp_db)
        apps = db.list_applications()
        assert isinstance(apps, list)
        assert len(apps) == 0

    def test_add_company(self, tmp_db):
        db = TrackerDB(tmp_db)
        company = Company(name="TestCorp", industry="Tech")
        company_id = db.add_company(company)
        assert company_id > 0

    def test_get_or_create_company(self, tmp_db):
        db = TrackerDB(tmp_db)
        id1 = db.get_or_create_company("TestCorp")
        id2 = db.get_or_create_company("TestCorp")
        assert id1 == id2

    def test_add_application(self, tmp_db):
        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")
        app = Application(
            company_id=company_id,
            role_title="Director of Design",
            location="SF",
        )
        app_id = db.add_application(app)
        assert app_id > 0

    def test_get_application(self, tmp_db):
        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")
        app = Application(company_id=company_id, role_title="Designer")
        app_id = db.add_application(app)
        result = db.get_application(app_id)
        assert result is not None
        assert result["role_title"] == "Designer"

    def test_update_application_status(self, tmp_db):
        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")
        app = Application(company_id=company_id, role_title="Designer")
        app_id = db.add_application(app)

        db.update_application_status(app_id, "application_status", "applied")
        result = db.get_application(app_id)
        assert result["application_status"] == "applied"

    def test_update_invalid_field_raises(self, tmp_db):
        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")
        app = Application(company_id=company_id, role_title="Designer")
        app_id = db.add_application(app)

        with pytest.raises(ValueError):
            db.update_application_status(app_id, "invalid_field", "value")

    def test_three_status_pipelines(self, tmp_db):
        """Verify all 3 status pipelines are independent."""
        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")
        app = Application(company_id=company_id, role_title="Designer")
        app_id = db.add_application(app)

        db.update_application_status(app_id, "resume_status", "exported")
        db.update_application_status(app_id, "application_status", "interview")
        db.update_application_status(app_id, "job_status", "closed")

        result = db.get_application(app_id)
        assert result["resume_status"] == "exported"
        assert result["application_status"] == "interview"
        assert result["job_status"] == "closed"

    def test_add_resume(self, tmp_db):
        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")
        app = Application(company_id=company_id, role_title="Designer")
        app_id = db.add_application(app)

        resume = Resume(
            application_id=app_id,
            template_used="ai_ux",
            ats_score=85,
            ats_platform="greenhouse",
        )
        resume_id = db.add_resume(resume)
        assert resume_id > 0

        resumes = db.get_resumes_for_application(app_id)
        assert len(resumes) == 1

    def test_log_cost(self, tmp_db):
        db = TrackerDB(tmp_db)
        cost = APICost(model="haiku", task="test", cost_usd=0.001)
        db.log_cost(cost)
        monthly = db.get_monthly_cost()
        assert monthly >= 0.001

    def test_search_tags(self, tmp_db):
        db = TrackerDB(tmp_db)
        db.add_search_tag("Director of Product")
        db.add_search_tag("UX Director")
        tags = db.list_search_tags()
        assert len(tags) == 2

    def test_search_tag_dedup(self, tmp_db):
        db = TrackerDB(tmp_db)
        db.add_search_tag("Director of Product")
        result = db.add_search_tag("Director of Product")
        assert result is None

    def test_search_tag_normalization_case_insensitive(self, tmp_db):
        db = TrackerDB(tmp_db)
        first = db.add_search_tag("  Director   of Product  ")
        second = db.add_search_tag("director of product")
        tags = db.list_search_tags(active_only=False)

        assert first is not None
        assert second is None
        assert len(tags) == 1
        assert tags[0]["tag"] == "Director of Product"

    def test_job_discovery(self, tmp_db):
        db = TrackerDB(tmp_db)
        disc = JobDiscovery(
            title="Product Director",
            company="TechCorp",
            url="https://example.com/job/123",
            source="indeed",
        )
        disc_id = db.add_discovery(disc)
        assert disc_id is not None

        discoveries = db.list_discoveries()
        assert len(discoveries) == 1

    def test_list_discoveries_status_filter_case_insensitive(self, tmp_db):
        db = TrackerDB(tmp_db)
        db.add_discovery(
            JobDiscovery(
                title="Role A",
                company="A Corp",
                url="https://example.com/a",
                source="indeed",
            )
        )
        db.add_discovery(
            JobDiscovery(
                title="Role B",
                company="B Corp",
                url="https://example.com/b",
                source="indeed",
                status=DiscoveryStatus.STARRED,
            )
        )

        filtered = db.list_discoveries(status="NEW")
        assert len(filtered) == 1
        assert filtered[0]["title"] == "Role A"

    def test_list_discoveries_search_filter(self, tmp_db):
        db = TrackerDB(tmp_db)
        db.add_discovery(
            JobDiscovery(
                title="Senior Product Designer",
                company="DesignCo",
                location="San Francisco",
                url="https://example.com/product-designer",
                source="indeed_us",
                search_tags="Product Design",
            )
        )
        db.add_discovery(
            JobDiscovery(
                title="Backend Engineer",
                company="InfraCo",
                location="Remote",
                url="https://example.com/backend-engineer",
                source="indeed_us",
                search_tags="Engineering",
            )
        )

        results = db.list_discoveries(search="designer")
        assert len(results) == 1
        assert results[0]["company"] == "DesignCo"

    def test_job_discovery_dedup(self, tmp_db):
        db = TrackerDB(tmp_db)
        disc = JobDiscovery(
            title="Product Director",
            url="https://example.com/job/123",
            source="indeed",
        )
        db.add_discovery(disc)
        result = db.add_discovery(disc)
        assert result is None  # Duplicate URL

    def test_dashboard_stats(self, tmp_db):
        db = TrackerDB(tmp_db)
        stats = db.get_dashboard_stats()
        assert "total_applications" in stats
        assert "active_applications" in stats
        assert "avg_ats_score" in stats
        assert "monthly_cost_usd" in stats

    def test_list_applications_filter(self, tmp_db):
        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")

        app1 = Application(company_id=company_id, role_title="Role A")
        app2 = Application(company_id=company_id, role_title="Role B")
        id1 = db.add_application(app1)
        id2 = db.add_application(app2)

        db.update_application_status(id1, "application_status", "applied")

        applied = db.list_applications(application_status="applied")
        assert len(applied) == 1
        assert applied[0]["role_title"] == "Role A"

    def test_create_from_pipeline(self, tmp_db):
        """Test creating application, resume, and company from PipelineResult."""
        db = TrackerDB(tmp_db)

        # Build minimal PipelineResult
        parsed_jd = ParsedJD(
            raw_text="test JD text",
            title="Director of Product",
            company="TestCorp",
            jd_url="https://example.com/job",
            location="San Francisco, CA",
            remote_policy="Hybrid",
            salary_range="$200k - $250k",
        )
        match_result = MatchResult(
            template_type=TemplateType.AI_UX,
            relevance_score=0.85,
        )
        adapted = AdaptedResume(
            summary="Test summary",
            contact=ContactInfo(full_name="Test User"),
        )
        ats_score = ATSScore(
            overall_score=87,
            platform=ATSPlatform.GREENHOUSE,
        )

        result = PipelineResult(
            parsed_jd=parsed_jd,
            match_result=match_result,
            adapted_resume=adapted,
            ats_score=ats_score,
            company="TestCorp",
            role="Director of Product",
            total_cost=0.05,
        )

        # Create from pipeline
        ids = db.create_from_pipeline(result)

        # Verify all IDs returned
        assert "company_id" in ids
        assert "application_id" in ids
        assert "resume_id" in ids
        assert ids["company_id"] > 0
        assert ids["application_id"] > 0
        assert ids["resume_id"] > 0

        # Verify application has correct status
        app = db.get_application(ids["application_id"])
        assert app["resume_status"] == "generated"
        assert app["application_status"] == "not_applied"
        assert app["role_title"] == "Director of Product"
        assert app["location"] == "San Francisco, CA"

        # Verify resume was created
        resumes = db.get_resumes_for_application(ids["application_id"])
        assert len(resumes) == 1
        assert resumes[0]["ats_score"] == 87

    def test_list_all_resumes(self, tmp_db):
        """Test listing all resumes with joined company and role info."""
        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")

        # Create first application with resume
        app1 = Application(company_id=company_id, role_title="Designer")
        app1_id = db.add_application(app1)
        resume1 = Resume(
            application_id=app1_id,
            template_used="ai_ux",
            ats_score=85,
        )
        db.add_resume(resume1)

        # Create second application with resume
        app2 = Application(company_id=company_id, role_title="Product Manager")
        app2_id = db.add_application(app2)
        resume2 = Resume(
            application_id=app2_id,
            template_used="ai_product",
            ats_score=90,
        )
        db.add_resume(resume2)

        # List all resumes
        all_resumes = db.list_all_resumes()

        assert len(all_resumes) == 2
        assert all_resumes[0]["company_name"] == "TestCorp"
        assert all_resumes[1]["company_name"] == "TestCorp"
        # Check both roles are present
        roles = {r["role_title"] for r in all_resumes}
        assert "Designer" in roles
        assert "Product Manager" in roles

    def test_get_next_resume_version(self, tmp_db):
        """Test getting next resume version number."""
        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")
        app = Application(company_id=company_id, role_title="Designer")
        app_id = db.add_application(app)

        # No resumes yet - should return 1
        next_v = db.get_next_resume_version(app_id)
        assert next_v == 1

        # Add version 1
        resume1 = Resume(application_id=app_id, version=1, template_used="ai_ux")
        db.add_resume(resume1)
        next_v = db.get_next_resume_version(app_id)
        assert next_v == 2

        # Add version 2
        resume2 = Resume(application_id=app_id, version=2, template_used="ai_ux")
        db.add_resume(resume2)
        next_v = db.get_next_resume_version(app_id)
        assert next_v == 3

    def test_delete_resume(self, tmp_db, tmp_path):
        """Test deleting a resume."""
        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")
        app = Application(company_id=company_id, role_title="Designer")
        app_id = db.add_application(app)

        # Create test file paths
        pdf_path = tmp_path / "test_resume.pdf"
        pdf_path.write_text("fake pdf")

        resume = Resume(
            application_id=app_id,
            template_used="ai_ux",
            pdf_path=str(pdf_path),
        )
        resume_id = db.add_resume(resume)

        # Verify resume exists
        resumes = db.get_resumes_for_application(app_id)
        assert len(resumes) == 1

        # Delete resume
        result = db.delete_resume(resume_id)
        assert result is True

        # Verify resume is gone from DB
        resumes = db.get_resumes_for_application(app_id)
        assert len(resumes) == 0

        # Verify file was deleted
        assert not pdf_path.exists()

    def test_delete_resume_nonexistent(self, tmp_db):
        """Test deleting a non-existent resume returns False."""
        db = TrackerDB(tmp_db)
        result = db.delete_resume(9999)
        assert result is False

    def test_is_url_known_in_discoveries(self, tmp_db):
        """Test URL detection in job_discoveries table."""
        db = TrackerDB(tmp_db)
        test_url = "https://example.com/job/123"

        # URL should not be known initially
        assert db.is_url_known(test_url) is False

        # Add to discoveries
        disc = JobDiscovery(
            title="Test Job",
            url=test_url,
            source="indeed",
        )
        db.add_discovery(disc)

        # Now URL should be known
        assert db.is_url_known(test_url) is True

    def test_is_url_known_in_applications(self, tmp_db):
        """Test URL detection in applications table."""
        db = TrackerDB(tmp_db)
        test_url = "https://example.com/job/456"
        company_id = db.get_or_create_company("TestCorp")

        # URL should not be known initially
        assert db.is_url_known(test_url) is False

        # Add application with URL
        app = Application(
            company_id=company_id,
            role_title="Designer",
            jd_url=test_url,
        )
        db.add_application(app)

        # Now URL should be known
        assert db.is_url_known(test_url) is True

    def test_is_url_known_unknown(self, tmp_db):
        """Test that unknown URL returns False."""
        db = TrackerDB(tmp_db)
        assert db.is_url_known("https://unknown.example.com") is False

    def test_is_url_known_empty(self, tmp_db):
        """Test that empty URL returns False."""
        db = TrackerDB(tmp_db)
        assert db.is_url_known("") is False

    def test_update_application(self, tmp_db):
        """Test updating application with multiple fields."""
        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")
        app = Application(company_id=company_id, role_title="Designer")
        app_id = db.add_application(app)

        # Update multiple fields
        db.update_application(
            app_id,
            notes="test note",
            location="SF",
            salary_range="$150k - $200k",
        )

        # Verify updates
        result = db.get_application(app_id)
        assert result["notes"] == "test note"
        assert result["location"] == "SF"
        assert result["salary_range"] == "$150k - $200k"
