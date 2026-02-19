"""Base SiteRunner ABC for ATS form automation."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from jseeker.models import AttemptResult, AttemptStatus

if TYPE_CHECKING:
    from autojs.answer_bank import AnswerBank

logger = logging.getLogger(__name__)


class SiteRunner(ABC):
    """Abstract base class for ATS-specific form fillers."""

    def __init__(self) -> None:
        self.attempt_log: list[dict] = []
        self._start_time: float = 0.0

    @abstractmethod
    def detect(self, url: str) -> bool:
        """Return True if this runner handles the given URL."""
        ...

    @abstractmethod
    def fill_and_submit(
        self,
        page: Page,
        job_url: str,
        resume_path: Path,
        answers: AnswerBank,
        market: str = "us",
        dry_run: bool = True,
    ) -> AttemptResult:
        """Fill out and optionally submit the application form."""
        ...

    def _start_attempt(self) -> None:
        """Reset state for a new attempt."""
        self.attempt_log = []
        self._start_time = time.time()

    def _elapsed(self) -> float:
        """Return elapsed seconds since attempt start."""
        return round(time.time() - self._start_time, 2)

    def _fill_field(self, page: Page, selector: str, value: str, timeout: int = 5000) -> bool:
        """Fill a form field. Returns True on success."""
        try:
            page.fill(selector, value, timeout=timeout)
            self._log_step("fill", selector, value, "success")
            return True
        except (PlaywrightTimeout, Exception) as e:
            self._log_step("fill", selector, value, f"failed: {e}")
            return False

    def _click(self, page: Page, selector: str, timeout: int = 5000) -> bool:
        """Click an element. Returns True on success."""
        try:
            page.click(selector, timeout=timeout)
            self._log_step("click", selector, "", "success")
            return True
        except (PlaywrightTimeout, Exception) as e:
            self._log_step("click", selector, "", f"failed: {e}")
            return False

    def _select_option(self, page: Page, selector: str, value: str, timeout: int = 5000) -> bool:
        """Select dropdown option. Returns True on success."""
        try:
            page.select_option(selector, value, timeout=timeout)
            self._log_step("select", selector, value, "success")
            return True
        except (PlaywrightTimeout, Exception) as e:
            self._log_step("select", selector, value, f"failed: {e}")
            return False

    def _upload_file(self, page: Page, selector: str, file_path: Path) -> bool:
        """Upload a file. Returns True on success."""
        try:
            page.set_input_files(selector, str(file_path))
            self._log_step("upload", selector, str(file_path), "success")
            return True
        except (PlaywrightTimeout, Exception) as e:
            self._log_step("upload", selector, str(file_path), f"failed: {e}")
            return False

    def _screenshot(self, page: Page, step_name: str, attempt_dir: Path) -> Path:
        """Take a screenshot. Returns the path."""
        attempt_dir.mkdir(parents=True, exist_ok=True)
        path = attempt_dir / f"{step_name}.png"
        try:
            page.screenshot(path=str(path), full_page=True)
            self._log_step("screenshot", str(path), "", "success")
        except Exception as e:
            self._log_step("screenshot", str(path), "", f"failed: {e}")
        return path

    def _check_for_overlay(self, page: Page) -> bool:
        """Check for and dismiss known overlays (cookie consent, GDPR, etc).

        Returns:
            True if an overlay was dismissed.
        """
        overlay_selectors = [
            "button[id*='cookie-accept']",
            "button[id*='consent']",
            "button[class*='cookie-accept']",
            "[data-testid='cookie-accept']",
            "button:has-text('Accept')",
            "button:has-text('Accept All')",
            "button:has-text('I agree')",
        ]
        for sel in overlay_selectors:
            try:
                if page.is_visible(sel, timeout=500):
                    page.click(sel, timeout=1000)
                    self._log_step("dismiss_overlay", sel, "", "success")
                    return True
            except Exception:
                continue
        return False

    def _log_step(self, action: str, target: str, value: str, result: str) -> None:
        """Log a step in the attempt log."""
        self.attempt_log.append(
            {
                "action": action,
                "target": target,
                "value": (value if action != "fill" or "password" not in target.lower() else "***"),
                "result": result,
                "timestamp": time.time(),
                "duration_ms": round((time.time() - self._start_time) * 1000),
            }
        )

    def _build_result(
        self,
        status: AttemptStatus,
        screenshots: list[str] | None = None,
        confirmation_text: str | None = None,
        confirmation_url: str | None = None,
        errors: list[str] | None = None,
        fields_filled: dict[str, str] | None = None,
    ) -> AttemptResult:
        """Build an AttemptResult with common fields filled in."""
        return AttemptResult(
            status=status,
            screenshots=screenshots or [],
            confirmation_text=confirmation_text,
            confirmation_url=confirmation_url,
            errors=errors or [],
            steps_taken=len(self.attempt_log),
            duration_seconds=self._elapsed(),
            fields_filled=fields_filled or {},
            cost_usd=0.0,
        )
