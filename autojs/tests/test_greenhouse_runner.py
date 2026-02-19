"""Tests for GreenhouseRunner and greenhouse.yaml config."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from autojs.ats_runners.base import SiteRunner
from autojs.ats_runners.greenhouse import GreenhouseRunner, _SELECTORS_PATH

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def runner():
    """Create a GreenhouseRunner."""
    return GreenhouseRunner()


@pytest.fixture
def config():
    """Load the greenhouse YAML config."""
    with open(_SELECTORS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── URL Detection ────────────────────────────────────────────────────


def test_detect_boards_greenhouse(runner):
    """Detects boards.greenhouse.io URLs."""
    assert runner.detect("https://boards.greenhouse.io/company/jobs/123") is True


def test_detect_job_boards_greenhouse(runner):
    """Detects job-boards.greenhouse.io URLs."""
    assert runner.detect("https://job-boards.greenhouse.io/company/jobs/456") is True


def test_detect_rejects_workday(runner):
    """Does not match Workday URLs."""
    assert runner.detect("https://company.myworkdayjobs.com/en-US/jobs/123") is False


def test_detect_rejects_lever(runner):
    """Does not match Lever URLs."""
    assert runner.detect("https://jobs.lever.co/company/abc-123") is False


def test_detect_rejects_random(runner):
    """Does not match random URLs."""
    assert runner.detect("https://example.com/careers/apply") is False


# ── YAML Config Validation ───────────────────────────────────────────


def test_yaml_loads_and_validates(config):
    """YAML file loads without errors and has expected top-level keys."""
    assert config["version"] == 1
    assert config["platform"] == "greenhouse"
    assert "url_patterns" in config
    assert "selectors" in config
    assert "confirmation_signals" in config
    assert "field_mappings" in config


def test_yaml_has_all_selector_keys(config):
    """YAML has selectors for all required fields."""
    required_keys = [
        "resume_upload",
        "first_name",
        "last_name",
        "email",
        "phone",
        "submit_button",
    ]
    for key in required_keys:
        assert key in config["selectors"], f"Missing selector: {key}"
        assert len(config["selectors"][key]) > 0, f"Empty selectors for: {key}"


def test_yaml_has_confirmation_signals(config):
    """YAML has confirmation signals for verification."""
    signals = config["confirmation_signals"]
    assert "url_patterns" in signals
    assert "dom_text" in signals
    assert "dom_selectors" in signals
    assert len(signals["url_patterns"]) > 0
    assert len(signals["dom_text"]) > 0


# ── Runner Type ──────────────────────────────────────────────────────


def test_greenhouse_runner_is_site_runner(runner):
    """GreenhouseRunner is a SiteRunner subclass."""
    assert isinstance(runner, SiteRunner)


# ── Verification Logic ──────────────────────────────────────────────


def test_verification_url_patterns(config):
    """URL patterns include expected confirmation paths."""
    url_patterns = config["confirmation_signals"]["url_patterns"]
    assert "/confirmation" in url_patterns
    assert "/thank" in url_patterns


def test_verification_dom_text_signals(config):
    """DOM text signals include common Greenhouse confirmation messages."""
    signals = config["confirmation_signals"]["dom_text"]
    # At least one signal about application submission
    submission_signals = [s for s in signals if "application" in s.lower()]
    assert len(submission_signals) >= 1


def test_verification_no_match_returns_false(runner):
    """_verify_submission returns (False, '') when no signals match."""
    from unittest.mock import MagicMock, PropertyMock

    page = MagicMock()
    type(page).url = PropertyMock(return_value="https://boards.greenhouse.io/company/jobs/123")
    page.text_content.return_value = "some random page content"
    page.is_visible.return_value = False

    verified, text = runner._verify_submission(page)
    assert verified is False
    assert text == ""


def test_verification_url_match(runner):
    """_verify_submission detects confirmation URL."""
    from unittest.mock import MagicMock, PropertyMock

    page = MagicMock()
    type(page).url = PropertyMock(return_value="https://boards.greenhouse.io/company/confirmation")
    page.text_content.return_value = ""

    verified, text = runner._verify_submission(page)
    assert verified is True
    assert "URL match" in text


def test_verification_dom_text_match(runner):
    """_verify_submission detects confirmation text in DOM."""
    from unittest.mock import MagicMock, PropertyMock

    page = MagicMock()
    type(page).url = PropertyMock(return_value="https://boards.greenhouse.io/company/jobs/123")
    page.text_content.return_value = "Thank you! Your application has been submitted."
    page.is_visible.return_value = False

    verified, text = runner._verify_submission(page)
    assert verified is True
    assert "Text match" in text


# ── Mock Form Fixture ────────────────────────────────────────────────


def test_greenhouse_form_fixture_exists():
    """Greenhouse mock HTML fixture exists."""
    fixture_path = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "ats_pages" / "greenhouse_form.html"
    assert fixture_path.exists()
    content = fixture_path.read_text()
    assert "first_name" in content
    assert "submit_app" in content
    assert "resume_file" in content
