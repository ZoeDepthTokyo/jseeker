"""Tests for jseeker.answer_bank module."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from autojs.answer_bank import (
    REQUIRED_MARKETS,
    AnswerBank,
    PersonalInfo,
    answer_screening_question,
    get_personal_info,
    get_resume_format,
    load_answer_bank,
)

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def valid_yaml_path(tmp_path: Path) -> Path:
    """Create a valid answer bank YAML in a temp directory."""
    data = {
        "version": 1,
        "personal_info": {},
        "screening_patterns": [
            {"pattern": "years of experience", "answer": "7"},
            {"pattern": "willing to relocate", "answer": "yes"},
            {"pattern": "salary|compensation|pay", "action": "pause"},
            {"pattern": "referr", "answer": "Company website"},
            {
                "pattern": "gender|race|ethnicity|veteran|disability",
                "answer": "Decline to self-identify",
            },
            {"pattern": "authorized to work", "answer": "yes"},
            {"pattern": "sponsorship", "answer": "no"},
            {
                "pattern": "start date|earliest start|when can you start",
                "answer": "immediately",
            },
            {"pattern": "notice period", "answer": "2 weeks"},
            {"pattern": "remote|hybrid|on.?site", "answer": "yes"},
            {"pattern": "education|degree|university", "answer": "Bachelor's degree"},
            {"pattern": "criminal|background check|felony", "answer": "no"},
            {"pattern": "drug test|drug screen", "answer": "yes"},
            {"pattern": "18 years|legal age|at least 18", "answer": "yes"},
            {"pattern": "clearance|security clearance", "answer": "no"},
            {"pattern": "non.?compete|non.?disclosure", "answer": "no"},
            {
                "pattern": "how did you hear|where did you find",
                "answer": "Online job board",
            },
        ],
        "resume_formats": {
            "workday": "docx",
            "greenhouse": "pdf",
            "default": "pdf",
        },
    }
    markets = {
        "us": ("San Francisco", "CA", "94102", "United States", "+1-555-000-0000"),
        "mx": ("Ciudad de Mexico", "CDMX", "06600", "Mexico", "+52-55-0000-0000"),
        "uk": (
            "London",
            "Greater London",
            "W1D 1BS",
            "United Kingdom",
            "+44-20-0000-0000",
        ),
        "ca": ("Toronto", "ON", "M5X 1A9", "Canada", "+1-416-000-0000"),
        "fr": ("Paris", "Ile-de-France", "75001", "France", "+33-1-00-00-00-00"),
        "es": ("Madrid", "Madrid", "28013", "Spain", "+34-91-000-0000"),
        "dk": ("Copenhagen", "Capital Region", "1620", "Denmark", "+45-00-00-00-00"),
    }
    for code, (city, state, zip_code, country, phone) in markets.items():
        data["personal_info"][code] = {
            "first_name": "Test",
            "last_name": "User",
            "email": f"test@{code}.example.com",
            "phone": phone,
            "city": city,
            "state": state,
            "zip": zip_code,
            "country": country,
        }

    path = tmp_path / "answer_bank.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    return path


@pytest.fixture
def bank(valid_yaml_path: Path) -> AnswerBank:
    """Load a valid AnswerBank from fixture YAML."""
    return load_answer_bank(valid_yaml_path)


# ── Loading Tests ─────────────────────────────────────────────────────


def test_load_valid_yaml(valid_yaml_path: Path) -> None:
    """Loading a valid YAML returns an AnswerBank."""
    bank = load_answer_bank(valid_yaml_path)
    assert isinstance(bank, AnswerBank)
    assert bank.version == 1


def test_load_invalid_yaml_raises(tmp_path: Path) -> None:
    """Invalid YAML structure raises a validation error."""
    path = tmp_path / "bad.yaml"
    path.write_text("version: 1\npersonal_info: not_a_dict\n")
    with pytest.raises(Exception):
        load_answer_bank(path)


def test_load_missing_market_raises(tmp_path: Path) -> None:
    """YAML missing a required market raises ValueError."""
    data = {
        "version": 1,
        "personal_info": {
            "us": {
                "first_name": "A",
                "last_name": "B",
                "email": "a@b.com",
                "phone": "+1-555-0000",
            }
        },
        "screening_patterns": [],
        "resume_formats": {"default": "pdf"},
    }
    path = tmp_path / "incomplete.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f)
    with pytest.raises(ValueError, match="Missing markets"):
        load_answer_bank(path)


def test_load_default_answer_bank() -> None:
    """The bundled data/answer_bank.yaml loads successfully."""
    bank = load_answer_bank()
    assert isinstance(bank, AnswerBank)
    assert len(bank.personal_info) >= 7


# ── Personal Info Tests ───────────────────────────────────────────────


def test_personal_info_all_7_markets(bank: AnswerBank) -> None:
    """All 7 required markets are present."""
    for market in REQUIRED_MARKETS:
        info = get_personal_info(bank, market)
        assert isinstance(info, PersonalInfo)


def test_personal_info_missing_market_raises(bank: AnswerBank) -> None:
    """Requesting an unknown market raises KeyError."""
    with pytest.raises(KeyError, match="zz"):
        get_personal_info(bank, "zz")


def test_personal_info_fields_populated(bank: AnswerBank) -> None:
    """Required fields are non-empty for all markets."""
    for market in REQUIRED_MARKETS:
        info = get_personal_info(bank, market)
        assert info.first_name
        assert info.last_name
        assert "@" in info.email
        assert len(info.phone) >= 5


def test_personal_info_case_insensitive(bank: AnswerBank) -> None:
    """Market lookup is case-insensitive."""
    info = get_personal_info(bank, "US")
    assert info.country == "United States"


# ── Screening Question Tests ─────────────────────────────────────────


def test_screening_years_of_experience(bank: AnswerBank) -> None:
    answer, pause = answer_screening_question(bank, "How many years of experience do you have?")
    assert answer == "7"
    assert pause is False


def test_screening_willing_to_relocate(bank: AnswerBank) -> None:
    answer, pause = answer_screening_question(bank, "Are you willing to relocate?")
    assert answer == "yes"
    assert pause is False


def test_screening_referral(bank: AnswerBank) -> None:
    answer, pause = answer_screening_question(bank, "Were you referred by someone?")
    assert answer == "Company website"
    assert pause is False


def test_screening_diversity_eeo(bank: AnswerBank) -> None:
    answer, pause = answer_screening_question(bank, "What is your gender?")
    assert answer == "Decline to self-identify"
    assert pause is False


def test_screening_work_authorization(bank: AnswerBank) -> None:
    answer, pause = answer_screening_question(bank, "Are you authorized to work in this country?")
    assert answer == "yes"
    assert pause is False


def test_screening_sponsorship(bank: AnswerBank) -> None:
    answer, pause = answer_screening_question(bank, "Will you require sponsorship?")
    assert answer == "no"
    assert pause is False


def test_screening_start_date(bank: AnswerBank) -> None:
    answer, pause = answer_screening_question(bank, "What is your earliest start date?")
    assert answer == "immediately"
    assert pause is False


def test_screening_notice_period(bank: AnswerBank) -> None:
    answer, pause = answer_screening_question(bank, "What is your notice period?")
    assert answer == "2 weeks"
    assert pause is False


def test_screening_education(bank: AnswerBank) -> None:
    answer, pause = answer_screening_question(bank, "What is your highest degree?")
    assert answer == "Bachelor's degree"
    assert pause is False


def test_screening_criminal_background(bank: AnswerBank) -> None:
    answer, pause = answer_screening_question(bank, "Do you have a criminal record?")
    assert answer == "no"
    assert pause is False


def test_screening_drug_test(bank: AnswerBank) -> None:
    answer, pause = answer_screening_question(bank, "Are you willing to take a drug test?")
    assert answer == "yes"
    assert pause is False


def test_screening_age_requirement(bank: AnswerBank) -> None:
    answer, pause = answer_screening_question(bank, "Are you at least 18 years old?")
    assert answer == "yes"
    assert pause is False


def test_screening_salary_always_pauses(bank: AnswerBank) -> None:
    """Salary questions should always pause for human review."""
    answer, pause = answer_screening_question(bank, "What is your expected salary?")
    assert pause is True
    assert answer == ""


def test_screening_unknown_always_pauses(bank: AnswerBank) -> None:
    """Unknown questions should pause for human review."""
    answer, pause = answer_screening_question(bank, "What is your favorite color?")
    assert pause is True
    assert answer == ""


def test_screening_case_insensitive(bank: AnswerBank) -> None:
    """Screening pattern matching is case-insensitive."""
    answer, pause = answer_screening_question(bank, "YEARS OF EXPERIENCE?")
    assert answer == "7"
    assert pause is False


# ── Field Validation Tests ────────────────────────────────────────────


def test_field_validation_empty_email_raises() -> None:
    """Empty email raises validation error."""
    with pytest.raises(Exception, match="email"):
        PersonalInfo(first_name="A", last_name="B", email="", phone="+1-555-0000")


def test_field_validation_empty_phone_raises() -> None:
    """Short phone raises validation error."""
    with pytest.raises(Exception, match="phone"):
        PersonalInfo(first_name="A", last_name="B", email="a@b.com", phone="123")


# ── Resume Format Tests ──────────────────────────────────────────────


def test_resume_format_workday_docx(bank: AnswerBank) -> None:
    assert get_resume_format(bank, "workday") == "docx"


def test_resume_format_greenhouse_pdf(bank: AnswerBank) -> None:
    assert get_resume_format(bank, "greenhouse") == "pdf"


def test_resume_format_unknown_defaults_pdf(bank: AnswerBank) -> None:
    assert get_resume_format(bank, "unknown_ats") == "pdf"
