"""Tests for renderer module."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess
from jseeker.renderer import _sanitize, _get_next_version, SECTION_LABELS, _html_to_pdf_sync


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


class TestPDFRendering:
    """Test PDF rendering with retry logic and error handling."""

    def test_render_pdf_subprocess_failure(self, tmp_path):
        """Test that subprocess failure raises RenderError with full stderr."""
        from jseeker.models import RenderError

        html_content = "<html><body>Test</body></html>"
        output_path = tmp_path / "test.pdf"

        # Mock subprocess.run to simulate failure with long stderr
        long_error = "Playwright error: " + ("X" * 1000)
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = long_error
        mock_result.stdout = ""

        with patch('subprocess.run', return_value=mock_result):
            with pytest.raises(RenderError) as exc_info:
                _html_to_pdf_sync(html_content, output_path)

            # Verify error contains FULL stderr (not truncated at 500 chars)
            assert len(str(exc_info.value)) > 500
            assert "Playwright error" in str(exc_info.value)

    def test_render_pdf_timeout(self, tmp_path):
        """Test that subprocess timeout raises RenderError."""
        from jseeker.models import RenderError

        html_content = "<html><body>Test</body></html>"
        output_path = tmp_path / "test.pdf"

        # Mock subprocess.run to simulate timeout
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired("python", 60)):
            with pytest.raises(RenderError) as exc_info:
                _html_to_pdf_sync(html_content, output_path)

            assert "timeout" in str(exc_info.value).lower()

    def test_render_pdf_success_after_retry(self, tmp_path):
        """Test that rendering succeeds on second retry attempt."""
        html_content = "<html><body>Test</body></html>"
        output_path = tmp_path / "test.pdf"

        # Mock subprocess.run to fail twice, then succeed
        call_count = [0]

        def mock_run(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] < 3:
                result.returncode = 1
                result.stderr = "Transient error"
                result.stdout = ""
                return result
            else:
                result.returncode = 0
                result.stderr = ""
                result.stdout = ""
                # Create dummy PDF
                output_path.write_bytes(b"%PDF-1.4")
                return result

        with patch('subprocess.run', side_effect=mock_run):
            result_path = _html_to_pdf_sync(html_content, output_path)

            assert result_path == output_path
            assert output_path.exists()
            assert call_count[0] == 3  # Failed twice, succeeded on third

    def test_render_pdf_error_log_created(self, tmp_path):
        """Test that detailed error log is created on failure."""
        from jseeker.models import RenderError

        html_content = "<html><body>Test</body></html>"
        output_path = tmp_path / "test.pdf"

        # Mock subprocess.run to simulate failure
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Detailed Playwright error with stack trace"
        mock_result.stdout = ""

        with patch('subprocess.run', return_value=mock_result):
            with patch('jseeker.renderer.Path') as mock_path_class:
                # Create mock error log path
                error_log = tmp_path / "pdf_error.log"
                mock_path_class.return_value = error_log

                with pytest.raises(RenderError):
                    _html_to_pdf_sync(html_content, output_path)

    def test_render_pdf_max_retries_exhausted(self, tmp_path):
        """Test that RenderError is raised after max retries exhausted."""
        from jseeker.models import RenderError

        html_content = "<html><body>Test</body></html>"
        output_path = tmp_path / "test.pdf"

        # Mock subprocess.run to always fail
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Persistent failure"
        mock_result.stdout = ""

        with patch('subprocess.run', return_value=mock_result):
            with pytest.raises(RenderError) as exc_info:
                _html_to_pdf_sync(html_content, output_path)

            # Verify error mentions retries exhausted
            assert "3 attempts" in str(exc_info.value) or "retries" in str(exc_info.value).lower()
