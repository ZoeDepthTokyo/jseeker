"""Tests for auto-apply models and DB schema extensions."""

from __future__ import annotations

import sqlite3

import pytest

from jseeker.models import AttemptResult, AttemptStatus, RateLimitConfig
from jseeker.tracker import (
    check_dedup,
    check_recurring_errors,
    get_queue_stats,
    get_queued_applications,
    init_db,
    log_apply_error,
    queue_application,
    update_queue_status,
)

# ── AttemptStatus Enum Tests ──────────────────────────────────────


def test_attempt_status_all_terminal_states():
    """Verify terminal success/failure/skip states exist."""
    terminal = {
        AttemptStatus.APPLIED_VERIFIED,
        AttemptStatus.APPLIED_SOFT,
        AttemptStatus.FAILED_PERMANENT,
        AttemptStatus.SKIPPED_UNSUPPORTED_ATS,
        AttemptStatus.SKIPPED_LINKEDIN,
        AttemptStatus.SKIPPED_DUPLICATE,
        AttemptStatus.SKIPPED_ERROR_PATTERN,
    }
    assert len(terminal) == 7


def test_attempt_status_all_pause_states():
    """Verify all paused_* states exist (17 total)."""
    pause_states = [s for s in AttemptStatus if s.value.startswith("paused_")]
    assert len(pause_states) == 17
    # Verify specific ones
    assert AttemptStatus.PAUSED_CAPTCHA in pause_states
    assert AttemptStatus.PAUSED_2FA in pause_states
    assert AttemptStatus.PAUSED_MAX_STEPS in pause_states
    assert AttemptStatus.PAUSED_COST_CAP in pause_states
    assert AttemptStatus.PAUSED_STUCK in pause_states


def test_attempt_status_active_states():
    """Verify queued and in_progress exist."""
    assert AttemptStatus.QUEUED.value == "queued"
    assert AttemptStatus.IN_PROGRESS.value == "in_progress"


def test_attempt_status_total_count():
    """Verify total enum count is 26 (2 active + 2 success + 1 failure + 4 skip + 17 pause)."""
    assert len(AttemptStatus) == 26


# ── AttemptResult Model Tests ─────────────────────────────────────


def test_attempt_result_serialization():
    """Create AttemptResult, serialize to dict, deserialize back."""
    result = AttemptResult(
        status=AttemptStatus.APPLIED_VERIFIED,
        screenshots=["/tmp/screen1.png"],
        confirmation_text="Application submitted",
        confirmation_url="https://example.com/confirm",
        errors=[],
        steps_taken=5,
        duration_seconds=12.3,
        fields_filled={"name": "John", "email": "john@example.com"},
        cost_usd=0.02,
    )
    data = result.model_dump()
    restored = AttemptResult.model_validate(data)
    assert restored.status == AttemptStatus.APPLIED_VERIFIED
    assert restored.screenshots == ["/tmp/screen1.png"]
    assert restored.confirmation_text == "Application submitted"
    assert restored.steps_taken == 5
    assert restored.fields_filled["name"] == "John"
    assert restored.cost_usd == 0.02


def test_attempt_result_defaults():
    """Check all default values are correct."""
    result = AttemptResult()
    assert result.status == AttemptStatus.QUEUED
    assert result.screenshots == []
    assert result.confirmation_text is None
    assert result.confirmation_url is None
    assert result.errors == []
    assert result.steps_taken == 0
    assert result.duration_seconds == 0.0
    assert result.fields_filled == {}
    assert result.cost_usd == 0.0


# ── RateLimitConfig Tests ─────────────────────────────────────────


def test_rate_limit_config_defaults():
    """Verify default rate limit values."""
    config = RateLimitConfig()
    assert config.max_per_hour == 10
    assert config.max_per_day == 50
    assert config.per_employer_per_day == 3
    assert config.cooldown_seconds == 120
    assert config.max_cost_per_day_usd == 5.0
    assert config.page_load_timeout_ms == 30000
    assert config.page_load_retry_timeout_ms == 60000


# ── Queue DB Tests ────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path):
    """Create isolated test DB."""
    path = tmp_path / "test.db"
    init_db(path)
    return path


def test_queue_application(db_path):
    """Insert and verify a queued application."""
    qid = queue_application(
        job_url="https://example.com/job/1",
        resume_path="/tmp/resume.pdf",
        ats_platform="greenhouse",
        market="us",
        db_path=db_path,
    )
    assert qid is not None
    assert qid > 0

    # Verify data
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM apply_queue WHERE id = ?", (qid,)).fetchone()
    conn.close()
    assert row["job_url"] == "https://example.com/job/1"
    assert row["status"] == "queued"
    assert row["ats_platform"] == "greenhouse"
    assert row["market"] == "us"


def test_get_queued_applications(db_path):
    """Insert 3 items, get them ordered by queued_at."""
    for i in range(3):
        queue_application(
            job_url=f"https://example.com/job/{i}",
            resume_path=f"/tmp/resume_{i}.pdf",
            ats_platform="workday",
            market="us",
            db_path=db_path,
        )
    results = get_queued_applications(limit=10, db_path=db_path)
    assert len(results) == 3
    # Should be ordered by queued_at ASC
    urls = [r["job_url"] for r in results]
    assert urls == [
        "https://example.com/job/0",
        "https://example.com/job/1",
        "https://example.com/job/2",
    ]


def test_update_queue_status(db_path):
    """Update status and verify."""
    qid = queue_application(
        job_url="https://example.com/job/update",
        resume_path="/tmp/resume.pdf",
        ats_platform="greenhouse",
        market="us",
        db_path=db_path,
    )
    update_queue_status(
        qid,
        "applied_verified",
        attempt_log_path="/tmp/log.json",
        cost_usd=0.05,
        db_path=db_path,
    )
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM apply_queue WHERE id = ?", (qid,)).fetchone()
    conn.close()
    assert row["status"] == "applied_verified"
    assert row["attempt_log_path"] == "/tmp/log.json"
    assert row["cost_usd"] == 0.05
    assert row["completed_at"] is not None


def test_get_queue_stats(db_path):
    """Verify counts by status."""
    queue_application(
        job_url="https://example.com/a",
        resume_path="/tmp/r.pdf",
        ats_platform="greenhouse",
        market="us",
        db_path=db_path,
    )
    queue_application(
        job_url="https://example.com/b",
        resume_path="/tmp/r.pdf",
        ats_platform="greenhouse",
        market="us",
        db_path=db_path,
    )
    qid3 = queue_application(
        job_url="https://example.com/c",
        resume_path="/tmp/r.pdf",
        ats_platform="greenhouse",
        market="us",
        db_path=db_path,
    )
    update_queue_status(qid3, "applied_verified", db_path=db_path)

    stats = get_queue_stats(db_path=db_path)
    assert stats["queued"] == 2
    assert stats["applied_verified"] == 1


def test_log_apply_error(db_path):
    """Insert an error and verify."""
    qid = queue_application(
        job_url="https://example.com/err",
        resume_path="/tmp/r.pdf",
        ats_platform="workday",
        market="us",
        db_path=db_path,
    )
    log_apply_error(
        queue_id=qid,
        error_type="captcha",
        message="CAPTCHA detected",
        screenshot_path="/tmp/captcha.png",
        platform="workday",
        url_pattern="workday.com/*/apply",
        db_path=db_path,
    )
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM apply_errors WHERE queue_id = ?", (qid,)
    ).fetchone()
    conn.close()
    assert row["error_type"] == "captcha"
    assert row["error_message"] == "CAPTCHA detected"
    assert row["ats_platform"] == "workday"


def test_recurring_error_detection(db_path):
    """Insert 3+ same pattern errors, verify count >= 3."""
    qid = queue_application(
        job_url="https://example.com/recurring",
        resume_path="/tmp/r.pdf",
        ats_platform="workday",
        market="us",
        db_path=db_path,
    )
    for _ in range(4):
        log_apply_error(
            queue_id=qid,
            error_type="timeout",
            message="Page load timeout",
            platform="workday",
            url_pattern="workday.com/*/apply",
            db_path=db_path,
        )
    count = check_recurring_errors(
        platform="workday",
        error_type="timeout",
        url_pattern="workday.com/*/apply",
        db_path=db_path,
    )
    assert count >= 3


def test_dedup_on_queue(db_path):
    """Second insert of same URL raises IntegrityError."""
    queue_application(
        job_url="https://example.com/dup",
        resume_path="/tmp/r.pdf",
        ats_platform="greenhouse",
        market="us",
        db_path=db_path,
    )
    with pytest.raises(sqlite3.IntegrityError):
        queue_application(
            job_url="https://example.com/dup",
            resume_path="/tmp/r2.pdf",
            ats_platform="greenhouse",
            market="us",
            db_path=db_path,
        )


def test_dedup_cross_table(db_path):
    """URL in applications table alone is NOT a dedup block.

    check_dedup only blocks on applied_verified / applied_soft in apply_queue
    so that tracked-but-not-auto-applied jobs can still be queued.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO applications (role_title, jd_url) VALUES (?, ?)",
        ("Engineer", "https://example.com/cross"),
    )
    conn.commit()
    conn.close()

    # URL only in applications table — should NOT trigger dedup
    assert check_dedup("https://example.com/cross", db_path=db_path) is False

    # URL with a successful auto-apply status in apply_queue — SHOULD block
    queue_application(
        job_url="https://example.com/cross",
        resume_path="/tmp/r.pdf",
        ats_platform="greenhouse",
        market="us",
        db_path=db_path,
    )
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE apply_queue SET status='applied_verified' WHERE job_url=?",
        ("https://example.com/cross",),
    )
    conn.commit()
    conn.close()

    assert check_dedup("https://example.com/cross", db_path=db_path) is True
    assert check_dedup("https://example.com/new", db_path=db_path) is False


def test_queue_stats_empty_db(db_path):
    """Empty DB returns all zeros for common statuses."""
    stats = get_queue_stats(db_path=db_path)
    assert stats["queued"] == 0
    assert stats["in_progress"] == 0
    assert stats["applied_verified"] == 0
    assert stats["applied_soft"] == 0
    assert stats["failed_permanent"] == 0
