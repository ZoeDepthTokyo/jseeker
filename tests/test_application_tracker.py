"""Tests for Application Tracker UI enhancements (Phase 2, Task #4)."""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from jseeker.models import Application, ApplicationStatus, JobStatus, ResumeStatus
from jseeker.tracker import TrackerDB


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        db_path = Path(tmp.name)
    db = TrackerDB(db_path)
    yield db
    db_path.unlink(missing_ok=True)


class TestSalaryFields:
    """Test salary field storage and retrieval."""

    def test_salary_fields_stored_correctly(self, temp_db):
        """Test that salary fields are stored and retrieved correctly."""
        # Create application with salary data
        app = Application(
            company_id=temp_db.get_or_create_company("Test Corp"),
            role_title="Senior Software Engineer",
            jd_url="https://example.com/job/123",
            salary_min=120000,
            salary_max=150000,
            salary_currency="USD",
            relevance_score=0.85,
        )

        app_id = temp_db.add_application(app)
        assert app_id > 0

        # Retrieve and verify
        retrieved = temp_db.get_application(app_id)
        assert retrieved is not None
        assert retrieved["salary_min"] == 120000
        assert retrieved["salary_max"] == 150000
        assert retrieved["salary_currency"] == "USD"

    def test_salary_fields_optional(self, temp_db):
        """Test that salary fields are optional (NULL handling)."""
        # Create application without salary data
        app = Application(
            company_id=temp_db.get_or_create_company("Test Corp"),
            role_title="Junior Developer",
            jd_url="https://example.com/job/456",
            relevance_score=0.65,
        )

        app_id = temp_db.add_application(app)
        assert app_id > 0

        # Retrieve and verify NULL fields
        retrieved = temp_db.get_application(app_id)
        assert retrieved is not None
        assert retrieved["salary_min"] is None
        assert retrieved["salary_max"] is None
        assert retrieved["salary_currency"] == "USD"  # Default value

    def test_salary_fields_update(self, temp_db):
        """Test updating salary fields on existing application."""
        # Create application without salary
        app = Application(
            company_id=temp_db.get_or_create_company("Test Corp"),
            role_title="Mid-Level Engineer",
            jd_url="https://example.com/job/789",
            relevance_score=0.75,
        )

        app_id = temp_db.add_application(app)

        # Update with salary data
        temp_db.update_application(
            app_id, salary_min=100000, salary_max=130000, salary_currency="EUR"
        )

        # Verify update
        retrieved = temp_db.get_application(app_id)
        assert retrieved["salary_min"] == 100000
        assert retrieved["salary_max"] == 130000
        assert retrieved["salary_currency"] == "EUR"

    def test_salary_currency_options(self, temp_db):
        """Test different currency options."""
        currencies = ["USD", "EUR", "GBP", "MXN"]

        for i, currency in enumerate(currencies):
            app = Application(
                company_id=temp_db.get_or_create_company(f"Company {i}"),
                role_title=f"Role {i}",
                salary_min=50000,
                salary_max=70000,
                salary_currency=currency,
            )

            app_id = temp_db.add_application(app)
            retrieved = temp_db.get_application(app_id)
            assert retrieved["salary_currency"] == currency

    def test_salary_zero_values(self, temp_db):
        """Test handling of zero salary values."""
        app = Application(
            company_id=temp_db.get_or_create_company("Test Corp"),
            role_title="Intern",
            salary_min=0,
            salary_max=0,
            salary_currency="USD",
        )

        app_id = temp_db.add_application(app)
        retrieved = temp_db.get_application(app_id)

        # Zero values should be stored as 0, not NULL
        assert retrieved["salary_min"] == 0
        assert retrieved["salary_max"] == 0


class TestRelevanceScore:
    """Test relevance score validation and storage."""

    def test_relevance_range_validation(self, temp_db):
        """Test that relevance score is within 0-1 range (stored as float)."""
        # Valid relevance scores (0.0 to 1.0)
        valid_scores = [0.0, 0.25, 0.50, 0.75, 1.0]

        for score in valid_scores:
            app = Application(
                company_id=temp_db.get_or_create_company("Test Corp"),
                role_title=f"Role {score}",
                relevance_score=score,
            )

            app_id = temp_db.add_application(app)
            retrieved = temp_db.get_application(app_id)
            assert abs(retrieved["relevance_score"] - score) < 0.001

    def test_relevance_score_categories(self, temp_db):
        """Test relevance score categories (Low/Medium/Good/Excellent)."""
        # Test all four categories
        categories = {
            "Low (0-25%)": 0.20,
            "Medium (26-50%)": 0.40,
            "Good (51-75%)": 0.65,
            "Excellent (76-100%)": 0.90,
        }

        for category, score in categories.items():
            app = Application(
                company_id=temp_db.get_or_create_company("Test Corp"),
                role_title=category,
                relevance_score=score,
            )

            app_id = temp_db.add_application(app)
            retrieved = temp_db.get_application(app_id)
            assert abs(retrieved["relevance_score"] - score) < 0.001


class TestTrackerIntegration:
    """Test tracker functionality with new fields."""

    def test_list_applications_with_salary(self, temp_db):
        """Test listing applications includes salary fields."""
        # Create multiple applications with varying salary data
        apps_data = [
            {"role": "Senior Dev", "min": 120000, "max": 150000, "currency": "USD"},
            {"role": "Mid Dev", "min": 90000, "max": 110000, "currency": "EUR"},
            {"role": "Junior Dev", "min": None, "max": None, "currency": "USD"},
        ]

        for data in apps_data:
            app = Application(
                company_id=temp_db.get_or_create_company("Test Corp"),
                role_title=data["role"],
                salary_min=data["min"],
                salary_max=data["max"],
                salary_currency=data["currency"],
                relevance_score=0.75,
            )
            temp_db.add_application(app)

        # List all applications
        apps = temp_db.list_applications()
        assert len(apps) == 3

        # Verify salary fields are present
        for app in apps:
            assert "salary_min" in app
            assert "salary_max" in app
            assert "salary_currency" in app

        # Verify specific values
        senior = [a for a in apps if a["role_title"] == "Senior Dev"][0]
        assert senior["salary_min"] == 120000
        assert senior["salary_max"] == 150000
        assert senior["salary_currency"] == "USD"

        junior = [a for a in apps if a["role_title"] == "Junior Dev"][0]
        assert junior["salary_min"] is None
        assert junior["salary_max"] is None

    def test_filter_applications_by_status(self, temp_db):
        """Test filtering applications preserves salary data."""
        # Create applications with different statuses
        for i, status in enumerate(
            [ApplicationStatus.NOT_APPLIED, ApplicationStatus.APPLIED, ApplicationStatus.INTERVIEW]
        ):
            app = Application(
                company_id=temp_db.get_or_create_company(f"Company {i}"),
                role_title=f"Role {i}",
                application_status=status,
                salary_min=100000 + (i * 10000),
                salary_max=120000 + (i * 10000),
                salary_currency="USD",
            )
            temp_db.add_application(app)

        # Filter by status
        applied_apps = temp_db.list_applications(application_status="applied")
        assert len(applied_apps) == 1
        assert applied_apps[0]["salary_min"] == 110000
        assert applied_apps[0]["salary_max"] == 130000

    def test_update_application_salary_fields(self, temp_db):
        """Test updating salary fields through update_application method."""
        app = Application(
            company_id=temp_db.get_or_create_company("Test Corp"),
            role_title="Test Role",
            relevance_score=0.50,
        )

        app_id = temp_db.add_application(app)

        # Update salary fields
        temp_db.update_application(
            app_id, salary_min=95000, salary_max=115000, salary_currency="GBP"
        )

        # Verify update
        updated = temp_db.get_application(app_id)
        assert updated["salary_min"] == 95000
        assert updated["salary_max"] == 115000
        assert updated["salary_currency"] == "GBP"


class TestDatabaseMigration:
    """Test database migration adds columns correctly."""

    def test_migration_adds_salary_columns(self, temp_db):
        """Test that migration successfully adds salary columns."""
        # The fixture already runs migrations, verify columns exist
        conn = temp_db._conn()
        c = conn.cursor()

        c.execute("PRAGMA table_info(applications)")
        columns = {row[1] for row in c.fetchall()}

        assert "salary_min" in columns
        assert "salary_max" in columns
        assert "salary_currency" in columns

        conn.close()

    def test_migration_idempotent(self, temp_db):
        """Test that migration can run multiple times without errors."""
        from jseeker.tracker import _run_migrations

        # Run migration again
        _run_migrations(temp_db.db_path)

        # Verify database is still functional
        app = Application(
            company_id=temp_db.get_or_create_company("Test Corp"),
            role_title="Test Role",
            salary_min=100000,
            salary_max=120000,
        )

        app_id = temp_db.add_application(app)
        assert app_id > 0

        retrieved = temp_db.get_application(app_id)
        assert retrieved["salary_min"] == 100000


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_very_large_salary_values(self, temp_db):
        """Test handling of very large salary values."""
        app = Application(
            company_id=temp_db.get_or_create_company("Big Tech"),
            role_title="Principal Engineer",
            salary_min=500000,
            salary_max=800000,
            salary_currency="USD",
        )

        app_id = temp_db.add_application(app)
        retrieved = temp_db.get_application(app_id)

        assert retrieved["salary_min"] == 500000
        assert retrieved["salary_max"] == 800000

    def test_inverted_salary_range(self, temp_db):
        """Test that inverted salary range (max < min) is stored as-is."""
        # Note: Validation should happen at UI layer, not DB layer
        app = Application(
            company_id=temp_db.get_or_create_company("Test Corp"),
            role_title="Test Role",
            salary_min=120000,
            salary_max=100000,  # Intentionally inverted
            salary_currency="USD",
        )

        app_id = temp_db.add_application(app)
        retrieved = temp_db.get_application(app_id)

        # DB stores as-is, validation is UI responsibility
        assert retrieved["salary_min"] == 120000
        assert retrieved["salary_max"] == 100000

    def test_partial_salary_data(self, temp_db):
        """Test applications with only min or only max salary."""
        # Only min
        app1 = Application(
            company_id=temp_db.get_or_create_company("Company A"),
            role_title="Role 1",
            salary_min=100000,
            salary_max=None,
        )

        app1_id = temp_db.add_application(app1)
        retrieved1 = temp_db.get_application(app1_id)
        assert retrieved1["salary_min"] == 100000
        assert retrieved1["salary_max"] is None

        # Only max
        app2 = Application(
            company_id=temp_db.get_or_create_company("Company B"),
            role_title="Role 2",
            salary_min=None,
            salary_max=150000,
        )

        app2_id = temp_db.add_application(app2)
        retrieved2 = temp_db.get_application(app2_id)
        assert retrieved2["salary_min"] is None
        assert retrieved2["salary_max"] == 150000
