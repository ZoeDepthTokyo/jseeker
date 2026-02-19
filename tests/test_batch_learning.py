"""Tests for batch learning pause and pattern analysis functionality."""

from __future__ import annotations

import time
from unittest.mock import patch, MagicMock
import pytest

from jseeker.batch_processor import BatchProcessor, BatchJobStatus as JobStatus
from jseeker.pattern_learner import analyze_batch_patterns

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_tracker_db():
    """Mock tracker_db for testing."""
    with patch("jseeker.batch_processor.tracker_db") as mock_db:
        mock_db.is_url_known.return_value = False
        mock_db.create_batch_job.return_value = "test_batch_123"
        mock_db.update_batch_job.return_value = None
        mock_db.create_batch_job_item.return_value = 1
        mock_db.create_from_pipeline.return_value = {
            "application_id": 1,
            "resume_id": 1,
            "company_id": 1,
        }
        mock_db.update_application.return_value = None
        yield mock_db


@pytest.fixture
def mock_pipeline():
    """Mock pipeline functions for testing."""
    with (
        patch("jseeker.batch_processor.extract_jd_from_url") as mock_extract,
        patch("jseeker.batch_processor.run_pipeline") as mock_run,
    ):

        # Mock JD extraction
        mock_extract.return_value = (
            "Test job description",
            {
                "success": True,
                "company": "Test Company",
                "selectors_tried": [],
                "method": "selector",
            },
        )

        # Mock pipeline result
        mock_result = MagicMock()
        mock_result.company = "Test Company"
        mock_result.role = "Test Role"
        mock_result.ats_score.overall_score = 85
        mock_result.total_cost = 0.05
        mock_run.return_value = mock_result

        yield mock_extract, mock_run


# ── Tests ───────────────────────────────────────────────────────────────────


def test_batch_processor_constants():
    """Test that batch processor has correct constants."""
    assert BatchProcessor.BATCH_SEGMENT_SIZE == 10
    assert BatchProcessor.MAX_BATCH_SIZE == 20


def test_batch_processor_enforces_max_size(mock_tracker_db, mock_pipeline):
    """Test that batch processor truncates to MAX_BATCH_SIZE."""
    processor = BatchProcessor(max_workers=2)

    # Create 25 URLs (exceeds limit)
    urls = [f"https://example.com/job{i}" for i in range(25)]

    processor.submit_batch(urls)
    progress = processor.get_progress()

    # Should truncate to 20
    assert progress.total == 20
    assert len(processor.jobs) == 20


def test_batch_progress_segment_fields():
    """Test that BatchProgress has segment tracking fields."""
    from jseeker.batch_processor import BatchProgress

    progress = BatchProgress(total=20, total_segments=2, current_segment=1)

    assert progress.total_segments == 2
    assert progress.current_segment == 1
    assert not progress.learning_phase


def test_batch_progress_to_dict_includes_segments():
    """Test that BatchProgress.to_dict() includes segment fields."""
    from jseeker.batch_processor import BatchProgress

    progress = BatchProgress(total=20, total_segments=2, current_segment=1, learning_phase=False)

    data = progress.to_dict()

    assert "total_segments" in data
    assert "current_segment" in data
    assert "learning_phase" in data
    assert data["total_segments"] == 2
    assert data["current_segment"] == 1
    assert not data["learning_phase"]


def test_batch_segments_calculated_correctly(mock_tracker_db, mock_pipeline):
    """Test that segment count is calculated correctly."""
    processor = BatchProcessor(max_workers=2)

    # Test various batch sizes
    test_cases = [
        (5, 1),  # 5 URLs = 1 segment
        (10, 1),  # 10 URLs = 1 segment
        (11, 2),  # 11 URLs = 2 segments
        (15, 2),  # 15 URLs = 2 segments
        (20, 2),  # 20 URLs = 2 segments
    ]

    for url_count, expected_segments in test_cases:
        urls = [f"https://example.com/job{i}" for i in range(url_count)]
        processor.submit_batch(urls)
        progress = processor.get_progress()

        assert (
            progress.total_segments == expected_segments
        ), f"Expected {expected_segments} segments for {url_count} URLs, got {progress.total_segments}"


def test_learning_pause_triggered_at_segment_boundary(mock_tracker_db, mock_pipeline):
    """Test that learning pause is triggered after 10 jobs."""
    processor = BatchProcessor(max_workers=1)

    # Create 15 URLs (2 segments)
    urls = [f"https://example.com/job{i}" for i in range(15)]

    # Mock pattern analysis to avoid DB access
    with patch("jseeker.pattern_learner.get_pattern_stats") as mock_stats:
        mock_stats.return_value = {
            "total_patterns": 5,
            "cache_hit_rate": 50.0,
            "by_type": [],
            "top_patterns": [],
            "cost_saved": 0.5,
            "total_uses": 10,
        }

        processor.submit_batch(urls)

        # Wait for first 10 jobs to complete and learning pause to trigger
        timeout = 20  # seconds
        start = time.time()
        learning_phase_seen = False

        while time.time() - start < timeout:
            progress = processor.get_progress()
            jobs_done = progress.completed + progress.failed + progress.skipped

            # Check if we've hit the learning pause
            if progress.learning_phase or (jobs_done == 10 and progress.paused):
                learning_phase_seen = True
                break

            time.sleep(0.5)

        progress = processor.get_progress()
        jobs_done = progress.completed + progress.failed + progress.skipped

        # Should have triggered learning pause after 10 jobs
        assert jobs_done >= 10, f"Expected at least 10 jobs done, got {jobs_done}"
        # Learning phase should have been triggered (even if it already auto-resumed)
        assert (
            learning_phase_seen or progress.current_segment > 1
        ), "Learning phase should have been triggered or segment should have advanced"

        # Cleanup
        processor.stop()


def test_analyze_batch_patterns_basic():
    """Test analyze_batch_patterns with mock completed jobs."""
    from jseeker.batch_processor import BatchJob

    # Create mock completed jobs
    jobs = []
    for i in range(5):
        job = BatchJob(url=f"https://example.com/job{i}")
        job.status = JobStatus.COMPLETED
        job.result = {
            "company": f"Company {i}",
            "role": "Software Engineer",
            "ats_score": 80 + i,
        }
        jobs.append(job)

    # Mock DB to avoid actual database access
    with patch("jseeker.pattern_learner.get_pattern_stats") as mock_stats:
        mock_stats.return_value = {
            "total_patterns": 42,
            "cache_hit_rate": 65.5,
            "by_type": [],
            "top_patterns": [],
            "cost_saved": 1.23,
            "total_uses": 100,
        }

        insights = analyze_batch_patterns(jobs)

        assert insights["jobs_analyzed"] == 5
        assert insights["pattern_count"] == 42
        assert insights["unique_roles"] == 1  # All same role
        assert insights["unique_companies"] == 5  # Different companies
        assert insights["avg_ats_score"] == 82.0  # Average of 80-84
        assert insights["cache_hit_rate"] == 65.5
        assert "message" in insights


def test_analyze_batch_patterns_empty():
    """Test analyze_batch_patterns with no jobs."""
    insights = analyze_batch_patterns([])

    assert insights["pattern_count"] == 0
    assert "message" in insights
    assert "No completed jobs" in insights["message"]


def test_learning_pause_auto_resumes(mock_tracker_db, mock_pipeline):
    """Test that learning pause automatically resumes after analysis."""
    processor = BatchProcessor(max_workers=1)

    # Create 15 URLs (2 segments)
    urls = [f"https://example.com/job{i}" for i in range(15)]

    # Mock pattern analysis
    with patch("jseeker.pattern_learner.analyze_batch_patterns") as mock_analyze:
        mock_analyze.return_value = {"pattern_count": 5, "message": "Test"}

        processor.submit_batch(urls)

        # Wait for learning pause to trigger and auto-resume
        timeout = 25
        start = time.time()
        learning_phase_seen = False
        auto_resumed = False

        while time.time() - start < timeout:
            progress = processor.get_progress()
            progress.completed + progress.failed + progress.skipped

            # Track if we saw learning phase
            if progress.learning_phase:
                learning_phase_seen = True

            # Check if it auto-resumed (learning_phase=False and segment incremented)
            if (
                learning_phase_seen
                and not progress.learning_phase
                and progress.current_segment == 2
            ):
                auto_resumed = True
                break

            time.sleep(0.5)

        assert learning_phase_seen, "Learning phase should have been triggered"
        assert auto_resumed, "Batch should have auto-resumed after learning"

        # Cleanup
        processor.stop()


def test_learning_pause_not_triggered_on_final_segment(mock_tracker_db, mock_pipeline):
    """Test that learning pause is NOT triggered after the final segment completes."""
    processor = BatchProcessor(max_workers=2)

    # Create exactly 10 URLs (1 segment) - should not trigger learning pause
    urls = [f"https://example.com/job{i}" for i in range(10)]

    with patch("jseeker.pattern_learner.analyze_batch_patterns") as mock_analyze:
        processor.submit_batch(urls)

        # Wait for all jobs to complete
        timeout = 15
        start = time.time()
        while time.time() - start < timeout:
            progress = processor.get_progress()
            jobs_done = progress.completed + progress.failed + progress.skipped

            if jobs_done == 10:
                break

            time.sleep(0.5)

        progress = processor.get_progress()

        # Should NOT have triggered learning pause (only 1 segment)
        assert not progress.learning_phase
        assert not mock_analyze.called

        # Cleanup
        processor.stop()


def test_segment_tracking_persists_through_pause(mock_tracker_db, mock_pipeline):
    """Test that segment tracking persists correctly through manual pause/resume."""
    processor = BatchProcessor(max_workers=2)

    urls = [f"https://example.com/job{i}" for i in range(15)]
    processor.submit_batch(urls)

    # Let it run for a bit
    time.sleep(2)

    # Manually pause
    processor.pause()
    progress = processor.get_progress()
    segment_before_pause = progress.current_segment

    # Resume
    processor.resume()

    # Segment should not have changed due to manual pause
    progress_after = processor.get_progress()
    assert progress_after.current_segment == segment_before_pause

    # Cleanup
    processor.stop()
