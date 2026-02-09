"""Tests for base resume source reference storage."""

from pathlib import Path

from jseeker.resume_sources import load_resume_sources, save_resume_sources


def test_resume_sources_defaults_when_file_missing(tmp_path):
    missing_path = tmp_path / "missing_sources.json"
    data = load_resume_sources(path=missing_path)
    assert data["base_a"] == ""
    assert data["base_b"] == ""
    assert data["base_c"] == ""
    assert data["linkedin_pdf"] == ""


def test_resume_sources_round_trip(tmp_path):
    target = tmp_path / "resume_sources.json"
    saved = save_resume_sources(
        {
            "base_a": "C:/resumes/base_a.pdf",
            "base_b": "C:/resumes/base_b.pdf",
            "base_c": "C:/resumes/base_c.pdf",
            "linkedin_pdf": "C:/resumes/linkedin.pdf",
        },
        path=target,
    )
    loaded = load_resume_sources(path=target)

    assert target.exists()
    assert saved == loaded

