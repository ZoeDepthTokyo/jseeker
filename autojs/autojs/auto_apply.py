"""Auto-apply orchestration engine for jSeeker."""

from __future__ import annotations

import json
import logging
import random
import time
import uuid
from pathlib import Path
from typing import Optional

from autojs.answer_bank import AnswerBank, load_answer_bank
from autojs.apply_monitor import ApplyMonitor
from autojs.apply_verifier import ApplyVerifier
from autojs.ats_runners.base import SiteRunner
from jseeker.models import (
    AttemptResult,
    AttemptStatus,
    BatchSummary,
    RateLimitConfig,
)

logger = logging.getLogger(__name__)


class AutoApplyEngine:
    """Routes jobs to platform-specific runners, manages queue, rate limits, and retries."""

    def __init__(
        self,
        answer_bank: Optional[AnswerBank] = None,
        config: Optional[RateLimitConfig] = None,
    ) -> None:
        self.answer_bank = answer_bank or load_answer_bank()
        self.config = config or RateLimitConfig()
        self.verifier = ApplyVerifier()
        self.monitor = ApplyMonitor(self.config)
        self._runners: list[SiteRunner] = []
        self._daily_attempts: int = 0
        self._hourly_attempts: int = 0
        self._daily_cost: float = 0.0
        self._consecutive_failures: int = 0
        self._hour_start: float = time.time()
        self._day_start: float = time.time()

    def register_runner(self, runner: SiteRunner) -> None:
        """Register an ATS-specific runner."""
        self._runners.append(runner)

    def detect_platform(self, url: str) -> Optional[SiteRunner]:
        """Find the runner that handles this URL.

        Args:
            url: Job application URL.

        Returns:
            Matching SiteRunner or None if unsupported.
        """
        for runner in self._runners:
            if runner.detect(url):
                return runner
        return None

    def apply_single(
        self,
        job_url: str,
        resume_path: Path,
        market: str = "us",
        dry_run: bool = True,
        attempt_dir: Optional[Path] = None,
    ) -> AttemptResult:
        """Apply to a single job (without pre-created page).

        Full pipeline: dedup -> rate limit -> detect -> log.
        For actual form filling, use apply_with_page().

        Args:
            job_url: URL of the job application.
            resume_path: Path to the resume file.
            market: Market code for personal info lookup.
            dry_run: If True, stop before submitting.
            attempt_dir: Directory for attempt artifacts.

        Returns:
            AttemptResult with status and metadata.
        """
        from jseeker import tracker

        # 1. Dedup check
        if tracker.check_dedup(job_url):
            return AttemptResult(
                status=AttemptStatus.SKIPPED_DUPLICATE,
                errors=[f"Already applied: {job_url}"],
            )

        # 2. Rate limit check
        if not self._check_rate_limit():
            return AttemptResult(
                status=AttemptStatus.PAUSED_COST_CAP,
                errors=["Rate limit exceeded"],
            )

        # 3. Detect platform
        runner = self.detect_platform(job_url)
        if runner is None:
            if "linkedin.com" in job_url.lower():
                return AttemptResult(
                    status=AttemptStatus.SKIPPED_LINKEDIN,
                    errors=["LinkedIn not supported in v1"],
                )
            return AttemptResult(
                status=AttemptStatus.SKIPPED_UNSUPPORTED_ATS,
                errors=[f"No runner for URL: {job_url}"],
            )

        # 4. Generate attempt ID and dir
        attempt_id = str(uuid.uuid4())[:8]
        if attempt_dir is None:
            from config import settings

            attempt_dir = settings.apply_logs_dir / attempt_id
        attempt_dir.mkdir(parents=True, exist_ok=True)

        # 5. Without a page, we can only record the attempt was detected
        result = AttemptResult(
            status=AttemptStatus.SKIPPED_UNSUPPORTED_ATS,
            errors=["Browser integration pending — use apply_with_page()"],
        )

        # 6. Save attempt log
        self._save_artifacts(attempt_id, result, attempt_dir)

        # 7. Update counters
        self._update_counters(result)

        return result

    def apply_with_page(
        self,
        page,  # playwright.sync_api.Page
        job_url: str,
        resume_path: Path,
        market: str = "us",
        dry_run: bool = True,
        attempt_dir: Optional[Path] = None,
    ) -> AttemptResult:
        """Apply using an already-created Playwright page.

        This is the main entry point for actual automation.

        Args:
            page: Playwright Page instance.
            job_url: URL of the job application.
            resume_path: Path to the resume file.
            market: Market code for personal info lookup.
            dry_run: If True, stop before submitting.
            attempt_dir: Directory for attempt artifacts.

        Returns:
            AttemptResult with status and metadata.
        """
        from jseeker import tracker

        # 1. Dedup
        if tracker.check_dedup(job_url):
            return AttemptResult(
                status=AttemptStatus.SKIPPED_DUPLICATE,
                errors=[f"Already applied: {job_url}"],
            )

        # 2. Rate limit
        if not self._check_rate_limit():
            return AttemptResult(
                status=AttemptStatus.PAUSED_COST_CAP,
                errors=["Rate limit exceeded"],
            )

        # 3. Detect platform
        runner = self.detect_platform(job_url)
        if runner is None:
            if "linkedin.com" in job_url.lower():
                return AttemptResult(
                    status=AttemptStatus.SKIPPED_LINKEDIN,
                    errors=["LinkedIn not supported in v1"],
                )
            return AttemptResult(
                status=AttemptStatus.SKIPPED_UNSUPPORTED_ATS,
                errors=[f"No runner for: {job_url}"],
            )

        # 4. Attempt dir
        attempt_id = str(uuid.uuid4())[:8]
        if attempt_dir is None:
            from config import settings

            attempt_dir = settings.apply_logs_dir / attempt_id
        attempt_dir.mkdir(parents=True, exist_ok=True)

        # 5. Run the runner
        result = runner.fill_and_submit(
            page, job_url, resume_path, self.answer_bank, market, dry_run
        )

        # 6. Post-submission verification (non-dry-run only)
        if not dry_run and result.status in (
            AttemptStatus.APPLIED_SOFT,
            AttemptStatus.APPLIED_VERIFIED,
        ):
            platform_name = self._get_platform_name(runner)
            verification = self.verifier.verify(page, platform_name, {}, logs_dir=attempt_dir)
            if verification.is_verified:
                result.status = AttemptStatus.APPLIED_VERIFIED
                result.confirmation_text = verification.confirmation_text
                result.confirmation_url = verification.confirmation_url
            elif verification.confidence == "soft":
                result.status = AttemptStatus.APPLIED_SOFT
            else:
                result.status = AttemptStatus.PAUSED_AMBIGUOUS_RESULT

        # 7. Save artifacts
        self._save_artifacts(attempt_id, result, attempt_dir)

        # 8. Update counters
        self._update_counters(result)

        return result

    def apply_batch(
        self,
        queue_items: list[dict],
        dry_run: bool = True,
    ) -> BatchSummary:
        """Process a batch of queued applications with rate limiting and failure detection.

        Args:
            queue_items: List of dicts with job_url, resume_path, and optional market.
                Each dict may also include queue_id (int) for tracking paused items.
            dry_run: If True, stop before submitting each application.

        Returns:
            BatchSummary with counts and status of the batch run.
        """
        results: list[AttemptResult] = []
        stopped_early = False
        stop_reason: Optional[str] = None
        paused_items: list[int] = []

        for item in queue_items:
            # Check consecutive failure limit
            if self._consecutive_failures >= 3:
                logger.warning("3 consecutive failures — pausing batch")
                stopped_early = True
                stop_reason = "3 consecutive failures"
                break

            # Check daily limits
            if not self._check_rate_limit():
                logger.warning("Rate limit reached — stopping batch")
                stopped_early = True
                stop_reason = "Rate limit reached"
                break

            result = self.apply_single(
                job_url=item["job_url"],
                resume_path=Path(item["resume_path"]),
                market=item.get("market", "us"),
                dry_run=dry_run,
            )
            results.append(result)

            # Record in monitor
            platform_name = self._detect_platform_name(item["job_url"])
            decision = self.monitor.record_attempt(result, platform_name)
            if not decision.should_continue:
                stopped_early = True
                stop_reason = decision.pause_reason
                logger.warning(f"Monitor stopped batch: {stop_reason}")
                break

            # Track paused items for HITL
            if result.status.value.startswith("paused"):
                queue_id = item.get("queue_id")
                if queue_id is not None:
                    paused_items.append(queue_id)

            # Cooldown between applications
            if len(queue_items) > 1:
                delay = self._randomized_delay(self.config.cooldown_seconds)
                logger.info(f"Cooldown: {delay}s before next application")

        return self._build_batch_summary(results, stopped_early, stop_reason, paused_items)

    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits.

        Returns:
            True if OK to proceed.
        """
        now = time.time()
        # Reset hourly counter
        if now - self._hour_start > 3600:
            self._hourly_attempts = 0
            self._hour_start = now
        # Reset daily counter
        if now - self._day_start > 86400:
            self._daily_attempts = 0
            self._daily_cost = 0.0
            self._day_start = now

        if self._hourly_attempts >= self.config.max_per_hour:
            return False
        if self._daily_attempts >= self.config.max_per_day:
            return False
        if self._daily_cost >= self.config.max_cost_per_day_usd:
            return False
        return True

    def _update_counters(self, result: AttemptResult) -> None:
        """Update attempt counters and failure tracking after an attempt."""
        self._daily_attempts += 1
        self._hourly_attempts += 1
        self._daily_cost += result.cost_usd

        if result.status in (
            AttemptStatus.APPLIED_VERIFIED,
            AttemptStatus.APPLIED_SOFT,
        ):
            self._consecutive_failures = 0
        elif result.status.value.startswith("failed") or result.status.value.startswith("paused"):
            self._consecutive_failures += 1

    def _save_artifacts(self, attempt_id: str, result: AttemptResult, attempt_dir: Path) -> Path:
        """Save attempt log and artifacts to disk.

        Args:
            attempt_id: Unique attempt identifier.
            result: The AttemptResult to persist.
            attempt_dir: Directory to write artifacts into.

        Returns:
            Path to the written attempt_log.json.
        """
        attempt_dir.mkdir(parents=True, exist_ok=True)
        log_path = attempt_dir / "attempt_log.json"
        log_data = {
            "attempt_id": attempt_id,
            "status": result.status.value,
            "steps_taken": result.steps_taken,
            "duration_seconds": result.duration_seconds,
            "cost_usd": result.cost_usd,
            "errors": result.errors,
            "fields_filled": result.fields_filled,
            "screenshots": result.screenshots,
            "confirmation_text": result.confirmation_text,
            "confirmation_url": result.confirmation_url,
        }
        with open(log_path, "w") as f:
            json.dump(log_data, f, indent=2, default=str)
        return log_path

    def _randomized_delay(self, base_seconds: int) -> int:
        """Return a randomized delay between base and 2.5x base.

        Args:
            base_seconds: Minimum delay.

        Returns:
            Random integer in [base_seconds, base_seconds * 2.5].
        """
        return random.randint(base_seconds, int(base_seconds * 2.5))

    def _get_platform_name(self, runner: SiteRunner) -> str:
        """Derive platform name from a runner instance.

        Args:
            runner: The SiteRunner instance.

        Returns:
            Lowercase platform name string.
        """
        name = type(runner).__name__.lower()
        # Strip "runner" suffix: "WorkdayRunner" -> "workday"
        if name.endswith("runner"):
            name = name[: -len("runner")]
        return name or "unknown"

    def _detect_platform_name(self, url: str) -> str:
        """Detect platform name from URL via registered runners.

        Args:
            url: Job application URL.

        Returns:
            Platform name string, or "unknown".
        """
        runner = self.detect_platform(url)
        if runner is not None:
            return self._get_platform_name(runner)
        return "unknown"

    def _build_batch_summary(
        self,
        results: list[AttemptResult],
        stopped_early: bool,
        stop_reason: Optional[str],
        paused_items: list[int],
    ) -> BatchSummary:
        """Build a BatchSummary from a list of AttemptResults.

        Args:
            results: All AttemptResults from the batch.
            stopped_early: Whether the batch was stopped before completion.
            stop_reason: Reason for early stop, if any.
            paused_items: Queue IDs of items that need HITL review.

        Returns:
            BatchSummary with aggregated counts.
        """
        verified = sum(1 for r in results if r.status == AttemptStatus.APPLIED_VERIFIED)
        soft = sum(1 for r in results if r.status == AttemptStatus.APPLIED_SOFT)
        paused = sum(1 for r in results if r.status.value.startswith("paused"))
        failed = sum(1 for r in results if r.status.value.startswith("failed"))
        skipped = sum(1 for r in results if r.status.value.startswith("skipped"))

        return BatchSummary(
            total=len(results),
            verified=verified,
            soft=soft,
            paused=paused,
            failed=failed,
            skipped=skipped,
            stopped_early=stopped_early,
            stop_reason=stop_reason,
            hitl_required=paused > 0,
            paused_items=paused_items,
        )

    @property
    def consecutive_failures(self) -> int:
        """Current consecutive failure count."""
        return self._consecutive_failures

    @property
    def daily_attempts(self) -> int:
        """Number of attempts today."""
        return self._daily_attempts

    @property
    def daily_cost(self) -> float:
        """Total cost today in USD."""
        return self._daily_cost
