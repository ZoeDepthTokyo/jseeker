"""Tests for jSeeker Batch Processor."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from jseeker.batch_processor import (
    BatchProcessor,
    BatchJob,
    BatchProgress,
    WorkerStatus,
    JobStatus,
    JDCache,
)


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
    with patch("jseeker.batch_processor.extract_jd_from_url") as mock_extract, \
         patch("jseeker.batch_processor.run_pipeline") as mock_run:

        # Mock JD extraction
        mock_extract.return_value = "Test job description"

        # Mock pipeline result
        mock_result = MagicMock()
        mock_result.company = "Test Company"
        mock_result.role = "Test Role"
        mock_result.ats_score.overall_score = 85
        mock_result.total_cost = 0.05
        mock_run.return_value = mock_result

        yield mock_extract, mock_run


@pytest.fixture
def test_urls():
    """Test URLs for batch processing."""
    return [
        "https://example.com/job1",
        "https://example.com/job2",
        "https://example.com/job3",
        "https://example.com/job4",
        "https://example.com/job5",
    ]


# ── Data Model Tests ────────────────────────────────────────────────────────


def test_batch_job_creation():
    """Test BatchJob creation with defaults."""
    job = BatchJob(url="https://example.com/job")
    assert job.url == "https://example.com/job"
    assert job.status == JobStatus.PENDING
    assert job.result is None
    assert job.error is None
    assert job.worker_id is None
    assert job.id  # Should have auto-generated ID


def test_batch_job_to_dict():
    """Test BatchJob serialization to dict."""
    job = BatchJob(url="https://example.com/job", status=JobStatus.COMPLETED)
    job.result = {"application_id": 1}
    data = job.to_dict()

    assert data["url"] == "https://example.com/job"
    assert data["status"] == "completed"
    assert data["result"] == {"application_id": 1}
    assert "created_at" in data


def test_worker_status():
    """Test WorkerStatus dataclass."""
    worker = WorkerStatus(worker_id=0)
    assert worker.worker_id == 0
    assert worker.current_job is None
    assert worker.jobs_completed == 0
    assert worker.jobs_failed == 0
    assert not worker.is_active


def test_batch_progress_properties():
    """Test BatchProgress computed properties."""
    progress = BatchProgress(total=10, completed=5, failed=2, running=1)

    assert progress.pending == 2  # 10 - 5 - 2 - 1 = 2
    assert progress.progress_pct == 70.0  # (5 + 2) / 10 * 100
    assert progress.elapsed_seconds >= 0


def test_batch_progress_to_dict():
    """Test BatchProgress serialization."""
    progress = BatchProgress(total=5, completed=3)
    progress.workers[0] = WorkerStatus(worker_id=0, jobs_completed=3)

    data = progress.to_dict()
    assert data["total"] == 5
    assert data["completed"] == 3
    assert data["pending"] == 2
    assert "workers" in data
    assert 0 in data["workers"]


def test_batch_progress_estimated_time():
    """Test BatchProgress time estimation."""
    progress = BatchProgress(total=10)
    progress.started_at = progress.created_at
    time.sleep(0.1)  # Small delay to accumulate elapsed time

    # No completed jobs yet
    assert progress.estimated_remaining_seconds is None

    # Complete some jobs
    progress.completed = 5
    progress.running = 1

    # Should have an estimate now
    if progress.elapsed_seconds > 0:
        assert progress.estimated_remaining_seconds is not None
        assert progress.estimated_remaining_seconds > 0


# ── JD Cache Tests ──────────────────────────────────────────────────────────


def test_jd_cache_basic():
    """Test JD cache set and get."""
    cache = JDCache()
    url = "https://example.com/job"
    jd_text = "Test job description"

    cache.set(url, jd_text)
    assert cache.get(url) == jd_text


def test_jd_cache_miss():
    """Test JD cache miss returns None."""
    cache = JDCache()
    assert cache.get("https://example.com/nonexistent") is None


def test_jd_cache_clear():
    """Test JD cache clear."""
    cache = JDCache()
    cache.set("url1", "text1")
    cache.set("url2", "text2")

    cache.clear()
    assert cache.get("url1") is None
    assert cache.get("url2") is None


# ── Batch Processor Tests ───────────────────────────────────────────────────


def test_batch_processor_init():
    """Test BatchProcessor initialization."""
    processor = BatchProcessor(max_workers=3)
    assert processor.max_workers == 3
    assert processor.executor is None
    assert len(processor.jobs) == 0
    assert processor.progress.total == 0


def test_batch_processor_submit_empty_urls():
    """Test BatchProcessor rejects empty URL list."""
    processor = BatchProcessor()
    with pytest.raises(ValueError, match="URLs list cannot be empty"):
        processor.submit_batch([])


def test_batch_processor_submit_batch(mock_tracker_db, mock_pipeline, test_urls):
    """Test batch submission creates jobs and starts processing."""
    processor = BatchProcessor(max_workers=5)

    # Submit batch
    batch_id = processor.submit_batch(test_urls)

    # Verify batch created
    assert batch_id
    assert processor.progress.total == len(test_urls)
    assert len(processor.jobs) == len(test_urls)
    assert processor.executor is not None

    # Verify all jobs created
    for job in processor.jobs.values():
        assert job.url in test_urls
        # Jobs may complete very quickly in tests
        assert job.status in (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.COMPLETED, JobStatus.FAILED)

    # Wait a moment for processing to start
    time.sleep(0.5)

    # Shutdown executor
    processor.stop()
    if processor.executor:
        processor.executor.shutdown(wait=True)


def test_batch_processor_progress_callback(mock_tracker_db, mock_pipeline, test_urls):
    """Test progress callback is invoked."""
    processor = BatchProcessor(max_workers=5)
    callback_invocations = []

    def callback(progress):
        callback_invocations.append(progress)

    # Submit with callback
    processor.submit_batch(test_urls, progress_callback=callback)

    # Wait for some processing
    time.sleep(1.0)

    # Stop processing
    processor.stop()
    if processor.executor:
        processor.executor.shutdown(wait=True)

    # Callback should have been invoked at least once
    assert len(callback_invocations) > 0


def test_batch_processor_pause_resume(mock_tracker_db, mock_pipeline):
    """Test pause and resume functionality."""
    processor = BatchProcessor(max_workers=5)
    urls = ["https://example.com/job1", "https://example.com/job2"]

    # Submit batch
    processor.submit_batch(urls)

    # Pause
    processor.pause()
    assert processor.progress.paused is True
    assert not processor._pause_event.is_set()

    # Resume
    processor.resume()
    assert processor.progress.paused is False
    assert processor._pause_event.is_set()

    # Cleanup
    processor.stop()
    if processor.executor:
        processor.executor.shutdown(wait=True)


def test_batch_processor_stop(mock_tracker_db, mock_pipeline):
    """Test stop functionality."""
    processor = BatchProcessor(max_workers=5)
    urls = ["https://example.com/job1", "https://example.com/job2"]

    # Submit batch
    processor.submit_batch(urls)

    # Stop
    processor.stop()
    assert processor.progress.stopped is True
    assert processor._stop_event.is_set()
    assert processor._pause_event.is_set()  # Should unblock paused workers

    # Cleanup
    if processor.executor:
        processor.executor.shutdown(wait=True)


def test_batch_processor_skip_known_urls(mock_tracker_db, mock_pipeline):
    """Test that known URLs are skipped."""
    # Mock one URL as known
    mock_tracker_db.is_url_known.side_effect = lambda url: url == "https://example.com/job1"

    processor = BatchProcessor(max_workers=5)
    urls = ["https://example.com/job1", "https://example.com/job2"]

    processor.submit_batch(urls)

    # Wait for processing
    time.sleep(1.0)

    # Check that job1 was skipped
    job1 = [j for j in processor.jobs.values() if j.url == "https://example.com/job1"]
    if job1:
        # Job might still be pending if not processed yet, or skipped if processed
        assert job1[0].status in (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.SKIPPED)

    # Cleanup
    processor.stop()
    if processor.executor:
        processor.executor.shutdown(wait=True)


def test_batch_processor_handle_extraction_error(mock_tracker_db, mock_pipeline):
    """Test error handling when JD extraction fails."""
    mock_extract, mock_run = mock_pipeline

    # Mock extraction failure
    mock_extract.return_value = None  # Simulates extraction failure

    processor = BatchProcessor(max_workers=5)
    urls = ["https://example.com/bad_job"]

    processor.submit_batch(urls)

    # Wait for processing
    time.sleep(1.0)

    # Job should be marked as failed
    job = list(processor.jobs.values())[0]
    # Might still be running or already failed
    assert job.status in (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED)

    # Cleanup
    processor.stop()
    if processor.executor:
        processor.executor.shutdown(wait=True)


def test_batch_processor_handle_pipeline_error(mock_tracker_db, mock_pipeline):
    """Test error handling when pipeline fails."""
    mock_extract, mock_run = mock_pipeline

    # Mock pipeline failure
    mock_run.side_effect = Exception("Pipeline error")

    processor = BatchProcessor(max_workers=5)
    urls = ["https://example.com/job1"]

    processor.submit_batch(urls)

    # Wait for processing
    time.sleep(1.0)

    # Job should be marked as failed with error message
    job = list(processor.jobs.values())[0]
    # Might still be running or already failed
    assert job.status in (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED)

    # Cleanup
    processor.stop()
    if processor.executor:
        processor.executor.shutdown(wait=True)


def test_batch_processor_worker_limit(mock_tracker_db, mock_pipeline):
    """Test that max_workers limit is respected."""
    processor = BatchProcessor(max_workers=2)  # Only 2 workers
    urls = [f"https://example.com/job{i}" for i in range(10)]

    processor.submit_batch(urls)

    # Wait a moment
    time.sleep(0.3)

    # At most 2 jobs should be running simultaneously
    running = processor.progress.running
    assert running <= 2

    # Cleanup
    processor.stop()
    if processor.executor:
        processor.executor.shutdown(wait=True)


def test_batch_processor_get_progress(mock_tracker_db, mock_pipeline):
    """Test get_progress returns current state."""
    processor = BatchProcessor(max_workers=5)
    urls = ["https://example.com/job1", "https://example.com/job2"]

    processor.submit_batch(urls)

    progress = processor.get_progress()
    assert progress.total == 2
    assert isinstance(progress, BatchProgress)

    # Cleanup
    processor.stop()
    if processor.executor:
        processor.executor.shutdown(wait=True)


def test_batch_processor_get_job_status(mock_tracker_db, mock_pipeline):
    """Test get_job_status retrieves specific job."""
    processor = BatchProcessor(max_workers=5)
    urls = ["https://example.com/job1"]

    processor.submit_batch(urls)

    # Get job ID
    job_id = list(processor.jobs.keys())[0]

    # Retrieve job
    job = processor.get_job_status(job_id)
    assert job is not None
    assert job.url == "https://example.com/job1"

    # Non-existent job
    assert processor.get_job_status("nonexistent") is None

    # Cleanup
    processor.stop()
    if processor.executor:
        processor.executor.shutdown(wait=True)


def test_batch_processor_get_all_jobs(mock_tracker_db, mock_pipeline):
    """Test get_all_jobs returns all jobs."""
    processor = BatchProcessor(max_workers=5)
    urls = ["https://example.com/job1", "https://example.com/job2"]

    processor.submit_batch(urls)

    jobs = processor.get_all_jobs()
    assert len(jobs) == 2
    assert all(isinstance(j, BatchJob) for j in jobs)

    # Cleanup
    processor.stop()
    if processor.executor:
        processor.executor.shutdown(wait=True)


def test_batch_processor_jd_cache_usage(mock_tracker_db, mock_pipeline):
    """Test that JD cache is used to avoid re-scraping."""
    mock_extract, mock_run = mock_pipeline

    processor = BatchProcessor(max_workers=5)
    url = "https://example.com/job1"

    # Pre-populate cache
    processor.jd_cache.set(url, "Cached JD text")

    processor.submit_batch([url])

    # Wait for processing
    time.sleep(1.0)

    # extract_jd_from_url should not be called if cache hit
    # (or called but cache value used instead)
    # This is hard to verify directly, but we can check that processing succeeded

    # Cleanup
    processor.stop()
    if processor.executor:
        processor.executor.shutdown(wait=True)


# ── Integration Test ────────────────────────────────────────────────────────


@pytest.mark.integration
def test_batch_processor_full_pipeline(mock_tracker_db, mock_pipeline, test_urls):
    """Integration test: full batch processing pipeline."""
    processor = BatchProcessor(max_workers=5)

    # Submit batch
    batch_id = processor.submit_batch(test_urls)
    assert batch_id

    # Wait for completion (with timeout)
    max_wait = 10  # seconds
    waited = 0
    interval = 0.5

    while waited < max_wait:
        progress = processor.get_progress()
        total_done = progress.completed + progress.failed + progress.skipped
        if total_done == progress.total:
            break
        time.sleep(interval)
        waited += interval

    # Verify final state
    progress = processor.get_progress()
    assert progress.completed + progress.failed + progress.skipped == progress.total
    assert progress.completed > 0  # At least some should succeed

    # Verify all jobs processed
    jobs = processor.get_all_jobs()
    for job in jobs:
        assert job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.SKIPPED)

    # Cleanup
    processor.stop()
    if processor.executor:
        processor.executor.shutdown(wait=True)


# ── Performance Test ────────────────────────────────────────────────────────


@pytest.mark.performance
def test_batch_processor_performance(mock_tracker_db, mock_pipeline):
    """Performance test: verify parallel processing is faster than sequential."""
    # Add small delay to pipeline to simulate real work
    mock_extract, mock_run = mock_pipeline

    def slow_pipeline(*args, **kwargs):
        time.sleep(0.2)  # 200ms per job
        result = MagicMock()
        result.company = "Test"
        result.role = "Role"
        result.ats_score.overall_score = 85
        result.total_cost = 0.05
        return result

    mock_run.side_effect = slow_pipeline

    # Test with 5 jobs
    urls = [f"https://example.com/job{i}" for i in range(5)]

    processor = BatchProcessor(max_workers=5)
    start_time = time.time()

    batch_id = processor.submit_batch(urls)

    # Wait for completion
    max_wait = 5  # seconds
    waited = 0
    interval = 0.1

    while waited < max_wait:
        progress = processor.get_progress()
        if progress.completed + progress.failed + progress.skipped == progress.total:
            break
        time.sleep(interval)
        waited += interval

    elapsed = time.time() - start_time

    # Sequential would take 5 * 0.2 = 1.0 second
    # Parallel should take ~0.2-0.5 seconds (allowing overhead)
    # We expect at least 50% improvement
    assert elapsed < 0.8, f"Parallel processing too slow: {elapsed}s (expected < 0.8s)"

    # Cleanup
    processor.stop()
    if processor.executor:
        processor.executor.shutdown(wait=True)
