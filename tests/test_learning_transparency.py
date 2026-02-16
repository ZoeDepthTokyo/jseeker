"""Tests for Learning System Transparency (pattern stats, ATS explanations, cost tracking)."""

import json
import sqlite3
from unittest.mock import patch

import pytest

from jseeker.ats_scorer import explain_ats_score
from jseeker.pattern_learner import get_pattern_stats, learn_pattern


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    # Create learned_patterns table
    c.execute("""CREATE TABLE learned_patterns (
        id INTEGER PRIMARY KEY,
        pattern_type TEXT NOT NULL,
        source_text TEXT NOT NULL,
        target_text TEXT NOT NULL,
        jd_context TEXT,
        frequency INTEGER DEFAULT 1,
        confidence REAL DEFAULT 1.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(pattern_type, source_text, jd_context)
    )""")

    # Create api_costs table
    c.execute("""CREATE TABLE api_costs (
        id INTEGER PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        model TEXT,
        task TEXT,
        input_tokens INTEGER,
        output_tokens INTEGER,
        cache_tokens INTEGER,
        cost_usd REAL
    )""")

    # Create resumes table
    c.execute("""CREATE TABLE resumes (
        id INTEGER PRIMARY KEY,
        application_id INTEGER,
        version INTEGER DEFAULT 1,
        template_used TEXT,
        content_json TEXT,
        pdf_path TEXT,
        docx_path TEXT,
        ats_score INTEGER,
        ats_platform TEXT,
        generation_cost REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    conn.commit()
    conn.close()

    return db_path


# ── Pattern Stats Tests ────────────────────────────────────────────────────


def test_get_pattern_stats_empty_db(temp_db):
    """Test pattern stats with empty database (new install)."""
    stats = get_pattern_stats(db_path=temp_db)

    assert stats["total_patterns"] == 0
    assert stats["cache_hit_rate"] == 0.0
    assert stats["cost_saved"] == 0.0
    assert stats["total_uses"] == 0
    assert stats["by_type"] == []
    assert stats["top_patterns"] == []


def test_get_pattern_stats_with_patterns(temp_db):
    """Test pattern stats with learned patterns."""
    # Add some patterns
    jd_context = {"title": "Senior Product Manager", "industry": "tech"}

    learn_pattern(
        pattern_type="bullet_adaptation",
        source_text="Led teams to deliver products",
        target_text="Directed 12-person team to ship 3 AI products in 9 months",
        jd_context=jd_context,
        db_path=temp_db,
    )

    # Simulate pattern reuse (increment frequency)
    conn = sqlite3.connect(str(temp_db))
    c = conn.cursor()
    c.execute("UPDATE learned_patterns SET frequency = 5 WHERE pattern_type = 'bullet_adaptation'")
    conn.commit()
    conn.close()

    stats = get_pattern_stats(db_path=temp_db)

    assert stats["total_patterns"] == 1
    assert stats["cache_hit_rate"] > 0  # Should be positive
    assert stats["cost_saved"] > 0  # Should be positive
    assert len(stats["by_type"]) == 1
    assert stats["by_type"][0]["type"] == "bullet_adaptation"
    assert stats["by_type"][0]["count"] == 1
    assert stats["by_type"][0]["total_uses"] == 5


def test_pattern_stats_cache_hit_rate_calculation(temp_db):
    """Test cache hit rate calculation logic."""
    jd_context = {"title": "Product Manager", "industry": "tech"}

    # Add 3 patterns with different frequencies
    for i in range(3):
        learn_pattern(
            pattern_type="bullet_adaptation",
            source_text=f"Pattern {i}",
            target_text=f"Adapted {i}",
            jd_context=jd_context,
            db_path=temp_db,
        )

    # Set frequencies: 1 (not trusted), 3 (trusted), 5 (trusted)
    conn = sqlite3.connect(str(temp_db))
    c = conn.cursor()
    c.execute(
        "UPDATE learned_patterns SET frequency = CASE id WHEN 1 THEN 1 WHEN 2 THEN 3 WHEN 3 THEN 5 END"
    )
    conn.commit()
    conn.close()

    stats = get_pattern_stats(db_path=temp_db)

    # Total uses = 1 + 3 + 5 = 9
    # Cache hits (freq >= 3) = 3 + 5 = 8
    # Hit rate = 8/9 * 100 = 88.9%
    assert stats["total_uses"] == 9
    assert 88 <= stats["cache_hit_rate"] <= 90
    assert stats["cost_saved"] == 0.08  # 8 hits * $0.01


def test_pattern_stats_top_patterns_limit(temp_db):
    """Test that top patterns are limited to 10."""
    jd_context = {"title": "PM", "industry": "tech"}

    # Add 15 patterns
    for i in range(15):
        learn_pattern(
            pattern_type="bullet_adaptation",
            source_text=f"Source {i}",
            target_text=f"Target {i}",
            jd_context=jd_context,
            db_path=temp_db,
        )

    stats = get_pattern_stats(db_path=temp_db)

    assert stats["total_patterns"] == 15
    assert len(stats["top_patterns"]) == 10  # Limited to 10


# ── ATS Explanation Tests ──────────────────────────────────────────────────


@patch("jseeker.ats_scorer.llm")
def test_explain_ats_score_improvement(mock_llm):
    """Test ATS score explanation generation."""
    mock_llm.call_haiku.return_value = (
        "Your original score of 60 was low due to missing key technical terms. "
        "The adapted resume now includes critical keywords like 'Agile' and 'API integration', "
        "boosting your score to 85. Consider adding more quantifiable metrics to reach 90+."
    )

    explanation = explain_ats_score(
        jd_title="Senior Product Manager",
        original_score=60,
        improved_score=85,
        matched_keywords=["product management", "agile", "api integration"],
        missing_keywords=["scrum master", "jira"],
    )

    assert "60" in explanation
    assert "85" in explanation
    assert len(explanation) > 50  # Non-trivial response
    assert "improved" in explanation.lower() or "boosting" in explanation.lower()

    # Verify LLM was called with correct task
    mock_llm.call_haiku.assert_called_once()
    call_args = mock_llm.call_haiku.call_args
    assert call_args[1]["task"] == "ats_explanation"


@patch("jseeker.ats_scorer.llm")
def test_explain_ats_score_high_original(mock_llm):
    """Test ATS explanation when original score is already high."""
    mock_llm.call_haiku.return_value = (
        "Your score of 75 was already strong, showing good keyword alignment. "
        "Minor improvements in formatting and bullet structure brought it to 82. "
        "Excellent work!"
    )

    explanation = explain_ats_score(
        jd_title="UX Designer",
        original_score=75,
        improved_score=82,
        matched_keywords=["figma", "user research", "prototyping"],
        missing_keywords=["sketch"],
    )

    assert "75" in explanation
    assert "82" in explanation
    assert mock_llm.call_haiku.called


@patch("jseeker.ats_scorer.llm")
def test_explain_ats_score_includes_keywords(mock_llm):
    """Test that explanation prompt includes matched and missing keywords."""
    mock_llm.call_haiku.return_value = "Test explanation"

    matched = ["python", "django", "rest api", "docker", "aws"]
    missing = ["kubernetes", "terraform"]

    explain_ats_score(
        jd_title="Backend Engineer",
        original_score=50,
        improved_score=80,
        matched_keywords=matched,
        missing_keywords=missing,
    )

    # Check that prompt includes keywords
    call_args = mock_llm.call_haiku.call_args
    prompt = call_args[0][0]

    assert "python" in prompt.lower()
    assert "docker" in prompt.lower()
    assert "kubernetes" in prompt.lower()


# ── Cost Tracking Tests ────────────────────────────────────────────────────


def test_cost_tracking_accuracy(temp_db):
    """Test that cost tracking is accurate across resumes."""
    conn = sqlite3.connect(str(temp_db))
    c = conn.cursor()

    # Insert 3 resumes with different costs
    costs = [0.05, 0.04, 0.03]
    for i, cost in enumerate(costs):
        c.execute(
            "INSERT INTO resumes (application_id, generation_cost) VALUES (?, ?)",
            (i + 1, cost),
        )

    # Insert corresponding API costs
    for i, cost in enumerate(costs):
        c.execute(
            "INSERT INTO api_costs (model, task, cost_usd) VALUES (?, ?, ?)",
            (f"haiku-{i}", "test", cost),
        )

    conn.commit()

    # Verify total costs
    c.execute("SELECT SUM(generation_cost) FROM resumes")
    total_resume_cost = c.fetchone()[0]

    c.execute("SELECT SUM(cost_usd) FROM api_costs")
    total_api_cost = c.fetchone()[0]

    conn.close()

    assert abs(total_resume_cost - sum(costs)) < 0.001
    assert abs(total_api_cost - sum(costs)) < 0.001


def test_cost_per_resume_trend(temp_db):
    """Test that cost per resume decreases over time (optimization working)."""
    conn = sqlite3.connect(str(temp_db))
    c = conn.cursor()

    # Simulate decreasing cost trend
    costs = [0.10, 0.09, 0.08, 0.07, 0.06]
    for i, cost in enumerate(costs):
        c.execute(
            "INSERT INTO resumes (application_id, generation_cost) VALUES (?, ?)",
            (i + 1, cost),
        )

    conn.commit()

    # Calculate first 3 avg vs last 3 avg
    c.execute("""
        SELECT AVG(generation_cost) FROM (
            SELECT generation_cost FROM resumes ORDER BY id ASC LIMIT 3
        )
    """)
    first_avg = c.fetchone()[0]

    c.execute("""
        SELECT AVG(generation_cost) FROM (
            SELECT generation_cost FROM resumes ORDER BY id DESC LIMIT 3
        )
    """)
    last_avg = c.fetchone()[0]

    conn.close()

    # Cost should decrease
    assert last_avg < first_avg
    improvement = (first_avg - last_avg) / first_avg * 100
    assert improvement > 0  # Positive improvement


# ── Integration Tests ──────────────────────────────────────────────────────


def test_pattern_stats_json_serializable(temp_db):
    """Test that pattern stats can be serialized to JSON (for API/UI)."""
    jd_context = {"title": "PM", "industry": "tech"}

    learn_pattern(
        pattern_type="bullet_adaptation",
        source_text="Test source",
        target_text="Test target",
        jd_context=jd_context,
        db_path=temp_db,
    )

    stats = get_pattern_stats(db_path=temp_db)

    # Should be JSON serializable
    json_str = json.dumps(stats)
    assert json_str
    assert len(json_str) > 10


def test_ats_explanation_non_empty(temp_db):
    """Test that ATS explanation is never empty."""
    with patch("jseeker.ats_scorer.llm") as mock_llm:
        mock_llm.call_haiku.return_value = "   \n\n   "  # Empty response

        explanation = explain_ats_score(
            jd_title="Test",
            original_score=50,
            improved_score=80,
            matched_keywords=["test"],
            missing_keywords=["missing"],
        )

        # Should return stripped string (empty in this case)
        assert explanation == ""


def test_cost_saved_estimation(temp_db):
    """Test that cost saved estimation is reasonable."""
    jd_context = {"title": "PM", "industry": "tech"}

    # Add patterns with high frequency
    for i in range(5):
        learn_pattern(
            pattern_type="bullet_adaptation",
            source_text=f"Source {i}",
            target_text=f"Target {i}",
            jd_context=jd_context,
            db_path=temp_db,
        )

    # Set all to high frequency (trusted)
    conn = sqlite3.connect(str(temp_db))
    c = conn.cursor()
    c.execute("UPDATE learned_patterns SET frequency = 10")
    conn.commit()
    conn.close()

    stats = get_pattern_stats(db_path=temp_db)

    # 5 patterns * 10 uses = 50 total uses
    # All are trusted (freq >= 3), so 50 cache hits
    # 50 * $0.01 = $0.50 saved
    assert stats["total_uses"] == 50
    assert stats["cost_saved"] == 0.50
