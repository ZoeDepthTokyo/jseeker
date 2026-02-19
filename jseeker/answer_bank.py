"""Answer Bank: structured personal info, screening patterns, and resume format preferences.

Loads a YAML-based answer bank keyed by market (us, mx, uk, ca, fr, es, dk)
and provides pattern-matching for common ATS screening questions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator

# ── Models ────────────────────────────────────────────────────────────


class PersonalInfo(BaseModel):
    """Contact and authorization info for a specific market."""

    first_name: str
    last_name: str
    email: str
    phone: str
    address: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""
    country: str = ""
    work_authorization: str = "authorized"
    requires_sponsorship: bool = False
    linkedin_url: str = ""
    start_date: str = "immediately"
    phone_extension: Optional[str] = None
    resume_skills: list[str] = Field(default_factory=list)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Ensure email contains @ symbol."""
        if not v or "@" not in v:
            raise ValueError("Invalid email format")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Ensure phone has minimum length."""
        if not v or len(v) < 5:
            raise ValueError("Invalid phone format")
        return v


class ScreeningPattern(BaseModel):
    """A regex pattern matched against screening questions."""

    pattern: str
    answer: Optional[str] = None
    action: Optional[str] = None  # "pause" to flag for human review


class AnswerBank(BaseModel):
    """Top-level answer bank containing all markets and screening patterns."""

    version: int = 1
    personal_info: dict[str, PersonalInfo]
    screening_patterns: list[ScreeningPattern]
    resume_formats: dict[str, str] = Field(default_factory=lambda: {"default": "pdf"})


# ── Constants ─────────────────────────────────────────────────────────

REQUIRED_MARKETS = {"us", "mx", "uk", "ca", "fr", "es", "dk"}

DEFAULT_ANSWER_BANK_PATH = Path(__file__).parent.parent / "data" / "answer_bank.yaml"


# ── Public API ────────────────────────────────────────────────────────


def load_answer_bank(path: Optional[Path] = None) -> AnswerBank:
    """Load and validate the answer bank from a YAML file.

    Args:
        path: Path to the YAML file. Defaults to data/answer_bank.yaml.

    Returns:
        Validated AnswerBank instance.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        ValueError: If required markets are missing.
    """
    if path is None:
        path = DEFAULT_ANSWER_BANK_PATH
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    bank = AnswerBank(**data)
    missing = REQUIRED_MARKETS - set(bank.personal_info.keys())
    if missing:
        raise ValueError(f"Missing markets in answer bank: {missing}")
    return bank


def get_personal_info(bank: AnswerBank, market: str) -> PersonalInfo:
    """Retrieve personal info for a specific market.

    Args:
        bank: Loaded AnswerBank instance.
        market: Market code (e.g., "us", "mx").

    Returns:
        PersonalInfo for the requested market.

    Raises:
        KeyError: If market is not found.
    """
    market = market.lower().strip()
    if market not in bank.personal_info:
        raise KeyError(
            f"Market '{market}' not found in answer bank. "
            f"Available: {list(bank.personal_info.keys())}"
        )
    return bank.personal_info[market]


def answer_screening_question(
    bank: AnswerBank, question: str, market: str = "us"
) -> tuple[str, bool]:
    """Match a screening question against known patterns.

    Args:
        bank: Loaded AnswerBank instance.
        question: The screening question text.
        market: Market code (unused currently, reserved for future locale-aware answers).

    Returns:
        Tuple of (answer_text, should_pause). If should_pause is True,
        the question needs human review.
    """
    result = _match_pattern(question, bank.screening_patterns)
    if result is None:
        return ("", True)  # Unknown question -> pause for human review
    answer, is_pause = result
    return (answer, is_pause)


def get_resume_format(bank: AnswerBank, ats_platform: str) -> str:
    """Get the preferred resume format for an ATS platform.

    Args:
        bank: Loaded AnswerBank instance.
        ats_platform: ATS platform name (e.g., "workday", "greenhouse").

    Returns:
        Format string ("pdf" or "docx").
    """
    return bank.resume_formats.get(ats_platform.lower(), bank.resume_formats.get("default", "pdf"))


# ── Internal ──────────────────────────────────────────────────────────


def _match_pattern(question: str, patterns: list[ScreeningPattern]) -> Optional[tuple[str, bool]]:
    """Match question text against screening patterns.

    Args:
        question: The question to match.
        patterns: List of screening patterns to check.

    Returns:
        Tuple of (answer, is_pause) or None if no pattern matches.
    """
    question_lower = question.lower().strip()
    for p in patterns:
        if re.search(p.pattern, question_lower, re.IGNORECASE):
            if p.action == "pause":
                return ("", True)
            return (p.answer or "", False)
    return None
