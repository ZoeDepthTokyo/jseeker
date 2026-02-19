"""Tests for jseeker/intelligence.py"""

import json
import sqlite3
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def empty_db(tmp_path):
    """Minimal DB with jd_cache and applications tables."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("""CREATE TABLE jd_cache (
        id INTEGER PRIMARY KEY,
        pruned_text_hash TEXT UNIQUE,
        parsed_json TEXT,
        title TEXT,
        company TEXT,
        ats_keywords TEXT,
        hit_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE applications (
        id INTEGER PRIMARY KEY,
        salary_min INTEGER,
        salary_max INTEGER,
        salary_currency TEXT
    )""")
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def populated_db(empty_db):
    """DB with 3 parsed JDs and 2 applications with salary."""
    conn = sqlite3.connect(str(empty_db))
    jds = [
        {
            "ats_keywords": ["Python", "SQL", "Leadership"],
            "culture_signals": ["fast-paced", "collaborative"],
            "market": "us",
            "role_exp": "5+ years",
            "remote_policy": "hybrid",
            "requirements": [
                {
                    "text": "5+ years Python",
                    "keywords": ["Python"],
                    "category": "hard_skill",
                    "priority": "required",
                }
            ],
        },
        {
            "ats_keywords": ["Python", "ML", "Data Science"],
            "culture_signals": ["innovative", "collaborative"],
            "market": "us",
            "role_exp": "3+ years",
            "remote_policy": "remote",
            "requirements": [
                {
                    "text": "ML experience",
                    "keywords": ["ML", "Python"],
                    "category": "hard_skill",
                    "priority": "required",
                }
            ],
        },
        {
            "ats_keywords": ["Leadership", "Strategy"],
            "culture_signals": ["fast-paced"],
            "market": "uk",
            "role_exp": "7+ years",
            "remote_policy": "onsite",
            "requirements": [],
        },
    ]
    for i, jd in enumerate(jds):
        conn.execute(
            "INSERT INTO jd_cache (pruned_text_hash, parsed_json, title, company) "
            "VALUES (?, ?, ?, ?)",
            (f"hash_{i}", json.dumps(jd), f"Role {i}", f"Company {i}"),
        )
    conn.execute(
        "INSERT INTO applications (salary_min, salary_max, salary_currency) VALUES (120000, 160000, 'USD')"
    )
    conn.execute(
        "INSERT INTO applications (salary_min, salary_max, salary_currency) VALUES (140000, 180000, 'USD')"
    )
    conn.commit()
    conn.close()
    return empty_db


def test_aggregate_empty_db(empty_db):
    """aggregate_jd_corpus with 0 JDs returns safe empty structure."""
    from jseeker.intelligence import aggregate_jd_corpus

    result = aggregate_jd_corpus(db_path=empty_db)
    assert result["total_jds"] == 0
    assert result["top_keywords"] == []
    assert result["salary_percentiles"] == {}


def test_aggregate_populated_db(populated_db):
    """aggregate_jd_corpus correctly counts keyword frequencies."""
    from jseeker.intelligence import aggregate_jd_corpus

    result = aggregate_jd_corpus(db_path=populated_db)
    assert result["total_jds"] == 3
    # Python appears in 2 JDs
    kw_dict = dict(result["top_keywords"])
    assert kw_dict.get("python", 0) >= 2
    # Salary: 2 data points in USD currency
    us_perc = result["salary_by_market"].get("USD", {})
    assert us_perc.get("count") == 2
    assert us_perc.get("p50") is not None


def test_aggregate_salary_percentiles(populated_db):
    """Salary percentiles calculated correctly from application data."""
    from jseeker.intelligence import aggregate_jd_corpus

    result = aggregate_jd_corpus(db_path=populated_db)
    perc = result["salary_percentiles"]
    assert perc["count"] == 2
    # midpoints: (120k+160k)/2=140k and (140k+180k)/2=160k → sorted=[140k,160k]
    # p50 = s[n//2] = s[1] = 160000
    assert perc["p50"] == 160000


def test_build_salary_insight_no_data():
    """_build_salary_insight with empty aggregate returns graceful message."""
    from jseeker.intelligence import _build_salary_insight

    mock_jd = MagicMock()
    mock_jd.market = "us"
    mock_jd.salary_min = None
    mock_jd.salary_max = None
    result = _build_salary_insight(mock_jd, {"salary_by_market": {}, "salary_percentiles": {}})
    assert result["available"] is False
    assert "message" in result


def test_build_salary_insight_with_data():
    """_build_salary_insight returns recommendation when data is available."""
    from jseeker.intelligence import _build_salary_insight

    mock_jd = MagicMock()
    mock_jd.market = "us"
    mock_jd.salary_max = None
    aggregate = {
        "salary_by_market": {"us": {"p50": 150000, "p75": 180000, "count": 5}},
        "salary_percentiles": {"p75": 170000, "count": 10},
    }
    result = _build_salary_insight(mock_jd, aggregate)
    assert result["available"] is True
    assert result["target_ask"] == 180000
    assert "recommendation" in result


def test_export_profile_docx(tmp_path):
    """export_profile_docx creates a valid DOCX file."""
    from jseeker.intelligence import export_profile_docx
    from jseeker.models import IntelligenceReport

    report = IntelligenceReport(
        jd_hash="test",
        ideal_profile="The ideal candidate has extensive Python experience.",
        strengths=["Strong Python background", "Leadership experience"],
        gaps=["Limited ML experience", "No cloud certification"],
        salary_angle="Ask for $160,000 based on market data.",
        keyword_coverage=0.75,
    )
    out = tmp_path / "test_profile.docx"
    result = export_profile_docx(report, out)
    assert result.exists()
    assert result.stat().st_size > 1000  # Non-empty DOCX


def test_aggregate_remote_policy_distribution(populated_db):
    """Remote policy breakdown is correctly counted across JDs."""
    from jseeker.intelligence import aggregate_jd_corpus

    result = aggregate_jd_corpus(db_path=populated_db)
    breakdown = result["remote_policy_breakdown"]
    assert "hybrid" in breakdown
    assert "remote" in breakdown
    assert "onsite" in breakdown


def test_aggregate_markets(populated_db):
    """Markets list contains all markets from JD corpus."""
    from jseeker.intelligence import aggregate_jd_corpus

    result = aggregate_jd_corpus(db_path=populated_db)
    assert "us" in result["markets"]
    assert "uk" in result["markets"]


def test_aggregate_culture_signals(populated_db):
    """Culture signals are counted correctly across all JDs."""
    from jseeker.intelligence import aggregate_jd_corpus

    result = aggregate_jd_corpus(db_path=populated_db)
    culture_dict = dict(result["culture_signals"])
    # "fast-paced" appears in 2 JDs, "collaborative" in 2 JDs
    assert culture_dict.get("fast-paced", 0) >= 2
    assert culture_dict.get("collaborative", 0) >= 2


def test_aggregate_handles_malformed_json(tmp_path):
    """aggregate_jd_corpus skips rows with malformed JSON without crashing."""
    db = tmp_path / "malformed.db"
    conn = sqlite3.connect(str(db))
    conn.execute("""CREATE TABLE jd_cache (
        id INTEGER PRIMARY KEY,
        parsed_json TEXT
    )""")
    conn.execute("""CREATE TABLE applications (
        id INTEGER PRIMARY KEY,
        salary_min INTEGER,
        salary_max INTEGER,
        salary_currency TEXT
    )""")
    conn.execute("INSERT INTO jd_cache (parsed_json) VALUES (?)", ("not valid json",))
    conn.execute(
        "INSERT INTO jd_cache (parsed_json) VALUES (?)",
        (json.dumps({"ats_keywords": ["Python"]}),),
    )
    conn.commit()
    conn.close()

    from jseeker.intelligence import aggregate_jd_corpus

    result = aggregate_jd_corpus(db_path=db)
    assert result["total_jds"] == 2  # Both rows counted (one skipped in parsing)
    kw_dict = dict(result["top_keywords"])
    assert kw_dict.get("python", 0) == 1
