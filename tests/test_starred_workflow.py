"""Tests for the starred jobs workflow."""

import pytest
from datetime import date
from jseeker.models import JobDiscovery, DiscoveryStatus
from jseeker.tracker import TrackerDB


class TestStarredJobsWorkflow:
    """Test the starred jobs workflow from discovery to batch import."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a temporary test database."""
        db_path = tmp_path / "test_starred.db"
        return TrackerDB(db_path)

    def test_star_and_unstar_job(self, db):
        """Test starring and unstarring a job discovery."""
        # Create a test discovery
        discovery = JobDiscovery(
            title="Senior Product Designer",
            company="Test Corp",
            location="San Francisco, CA",
            url="https://example.com/job/123",
            source="linkedin",
            market="us",
            posting_date=date.today(),
            search_tags="product design, senior",
            status=DiscoveryStatus.NEW,
        )

        discovery_id = db.add_discovery(discovery)
        assert discovery_id is not None

        # Verify initial status is NEW
        discoveries = db.list_discoveries(status="new")
        assert len(discoveries) == 1
        assert discoveries[0]["status"].lower() == "new"

        # Star the job
        db.update_discovery_status(discovery_id, "starred")

        # Verify it's now starred
        starred = db.list_discoveries(status="starred")
        assert len(starred) == 1
        assert starred[0]["id"] == discovery_id
        assert starred[0]["status"].lower() == "starred"

        # Verify it's no longer in NEW
        discoveries = db.list_discoveries(status="new")
        assert len(discoveries) == 0

        # Unstar (set back to NEW)
        db.update_discovery_status(discovery_id, "new")

        # Verify it's back to NEW
        discoveries = db.list_discoveries(status="new")
        assert len(discoveries) == 1
        assert discoveries[0]["status"].lower() == "new"

    def test_list_starred_jobs(self, db):
        """Test listing multiple starred jobs."""
        # Create multiple discoveries
        jobs = [
            JobDiscovery(
                title=f"Job {i}",
                company=f"Company {i}",
                url=f"https://example.com/job/{i}",
                source="linkedin",
                market="us",
                status=DiscoveryStatus.NEW,
            )
            for i in range(5)
        ]

        job_ids = [db.add_discovery(job) for job in jobs]

        # Star 3 of them
        for job_id in job_ids[:3]:
            db.update_discovery_status(job_id, "starred")

        # Verify we can list starred jobs
        starred = db.list_discoveries(status="starred")
        assert len(starred) == 3

        # Verify all starred jobs have URLs
        for job in starred:
            assert job["url"]
            assert job["url"].startswith("https://example.com/job/")

    def test_starred_jobs_have_valid_urls(self, db):
        """Test that starred jobs always have valid URLs for batch import."""
        # Create jobs with and without URLs
        job_with_url = JobDiscovery(
            title="Job with URL",
            company="Company A",
            url="https://example.com/job/valid",
            source="linkedin",
            market="us",
            status=DiscoveryStatus.NEW,
        )

        job_without_url = JobDiscovery(
            title="Job without URL",
            company="Company B",
            url="",  # Empty URL
            source="linkedin",
            market="us",
            status=DiscoveryStatus.NEW,
        )

        id1 = db.add_discovery(job_with_url)
        id2 = db.add_discovery(job_without_url)

        # Star both
        db.update_discovery_status(id1, "starred")
        db.update_discovery_status(id2, "starred")

        # Get starred jobs
        starred = db.list_discoveries(status="starred")
        assert len(starred) == 2

        # Filter to only jobs with valid URLs (like UI does)
        starred_with_urls = [job for job in starred if job.get("url")]
        assert len(starred_with_urls) == 1
        assert starred_with_urls[0]["url"] == "https://example.com/job/valid"

    def test_starred_status_enum(self):
        """Test that the DiscoveryStatus enum includes STARRED."""
        assert hasattr(DiscoveryStatus, "STARRED")
        assert DiscoveryStatus.STARRED.value == "starred"

    def test_status_filter_case_insensitive(self, db):
        """Test that status filtering is case-insensitive."""
        job = JobDiscovery(
            title="Test Job",
            company="Test Corp",
            url="https://example.com/test",
            source="linkedin",
            market="us",
            status=DiscoveryStatus.STARRED,
        )

        job_id = db.add_discovery(job)

        # All these should work
        for status_input in ["starred", "STARRED", "Starred", "StArReD"]:
            results = db.list_discoveries(status=status_input)
            assert len(results) == 1
            assert results[0]["id"] == job_id

    def test_import_starred_workflow_integration(self, db):
        """Test the full workflow: discover -> star -> import to batch."""
        # Step 1: Create discoveries
        jobs = [
            JobDiscovery(
                title=f"Designer {i}",
                company=f"Company {i}",
                url=f"https://greenhouse.io/company{i}/job{i}",
                source="linkedin",
                market="us",
                posting_date=date.today(),
                search_tags="ux design",
                status=DiscoveryStatus.NEW,
            )
            for i in range(10)
        ]

        job_ids = [db.add_discovery(job) for job in jobs]

        # Step 2: User stars interesting jobs (5 of them)
        starred_indices = [0, 2, 4, 6, 8]
        for idx in starred_indices:
            db.update_discovery_status(job_ids[idx], "starred")

        # Step 3: Get starred jobs (simulating Dashboard import)
        starred_jobs = db.list_discoveries(status="starred")
        assert len(starred_jobs) == 5

        # Step 4: Extract URLs for batch processing
        starred_urls = [job["url"] for job in starred_jobs if job.get("url")]
        assert len(starred_urls) == 5

        # Step 5: Verify URLs are valid for batch processing
        for url in starred_urls:
            assert url.startswith("https://")
            assert "company" in url
            assert "job" in url

        # Step 6: Verify original discoveries still exist in DB
        all_discoveries = db.list_discoveries()
        assert len(all_discoveries) == 10

    def test_star_button_updates_status(self, db):
        """Test that clicking star button changes status correctly."""
        # Simulates user clicking the Star button in Job Discovery UI
        job = JobDiscovery(
            title="UX Designer",
            company="Tech Corp",
            url="https://lever.co/techcorp/ux-designer",
            source="indeed",
            market="us",
            status=DiscoveryStatus.NEW,
        )

        job_id = db.add_discovery(job)

        # Simulate star button click (calls update_discovery_status)
        db.update_discovery_status(job_id, "starred")

        # Verify status changed
        starred = db.list_discoveries(status="starred")
        assert len(starred) == 1
        assert starred[0]["id"] == job_id

        # Verify the job is no longer in "new" status
        new_jobs = db.list_discoveries(status="new")
        assert len(new_jobs) == 0

    def test_multiple_markets_starred_workflow(self, db):
        """Test starring jobs from multiple markets."""
        markets = ["us", "uk", "ca", "mx", "es"]

        for i, market in enumerate(markets):
            job = JobDiscovery(
                title=f"Job {market}",
                company=f"Company {market}",
                url=f"https://example.com/{market}/job",
                source="linkedin",
                market=market,
                status=DiscoveryStatus.NEW,
            )
            job_id = db.add_discovery(job)
            db.update_discovery_status(job_id, "starred")

        # Get all starred jobs
        starred = db.list_discoveries(status="starred")
        assert len(starred) == 5

        # Verify each market is represented
        starred_markets = {job["market"] for job in starred}
        assert starred_markets == set(markets)

        # Verify all have URLs for batch import
        starred_urls = [job["url"] for job in starred if job.get("url")]
        assert len(starred_urls) == 5

    def test_starred_jobs_preserved_after_dismissed(self, db):
        """Test that dismissing other jobs doesn't affect starred jobs."""
        # Create 3 jobs
        job_ids = []
        for i in range(3):
            job = JobDiscovery(
                title=f"Job {i}",
                company=f"Company {i}",
                url=f"https://example.com/job/{i}",
                source="linkedin",
                market="us",
                status=DiscoveryStatus.NEW,
            )
            job_ids.append(db.add_discovery(job))

        # Star job 0
        db.update_discovery_status(job_ids[0], "starred")

        # Dismiss jobs 1 and 2
        db.update_discovery_status(job_ids[1], "dismissed")
        db.update_discovery_status(job_ids[2], "dismissed")

        # Verify starred job is still there
        starred = db.list_discoveries(status="starred")
        assert len(starred) == 1
        assert starred[0]["id"] == job_ids[0]

        # Verify dismissed jobs are separate
        dismissed = db.list_discoveries(status="dismissed")
        assert len(dismissed) == 2

    def test_empty_starred_list(self, db):
        """Test behavior when no jobs are starred."""
        # Create some jobs but don't star any
        for i in range(3):
            job = JobDiscovery(
                title=f"Job {i}",
                company=f"Company {i}",
                url=f"https://example.com/job/{i}",
                source="linkedin",
                market="us",
                status=DiscoveryStatus.NEW,
            )
            db.add_discovery(job)

        # Try to get starred jobs
        starred = db.list_discoveries(status="starred")
        assert len(starred) == 0
        assert starred == []
