"""Tests for the SiteRunner abstract base class."""

import time

import pytest

from autojs.ats_runners.base import SiteRunner
from jseeker.models import AttemptResult, AttemptStatus


class _DummyRunner(SiteRunner):
    """Minimal concrete subclass for testing."""

    def detect(self, url: str) -> bool:
        return "example.com" in url

    def fill_and_submit(self, page, job_url, resume_path, answers, market="us", dry_run=True):
        return self._build_result(status=AttemptStatus.APPLIED_SOFT)


class TestBaseCannotInstantiate:
    """ABC enforcement tests."""

    def test_base_cannot_instantiate(self):
        with pytest.raises(TypeError):
            SiteRunner()

    def test_concrete_subclass_instantiates(self):
        runner = _DummyRunner()
        assert isinstance(runner, SiteRunner)
        assert runner.attempt_log == []


class TestLogStep:
    """Test _log_step behavior."""

    def test_log_step_format(self):
        runner = _DummyRunner()
        runner._start_time = time.time()
        runner._log_step("fill", "#name", "John", "success")

        assert len(runner.attempt_log) == 1
        entry = runner.attempt_log[0]
        assert entry["action"] == "fill"
        assert entry["target"] == "#name"
        assert entry["value"] == "John"
        assert entry["result"] == "success"
        assert "timestamp" in entry
        assert "duration_ms" in entry

    def test_log_step_redacts_password(self):
        runner = _DummyRunner()
        runner._start_time = time.time()
        runner._log_step("fill", "input[type='password']", "secret123", "success")

        entry = runner.attempt_log[0]
        assert entry["value"] == "***"
        assert "secret" not in str(entry)


class TestBuildResult:
    """Test _build_result helper."""

    def test_build_result_defaults(self):
        runner = _DummyRunner()
        runner._start_time = time.time()
        result = runner._build_result(status=AttemptStatus.QUEUED)

        assert isinstance(result, AttemptResult)
        assert result.status == AttemptStatus.QUEUED
        assert result.screenshots == []
        assert result.errors == []
        assert result.fields_filled == {}
        assert result.steps_taken == 0
        assert result.cost_usd == 0.0

    def test_build_result_with_fields(self):
        runner = _DummyRunner()
        runner._start_time = time.time()
        runner._log_step("fill", "#x", "y", "success")
        runner._log_step("click", "#btn", "", "success")

        result = runner._build_result(
            status=AttemptStatus.APPLIED_VERIFIED,
            screenshots=["shot1.png", "shot2.png"],
            confirmation_text="Thank you",
            confirmation_url="https://example.com/thanks",
            errors=["minor warning"],
            fields_filled={"name": "John"},
        )

        assert result.status == AttemptStatus.APPLIED_VERIFIED
        assert result.screenshots == ["shot1.png", "shot2.png"]
        assert result.confirmation_text == "Thank you"
        assert result.confirmation_url == "https://example.com/thanks"
        assert result.errors == ["minor warning"]
        assert result.steps_taken == 2
        assert result.fields_filled == {"name": "John"}
        assert result.duration_seconds >= 0.0


class TestElapsed:
    """Test elapsed time tracking."""

    def test_elapsed_tracking(self):
        runner = _DummyRunner()
        runner._start_time = time.time() - 1.5  # Simulate 1.5s elapsed
        elapsed = runner._elapsed()
        assert elapsed >= 1.0
        assert elapsed < 5.0
