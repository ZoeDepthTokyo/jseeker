"""Tests for renderer module."""

import pytest
from pathlib import Path
from jseeker.renderer import _sanitize, _get_next_version, SECTION_LABELS


class TestSanitize:
    """Test filename sanitization."""

    def test_sanitize_basic(self):
        """Test basic string sanitization."""
        result = _sanitize("Hello World")
        assert result == "Hello_World"

    def test_sanitize_special_chars(self):
        """Test sanitization removes special characters."""
        result = _sanitize("Director (VP)")
        assert result == "Director_VP"

    def test_sanitize_max_length(self):
        """Test sanitization truncates to max_len."""
        long_string = "This is a very long string that should be truncated to the maximum length"
        result = _sanitize(long_string, max_len=20)
        assert len(result) <= 20


class TestGetNextVersion:
    """Test version number generation."""

    def test_get_next_version_empty_folder(self, tmp_path):
        """Test returns 1 for empty folder."""
        folder = tmp_path / "empty"
        result = _get_next_version(folder, "TestResume")
        assert result == 1

    def test_get_next_version_nonexistent_folder(self, tmp_path):
        """Test returns 1 for non-existent folder."""
        folder = tmp_path / "nonexistent"
        result = _get_next_version(folder, "TestResume")
        assert result == 1

    def test_get_next_version_with_existing(self, tmp_path):
        """Test returns correct next version with existing files."""
        folder = tmp_path / "resumes"
        folder.mkdir()

        # Create dummy v1 and v2 files
        (folder / "TestResume_v1.pdf").write_text("fake pdf v1")
        (folder / "TestResume_v2.pdf").write_text("fake pdf v2")

        result = _get_next_version(folder, "TestResume")
        assert result == 3


class TestSectionLabels:
    """Test bilingual section labels."""

    def test_section_labels_en(self):
        """Test all section keys exist in English."""
        expected_keys = [
            "contact", "online", "skills", "education",
            "certifications", "awards", "languages",
            "summary", "experience", "early_career",
        ]
        for key in expected_keys:
            assert key in SECTION_LABELS["en"]

    def test_section_labels_es(self):
        """Test all section keys exist in Spanish."""
        expected_keys = [
            "contact", "online", "skills", "education",
            "certifications", "awards", "languages",
            "summary", "experience", "early_career",
        ]
        for key in expected_keys:
            assert key in SECTION_LABELS["es"]

    def test_section_labels_es_values(self):
        """Test specific Spanish translations."""
        assert SECTION_LABELS["es"]["summary"] == "RESUMEN PROFESIONAL"
        assert SECTION_LABELS["es"]["experience"] == "EXPERIENCIA PROFESIONAL"
        assert SECTION_LABELS["es"]["contact"] == "CONTACTO"
        assert SECTION_LABELS["es"]["skills"] == "HABILIDADES"
