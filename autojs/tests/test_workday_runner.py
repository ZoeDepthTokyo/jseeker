"""Tests for the WorkdayRunner."""

from unittest.mock import MagicMock

import pytest
import yaml

from jseeker.automation.answer_bank import answer_screening_question, load_answer_bank
from jseeker.automation.ats_runners.base import SiteRunner
from jseeker.automation.ats_runners.workday import WorkdayRunner, _SELECTORS_PATH


@pytest.fixture
def runner():
    """Create a WorkdayRunner instance."""
    return WorkdayRunner()


# ── URL Detection ─────────────────────────────────────────────────────


class TestDetect:
    """Test URL pattern matching."""

    def test_detect_myworkdayjobs_url(self, runner):
        assert runner.detect("https://company.myworkdayjobs.com/en-US/careers/job/123")

    def test_detect_wd5_url(self, runner):
        assert runner.detect("https://wd5.myworkdayjobs.com/acme/job/456")

    def test_detect_workday_careers_url(self, runner):
        assert runner.detect("https://company.workday.com/en/career/detail/789")

    def test_detect_myworkday_url(self, runner):
        assert runner.detect("https://myworkday.com/acme/d/task/123")

    def test_detect_rejects_greenhouse_url(self, runner):
        assert not runner.detect("https://boards.greenhouse.io/acme/jobs/123")

    def test_detect_rejects_lever_url(self, runner):
        assert not runner.detect("https://jobs.lever.co/acme/456")

    def test_detect_rejects_random_url(self, runner):
        assert not runner.detect("https://example.com/careers")


# ── YAML Config ───────────────────────────────────────────────────────


class TestYAMLConfig:
    """Test Workday YAML configuration file."""

    def test_yaml_loads_and_validates(self):
        assert _SELECTORS_PATH.exists(), f"YAML not found at {_SELECTORS_PATH}"
        with open(_SELECTORS_PATH, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        assert "version" in config
        assert "platform" in config
        assert config["platform"] == "workday"
        assert "url_patterns" in config
        assert "selectors" in config
        assert "confirmation_signals" in config

    def test_yaml_has_all_selector_keys(self):
        with open(_SELECTORS_PATH, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        required_keys = [
            "apply_button",
            "resume_upload",
            "first_name",
            "last_name",
            "email",
            "phone",
            "submit_button",
            "next_button",
        ]
        for key in required_keys:
            assert key in config["selectors"], f"Missing selector: {key}"
            assert len(config["selectors"][key]) > 0, f"Empty selector list: {key}"

    def test_yaml_has_confirmation_signals(self):
        with open(_SELECTORS_PATH, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        signals = config["confirmation_signals"]
        assert "url_patterns" in signals
        assert "dom_text" in signals
        assert "dom_selectors" in signals
        assert len(signals["url_patterns"]) > 0
        assert len(signals["dom_text"]) > 0


# ── Runner Type ───────────────────────────────────────────────────────


class TestRunnerType:
    """Test WorkdayRunner is a proper SiteRunner subclass."""

    def test_workday_runner_is_site_runner(self, runner):
        assert isinstance(runner, SiteRunner)


# ── Verification Logic ───────────────────────────────────────────────


class TestVerification:
    """Test _verify_submission logic without a real browser."""

    def test_verification_url_patterns(self, runner):
        """Mock page with URL containing /thankyou."""

        class _FakePage:
            url = "https://company.myworkdayjobs.com/thankyou"

        verified, text = runner._verify_submission(_FakePage())
        assert verified is True
        assert "/thankyou" in text

    def test_verification_dom_text_signals(self, runner):
        """Mock page with confirmation text in body."""

        class _FakePage:
            url = "https://company.myworkdayjobs.com/status"

            def text_content(self, selector):
                return "Your application has been submitted successfully."

            def is_visible(self, sel, timeout=1000):
                return False

        verified, text = runner._verify_submission(_FakePage())
        assert verified is True
        assert "application has been submitted" in text.lower()

    def test_verification_no_match_returns_false(self, runner):
        """Mock page with no confirmation signals."""

        class _FakePage:
            url = "https://company.myworkdayjobs.com/apply/step3"

            def text_content(self, selector):
                return "Please complete all fields."

            def is_visible(self, sel, timeout=1000):
                return False

        verified, text = runner._verify_submission(_FakePage())
        assert verified is False
        assert text == ""


# ── SMS Consent ──────────────────────────────────────────────────────


class TestSMSConsent:
    """Test _handle_sms_consent with mock page."""

    def test_sms_consent_checkbox_clicked(self, runner):
        """Checkbox found and unchecked -> click() called."""
        mock_elem = MagicMock()
        mock_elem.is_checked.return_value = False

        mock_page = MagicMock()
        mock_page.query_selector.return_value = mock_elem

        runner._handle_sms_consent(mock_page)
        mock_elem.click.assert_called_once()

    def test_sms_consent_skipped_when_not_found(self, runner):
        """No checkbox found -> no error raised."""
        mock_page = MagicMock()
        mock_page.query_selector.return_value = None

        # Should not raise
        runner._handle_sms_consent(mock_page)


# ── FCRA Acknowledgement ─────────────────────────────────────────────


class TestFCRAAck:
    """Test _handle_fcra_ack with mock page."""

    def test_fcra_ack_checkbox_clicked(self, runner):
        """FCRA checkbox found and unchecked -> click() called."""
        mock_elem = MagicMock()
        mock_elem.is_checked.return_value = False

        mock_page = MagicMock()
        mock_page.query_selector.return_value = mock_elem

        runner._handle_fcra_ack(mock_page)
        mock_elem.click.assert_called_once()


# ── Reasons for Leaving Pattern ──────────────────────────────────────


class TestReasonsForLeaving:
    """Test screening pattern for reasons for leaving."""

    def test_reasons_for_leaving_pattern_match(self):
        """'reason for leaving' should match the pattern and not pause."""
        bank = load_answer_bank()
        answer, is_pause = answer_screening_question(
            bank, "What is the reason for leaving your last position?", "us"
        )
        assert is_pause is False
        assert "career growth" in answer.lower()


# ── Skills Tags ──────────────────────────────────────────────────────


class TestSkillsTags:
    """Test _fill_skills_tags with mock page."""

    def test_skills_tags_filled(self, runner):
        """Skills input found -> type() called for each skill."""
        mock_elem = MagicMock()

        mock_page = MagicMock()
        mock_page.query_selector.return_value = mock_elem

        skills = ["UX Design", "Figma", "User Research"]
        runner._fill_skills_tags(mock_page, skills)

        assert mock_elem.type.call_count == 3
        assert mock_elem.press.call_count == 3
        mock_elem.type.assert_any_call("UX Design")
        mock_elem.type.assert_any_call("Figma")
        mock_elem.type.assert_any_call("User Research")
