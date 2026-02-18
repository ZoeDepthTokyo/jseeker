"""Greenhouse ATS form filler."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import yaml
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from jseeker.answer_bank import (
    AnswerBank,
    PersonalInfo,
    answer_screening_question,
    get_personal_info,
)
from jseeker.ats_runners.base import SiteRunner
from jseeker.models import AttemptResult, AttemptStatus

logger = logging.getLogger(__name__)

_SELECTORS_PATH = (
    Path(__file__).parent.parent.parent / "data" / "ats_runners" / "greenhouse.yaml"
)


def _load_greenhouse_config() -> dict:
    """Load Greenhouse selectors and config from YAML."""
    with open(_SELECTORS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


class GreenhouseRunner(SiteRunner):
    """Playwright-based Greenhouse form filler.

    Greenhouse applications are typically single-page forms
    with no login required.
    """

    def __init__(self) -> None:
        super().__init__()
        self.config = _load_greenhouse_config()

    def detect(self, url: str) -> bool:
        """Return True if the URL matches a known Greenhouse pattern."""
        url_lower = url.lower()
        for pattern in self.config["url_patterns"]:
            if re.search(pattern, url_lower):
                return True
        return False

    def fill_and_submit(
        self,
        page: Page,
        job_url: str,
        resume_path: Path,
        answers: AnswerBank,
        market: str = "us",
        dry_run: bool = True,
    ) -> AttemptResult:
        """Fill out and optionally submit a Greenhouse application form.

        Args:
            page: Playwright Page instance.
            job_url: URL of the Greenhouse job posting.
            resume_path: Path to the resume PDF.
            answers: AnswerBank with personal info and screening answers.
            market: Market code for personal info lookup.
            dry_run: If True, stop before clicking submit.

        Returns:
            AttemptResult with status and metadata.
        """
        self._start_attempt()
        fields_filled: dict[str, str] = {}
        screenshots: list[str] = []
        errors: list[str] = []

        try:
            # 1. Navigate
            page.goto(job_url, timeout=30000)
            self._log_step("navigate", job_url, "", "success")
            self._check_for_overlay(page)

            # 2. Get personal info for market
            personal = get_personal_info(answers, market)

            # 3. Upload resume (PDF preferred for Greenhouse)
            uploaded = self._try_upload(page, resume_path)
            if not uploaded:
                errors.append("Resume upload failed")

            # 4. Fill personal info
            self._fill_personal_info(page, personal, fields_filled)

            # 5. Handle screening questions
            q_result = self._fill_screening_questions(
                page, answers, market, fields_filled
            )
            if q_result is not None:
                return q_result  # Paused on unknown/salary question

            # 6. Screenshot before submit
            attempt_dir = Path("data/apply_logs/greenhouse_temp")
            ss = self._screenshot(page, "form_before_submit", attempt_dir)
            screenshots.append(str(ss))

            # 7. Dry run -- stop before submit
            if dry_run:
                return self._build_result(
                    status=AttemptStatus.APPLIED_SOFT,
                    screenshots=screenshots,
                    errors=errors,
                    fields_filled=fields_filled,
                )

            # 8. Click submit
            submitted = self._try_selectors(page, "submit_button")
            if not submitted:
                errors.append("Submit button not found")
                return self._build_result(
                    status=AttemptStatus.PAUSED_SELECTOR_FAILED,
                    screenshots=screenshots,
                    errors=errors,
                    fields_filled=fields_filled,
                )

            # 9. Verify submission
            page.wait_for_timeout(3000)
            verified, conf_text = self._verify_submission(page)

            ss2 = self._screenshot(page, "confirmation", attempt_dir)
            screenshots.append(str(ss2))

            if verified:
                return self._build_result(
                    status=AttemptStatus.APPLIED_VERIFIED,
                    screenshots=screenshots,
                    confirmation_text=conf_text,
                    confirmation_url=page.url,
                    fields_filled=fields_filled,
                )
            else:
                return self._build_result(
                    status=AttemptStatus.PAUSED_AMBIGUOUS_RESULT,
                    screenshots=screenshots,
                    errors=["Submission not verified"],
                    fields_filled=fields_filled,
                )

        except PlaywrightTimeout as e:
            return self._build_result(
                status=AttemptStatus.PAUSED_TIMEOUT,
                screenshots=screenshots,
                errors=[str(e)],
                fields_filled=fields_filled,
            )
        except Exception as e:
            errors.append(str(e))
            return self._build_result(
                status=AttemptStatus.FAILED_PERMANENT,
                screenshots=screenshots,
                errors=errors,
                fields_filled=fields_filled,
            )

    def _try_selectors(self, page: Page, field_key: str) -> bool:
        """Try selector fallback chain from config.

        Returns:
            True if any selector matched and was clicked.
        """
        selectors = self.config.get("selectors", {}).get(field_key, [])
        for sel in selectors:
            try:
                if page.is_visible(sel, timeout=2000):
                    page.click(sel, timeout=3000)
                    self._log_step("click", sel, field_key, "success")
                    return True
            except Exception:
                continue
        self._log_step("click", field_key, "", "all_selectors_failed")
        return False

    def _try_fill(self, page: Page, field_key: str, value: str) -> bool:
        """Try fill with selector fallback chain."""
        selectors = self.config.get("selectors", {}).get(field_key, [])
        for sel in selectors:
            if self._fill_field(page, sel, value, timeout=3000):
                return True
        return False

    def _try_upload(self, page: Page, resume_path: Path) -> bool:
        """Try resume upload with fallback selectors."""
        selectors = self.config.get("selectors", {}).get("resume_upload", [])
        for sel in selectors:
            if self._upload_file(page, sel, resume_path):
                return True
        return False

    def _fill_personal_info(
        self, page: Page, info: PersonalInfo, fields_filled: dict[str, str]
    ) -> bool:
        """Fill personal info fields.

        Args:
            page: Playwright Page.
            info: PersonalInfo from the answer bank.
            fields_filled: Dict to record which fields were successfully filled.

        Returns:
            True if all fields with values were filled.
        """
        field_map = {
            "first_name": info.first_name,
            "last_name": info.last_name,
            "email": info.email,
            "phone": info.phone,
            "linkedin": info.linkedin_url,
            "location": info.city,
        }
        success = True
        for field_key, value in field_map.items():
            if value and self._try_fill(page, field_key, value):
                fields_filled[field_key] = value
            elif value:
                success = False
        return success

    # Labels that belong to personal info fields — skip during screening question scan
    _PERSONAL_INFO_LABELS = frozenset(
        {
            "first name",
            "last name",
            "full name",
            "name",
            "email",
            "email address",
            "phone",
            "phone number",
            "mobile",
            "resume",
            "resume/cv",
            "cv",
            "linkedin",
            "linkedin profile",
            "location",
            "city",
            "address",
            "website",
            "cover letter",
            "portfolio",
            "pronouns",
        }
    )

    def _fill_screening_questions(
        self,
        page: Page,
        answers: AnswerBank,
        market: str,
        fields_filled: dict[str, str],
    ) -> Optional[AttemptResult]:
        """Fill screening questions.

        Returns:
            AttemptResult if paused on an unknown question, None if all answered.
        """
        # Prefer the dedicated custom fields section; fall back to broader selectors.
        # Broader selectors (like ".field label") pick up personal info labels too,
        # so we filter those out via _PERSONAL_INFO_LABELS.
        question_selectors = [
            "#custom_fields label",
            ".field label",
            "fieldset legend",
        ]
        for q_sel in question_selectors:
            try:
                questions = page.query_selector_all(q_sel)
                for q_elem in questions:
                    q_text = q_elem.text_content().strip()
                    if not q_text:
                        continue
                    # Strip trailing asterisk (required marker) before matching
                    q_normalized = q_text.rstrip("* \t").lower()
                    if q_normalized in self._PERSONAL_INFO_LABELS:
                        continue  # Personal info field — already handled separately
                    answer, is_pause = answer_screening_question(
                        answers, q_text, market
                    )
                    if is_pause:
                        status = (
                            AttemptStatus.PAUSED_SALARY_QUESTION
                            if "salary" in q_text.lower()
                            else AttemptStatus.PAUSED_UNKNOWN_QUESTION
                        )
                        return self._build_result(
                            status=status,
                            errors=[f"Cannot answer: {q_text}"],
                            fields_filled=fields_filled,
                        )
                    fields_filled[f"screening_{q_text[:50]}"] = answer
            except Exception:
                continue
        return None

    def _verify_submission(self, page: Page) -> tuple[bool, str]:
        """Check for hard verification signals.

        Returns:
            Tuple of (verified, confirmation_text).
        """
        signals = self.config.get("confirmation_signals", {})

        # Check URL patterns
        current_url = page.url.lower()
        for pattern in signals.get("url_patterns", []):
            if pattern in current_url:
                return (True, f"URL match: {pattern}")

        # Check DOM text
        try:
            page_text = page.text_content("body").lower()
        except Exception:
            page_text = ""

        for text_signal in signals.get("dom_text", []):
            if text_signal.lower() in page_text:
                return (True, f"Text match: {text_signal}")

        # Check DOM selectors
        for sel in signals.get("dom_selectors", []):
            try:
                if page.is_visible(sel, timeout=1000):
                    return (True, f"Selector match: {sel}")
            except Exception:
                continue

        return (False, "")
