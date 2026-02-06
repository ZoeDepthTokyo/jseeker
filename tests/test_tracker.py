"""Tests for tracker module."""

import pytest
from pathlib import Path
from proteus.tracker import TrackerDB
from proteus.models import (
    Application, Company, Resume, APICost, JobDiscovery,
    ResumeStatus, ApplicationStatus, JobStatus, DiscoveryStatus,
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
