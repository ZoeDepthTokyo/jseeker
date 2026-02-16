"""Tests for tracker module."""

import pytest
from jseeker.tracker import TrackerDB
from jseeker.models import (
    Application,
    Company,
    Resume,
    APICost,
    JobDiscovery,
    DiscoveryStatus,
    PipelineResult,
    ParsedJD,
    MatchResult,
    AdaptedResume,
    ATSScore,
    ContactInfo,
    TemplateType,
    ATSPlatform,
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
        db.add_application(app2)

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

    def test_delete_application(self, tmp_db, tmp_path):
        """Test deleting an application and its associated resumes."""
        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")

        # Create application
        app = Application(company_id=company_id, role_title="Designer")
        app_id = db.add_application(app)

        # Create resume with file
        pdf_path = tmp_path / "test_resume.pdf"
        pdf_path.write_text("fake pdf content")
        resume = Resume(
            application_id=app_id,
            template_used="ai_ux",
            pdf_path=str(pdf_path),
            ats_score=85,
        )
        db.add_resume(resume)

        # Verify application and resume exist
        assert db.get_application(app_id) is not None
        assert len(db.get_resumes_for_application(app_id)) == 1
        assert pdf_path.exists()

        # Delete application
        result = db.delete_application(app_id)
        assert result is True

        # Verify application is gone
        assert db.get_application(app_id) is None

        # Verify resumes are gone
        assert len(db.get_resumes_for_application(app_id)) == 0

        # Verify file was deleted
        assert not pdf_path.exists()

    def test_delete_application_with_multiple_resumes(self, tmp_db, tmp_path):
        """Test deleting an application with multiple resume versions."""
        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")

        # Create application
        app = Application(company_id=company_id, role_title="Designer")
        app_id = db.add_application(app)

        # Create multiple resume versions with files
        resume_files = []
        for i in range(3):
            pdf_path = tmp_path / f"resume_v{i+1}.pdf"
            pdf_path.write_text(f"fake pdf v{i+1}")
            resume_files.append(pdf_path)

            resume = Resume(
                application_id=app_id,
                version=i + 1,
                template_used="ai_ux",
                pdf_path=str(pdf_path),
            )
            db.add_resume(resume)

        # Verify all resumes exist
        assert len(db.get_resumes_for_application(app_id)) == 3
        for path in resume_files:
            assert path.exists()

        # Delete application
        result = db.delete_application(app_id)
        assert result is True

        # Verify all resumes are gone
        assert len(db.get_resumes_for_application(app_id)) == 0

        # Verify all files are deleted
        for path in resume_files:
            assert not path.exists()

    def test_delete_application_nonexistent(self, tmp_db):
        """Test deleting a non-existent application returns False."""
        db = TrackerDB(tmp_db)
        result = db.delete_application(9999)
        assert result is False

    def test_delete_application_preserves_company(self, tmp_db):
        """Test that deleting an application doesn't delete the company."""
        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")

        # Create two applications for same company
        app1 = Application(company_id=company_id, role_title="Designer")
        app1_id = db.add_application(app1)

        app2 = Application(company_id=company_id, role_title="Product Manager")
        app2_id = db.add_application(app2)

        # Delete first application
        db.delete_application(app1_id)

        # Verify second application still exists with company
        app2_result = db.get_application(app2_id)
        assert app2_result is not None
        assert app2_result["company_name"] == "TestCorp"
        assert app2_result["company_id"] == company_id


class TestTrackerConcurrency:
    """Test connection pooling and concurrency management."""

    def test_connection_pooling_enabled(self, tmp_db):
        """Test that connection pooling is properly configured."""
        db = TrackerDB(tmp_db)

        # Get connection should be configured with timeout and thread safety
        conn = db._get_conn()

        # Connection should be usable (health check passed)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        assert result[0] == 1

        # Verify connection can be used again (not closed after health check)
        cursor.execute("SELECT 2")
        result2 = cursor.fetchone()
        assert result2[0] == 2

        conn.close()

    def test_connection_health_check(self, tmp_db):
        """Test that _get_conn performs health check on connections."""
        db = TrackerDB(tmp_db)

        # First connection should work
        conn1 = db._get_conn()
        assert conn1 is not None
        cursor1 = conn1.cursor()
        cursor1.execute("SELECT 1")
        assert cursor1.fetchone()[0] == 1
        conn1.close()

        # Second connection should also work (health check passes)
        conn2 = db._get_conn()
        assert conn2 is not None
        cursor2 = conn2.cursor()
        cursor2.execute("SELECT 1")
        assert cursor2.fetchone()[0] == 1
        conn2.close()

    def test_transaction_context_manager(self, tmp_db):
        """Test atomic transaction context manager."""
        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")

        # Use transaction context for atomic operations
        with db._transaction() as (conn, cursor):
            cursor.execute(
                "INSERT INTO applications (company_id, role_title) VALUES (?, ?)",
                (company_id, "Test Role"),
            )
            app_id = cursor.lastrowid

        # Verify the insert was committed
        app = db.get_application(app_id)
        assert app is not None
        assert app["role_title"] == "Test Role"

    def test_transaction_rollback_on_error(self, tmp_db):
        """Test that transaction rolls back on error."""
        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")

        # Count initial applications
        initial_apps = db.list_applications()
        initial_count = len(initial_apps)

        # Try a transaction that will fail
        try:
            with db._transaction() as (conn, cursor):
                cursor.execute(
                    "INSERT INTO applications (company_id, role_title) VALUES (?, ?)",
                    (company_id, "Test Role"),
                )
                # Force an error by inserting invalid data
                cursor.execute(
                    "INSERT INTO applications (company_id, role_title) VALUES (?, ?)",
                    (999999, None),  # Invalid company_id and NULL role_title
                )
        except Exception:
            pass  # Expected to fail

        # Verify rollback - count should be unchanged
        final_apps = db.list_applications()
        assert len(final_apps) == initial_count

    def test_concurrent_updates_no_lock_error(self, tmp_db):
        """Test that concurrent updates don't cause 'database is locked' errors."""
        from concurrent.futures import ThreadPoolExecutor

        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")

        # Create an application
        app = Application(company_id=company_id, role_title="Test Role")
        app_id = db.add_application(app)

        errors = []

        def update_app(field_val):
            """Update application from thread."""
            try:
                db.update_application(app_id, notes=f"Update {field_val}")
            except Exception as e:
                errors.append(str(e))

        # Run 10 concurrent updates
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(update_app, i) for i in range(10)]
            for future in futures:
                future.result()

        # Verify no "database is locked" errors
        locked_errors = [e for e in errors if "database is locked" in e.lower()]
        assert len(locked_errors) == 0, f"Found lock errors: {locked_errors}"

        # Verify application still exists
        result = db.get_application(app_id)
        assert result is not None

    def test_server_side_timestamps(self, tmp_db):
        """Test that timestamps use SQLite CURRENT_TIMESTAMP, not Python datetime."""
        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")

        # Add application (should use CURRENT_TIMESTAMP for created_at)
        app = Application(company_id=company_id, role_title="Test Role")
        app_id = db.add_application(app)

        # Get raw timestamp from database
        conn = db._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT created_at, updated_at FROM applications WHERE id = ?", (app_id,))
        row = cursor.fetchone()
        conn.close()

        # Timestamps should be in SQLite format (YYYY-MM-DD HH:MM:SS)
        # Not Python isoformat with 'T' separator
        created_at = row["created_at"]
        updated_at = row["updated_at"]

        assert created_at is not None
        assert updated_at is not None

        # SQLite timestamps should have space separator, not 'T'
        # and should not have microseconds
        import re

        sqlite_timestamp_pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"
        assert re.match(
            sqlite_timestamp_pattern, created_at
        ), f"created_at '{created_at}' doesn't match SQLite timestamp format"
        assert re.match(
            sqlite_timestamp_pattern, updated_at
        ), f"updated_at '{updated_at}' doesn't match SQLite timestamp format"

    def test_update_uses_server_timestamp(self, tmp_db):
        """Test that update_application_status uses SQLite CURRENT_TIMESTAMP."""
        import time

        db = TrackerDB(tmp_db)
        company_id = db.get_or_create_company("TestCorp")
        app = Application(company_id=company_id, role_title="Test Role")
        app_id = db.add_application(app)

        # Get initial timestamp
        app1 = db.get_application(app_id)
        initial_updated = app1["updated_at"]

        # Wait 1+ seconds for timestamp to change (SQLite has 1-second resolution)
        time.sleep(1.1)
        db.update_application_status(app_id, "application_status", "applied")

        # Get new timestamp
        app2 = db.get_application(app_id)
        new_updated = app2["updated_at"]

        # Verify timestamp changed and is in SQLite format
        assert (
            new_updated != initial_updated
        ), f"Timestamp should have changed: {initial_updated} -> {new_updated}"
        import re

        sqlite_timestamp_pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"
        assert re.match(
            sqlite_timestamp_pattern, new_updated
        ), f"updated_at '{new_updated}' doesn't match SQLite timestamp format"
