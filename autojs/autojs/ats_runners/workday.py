"""Workday ATS form filler."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import yaml
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from autojs.answer_bank import (
    AnswerBank,
    PersonalInfo,
    answer_screening_question,
    get_personal_info,
)
from autojs.ats_runners.base import SiteRunner
from jseeker.models import AttemptResult, AttemptStatus

logger = logging.getLogger(__name__)

_SELECTORS_PATH = Path(__file__).parent.parent.parent.parent / "data" / "ats_runners" / "workday.yaml"


def _load_workday_config() -> dict:
    """Load Workday selectors and config from YAML."""
    with open(_SELECTORS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


class WorkdayRunner(SiteRunner):
    """Playwright-based Workday form filler."""

    def __init__(self) -> None:
        super().__init__()
        self.config = _load_workday_config()

    def detect(self, url: str) -> bool:
        """Return True if the URL matches a known Workday pattern."""
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
        """Fill out and optionally submit a Workday application form."""
        self._start_attempt()
        fields_filled: dict[str, str] = {}
        screenshots: list[str] = []
        errors: list[str] = []

        try:
            # 1. Navigate
            page.goto(
                job_url,
                timeout=self.config.get("page_load_timeout_ms", 45000),
            )
            self._log_step("navigate", job_url, "", "success")
            self._check_for_overlay(page)

            # 2. Click Apply (if button exists)
            self._try_selectors(page, "apply_button")

            # 2b. Handle auth gate — Workday shows a login wall per employer.
            # Each employer has an isolated instance; no unified account exists.
            # Always attempt guest/anonymous flow first.
            guest_result = self._handle_guest_flow(page)
            if guest_result is not None:
                return guest_result  # Paused — login wall with no guest option

            # 3. Get personal info for market
            personal = get_personal_info(answers, market)

            # 4. Upload resume (DOCX preferred for Workday)
            uploaded = self._try_upload(page, resume_path)
            if not uploaded:
                errors.append("Resume upload failed")

            # 5. Fill personal info
            self._fill_personal_info(page, personal, fields_filled)

            # 5b. Fill phone extension if available
            self._fill_phone_extension(page, personal, fields_filled)

            # 5c. Handle SMS consent checkbox
            self._handle_sms_consent(page)

            # 6. Handle screening questions
            q_result = self._fill_screening_questions(page, answers, market, fields_filled)
            if q_result is not None:
                return q_result  # Paused on unknown/salary question

            # 6b. Handle FCRA acknowledgement
            self._handle_fcra_ack(page)

            # 6c. Fill skills tags if available
            skills = getattr(personal, "resume_skills", [])
            if skills:
                self._fill_skills_tags(page, skills)

            # 7. Screenshot before submit
            attempt_dir = Path("data/apply_logs/workday_temp")
            ss = self._screenshot(page, "form_before_submit", attempt_dir)
            screenshots.append(str(ss))

            # 8. Dry run -- stop before submit
            if dry_run:
                return self._build_result(
                    status=AttemptStatus.APPLIED_SOFT,
                    screenshots=screenshots,
                    errors=errors,
                    fields_filled=fields_filled,
                )

            # 9. Click submit
            submitted = self._try_selectors(page, "submit_button")
            if not submitted:
                errors.append("Submit button not found")
                return self._build_result(
                    status=AttemptStatus.PAUSED_SELECTOR_FAILED,
                    screenshots=screenshots,
                    errors=errors,
                    fields_filled=fields_filled,
                )

            # 10. Verify submission
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

    def _handle_guest_flow(self, page: Page) -> Optional[AttemptResult]:
        """Handle Workday per-employer login wall using guest/anonymous flow.

        Workday has no unified account — each employer runs an isolated instance.
        After clicking Apply, some instances show a login gate. This method
        detects that gate and clicks through as guest. If no login wall is
        present the form is already accessible and we return None to continue.

        Returns:
            None if guest flow succeeded or no login wall detected.
            AttemptResult(paused_login_failed) if login wall exists but no guest option.
        """
        # Brief settle time for SPA navigation after Apply click
        try:
            page.wait_for_timeout(1500)
        except Exception:
            pass

        # Detect login wall
        login_wall_selectors = self.config.get("selectors", {}).get("login_wall_signals", [])
        on_login_wall = False
        for sel in login_wall_selectors:
            try:
                if page.is_visible(sel, timeout=2000):
                    on_login_wall = True
                    self._log_step("detect", sel, "login_wall_detected", "found")
                    break
            except Exception:
                continue

        if not on_login_wall:
            # Form is directly accessible — no auth gate
            self._log_step("auth", "guest_flow", "no_login_wall", "skip")
            return None

        # Login wall detected — try guest selectors
        guest_selectors = self.config.get("selectors", {}).get("guest_apply_button", [])
        for sel in guest_selectors:
            try:
                if page.is_visible(sel, timeout=2000):
                    page.click(sel, timeout=3000)
                    page.wait_for_timeout(1500)
                    self._log_step("click", sel, "guest_apply_selected", "success")
                    return None  # Proceeded as guest — continue with form filling
            except Exception:
                continue

        # Login wall present but no guest option found — HITL required
        self._log_step("auth", "guest_flow", "no_guest_option_found", "paused")
        return self._build_result(
            status=AttemptStatus.PAUSED_LOGIN_FAILED,
            errors=[
                "Workday login wall detected but no guest/anonymous apply option found. "
                "This employer may require account creation. Manual intervention needed."
            ],
            fields_filled={},
        )

    def _try_selectors(self, page: Page, field_key: str) -> bool:
        """Try selector fallback chain from config. Returns True if any succeeded."""
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
        """Fill personal info fields."""
        field_map = {
            "first_name": info.first_name,
            "last_name": info.last_name,
            "email": info.email,
            "phone": info.phone,
            "address": info.address,
            "city": info.city,
            "zip": info.zip,
        }
        success = True
        for field_key, value in field_map.items():
            if value and self._try_fill(page, field_key, value):
                fields_filled[field_key] = value
            elif value:
                success = False
        return success

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
            "postal code",
            "zip",
            "state",
            "country",
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
        """Fill screening questions. Returns AttemptResult if paused, None if all answered."""
        question_selectors = [
            "[data-automation-id='questionSection'] label",
            ".css-1wc5dpp label",
            "fieldset legend",
        ]
        for q_sel in question_selectors:
            try:
                questions = page.query_selector_all(q_sel)
                for q_elem in questions:
                    q_text = q_elem.text_content().strip()
                    if not q_text:
                        continue
                    q_normalized = q_text.rstrip("* \t").lower()
                    if q_normalized in self._PERSONAL_INFO_LABELS:
                        continue
                    answer, is_pause = answer_screening_question(answers, q_text, market)
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

    def _handle_sms_consent(self, page: Page) -> None:
        """Check for and accept SMS consent checkbox if present."""
        sms_cfg = self.config.get("selectors", {}).get("sms_consent", {})
        selectors = [
            sms_cfg.get("primary", ""),
            sms_cfg.get("fallback_1", ""),
            sms_cfg.get("fallback_2", ""),
        ]
        for sel in selectors:
            if not sel:
                continue
            try:
                elem = page.query_selector(sel)
                if elem and not elem.is_checked():
                    elem.click()
                    self._log_step("click", sel, "sms_consent_accepted", "success")
                    return
            except Exception:
                continue

    def _handle_fcra_ack(self, page: Page) -> None:
        """Check for and accept FCRA background check acknowledgement if present."""
        fcra_cfg = self.config.get("selectors", {}).get("fcra_ack", {})
        selectors = [
            fcra_cfg.get("primary", ""),
            fcra_cfg.get("fallback_1", ""),
            fcra_cfg.get("fallback_2", ""),
            fcra_cfg.get("fallback_3", ""),
        ]
        for sel in selectors:
            if not sel:
                continue
            try:
                elem = page.query_selector(sel)
                if elem and not elem.is_checked():
                    elem.click()
                    self._log_step("click", sel, "fcra_ack_accepted", "success")
                    return
            except Exception:
                continue

    def _fill_phone_extension(
        self, page: Page, info: PersonalInfo, fields_filled: dict[str, str]
    ) -> None:
        """Fill phone extension field if present and value is set."""
        ext = getattr(info, "phone_extension", None)
        if not ext:
            return
        if self._try_fill(page, "phone_extension", ext):
            fields_filled["phone_extension"] = ext

    def _fill_skills_tags(self, page: Page, skills: list[str]) -> None:
        """Fill skills tag input by typing each skill and pressing Enter."""
        selectors = self.config.get("selectors", {}).get("skills_input", [])
        for sel in selectors:
            try:
                elem = page.query_selector(sel)
                if elem:
                    for skill in skills[:10]:
                        elem.type(skill)
                        page.wait_for_timeout(500)
                        elem.press("Enter")
                        self._log_step("fill_skill", sel, skill, "success")
                    return
            except Exception:
                continue

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
