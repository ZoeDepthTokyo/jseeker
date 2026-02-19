"""Tests for ApplyMonitor health monitoring and circuit breaker."""

from __future__ import annotations

import pytest

from jseeker.automation.apply_monitor import ApplyMonitor
from jseeker.models import (
    AttemptResult,
    AttemptStatus,
    MonitorDecision,
    RateLimitConfig,
)

# ── Helpers ──────────────────────────────────────────────────────────


def make_result(status: str, cost_usd: float = 0.0) -> AttemptResult:
    """Create a minimal AttemptResult with the given status."""
    return AttemptResult(
        status=AttemptStatus(status),
        screenshots=[],
        confirmation_text=None,
        confirmation_url=None,
        errors=[],
        steps_taken=1,
        duration_seconds=1.0,
        fields_filled={},
        cost_usd=cost_usd,
    )


@pytest.fixture
def monitor() -> ApplyMonitor:
    """Fresh monitor with default config."""
    return ApplyMonitor()


@pytest.fixture
def tight_monitor() -> ApplyMonitor:
    """Monitor with tight limits for easier threshold testing."""
    return ApplyMonitor(
        config=RateLimitConfig(
            max_per_hour=3,
            max_per_day=5,
            max_cost_per_day_usd=1.0,
        )
    )


# ── Tests ────────────────────────────────────────────────────────────


class TestConsecutiveFailures:
    """Tests for consecutive failure circuit breaker."""

    def test_consecutive_failures_pauses_engine(self, monitor: ApplyMonitor):
        """3 consecutive failures should pause the engine."""
        for _ in range(3):
            decision = monitor.record_attempt(make_result("failed_permanent"), "workday")
        assert decision.should_continue is False
        assert decision.consecutive_failures == 3
        assert "consecutive failures" in decision.pause_reason

    def test_single_failure_does_not_pause(self, monitor: ApplyMonitor):
        """A single failure should not stop the engine."""
        decision = monitor.record_attempt(make_result("failed_permanent"), "workday")
        assert decision.should_continue is True
        assert decision.consecutive_failures == 1

    def test_two_failures_does_not_pause(self, monitor: ApplyMonitor):
        """Two consecutive failures should still allow continuation."""
        for _ in range(2):
            decision = monitor.record_attempt(make_result("failed_permanent"), "workday")
        assert decision.should_continue is True
        assert decision.consecutive_failures == 2

    def test_success_resets_consecutive_counter(self, monitor: ApplyMonitor):
        """A success between failures should reset the consecutive counter."""
        monitor.record_attempt(make_result("failed_permanent"), "workday")
        monitor.record_attempt(make_result("failed_permanent"), "workday")
        # Success resets
        monitor.record_attempt(make_result("applied_verified"), "workday")
        decision = monitor.check_health()
        assert decision.consecutive_failures == 0
        assert decision.should_continue is True

    def test_soft_success_also_resets_counter(self, monitor: ApplyMonitor):
        """applied_soft should also reset the consecutive failure counter."""
        monitor.record_attempt(make_result("failed_permanent"), "workday")
        monitor.record_attempt(make_result("failed_permanent"), "workday")
        monitor.record_attempt(make_result("applied_soft"), "workday")
        decision = monitor.check_health()
        assert decision.consecutive_failures == 0


class TestPlatformDisable:
    """Tests for per-platform circuit breaker."""

    def test_platform_failures_disables_platform(self, monitor: ApplyMonitor):
        """3 failures on same platform should disable it."""
        for _ in range(3):
            decision = monitor.record_attempt(make_result("failed_permanent"), "greenhouse")
        assert "greenhouse" in decision.platform_disabled

    def test_reset_platform_re_enables(self, monitor: ApplyMonitor):
        """reset_platform() should remove it from disabled set."""
        for _ in range(3):
            monitor.record_attempt(make_result("failed_permanent"), "greenhouse")
        monitor.reset_platform("greenhouse")
        decision = monitor.check_health()
        assert "greenhouse" not in decision.platform_disabled

    def test_different_platforms_tracked_independently(self, monitor: ApplyMonitor):
        """Failures on different platforms should not cross-contaminate."""
        monitor.record_attempt(make_result("failed_permanent"), "workday")
        monitor.record_attempt(make_result("failed_permanent"), "workday")
        monitor.record_attempt(make_result("failed_permanent"), "greenhouse")
        # Neither should be disabled yet (workday=2, greenhouse=1)
        decision = monitor.check_health()
        assert "workday" not in decision.platform_disabled
        assert "greenhouse" not in decision.platform_disabled


class TestRateLimits:
    """Tests for daily and hourly rate limits."""

    def test_daily_limit_stops_engine(self, tight_monitor: ApplyMonitor):
        """Exceeding daily limit should stop the engine."""
        for _ in range(5):
            decision = tight_monitor.record_attempt(make_result("applied_soft"), "workday")
        assert decision.should_continue is False
        assert "Daily limit" in decision.pause_reason
        assert decision.daily_count == 5

    def test_hourly_limit_throttles(self, tight_monitor: ApplyMonitor):
        """Exceeding hourly limit should throttle the engine."""
        for _ in range(3):
            decision = tight_monitor.record_attempt(make_result("applied_soft"), "workday")
        assert decision.should_continue is False
        assert "Hourly limit" in decision.pause_reason
        assert decision.hourly_count == 3

    def test_cost_cap_stops_engine(self, tight_monitor: ApplyMonitor):
        """Exceeding cost cap should stop the engine."""
        decision = tight_monitor.record_attempt(
            make_result("applied_soft", cost_usd=1.50), "workday"
        )
        assert decision.should_continue is False
        assert "cost cap" in decision.pause_reason.lower()
        assert decision.daily_cost_usd == 1.50


class TestCheckHealth:
    """Tests for check_health() passive monitoring."""

    def test_check_health_returns_green_under_limits(self, monitor: ApplyMonitor):
        """A fresh monitor should report healthy."""
        decision = monitor.check_health()
        assert decision.should_continue is True
        assert decision.pause_reason is None
        assert decision.consecutive_failures == 0
        assert decision.daily_count == 0
        assert decision.hourly_count == 0
        assert decision.daily_cost_usd == 0.0

    def test_check_health_reflects_recorded_state(self, monitor: ApplyMonitor):
        """check_health() should reflect previously recorded attempts."""
        monitor.record_attempt(make_result("applied_soft", cost_usd=0.10), "workday")
        decision = monitor.check_health()
        assert decision.daily_count == 1
        assert decision.hourly_count == 1
        assert decision.daily_cost_usd == pytest.approx(0.10)


class TestAlertMessages:
    """Tests for HITL alert messages."""

    def test_monitor_decision_has_alert_message_on_pause(self, monitor: ApplyMonitor):
        """3 consecutive failures should produce an alert message."""
        for _ in range(3):
            decision = monitor.record_attempt(make_result("failed_permanent"), "workday")
        assert decision.alert_message is not None
        assert "HITL required" in decision.alert_message

    def test_cost_cap_alert_message(self, tight_monitor: ApplyMonitor):
        """Cost cap breach should produce an alert message."""
        decision = tight_monitor.record_attempt(
            make_result("applied_soft", cost_usd=2.00), "workday"
        )
        assert decision.alert_message is not None
        assert "cost cap" in decision.alert_message.lower()

    def test_no_alert_when_healthy(self, monitor: ApplyMonitor):
        """Healthy state should have no alert message."""
        decision = monitor.check_health()
        assert decision.alert_message is None


class TestMonitorDecisionModel:
    """Tests for MonitorDecision Pydantic model."""

    def test_default_values(self):
        """MonitorDecision should have sensible defaults."""
        d = MonitorDecision(should_continue=True)
        assert d.pause_reason is None
        assert d.platform_disabled == []
        assert d.consecutive_failures == 0
        assert d.daily_count == 0
        assert d.hourly_count == 0
        assert d.daily_cost_usd == 0.0
        assert d.alert_message is None

    def test_model_serialization(self):
        """MonitorDecision should serialize to dict cleanly."""
        d = MonitorDecision(
            should_continue=False,
            pause_reason="test",
            platform_disabled=["workday"],
            consecutive_failures=3,
            daily_count=10,
            hourly_count=5,
            daily_cost_usd=2.50,
            alert_message="Stop!",
        )
        data = d.model_dump()
        assert data["should_continue"] is False
        assert data["platform_disabled"] == ["workday"]
        assert data["daily_cost_usd"] == 2.50


class TestMixedStatusTracking:
    """Tests for status types that neither reset nor increment failure counters."""

    def test_pause_status_does_not_reset_failures(self, monitor: ApplyMonitor):
        """Non-failure pause statuses should not reset consecutive counter."""
        monitor.record_attempt(make_result("failed_permanent"), "workday")
        monitor.record_attempt(make_result("failed_permanent"), "workday")
        # A CAPTCHA pause is neither success nor failure
        monitor.record_attempt(make_result("paused_captcha"), "workday")
        decision = monitor.check_health()
        assert decision.consecutive_failures == 2

    def test_timeout_counts_as_failure(self, monitor: ApplyMonitor):
        """paused_timeout should count as a failure."""
        for _ in range(3):
            monitor.record_attempt(make_result("paused_timeout"), "workday")
        decision = monitor.check_health()
        assert decision.should_continue is False
        assert decision.consecutive_failures == 3

    def test_selector_failed_counts_as_failure(self, monitor: ApplyMonitor):
        """paused_selector_failed should count as a failure."""
        for _ in range(3):
            monitor.record_attempt(make_result("paused_selector_failed"), "workday")
        decision = monitor.check_health()
        assert decision.should_continue is False
