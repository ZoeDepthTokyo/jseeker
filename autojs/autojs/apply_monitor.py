"""Health monitoring and circuit breaker for AutoApplyEngine."""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Optional

from jseeker.models import (
    AttemptResult,
    AttemptStatus,
    MonitorDecision,
    RateLimitConfig,
)

logger = logging.getLogger(__name__)

# Failure statuses that increment consecutive / platform failure counters
_FAILURE_STATUSES = frozenset(
    {
        AttemptStatus.FAILED_PERMANENT,
        AttemptStatus.PAUSED_TIMEOUT,
        AttemptStatus.PAUSED_STUCK,
        AttemptStatus.PAUSED_SELECTOR_FAILED,
    }
)

# Success statuses that reset consecutive failure counter
_SUCCESS_STATUSES = frozenset(
    {
        AttemptStatus.APPLIED_VERIFIED,
        AttemptStatus.APPLIED_SOFT,
    }
)

# Platform disable threshold
_PLATFORM_FAILURE_THRESHOLD = 3

# Global consecutive failure threshold
_CONSECUTIVE_FAILURE_THRESHOLD = 3


class ApplyMonitor:
    """Health monitoring and circuit breaker for AutoApplyEngine.

    Tracks attempt counts, costs, and failure streaks to decide whether
    the engine should continue, pause, or disable specific platforms.
    """

    def __init__(self, config: Optional[RateLimitConfig] = None) -> None:
        self.config = config or RateLimitConfig()
        self._consecutive_failures: int = 0
        self._platform_failures: dict[str, int] = defaultdict(int)
        self._disabled_platforms: set[str] = set()
        self._daily_attempts: list[datetime] = []
        self._hourly_attempts: deque[datetime] = deque()
        self._daily_cost: float = 0.0
        self._day_start: datetime = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    def record_attempt(self, result: AttemptResult, platform: str) -> MonitorDecision:
        """Record an attempt result and return health decision.

        Args:
            result: The outcome of the apply attempt.
            platform: ATS platform identifier (e.g. "workday").

        Returns:
            MonitorDecision indicating whether the engine should continue.
        """
        self._cleanup_expired()
        now = datetime.now()

        # Track counts
        self._daily_attempts.append(now)
        self._hourly_attempts.append(now)
        self._daily_cost += getattr(result, "cost_usd", 0.0)

        # Track failures
        if result.status in _FAILURE_STATUSES:
            self._consecutive_failures += 1
            self._platform_failures[platform] += 1
        elif result.status in _SUCCESS_STATUSES:
            self._consecutive_failures = 0
            self._platform_failures[platform] = 0

        # Check platform disable
        newly_disabled: list[str] = []
        if (
            self._platform_failures[platform] >= _PLATFORM_FAILURE_THRESHOLD
            and platform not in self._disabled_platforms
        ):
            self._disabled_platforms.add(platform)
            newly_disabled.append(platform)
            logger.warning(
                "Platform %s disabled after %d consecutive failures",
                platform,
                _PLATFORM_FAILURE_THRESHOLD,
            )

        return self._evaluate(newly_disabled)

    def check_health(self) -> MonitorDecision:
        """Check current health without recording an attempt.

        Returns:
            MonitorDecision with current engine health status.
        """
        self._cleanup_expired()
        return self._evaluate([])

    def reset_platform(self, platform: str) -> None:
        """Re-enable a disabled platform after manual review.

        Args:
            platform: Platform identifier to re-enable.
        """
        self._disabled_platforms.discard(platform)
        self._platform_failures[platform] = 0
        logger.info("Platform %s re-enabled", platform)

    def _evaluate(self, newly_disabled: list[str]) -> MonitorDecision:
        """Evaluate all health checks and return decision.

        Args:
            newly_disabled: Platforms disabled during this evaluation cycle.

        Returns:
            MonitorDecision with current status.
        """
        daily = len(self._daily_attempts)
        hourly = len(self._hourly_attempts)
        all_disabled = list(self._disabled_platforms)

        # Global stop: consecutive failures
        if self._consecutive_failures >= _CONSECUTIVE_FAILURE_THRESHOLD:
            return MonitorDecision(
                should_continue=False,
                pause_reason=f"{_CONSECUTIVE_FAILURE_THRESHOLD} consecutive failures — engine paused",
                platform_disabled=all_disabled,
                consecutive_failures=self._consecutive_failures,
                daily_count=daily,
                hourly_count=hourly,
                daily_cost_usd=self._daily_cost,
                alert_message=(
                    f"HITL required: {self._consecutive_failures} consecutive "
                    f"failures. Review logs and reset."
                ),
            )

        # Global stop: daily cost cap
        if self._daily_cost >= self.config.max_cost_per_day_usd:
            return MonitorDecision(
                should_continue=False,
                pause_reason=f"Daily cost cap reached: ${self._daily_cost:.2f}",
                platform_disabled=all_disabled,
                consecutive_failures=self._consecutive_failures,
                daily_count=daily,
                hourly_count=hourly,
                daily_cost_usd=self._daily_cost,
                alert_message=(
                    f"HITL required: daily cost cap "
                    f"${self.config.max_cost_per_day_usd} reached."
                ),
            )

        # Global stop: daily attempts
        if daily >= self.config.max_per_day:
            return MonitorDecision(
                should_continue=False,
                pause_reason=f"Daily limit reached: {daily}/{self.config.max_per_day}",
                platform_disabled=all_disabled,
                consecutive_failures=self._consecutive_failures,
                daily_count=daily,
                hourly_count=hourly,
                daily_cost_usd=self._daily_cost,
            )

        # Hourly throttle
        if hourly >= self.config.max_per_hour:
            return MonitorDecision(
                should_continue=False,
                pause_reason=f"Hourly limit reached: {hourly}/{self.config.max_per_hour}",
                platform_disabled=all_disabled,
                consecutive_failures=self._consecutive_failures,
                daily_count=daily,
                hourly_count=hourly,
                daily_cost_usd=self._daily_cost,
            )

        # All good
        return MonitorDecision(
            should_continue=True,
            platform_disabled=newly_disabled,
            consecutive_failures=self._consecutive_failures,
            daily_count=daily,
            hourly_count=hourly,
            daily_cost_usd=self._daily_cost,
        )

    def _cleanup_expired(self) -> None:
        """Remove expired entries from daily and hourly windows."""
        now = datetime.now()
        # Reset daily counters if new day
        if now >= self._day_start + timedelta(days=1):
            self._daily_attempts = []
            self._daily_cost = 0.0
            self._day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        # Clean hourly window
        hour_ago = now - timedelta(hours=1)
        while self._hourly_attempts and self._hourly_attempts[0] < hour_ago:
            self._hourly_attempts.popleft()
