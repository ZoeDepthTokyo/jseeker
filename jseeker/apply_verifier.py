"""Post-submission verification for auto-apply attempts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from jseeker.models import VerificationResult

logger = logging.getLogger(__name__)


class ApplyVerifier:
    """Hard verification of post-submission page state."""

    WORKDAY_HARD_SIGNALS = {
        "url_thankyou": lambda url: any(
            s in url for s in ["/thankyou", "/confirmationpage", "/myApplications"]
        ),
        "dom_thank_you_for_applying": lambda text: "thank you for applying"
        in text.lower(),
        "dom_application_submitted": lambda text: "application has been submitted"
        in text.lower(),
        "dom_successfully_submitted": lambda text: "successfully submitted"
        in text.lower(),
    }
    WORKDAY_AUTOMATION_ID = "thankYouMessage"

    GREENHOUSE_HARD_SIGNALS = {
        "url_confirmation": lambda url: url.endswith("/confirmation")
        or "/confirmation" in url,
        "dom_application_submitted": lambda text: "application has been submitted"
        in text.lower(),
        "dom_received_application": lambda text: "we've received your application"
        in text.lower(),
    }
    GREENHOUSE_CONTAINER = ".application-confirmation"

    ERROR_SELECTORS = [
        "[data-automation-id='errorBanner']",
        ".error-banner",
        ".alert-error",
        "[role='alert'][class*='error']",
    ]

    def verify(
        self,
        page,
        platform: str,
        attempt_log: dict,
        logs_dir: Optional[Path] = None,
    ) -> VerificationResult:
        """Verify submission was successful.

        Args:
            page: Playwright Page object (or mock in tests).
            platform: ATS platform name ("workday" or "greenhouse").
            attempt_log: Dict from the runner with attempt metadata.
            logs_dir: Directory for saving verification artifacts.

        Returns:
            VerificationResult with verification outcome.
        """
        try:
            current_url = page.url
            page_text = page.inner_text("body") if hasattr(page, "inner_text") else ""

            # Check error banners first
            error_banners = self._check_error_banners(page)
            if error_banners:
                return VerificationResult(
                    is_verified=False,
                    confidence="none",
                    error_banners=error_banners,
                    form_still_visible=True,
                    reason=f"Error banners detected: {error_banners}",
                )

            # Check form still visible
            form_visible = self._check_form_visible(page)

            # Platform-specific verification
            if platform == "workday":
                return self._verify_workday(
                    page, current_url, page_text, form_visible, logs_dir
                )
            elif platform == "greenhouse":
                return self._verify_greenhouse(
                    page, current_url, page_text, form_visible, logs_dir
                )
            else:
                return VerificationResult(
                    is_verified=False,
                    confidence="none",
                    reason=f"Unknown platform: {platform}",
                )
        except Exception as e:
            logger.error(f"Verification error: {e}")
            return VerificationResult(
                is_verified=False,
                confidence="none",
                reason=f"Verification exception: {e}",
            )

    def _verify_workday(
        self, page, url: str, text: str, form_visible: bool, logs_dir: Optional[Path]
    ) -> VerificationResult:
        """Verify Workday submission via automation-id, URL, and DOM signals."""
        # Check automation-id first (most reliable)
        try:
            elem = page.query_selector(
                f"[data-automation-id='{self.WORKDAY_AUTOMATION_ID}']"
            )
            if elem:
                screenshot = self._save_screenshot(
                    page, logs_dir, "confirmation_screenshot.png"
                )
                self._save_text(text, logs_dir, "confirmation_text.txt")
                return VerificationResult(
                    is_verified=True,
                    confidence="hard",
                    signal_matched="automation_id_thankYouMessage",
                    confirmation_text=text[:500],
                    confirmation_url=url,
                    screenshot_path=screenshot,
                    reason="Workday thankYouMessage element found",
                )
        except Exception:
            pass

        # Check URL signals
        for name, check in self.WORKDAY_HARD_SIGNALS.items():
            if name.startswith("url_") and check(url):
                screenshot = self._save_screenshot(
                    page, logs_dir, "confirmation_screenshot.png"
                )
                self._save_text(text, logs_dir, "confirmation_text.txt")
                return VerificationResult(
                    is_verified=True,
                    confidence="hard",
                    signal_matched=name,
                    confirmation_text=text[:500],
                    confirmation_url=url,
                    screenshot_path=screenshot,
                    reason=f"Workday URL signal: {name}",
                )

        # Check DOM signals
        for name, check in self.WORKDAY_HARD_SIGNALS.items():
            if name.startswith("dom_") and check(text):
                screenshot = self._save_screenshot(
                    page, logs_dir, "confirmation_screenshot.png"
                )
                self._save_text(text, logs_dir, "confirmation_text.txt")
                return VerificationResult(
                    is_verified=True,
                    confidence="hard",
                    signal_matched=name,
                    confirmation_text=text[:500],
                    confirmation_url=url,
                    screenshot_path=screenshot,
                    reason=f"Workday DOM signal: {name}",
                )

        # Soft: page changed but no hard signal
        if not form_visible:
            screenshot = self._save_screenshot(
                page, logs_dir, "last_page_screenshot.png"
            )
            return VerificationResult(
                is_verified=False,
                confidence="soft",
                confirmation_url=url,
                form_still_visible=False,
                screenshot_path=screenshot,
                reason="Form gone but no hard confirmation signal",
            )

        # None: form still visible or ambiguous
        self._save_html(page, logs_dir)
        return VerificationResult(
            is_verified=False,
            confidence="none",
            form_still_visible=form_visible,
            reason="No confirmation signals detected",
        )

    def _verify_greenhouse(
        self, page, url: str, text: str, form_visible: bool, logs_dir: Optional[Path]
    ) -> VerificationResult:
        """Verify Greenhouse submission via container, URL, and DOM signals."""
        # Check container
        try:
            elem = page.query_selector(self.GREENHOUSE_CONTAINER)
            if elem:
                screenshot = self._save_screenshot(
                    page, logs_dir, "confirmation_screenshot.png"
                )
                self._save_text(text, logs_dir, "confirmation_text.txt")
                return VerificationResult(
                    is_verified=True,
                    confidence="hard",
                    signal_matched="container_application_confirmation",
                    confirmation_text=text[:500],
                    confirmation_url=url,
                    screenshot_path=screenshot,
                    reason="Greenhouse .application-confirmation found",
                )
        except Exception:
            pass

        for name, check in self.GREENHOUSE_HARD_SIGNALS.items():
            if name.startswith("url_") and check(url):
                screenshot = self._save_screenshot(
                    page, logs_dir, "confirmation_screenshot.png"
                )
                self._save_text(text, logs_dir, "confirmation_text.txt")
                return VerificationResult(
                    is_verified=True,
                    confidence="hard",
                    signal_matched=name,
                    confirmation_text=text[:500],
                    confirmation_url=url,
                    screenshot_path=screenshot,
                    reason=f"Greenhouse URL signal: {name}",
                )

        for name, check in self.GREENHOUSE_HARD_SIGNALS.items():
            if name.startswith("dom_") and check(text):
                screenshot = self._save_screenshot(
                    page, logs_dir, "confirmation_screenshot.png"
                )
                self._save_text(text, logs_dir, "confirmation_text.txt")
                return VerificationResult(
                    is_verified=True,
                    confidence="hard",
                    signal_matched=name,
                    confirmation_text=text[:500],
                    confirmation_url=url,
                    screenshot_path=screenshot,
                    reason=f"Greenhouse DOM signal: {name}",
                )

        if not form_visible:
            screenshot = self._save_screenshot(
                page, logs_dir, "last_page_screenshot.png"
            )
            return VerificationResult(
                is_verified=False,
                confidence="soft",
                form_still_visible=False,
                screenshot_path=screenshot,
                reason="Form gone but no hard signal",
            )

        self._save_html(page, logs_dir)
        return VerificationResult(
            is_verified=False,
            confidence="none",
            form_still_visible=form_visible,
            reason="No Greenhouse confirmation signals",
        )

    def _check_error_banners(self, page) -> list[str]:
        """Check for error banner elements on page.

        Args:
            page: Playwright Page object.

        Returns:
            List of error banner text strings found.
        """
        banners = []
        for sel in self.ERROR_SELECTORS:
            try:
                elem = page.query_selector(sel)
                if elem:
                    text = elem.inner_text()
                    if text.strip():
                        banners.append(text.strip()[:200])
            except Exception:
                pass
        return banners

    def _check_form_visible(self, page) -> bool:
        """Check if a form element is still visible on the page.

        Args:
            page: Playwright Page object.

        Returns:
            True if a visible form element is found.
        """
        try:
            form = page.query_selector("form")
            return form is not None and form.is_visible()
        except Exception:
            return False

    def _save_screenshot(
        self, page, logs_dir: Optional[Path], filename: str
    ) -> Optional[Path]:
        """Save a page screenshot to logs_dir.

        Args:
            page: Playwright Page object.
            logs_dir: Directory to save into, or None to skip.
            filename: Screenshot filename.

        Returns:
            Path to saved screenshot, or None.
        """
        if logs_dir is None:
            return None
        try:
            p = Path(logs_dir) / filename
            p.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(p))
            return p
        except Exception:
            return None

    def _save_text(self, text: str, logs_dir: Optional[Path], filename: str) -> None:
        """Save text content to logs_dir.

        Args:
            text: Text content to save (truncated to 5000 chars).
            logs_dir: Directory to save into, or None to skip.
            filename: Output filename.
        """
        if logs_dir is None:
            return
        try:
            p = Path(logs_dir) / filename
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text[:5000], encoding="utf-8")
        except Exception:
            pass

    def _save_html(self, page, logs_dir: Optional[Path]) -> None:
        """Save page HTML to logs_dir for debugging.

        Args:
            page: Playwright Page object.
            logs_dir: Directory to save into, or None to skip.
        """
        if logs_dir is None:
            return
        try:
            html = page.content()
            p = Path(logs_dir) / "page_html.txt"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(html[:50000], encoding="utf-8")
        except Exception:
            pass
