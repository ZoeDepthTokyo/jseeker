"""Tests for job_monitor.py — Job URL status monitoring."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from jseeker import job_monitor
from jseeker.models import JobStatus


class TestCheckUrlStatus:
    """Test job URL status checking."""

    @patch("jseeker.job_monitor.requests.get")
    def test_check_url_status_active(self, mock_get):
        """Test active job URL returns ACTIVE."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "Apply now for this exciting opportunity!"
        mock_get.return_value = mock_response

        status = job_monitor.check_url_status("https://example.com/job")

        assert status == JobStatus.ACTIVE

    @patch("jseeker.job_monitor.requests.get")
    def test_check_url_status_closed_404(self, mock_get):
        """Test 404 returns CLOSED."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        status = job_monitor.check_url_status("https://example.com/job")

        assert status == JobStatus.CLOSED

    @patch("jseeker.job_monitor.requests.get")
    def test_check_url_status_closed_signal(self, mock_get):
        """Test closure signal in page content returns CLOSED."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "This position has been filled. Thank you for your interest."
        mock_get.return_value = mock_response

        status = job_monitor.check_url_status("https://example.com/job")

        assert status == JobStatus.CLOSED

    @patch("jseeker.job_monitor.requests.get")
    def test_check_url_status_expired_signal(self, mock_get):
        """Test expiry signal returns EXPIRED."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "The posting is closed as of last week."
        mock_get.return_value = mock_response

        status = job_monitor.check_url_status("https://example.com/job")

        assert status == JobStatus.EXPIRED

    @patch("jseeker.job_monitor.requests.get")
    def test_check_url_status_server_error(self, mock_get):
        """Test server error returns ACTIVE (benefit of doubt)."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        status = job_monitor.check_url_status("https://example.com/job")

        assert status == JobStatus.ACTIVE

    @patch("jseeker.job_monitor.requests.get")
    def test_check_url_status_request_exception(self, mock_get):
        """Test request exception returns ACTIVE."""
        mock_get.side_effect = requests.RequestException("Connection error")

        status = job_monitor.check_url_status("https://example.com/job")

        assert status == JobStatus.ACTIVE

    def test_check_url_status_empty_url(self):
        """Test empty URL returns ACTIVE."""
        status = job_monitor.check_url_status("")

        assert status == JobStatus.ACTIVE

    @patch("jseeker.job_monitor.requests.get")
    def test_check_url_status_closure_signals(self, mock_get):
        """Test all closure signals are detected."""
        for signal in job_monitor.CLOSURE_SIGNALS:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = f"Dear candidate, {signal}. Best regards."
            mock_get.return_value = mock_response

            status = job_monitor.check_url_status("https://example.com/job")

            assert status == JobStatus.CLOSED, f"Signal '{signal}' not detected"

    @patch("jseeker.job_monitor.requests.get")
    def test_check_url_status_expiry_signals(self, mock_get):
        """Test all expiry signals are detected."""
        for signal in job_monitor.EXPIRY_SIGNALS:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = f"Notice: {signal} since last week."
            mock_get.return_value = mock_response

            status = job_monitor.check_url_status("https://example.com/job")

            assert status == JobStatus.EXPIRED, f"Signal '{signal}' not detected"

    @patch("jseeker.job_monitor.requests.get")
    def test_check_url_status_case_insensitive(self, mock_get):
        """Test signal detection is case-insensitive."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "This POSITION HAS BEEN FILLED"
        mock_get.return_value = mock_response

        status = job_monitor.check_url_status("https://example.com/job")

        assert status == JobStatus.CLOSED

    @patch("jseeker.job_monitor.requests.get")
    def test_check_url_status_user_agent_header(self, mock_get):
        """Test request includes user agent header."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "Active job"
        mock_get.return_value = mock_response

        job_monitor.check_url_status("https://example.com/job")

        call_args = mock_get.call_args
        assert "headers" in call_args[1]
        assert "User-Agent" in call_args[1]["headers"]


class TestCheckAllActiveJobs:
    """Test bulk job status checking."""

    @patch("jseeker.job_monitor.tracker_db")
    @patch("jseeker.job_monitor.check_url_status")
    def test_check_all_active_jobs_updates_status(self, mock_check, mock_tracker):
        """Test check_all_active_jobs updates changed statuses."""
        mock_tracker.list_applications.return_value = [
            {"id": 1, "jd_url": "https://job1.com", "job_status": "active", "company_name": "Co1", "role_title": "Dev"},
            {"id": 2, "jd_url": "https://job2.com", "job_status": "active", "company_name": "Co2", "role_title": "Eng"},
        ]
        mock_check.side_effect = [JobStatus.CLOSED, JobStatus.ACTIVE]

        changes = job_monitor.check_all_active_jobs()

        assert len(changes) == 1
        assert changes[0]["app_id"] == 1
        assert changes[0]["new_status"] == "closed"
        mock_tracker.update_application_status.assert_called_once_with(1, "job_status", "closed")

    @patch("jseeker.job_monitor.tracker_db")
    @patch("jseeker.job_monitor.check_url_status")
    def test_check_all_active_jobs_updates_timestamp(self, mock_check, mock_tracker):
        """Test check_all_active_jobs updates timestamp even if status unchanged."""
        mock_tracker.list_applications.return_value = [
            {"id": 1, "jd_url": "https://job1.com", "job_status": "active"},
        ]
        mock_check.return_value = JobStatus.ACTIVE

        job_monitor.check_all_active_jobs()

        # Should update timestamp
        mock_tracker.update_application.assert_called()
        call_args = mock_tracker.update_application.call_args[1]
        assert "job_status_checked_at" in call_args

    @patch("jseeker.job_monitor.tracker_db")
    def test_check_all_active_jobs_skips_empty_urls(self, mock_tracker):
        """Test check_all_active_jobs skips apps with no URL."""
        mock_tracker.list_applications.return_value = [
            {"id": 1, "jd_url": "", "job_status": "active"},
            {"id": 2, "jd_url": None, "job_status": "active"},
        ]

        changes = job_monitor.check_all_active_jobs()

        assert len(changes) == 0
        mock_tracker.update_application_status.assert_not_called()

    @patch("jseeker.job_monitor.tracker_db")
    @patch("jseeker.job_monitor.check_url_status")
    def test_check_all_active_jobs_returns_change_details(self, mock_check, mock_tracker):
        """Test check_all_active_jobs returns detailed change info."""
        mock_tracker.list_applications.return_value = [
            {
                "id": 1,
                "jd_url": "https://job1.com",
                "job_status": "active",
                "company_name": "TechCorp",
                "role_title": "Senior Developer",
            },
        ]
        mock_check.return_value = JobStatus.CLOSED

        changes = job_monitor.check_all_active_jobs()

        assert changes[0]["company"] == "TechCorp"
        assert changes[0]["role"] == "Senior Developer"
        assert changes[0]["url"] == "https://job1.com"


class TestGetGhostCandidates:
    """Test ghost candidate detection."""

    @patch("jseeker.job_monitor.tracker_db")
    def test_get_ghost_candidates_finds_stale_applications(self, mock_tracker):
        """Test get_ghost_candidates finds applications with no recent activity."""
        cutoff = datetime.now() - timedelta(days=14)
        old_date = (cutoff - timedelta(days=1)).isoformat()

        mock_tracker.list_applications.return_value = [
            {"id": 1, "last_activity": old_date, "application_status": "applied"},
            {"id": 2, "applied_date": old_date, "application_status": "applied"},
        ]

        ghosts = job_monitor.get_ghost_candidates(days=14)

        assert len(ghosts) == 2
        assert ghosts[0]["id"] == 1
        assert ghosts[1]["id"] == 2

    @patch("jseeker.job_monitor.tracker_db")
    def test_get_ghost_candidates_excludes_recent_activity(self, mock_tracker):
        """Test get_ghost_candidates excludes recent applications."""
        recent_date = (datetime.now() - timedelta(days=7)).isoformat()

        mock_tracker.list_applications.return_value = [
            {"id": 1, "last_activity": recent_date, "application_status": "applied"},
        ]

        ghosts = job_monitor.get_ghost_candidates(days=14)

        assert len(ghosts) == 0

    @patch("jseeker.job_monitor.tracker_db")
    def test_get_ghost_candidates_respects_days_parameter(self, mock_tracker):
        """Test get_ghost_candidates respects custom days parameter."""
        old_date = (datetime.now() - timedelta(days=31)).isoformat()

        mock_tracker.list_applications.return_value = [
            {"id": 1, "last_activity": old_date, "application_status": "applied"},
        ]

        ghosts = job_monitor.get_ghost_candidates(days=30)

        assert len(ghosts) == 1

    @patch("jseeker.job_monitor.tracker_db")
    def test_get_ghost_candidates_handles_missing_dates(self, mock_tracker):
        """Test get_ghost_candidates handles missing date fields."""
        mock_tracker.list_applications.return_value = [
            {"id": 1, "application_status": "applied"},  # No dates
        ]

        ghosts = job_monitor.get_ghost_candidates(days=14)

        assert len(ghosts) == 0

    @patch("jseeker.job_monitor.tracker_db")
    def test_get_ghost_candidates_handles_invalid_dates(self, mock_tracker):
        """Test get_ghost_candidates handles invalid date formats."""
        mock_tracker.list_applications.return_value = [
            {"id": 1, "last_activity": "invalid-date", "application_status": "applied"},
        ]

        ghosts = job_monitor.get_ghost_candidates(days=14)

        assert len(ghosts) == 0

    @patch("jseeker.job_monitor.tracker_db")
    def test_get_ghost_candidates_uses_applied_date_fallback(self, mock_tracker):
        """Test get_ghost_candidates falls back to applied_date."""
        old_date = (datetime.now() - timedelta(days=20)).isoformat()

        mock_tracker.list_applications.return_value = [
            {"id": 1, "applied_date": old_date, "application_status": "applied"},  # No last_activity
        ]

        ghosts = job_monitor.get_ghost_candidates(days=14)

        assert len(ghosts) == 1
