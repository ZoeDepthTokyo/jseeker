"""Tests for AutoApplyEngine orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autojs.auto_apply import AutoApplyEngine
from autojs.ats_runners.base import SiteRunner
from jseeker.models import (
    AttemptResult,
    AttemptStatus,
    BatchSummary,
    RateLimitConfig,
    VerificationResult,
)

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_answer_bank():
    """Create a mock AnswerBank to avoid loading YAML."""
    bank = MagicMock()
    bank.personal_info = {"us": MagicMock()}
    bank.screening_patterns = []
    bank.resume_formats = {"default": "pdf"}
    return bank


@pytest.fixture
def engine(mock_answer_bank):
    """Create an AutoApplyEngine with default config and mock answer bank."""
    return AutoApplyEngine(
        answer_bank=mock_answer_bank,
        config=RateLimitConfig(),
    )


class FakeRunner(SiteRunner):
    """Fake runner for testing that matches a configurable URL pattern."""

    def __init__(self, pattern: str = "fake.ats.com", result_status=None):
        super().__init__()
        self.pattern = pattern
        self.result_status = result_status or AttemptStatus.APPLIED_SOFT

    def detect(self, url: str) -> bool:
        return self.pattern in url.lower()

    def fill_and_submit(self, page, job_url, resume_path, answers, market="us", dry_run=True):
        return AttemptResult(
            status=self.result_status,
            steps_taken=3,
            duration_seconds=1.5,
            fields_filled={"first_name": "Test"},
        )


class FailingRunner(SiteRunner):
    """Runner that always returns FAILED_PERMANENT."""

    def __init__(self, pattern: str = "fail.ats.com"):
        super().__init__()
        self.pattern = pattern

    def detect(self, url: str) -> bool:
        return self.pattern in url.lower()

    def fill_and_submit(self, page, job_url, resume_path, answers, market="us", dry_run=True):
        return AttemptResult(
            status=AttemptStatus.FAILED_PERMANENT,
            errors=["Simulated failure"],
        )


# ── Engine Init ──────────────────────────────────────────────────────


def test_engine_init_defaults(mock_answer_bank):
    """Engine initializes with default config."""
    engine = AutoApplyEngine(answer_bank=mock_answer_bank)
    assert engine.daily_attempts == 0
    assert engine.daily_cost == 0.0
    assert engine.consecutive_failures == 0
    assert engine.config.max_per_hour == 10
    assert engine.config.max_per_day == 50


def test_engine_init_custom_config(mock_answer_bank):
    """Engine accepts custom RateLimitConfig."""
    config = RateLimitConfig(max_per_hour=5, max_per_day=20)
    engine = AutoApplyEngine(answer_bank=mock_answer_bank, config=config)
    assert engine.config.max_per_hour == 5
    assert engine.config.max_per_day == 20


# ── Runner Registration & Detection ─────────────────────────────────


def test_register_runner(engine):
    """Runners can be registered."""
    runner = FakeRunner("example.com")
    engine.register_runner(runner)
    assert len(engine._runners) == 1


def test_detect_workday_routes_correctly(engine):
    """WorkdayRunner detected for Workday URLs."""
    from autojs.ats_runners.workday import WorkdayRunner

    wd = WorkdayRunner()
    engine.register_runner(wd)
    result = engine.detect_platform("https://company.myworkdayjobs.com/jobs/123")
    assert result is wd


def test_detect_greenhouse_routes_correctly(engine):
    """GreenhouseRunner detected for Greenhouse URLs."""
    from autojs.ats_runners.greenhouse import GreenhouseRunner

    gh = GreenhouseRunner()
    engine.register_runner(gh)
    result = engine.detect_platform("https://boards.greenhouse.io/company/jobs/123")
    assert result is gh


def test_detect_unknown_returns_none(engine):
    """Unknown URLs return None."""
    engine.register_runner(FakeRunner("fake.ats.com"))
    result = engine.detect_platform("https://unknown-site.com/jobs/456")
    assert result is None


def test_detect_linkedin_skipped(engine):
    """LinkedIn URLs return SKIPPED_LINKEDIN."""
    with patch("jseeker.tracker.check_dedup", return_value=False):
        result = engine.apply_single(
            job_url="https://linkedin.com/jobs/view/123",
            resume_path=Path("fake_resume.pdf"),
        )
    assert result.status == AttemptStatus.SKIPPED_LINKEDIN


# ── Dedup ────────────────────────────────────────────────────────────


def test_dedup_blocks_duplicate(engine):
    """Duplicate URLs are skipped."""
    with patch("jseeker.tracker.check_dedup", return_value=True):
        result = engine.apply_single(
            job_url="https://boards.greenhouse.io/company/jobs/123",
            resume_path=Path("resume.pdf"),
        )
    assert result.status == AttemptStatus.SKIPPED_DUPLICATE


# ── Rate Limiting ────────────────────────────────────────────────────


def test_rate_limit_hourly(mock_answer_bank):
    """Hourly rate limit blocks after max_per_hour."""
    config = RateLimitConfig(max_per_hour=2, max_per_day=100)
    engine = AutoApplyEngine(answer_bank=mock_answer_bank, config=config)
    engine.register_runner(FakeRunner("fake.ats.com"))

    with patch("jseeker.tracker.check_dedup", return_value=False):
        engine.apply_single("https://fake.ats.com/job/1", Path("r.pdf"))
        engine.apply_single("https://fake.ats.com/job/2", Path("r.pdf"))
        r3 = engine.apply_single("https://fake.ats.com/job/3", Path("r.pdf"))

    # First two consume slots, third is blocked
    assert r3.status == AttemptStatus.PAUSED_COST_CAP


def test_rate_limit_daily(mock_answer_bank):
    """Daily rate limit blocks after max_per_day."""
    config = RateLimitConfig(max_per_hour=100, max_per_day=2)
    engine = AutoApplyEngine(answer_bank=mock_answer_bank, config=config)
    engine.register_runner(FakeRunner("fake.ats.com"))

    with patch("jseeker.tracker.check_dedup", return_value=False):
        engine.apply_single("https://fake.ats.com/job/1", Path("r.pdf"))
        engine.apply_single("https://fake.ats.com/job/2", Path("r.pdf"))
        r3 = engine.apply_single("https://fake.ats.com/job/3", Path("r.pdf"))

    assert r3.status == AttemptStatus.PAUSED_COST_CAP


def test_rate_limit_cost(mock_answer_bank):
    """Cost cap blocks when daily cost exceeded."""
    config = RateLimitConfig(max_per_hour=100, max_per_day=100, max_cost_per_day_usd=0.01)
    engine = AutoApplyEngine(answer_bank=mock_answer_bank, config=config)
    # Manually set cost above cap
    engine._daily_cost = 0.02
    assert engine._check_rate_limit() is False


# ── Batch Processing ─────────────────────────────────────────────────


def test_apply_batch_stops_on_3_failures(mock_answer_bank):
    """Batch stops after 3 consecutive failures."""
    config = RateLimitConfig(max_per_hour=100, max_per_day=100)
    engine = AutoApplyEngine(answer_bank=mock_answer_bank, config=config)

    fail_result = AttemptResult(status=AttemptStatus.FAILED_PERMANENT, errors=["Simulated failure"])

    def fake_apply_single(job_url, resume_path, market="us", dry_run=True, attempt_dir=None):
        engine._update_counters(fail_result)
        return fail_result

    queue = [{"job_url": f"https://fail.ats.com/job/{i}", "resume_path": "r.pdf"} for i in range(6)]

    with patch.object(engine, "apply_single", side_effect=fake_apply_single):
        summary = engine.apply_batch(queue)

    # 3 failures processed, then loop breaks before 4th
    assert isinstance(summary, BatchSummary)
    assert summary.total == 3
    assert summary.failed == 3
    assert engine.consecutive_failures == 3


# ── Artifacts ────────────────────────────────────────────────────────


def test_artifacts_saved_to_correct_path(engine, tmp_path):
    """Attempt artifacts are saved to the specified directory."""
    result = AttemptResult(
        status=AttemptStatus.APPLIED_SOFT,
        steps_taken=5,
        duration_seconds=2.3,
    )
    log_path = engine._save_artifacts("test-id", result, tmp_path)
    assert log_path.exists()
    assert log_path.name == "attempt_log.json"

    with open(log_path) as f:
        data = json.load(f)
    assert data["attempt_id"] == "test-id"
    assert data["status"] == "applied_soft"


def test_save_artifacts_format(engine, tmp_path):
    """Verify JSON structure of saved artifacts."""
    result = AttemptResult(
        status=AttemptStatus.FAILED_PERMANENT,
        steps_taken=2,
        duration_seconds=1.0,
        cost_usd=0.05,
        errors=["timeout"],
        fields_filled={"email": "test@example.com"},
        screenshots=["screenshot1.png"],
        confirmation_text="confirmed",
        confirmation_url="https://example.com/confirm",
    )
    log_path = engine._save_artifacts("fmt-id", result, tmp_path)

    with open(log_path) as f:
        data = json.load(f)

    expected_keys = {
        "attempt_id",
        "status",
        "steps_taken",
        "duration_seconds",
        "cost_usd",
        "errors",
        "fields_filled",
        "screenshots",
        "confirmation_text",
        "confirmation_url",
    }
    assert set(data.keys()) == expected_keys
    assert data["cost_usd"] == 0.05
    assert data["errors"] == ["timeout"]
    assert data["fields_filled"] == {"email": "test@example.com"}
    assert data["confirmation_text"] == "confirmed"


# ── Cooldown ─────────────────────────────────────────────────────────


def test_cooldown_randomization(engine):
    """Randomized delay is within [base, 2.5 * base]."""
    base = 60
    for _ in range(50):
        delay = engine._randomized_delay(base)
        assert base <= delay <= int(base * 2.5)


# ── Failure Tracking ─────────────────────────────────────────────────


def test_consecutive_failure_tracking(engine):
    """Consecutive failures reset on success."""
    # Simulate 2 failures
    fail_result = AttemptResult(status=AttemptStatus.FAILED_PERMANENT)
    engine._update_counters(fail_result)
    engine._update_counters(fail_result)
    assert engine.consecutive_failures == 2

    # Simulate success — resets counter
    success_result = AttemptResult(status=AttemptStatus.APPLIED_VERIFIED)
    engine._update_counters(success_result)
    assert engine.consecutive_failures == 0


def test_consecutive_failure_increments_on_paused(engine):
    """Paused statuses also count as failures."""
    paused_result = AttemptResult(status=AttemptStatus.PAUSED_TIMEOUT)
    engine._update_counters(paused_result)
    assert engine.consecutive_failures == 1


def test_skip_status_does_not_increment_failures(engine):
    """Skip statuses do not increment consecutive failures."""
    skip_result = AttemptResult(status=AttemptStatus.SKIPPED_DUPLICATE)
    engine._update_counters(skip_result)
    assert engine.consecutive_failures == 0


# ── Verifier Integration ────────────────────────────────────────────


def test_verifier_wired_into_apply_with_page(mock_answer_bank):
    """Verifier upgrades APPLIED_SOFT to APPLIED_VERIFIED when hard signal found."""
    engine = AutoApplyEngine(answer_bank=mock_answer_bank, config=RateLimitConfig())
    runner = FakeRunner("fake.ats.com", result_status=AttemptStatus.APPLIED_SOFT)
    engine.register_runner(runner)

    verified_result = VerificationResult(
        is_verified=True,
        confidence="hard",
        signal_matched="url_thankyou",
        confirmation_text="Thank you for applying",
        confirmation_url="https://fake.ats.com/thankyou",
    )

    mock_page = MagicMock()
    with (
        patch("jseeker.tracker.check_dedup", return_value=False),
        patch.object(engine.verifier, "verify", return_value=verified_result),
    ):
        result = engine.apply_with_page(
            page=mock_page,
            job_url="https://fake.ats.com/job/1",
            resume_path=Path("resume.pdf"),
            dry_run=False,
        )

    assert result.status == AttemptStatus.APPLIED_VERIFIED
    assert result.confirmation_text == "Thank you for applying"
    assert result.confirmation_url == "https://fake.ats.com/thankyou"


# ── Monitor Integration ─────────────────────────────────────────────


def test_monitor_stops_batch_on_consecutive_failures(mock_answer_bank):
    """Monitor stops batch when consecutive failures exceed threshold."""
    config = RateLimitConfig(max_per_hour=100, max_per_day=100)
    engine = AutoApplyEngine(answer_bank=mock_answer_bank, config=config)

    fail_result = AttemptResult(status=AttemptStatus.FAILED_PERMANENT, errors=["Simulated failure"])

    def fake_apply_single(job_url, resume_path, market="us", dry_run=True, attempt_dir=None):
        engine._update_counters(fail_result)
        return fail_result

    queue = [{"job_url": f"https://fail.ats.com/job/{i}", "resume_path": "r.pdf"} for i in range(6)]

    with patch.object(engine, "apply_single", side_effect=fake_apply_single):
        summary = engine.apply_batch(queue)

    assert isinstance(summary, BatchSummary)
    assert summary.stopped_early is True
    assert summary.failed > 0


# ── BatchSummary ────────────────────────────────────────────────────


def test_batch_summary_returned(mock_answer_bank):
    """apply_batch returns a BatchSummary with correct counts."""
    config = RateLimitConfig(max_per_hour=100, max_per_day=100)
    engine = AutoApplyEngine(answer_bank=mock_answer_bank, config=config)
    engine.register_runner(FakeRunner("fake.ats.com"))

    soft_result = AttemptResult(status=AttemptStatus.APPLIED_SOFT)

    def fake_apply_single(job_url, resume_path, market="us", dry_run=True, attempt_dir=None):
        engine._update_counters(soft_result)
        return soft_result

    queue = [{"job_url": f"https://fake.ats.com/job/{i}", "resume_path": "r.pdf"} for i in range(3)]

    with patch.object(engine, "apply_single", side_effect=fake_apply_single):
        summary = engine.apply_batch(queue)

    assert isinstance(summary, BatchSummary)
    assert summary.total == 3
    assert summary.soft == 3
    assert summary.stopped_early is False
    assert summary.hitl_required is False


def test_hitl_flag_set_when_pauses_exist(mock_answer_bank):
    """hitl_required is True when any result has a paused status."""
    config = RateLimitConfig(max_per_hour=100, max_per_day=100)
    engine = AutoApplyEngine(answer_bank=mock_answer_bank, config=config)
    engine.register_runner(FakeRunner("fake.ats.com"))

    paused_result = AttemptResult(status=AttemptStatus.PAUSED_UNKNOWN_QUESTION)

    def fake_apply_single(job_url, resume_path, market="us", dry_run=True, attempt_dir=None):
        engine._update_counters(paused_result)
        return paused_result

    queue = [
        {
            "job_url": "https://fake.ats.com/job/1",
            "resume_path": "r.pdf",
            "queue_id": 42,
        }
    ]

    with patch.object(engine, "apply_single", side_effect=fake_apply_single):
        summary = engine.apply_batch(queue)

    assert summary.hitl_required is True
    assert 42 in summary.paused_items
