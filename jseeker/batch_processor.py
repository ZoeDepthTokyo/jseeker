"""jSeeker Batch Processor — Parallel batch processing with pause/resume/stop controls."""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from threading import Event, Lock
from typing import Optional, Callable

from jseeker.jd_parser import extract_jd_from_url
from jseeker.pipeline import run_pipeline
from jseeker.tracker import tracker_db

logger = logging.getLogger(__name__)


# ── Enums & Data Models ────────────────────────────────────────────────────


class JobStatus(str, Enum):
    """Status of individual batch job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    STOPPED = "stopped"


@dataclass
class BatchJob:
    """Individual job within a batch."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    url: str = ""
    status: JobStatus = JobStatus.PENDING
    result: Optional[dict] = None
    error: Optional[str] = None
    worker_id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "id": self.id,
            "url": self.url,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "worker_id": self.worker_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class WorkerStatus:
    """Status of a single worker thread."""

    worker_id: int
    current_job: Optional[str] = None
    current_url: Optional[str] = None
    jobs_completed: int = 0
    jobs_failed: int = 0
    is_active: bool = False


@dataclass
class BatchProgress:
    """Overall batch progress tracking."""

    batch_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    running: int = 0
    paused: bool = False
    stopped: bool = False
    workers: dict[int, WorkerStatus] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_segment: int = 1
    total_segments: int = 1
    learning_phase: bool = False

    @property
    def pending(self) -> int:
        """Calculate pending jobs."""
        return max(0, self.total - self.completed - self.failed - self.skipped - self.running)

    @property
    def progress_pct(self) -> float:
        """Calculate progress percentage."""
        if self.total == 0:
            return 0.0
        return ((self.completed + self.failed + self.skipped) / self.total) * 100

    @property
    def elapsed_seconds(self) -> float:
        """Calculate elapsed time in seconds."""
        if not self.started_at:
            return 0.0
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()

    @property
    def estimated_remaining_seconds(self) -> Optional[float]:
        """Estimate remaining time based on current rate."""
        if self.completed == 0 or self.elapsed_seconds == 0:
            return None
        rate = self.completed / self.elapsed_seconds
        remaining = self.pending + self.running
        return remaining / rate if rate > 0 else None

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "batch_id": self.batch_id,
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "skipped": self.skipped,
            "running": self.running,
            "pending": self.pending,
            "paused": self.paused,
            "stopped": self.stopped,
            "progress_pct": round(self.progress_pct, 1),
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "estimated_remaining_seconds": (
                round(self.estimated_remaining_seconds, 1)
                if self.estimated_remaining_seconds
                else None
            ),
            "current_segment": self.current_segment,
            "total_segments": self.total_segments,
            "learning_phase": self.learning_phase,
            "workers": {
                wid: {
                    "worker_id": w.worker_id,
                    "current_job": w.current_job,
                    "current_url": w.current_url,
                    "jobs_completed": w.jobs_completed,
                    "jobs_failed": w.jobs_failed,
                    "is_active": w.is_active,
                }
                for wid, w in self.workers.items()
            },
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# ── JD Extraction Cache ─────────────────────────────────────────────────────


class JDCache:
    """Simple in-memory cache for JD extractions to avoid re-scraping."""

    def __init__(self):
        self._cache: dict[str, tuple[str, datetime]] = {}
        self._lock = Lock()
        self._ttl_seconds = 3600  # 1 hour TTL

    def get(self, url: str) -> Optional[str]:
        """Get cached JD text if available and not expired."""
        with self._lock:
            if url not in self._cache:
                return None
            jd_text, cached_at = self._cache[url]
            if (datetime.now() - cached_at).total_seconds() > self._ttl_seconds:
                del self._cache[url]
                return None
            return jd_text

    def set(self, url: str, jd_text: str):
        """Cache JD text for URL."""
        with self._lock:
            self._cache[url] = (jd_text, datetime.now())

    def clear(self):
        """Clear entire cache."""
        with self._lock:
            self._cache.clear()


# ── Batch Processor ─────────────────────────────────────────────────────────


class BatchProcessor:
    """Parallel batch processor with pause/resume/stop controls."""

    BATCH_SEGMENT_SIZE = 10  # Pause for learning every 10 resumes
    MAX_BATCH_SIZE = 20  # Maximum total resumes per batch

    def __init__(self, max_workers: int = 5, output_dir: Path = None):
        """Initialize batch processor.

        Args:
            max_workers: Maximum concurrent workers (default: 5)
            output_dir: Override output directory for resumes
        """
        self.max_workers = max_workers
        self.output_dir = output_dir
        self.executor: Optional[ThreadPoolExecutor] = None
        self.jobs: dict[str, BatchJob] = {}
        self.progress = BatchProgress()
        self.jd_cache = JDCache()

        # Control flags
        self._pause_event = Event()
        self._pause_event.set()  # Start unpaused
        self._stop_event = Event()
        self._lock = Lock()

        # Progress callback
        self._progress_callback: Optional[Callable[[BatchProgress], None]] = None

        # Learning pause tracking
        self._learning_pause_triggered = False
        self._current_segment = 1
        self._total_segments = 1

        logger.info(f"BatchProcessor initialized with {max_workers} workers")

    def submit_batch(
        self,
        urls: list[str],
        progress_callback: Optional[Callable[[BatchProgress], None]] = None,
    ) -> str:
        """Submit a batch of URLs for processing.

        Args:
            urls: List of job URLs to process
            progress_callback: Optional callback to invoke on progress updates

        Returns:
            Batch ID for tracking
        """
        if not urls:
            raise ValueError("URLs list cannot be empty")

        # Enforce max batch size
        if len(urls) > self.MAX_BATCH_SIZE:
            logger.warning(
                f"Batch size {len(urls)} exceeds maximum {self.MAX_BATCH_SIZE}, truncating"
            )
            urls = urls[: self.MAX_BATCH_SIZE]

        # Reset state for new batch
        self.jobs.clear()
        self._stop_event.clear()
        self._pause_event.set()
        self._progress_callback = progress_callback
        self.jd_cache.clear()
        self._learning_pause_triggered = False

        # Calculate segments
        total_segments = (len(urls) + self.BATCH_SEGMENT_SIZE - 1) // self.BATCH_SEGMENT_SIZE
        self._total_segments = total_segments
        self._current_segment = 1

        # Create progress tracker
        self.progress = BatchProgress(
            total=len(urls), total_segments=total_segments, current_segment=1
        )
        self.progress.started_at = datetime.now()

        # Initialize worker status
        for i in range(self.max_workers):
            self.progress.workers[i] = WorkerStatus(worker_id=i)

        # Create batch job in database
        batch_id = tracker_db.create_batch_job(len(urls))
        self.progress.batch_id = batch_id

        logger.info(f"Batch {batch_id} submitted with {len(urls)} URLs ({total_segments} segments)")

        # Create jobs
        for url in urls:
            job = BatchJob(url=url)
            self.jobs[job.id] = job

        # Start executor
        self.executor = ThreadPoolExecutor(
            max_workers=self.max_workers, thread_name_prefix="BatchWorker"
        )

        # Submit all jobs
        futures: dict[Future, str] = {}
        for job_id, job in self.jobs.items():
            future = self.executor.submit(self._process_job, job_id)
            futures[future] = job_id

        # Monitor futures in background (non-blocking)
        def monitor_completion():
            for future in futures:
                try:
                    future.result()  # Wait for completion
                except Exception as e:
                    job_id = futures[future]
                    logger.error(f"Future for job {job_id} failed: {e}")

            # Mark batch as completed
            self.progress.completed_at = datetime.now()
            self.progress.stopped = self._stop_event.is_set()
            tracker_db.update_batch_job(
                batch_id,
                status="stopped" if self.progress.stopped else "completed",
                completed_at=datetime.now(),
                completed_count=self.progress.completed,
                failed_count=self.progress.failed,
                skipped_count=self.progress.skipped,
            )
            logger.info(
                f"Batch {batch_id} finished: {self.progress.completed} completed, {self.progress.failed} failed, {self.progress.skipped} skipped"
            )

            # Final progress callback
            if self._progress_callback:
                self._progress_callback(self.progress)

        import threading

        threading.Thread(target=monitor_completion, daemon=True).start()

        return batch_id

    def _process_job(self, job_id: str) -> None:
        """Process a single job (runs in worker thread).

        Args:
            job_id: Job ID to process
        """
        import threading

        # Extract worker ID from thread name (format: BatchWorker_0, BatchWorker_1, etc.)
        thread_name = threading.current_thread().name
        try:
            # Try to parse from ThreadPoolExecutor format: "BatchWorker_N"
            if "_" in thread_name:
                worker_id = int(thread_name.split("_")[-1]) % self.max_workers
            else:
                # Fallback: use hash of thread name
                worker_id = hash(thread_name) % self.max_workers
        except (ValueError, IndexError):
            # Final fallback: use thread ident
            worker_id = threading.get_ident() % self.max_workers

        job = self.jobs[job_id]
        job.worker_id = worker_id
        job.started_at = datetime.now()

        # Update worker status
        with self._lock:
            worker = self.progress.workers[worker_id]
            worker.is_active = True
            worker.current_job = job_id
            worker.current_url = job.url

        logger.debug(f"Worker {worker_id} started job {job_id}: {job.url}")

        try:
            # Check for stop signal
            if self._stop_event.is_set():
                job.status = JobStatus.STOPPED
                job.completed_at = datetime.now()
                self._update_progress("stopped")
                return

            # Wait if paused
            self._pause_event.wait()

            # Check for stop again after pause
            if self._stop_event.is_set():
                job.status = JobStatus.STOPPED
                job.completed_at = datetime.now()
                self._update_progress("stopped")
                return

            # Mark as running
            job.status = JobStatus.RUNNING
            self._update_progress("running_increment")

            # Check if URL already known
            if tracker_db.is_url_known(job.url):
                logger.info(f"Job {job_id} skipped (URL already known): {job.url}")
                job.status = JobStatus.SKIPPED
                job.error = "URL already exists in tracker"
                job.completed_at = datetime.now()
                tracker_db.create_batch_job_item(
                    self.progress.batch_id,
                    job.url,
                    status="skipped",
                    error=job.error,
                )
                with self._lock:
                    worker.jobs_completed += 1
                self._update_progress("skipped")
                return

            # Extract JD (with caching)
            jd_text = self.jd_cache.get(job.url)
            if jd_text:
                logger.debug(f"Using cached JD for {job.url}")
            else:
                logger.debug(f"Extracting JD from {job.url}")
                jd_text, extraction_meta = extract_jd_from_url(job.url)
                if not jd_text:
                    error_msg = f"Could not extract job description from URL (method: {extraction_meta.get('method', 'unknown')})"
                    if extraction_meta.get("company"):
                        error_msg += f" | Company: {extraction_meta['company']}"
                    raise ValueError(error_msg)
                self.jd_cache.set(job.url, jd_text)

            # Check for stop before expensive operation
            if self._stop_event.is_set():
                job.status = JobStatus.STOPPED
                job.completed_at = datetime.now()
                self._update_progress("stopped")
                return

            # Run pipeline (expensive operation)
            from config import settings

            output_dir = self.output_dir or settings.output_dir
            result = run_pipeline(jd_text=jd_text, jd_url=job.url, output_dir=output_dir)

            # Check for stop before DB write
            if self._stop_event.is_set():
                job.status = JobStatus.STOPPED
                job.completed_at = datetime.now()
                self._update_progress("stopped")
                return

            # Create application in tracker
            created = tracker_db.create_from_pipeline(result)
            tracker_db.update_application(created["application_id"], resume_status="exported")

            # Store result
            job.result = {
                "application_id": created["application_id"],
                "company": result.company,
                "role": result.role,
                "ats_score": result.ats_score.overall_score,
                "cost_usd": result.total_cost,
            }
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now()

            # Log to batch_job_items
            tracker_db.create_batch_job_item(
                self.progress.batch_id,
                job.url,
                status="completed",
                resume_id=created.get("resume_id"),
                application_id=created["application_id"],
            )

            with self._lock:
                worker.jobs_completed += 1

            logger.info(f"Job {job_id} completed: {result.company} - {result.role}")
            self._update_progress("completed")

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.completed_at = datetime.now()

            # Log to batch_job_items
            tracker_db.create_batch_job_item(
                self.progress.batch_id,
                job.url,
                status="failed",
                error=str(e),
            )

            with self._lock:
                worker.jobs_failed += 1

            self._update_progress("failed")

        finally:
            # Clear worker status
            with self._lock:
                worker = self.progress.workers[worker_id]
                worker.is_active = False
                worker.current_job = None
                worker.current_url = None

            self._update_progress("running_decrement")

    def _update_progress(self, event: str):
        """Update progress counters and invoke callback.

        Args:
            event: One of "completed", "failed", "skipped", "stopped", "running_increment", "running_decrement"
        """
        with self._lock:
            if event == "completed":
                self.progress.completed += 1
                self.progress.running = max(0, self.progress.running - 1)
            elif event == "failed":
                self.progress.failed += 1
                self.progress.running = max(0, self.progress.running - 1)
            elif event == "skipped":
                self.progress.skipped += 1
                self.progress.running = max(0, self.progress.running - 1)
            elif event == "stopped":
                self.progress.running = max(0, self.progress.running - 1)
            elif event == "running_increment":
                self.progress.running += 1
            elif event == "running_decrement":
                self.progress.running = max(0, self.progress.running - 1)

            # Check if we've completed a segment (trigger learning pause)
            jobs_processed = self.progress.completed + self.progress.failed + self.progress.skipped
            segment_boundary = self._current_segment * self.BATCH_SEGMENT_SIZE

            # Trigger learning pause at segment boundaries (but not at the end of the final segment)
            if (
                jobs_processed == segment_boundary
                and jobs_processed < self.progress.total
                and not self._learning_pause_triggered
                and self._current_segment < self._total_segments
            ):
                self._trigger_learning_pause()

        # Invoke callback
        if self._progress_callback:
            try:
                self._progress_callback(self.progress)
            except Exception as e:
                logger.error(f"Progress callback failed: {e}")

    def _trigger_learning_pause(self):
        """Trigger automatic learning pause at segment boundary."""
        logger.info(f"Segment {self._current_segment} completed. Triggering learning pause...")
        self._learning_pause_triggered = True
        self.progress.learning_phase = True
        self._pause_event.clear()
        self.progress.paused = True

        # Analyze patterns in background thread
        import threading

        def analyze_and_resume():
            try:
                self._analyze_patterns()
                time.sleep(2)  # Brief pause to let UI update
                # Auto-resume after analysis
                self._current_segment += 1
                self.progress.current_segment = self._current_segment
                self.progress.learning_phase = False
                self._learning_pause_triggered = False
                self.resume()
            except Exception as e:
                logger.error(f"Pattern analysis failed: {e}")
                # Resume anyway to prevent getting stuck
                self._current_segment += 1
                self.progress.current_segment = self._current_segment
                self.progress.learning_phase = False
                self._learning_pause_triggered = False
                self.resume()

        threading.Thread(target=analyze_and_resume, daemon=True).start()

    def _analyze_patterns(self):
        """Analyze patterns from completed jobs in current segment."""
        from jseeker.pattern_learner import analyze_batch_patterns

        completed_jobs = [job for job in self.jobs.values() if job.status == JobStatus.COMPLETED]

        if not completed_jobs:
            logger.info("No completed jobs to analyze patterns")
            return

        logger.info(f"Analyzing patterns from {len(completed_jobs)} completed jobs...")

        try:
            # Call pattern learner to extract insights
            insights = analyze_batch_patterns(completed_jobs)
            logger.info(
                f"Pattern analysis complete. Found {insights.get('pattern_count', 0)} patterns"
            )
        except Exception as e:
            logger.warning(f"Pattern analysis encountered error: {e}")

    def pause(self):
        """Pause batch processing. Workers will block until resumed."""
        logger.info("Pausing batch processing")
        self._pause_event.clear()
        self.progress.paused = True
        if self._progress_callback:
            self._progress_callback(self.progress)

    def resume(self):
        """Resume batch processing."""
        logger.info("Resuming batch processing")
        self._pause_event.set()
        self.progress.paused = False
        if self._progress_callback:
            self._progress_callback(self.progress)

    def stop(self):
        """Stop batch processing. Workers will exit gracefully."""
        logger.info("Stopping batch processing")
        self._stop_event.set()
        self._pause_event.set()  # Unblock any paused workers
        self.progress.stopped = True
        if self._progress_callback:
            self._progress_callback(self.progress)

        # Shutdown executor
        if self.executor:
            self.executor.shutdown(wait=False)

    def get_progress(self) -> BatchProgress:
        """Get current batch progress.

        Returns:
            BatchProgress snapshot
        """
        return self.progress

    def get_job_status(self, job_id: str) -> Optional[BatchJob]:
        """Get status of a specific job.

        Args:
            job_id: Job ID to query

        Returns:
            BatchJob or None if not found
        """
        return self.jobs.get(job_id)

    def get_all_jobs(self) -> list[BatchJob]:
        """Get all jobs in current batch.

        Returns:
            List of BatchJob objects
        """
        return list(self.jobs.values())
