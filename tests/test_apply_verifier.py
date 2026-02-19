"""Tests for ApplyVerifier post-submission verification."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jseeker.automation.apply_verifier import ApplyVerifier

# ── Helper ───────────────────────────────────────────────────────────


def make_mock_page(
    url: str = "https://example.com",
    body_text: str = "",
    automation_id_element=None,
    greenhouse_container=None,
    form_visible: bool = False,
    error_banner_text: str = "",
) -> MagicMock:
    """Build a mock Playwright page for verifier tests.

    Args:
        url: Page URL to report.
        body_text: Text returned by inner_text("body").
        automation_id_element: Element returned for Workday automation-id selector.
        greenhouse_container: Element returned for Greenhouse container selector.
        form_visible: Whether the form element reports as visible.
        error_banner_text: Text for an error banner element (empty = no banner).
    """
    page = MagicMock()
    page.url = url
    page.inner_text.return_value = body_text

    form_elem = MagicMock()
    form_elem.is_visible.return_value = form_visible

    error_elem = None
    if error_banner_text:
        error_elem = MagicMock()
        error_elem.inner_text.return_value = error_banner_text

    def qs_side_effect(sel: str):
        if sel == "form":
            return form_elem if form_visible else None
        if "thankYouMessage" in sel and automation_id_element is not None:
            return automation_id_element
        if ".application-confirmation" in sel and greenhouse_container is not None:
            return greenhouse_container
        if "errorBanner" in sel and error_elem is not None:
            return error_elem
        return None

    page.query_selector.side_effect = qs_side_effect
    page.screenshot.return_value = None
    page.content.return_value = "<html></html>"
    return page


@pytest.fixture
def verifier() -> ApplyVerifier:
    return ApplyVerifier()


# ── Workday Hard Signals ─────────────────────────────────────────────


def test_hard_verification_workday_url_signal(verifier: ApplyVerifier) -> None:
    """URL containing /thankyou produces hard verification."""
    page = make_mock_page(url="https://company.myworkdayjobs.com/thankyou")
    result = verifier.verify(page, "workday", {})
    assert result.is_verified is True
    assert result.confidence == "hard"
    assert result.signal_matched == "url_thankyou"


def test_hard_verification_workday_dom_signal(verifier: ApplyVerifier) -> None:
    """Body text 'thank you for applying' produces hard verification."""
    page = make_mock_page(
        url="https://company.myworkdayjobs.com/somepage",
        body_text="Thank you for applying to our position!",
    )
    result = verifier.verify(page, "workday", {})
    assert result.is_verified is True
    assert result.confidence == "hard"
    assert result.signal_matched == "dom_thank_you_for_applying"


def test_hard_verification_workday_automation_id(verifier: ApplyVerifier) -> None:
    """Workday automation-id thankYouMessage element produces hard verification."""
    elem = MagicMock()
    page = make_mock_page(
        url="https://company.myworkdayjobs.com/somepage",
        automation_id_element=elem,
    )
    result = verifier.verify(page, "workday", {})
    assert result.is_verified is True
    assert result.confidence == "hard"
    assert result.signal_matched == "automation_id_thankYouMessage"


def test_hard_verification_workday_confirmationpage_url(
    verifier: ApplyVerifier,
) -> None:
    """URL containing /confirmationpage produces hard verification."""
    page = make_mock_page(url="https://company.myworkdayjobs.com/confirmationpage")
    result = verifier.verify(page, "workday", {})
    assert result.is_verified is True
    assert result.confidence == "hard"
    assert result.signal_matched == "url_thankyou"


# ── Greenhouse Hard Signals ──────────────────────────────────────────


def test_hard_verification_greenhouse_url_signal(verifier: ApplyVerifier) -> None:
    """URL ending with /confirmation produces hard verification."""
    page = make_mock_page(url="https://boards.greenhouse.io/company/jobs/123/confirmation")
    result = verifier.verify(page, "greenhouse", {})
    assert result.is_verified is True
    assert result.confidence == "hard"
    assert result.signal_matched == "url_confirmation"


def test_hard_verification_greenhouse_dom_signal(verifier: ApplyVerifier) -> None:
    """Body text containing received application produces hard verification."""
    page = make_mock_page(
        url="https://boards.greenhouse.io/company/jobs/123",
        body_text="We've received your application and will review it shortly.",
    )
    result = verifier.verify(page, "greenhouse", {})
    assert result.is_verified is True
    assert result.confidence == "hard"
    assert result.signal_matched == "dom_received_application"


def test_hard_verification_greenhouse_container(verifier: ApplyVerifier) -> None:
    """Greenhouse .application-confirmation container produces hard verification."""
    container = MagicMock()
    page = make_mock_page(
        url="https://boards.greenhouse.io/company/jobs/123",
        greenhouse_container=container,
    )
    result = verifier.verify(page, "greenhouse", {})
    assert result.is_verified is True
    assert result.confidence == "hard"
    assert result.signal_matched == "container_application_confirmation"


# ── Soft / None Signals ──────────────────────────────────────────────


def test_soft_verification_no_hard_signal_form_gone(verifier: ApplyVerifier) -> None:
    """No hard signal but form not visible produces soft verification."""
    page = make_mock_page(
        url="https://company.myworkdayjobs.com/unknown",
        body_text="Some generic page content",
        form_visible=False,
    )
    result = verifier.verify(page, "workday", {})
    assert result.is_verified is False
    assert result.confidence == "soft"
    assert result.form_still_visible is False


def test_no_verification_form_still_visible(verifier: ApplyVerifier) -> None:
    """Form still visible with no signals produces none confidence."""
    page = make_mock_page(
        url="https://company.myworkdayjobs.com/apply",
        body_text="Fill out the form below",
        form_visible=True,
    )
    result = verifier.verify(page, "workday", {})
    assert result.is_verified is False
    assert result.confidence == "none"
    assert result.form_still_visible is True


def test_no_verification_error_banner_present(verifier: ApplyVerifier) -> None:
    """Error banner detected produces none confidence with is_verified=False."""
    page = make_mock_page(
        url="https://company.myworkdayjobs.com/apply",
        error_banner_text="Please fix the errors below",
        form_visible=True,
    )
    result = verifier.verify(page, "workday", {})
    assert result.is_verified is False
    assert result.confidence == "none"
    assert len(result.error_banners) > 0
    assert "Please fix the errors below" in result.error_banners[0]


# ── Edge Cases ───────────────────────────────────────────────────────


def test_unknown_platform_returns_none(verifier: ApplyVerifier) -> None:
    """Unknown platform returns none confidence."""
    page = make_mock_page(url="https://lever.co/jobs/123")
    result = verifier.verify(page, "lever", {})
    assert result.is_verified is False
    assert result.confidence == "none"
    assert "Unknown platform" in result.reason


def test_verification_saves_screenshot_on_success(verifier: ApplyVerifier, tmp_path: Path) -> None:
    """Successful verification saves screenshot artifact."""
    page = make_mock_page(url="https://company.myworkdayjobs.com/thankyou")

    # Make screenshot actually write a file
    def fake_screenshot(path: str, **kwargs):
        Path(path).write_bytes(b"fake_png_data")

    page.screenshot.side_effect = fake_screenshot

    result = verifier.verify(page, "workday", {}, logs_dir=tmp_path)
    assert result.is_verified is True
    assert result.screenshot_path is not None
    assert result.screenshot_path.exists()


def test_verification_exception_returns_safe_result(verifier: ApplyVerifier) -> None:
    """Exception during verification returns safe none result."""
    page = MagicMock()
    page.url = "https://example.com"
    page.inner_text.side_effect = RuntimeError("Page crashed")

    result = verifier.verify(page, "workday", {})
    assert result.is_verified is False
    assert result.confidence == "none"
    assert "exception" in result.reason.lower()
