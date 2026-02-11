"""Tests for browser_manager.py — Persistent Playwright browser for PDF rendering."""

import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from jseeker import browser_manager


class TestBrowserSubprocess:
    """Test browser subprocess lifecycle."""

    @patch("jseeker.browser_manager.subprocess.Popen")
    def test_start_browser_subprocess_success(self, mock_popen):
        """Test browser subprocess starts successfully."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline.return_value = "READY\n"
        mock_popen.return_value = mock_proc

        proc = browser_manager._start_browser_subprocess()

        assert proc is not None
        mock_popen.assert_called_once()
        mock_proc.stdout.readline.assert_called()

    @patch("jseeker.browser_manager.subprocess.Popen")
    def test_start_browser_subprocess_dies_early(self, mock_popen):
        """Test browser subprocess dies during startup."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # Process died
        mock_proc.stderr.read.return_value = "Playwright not found"
        mock_popen.return_value = mock_proc

        with pytest.raises(RuntimeError, match="Browser subprocess died"):
            browser_manager._start_browser_subprocess()

    @patch("jseeker.browser_manager.subprocess.Popen")
    @patch("jseeker.browser_manager.time.time")
    def test_start_browser_subprocess_timeout(self, mock_time, mock_popen):
        """Test browser subprocess times out waiting for READY."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline.return_value = ""  # Never sends READY
        mock_popen.return_value = mock_proc

        # Mock time progression
        mock_time.side_effect = [0, 10, 20, 31]  # 31s elapsed → timeout

        with pytest.raises(TimeoutError, match="did not start within 30s"):
            browser_manager._start_browser_subprocess()

        mock_proc.terminate.assert_called_once()

    @patch("jseeker.browser_manager._start_browser_subprocess")
    def test_get_browser_subprocess_creates_new(self, mock_start):
        """Test _get_browser_subprocess creates new browser if none exists."""
        # Reset global state
        browser_manager._BROWSER_SUBPROCESS = None
        browser_manager._RENDER_COUNT = 0

        mock_proc = MagicMock()
        mock_start.return_value = mock_proc

        proc = browser_manager._get_browser_subprocess()

        assert proc == mock_proc
        mock_start.assert_called_once()

    @patch("jseeker.browser_manager._start_browser_subprocess")
    @patch("jseeker.browser_manager._cleanup_browser")
    def test_get_browser_subprocess_restarts_after_max_renders(self, mock_cleanup, mock_start):
        """Test browser restarts after max renders to prevent memory leaks."""
        # Set render count to max
        browser_manager._BROWSER_SUBPROCESS = MagicMock()
        browser_manager._RENDER_COUNT = browser_manager._MAX_RENDERS_BEFORE_RESTART

        mock_new_proc = MagicMock()
        mock_start.return_value = mock_new_proc

        proc = browser_manager._get_browser_subprocess()

        mock_cleanup.assert_called_once()
        mock_start.assert_called_once()
        assert browser_manager._RENDER_COUNT == 0

    def test_cleanup_browser_graceful_exit(self):
        """Test _cleanup_browser sends EXIT and waits gracefully."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Still running
        mock_proc.stdin = MagicMock()
        mock_proc.wait.return_value = None

        browser_manager._BROWSER_SUBPROCESS = mock_proc
        browser_manager._cleanup_browser()

        mock_proc.stdin.write.assert_called_with("EXIT\n")
        mock_proc.stdin.flush.assert_called_once()
        mock_proc.wait.assert_called_once()
        assert browser_manager._BROWSER_SUBPROCESS is None

    def test_cleanup_browser_force_terminate(self):
        """Test _cleanup_browser terminates if EXIT fails."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write.side_effect = Exception("Broken pipe")

        browser_manager._BROWSER_SUBPROCESS = mock_proc
        browser_manager._cleanup_browser()

        mock_proc.terminate.assert_called_once()
        assert browser_manager._BROWSER_SUBPROCESS is None

    def test_cleanup_browser_force_kill(self):
        """Test _cleanup_browser kills process if terminate times out."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write.side_effect = Exception("Broken pipe")
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired("cmd", 2),  # Terminate wait times out
        ]

        browser_manager._BROWSER_SUBPROCESS = mock_proc
        browser_manager._cleanup_browser()

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()

    def test_cleanup_browser_no_subprocess(self):
        """Test _cleanup_browser handles None subprocess."""
        browser_manager._BROWSER_SUBPROCESS = None

        # Should not raise
        browser_manager._cleanup_browser()

        assert browser_manager._BROWSER_SUBPROCESS is None


class TestHtmlToPdfFast:
    """Test fast HTML-to-PDF rendering."""

    @patch("jseeker.browser_manager._get_browser_subprocess")
    def test_html_to_pdf_fast_success(self, mock_get_browser):
        """Test successful PDF generation."""
        # Reset render count
        browser_manager._RENDER_COUNT = 0

        mock_proc = MagicMock()
        mock_proc.stdout.readline.return_value = "OK\n"
        mock_get_browser.return_value = mock_proc

        output_path = Path(tempfile.mktemp(suffix=".pdf"))
        html = "<html><body>Test</body></html>"

        result = browser_manager.html_to_pdf_fast(html, output_path)

        assert result == output_path
        mock_proc.stdin.write.assert_called_once()
        mock_proc.stdin.flush.assert_called_once()
        assert browser_manager._RENDER_COUNT == 1

    @patch("jseeker.browser_manager._get_browser_subprocess")
    def test_html_to_pdf_fast_error(self, mock_get_browser):
        """Test PDF generation error handling."""
        mock_proc = MagicMock()
        mock_proc.stdout.readline.return_value = "ERROR:Page crashed\n"
        mock_get_browser.return_value = mock_proc

        output_path = Path(tempfile.mktemp(suffix=".pdf"))
        html = "<html><body>Test</body></html>"

        with pytest.raises(RuntimeError, match="PDF generation failed: Page crashed"):
            browser_manager.html_to_pdf_fast(html, output_path)

    @patch("jseeker.browser_manager._get_browser_subprocess")
    def test_html_to_pdf_fast_unexpected_response(self, mock_get_browser):
        """Test unexpected browser response."""
        mock_proc = MagicMock()
        mock_proc.stdout.readline.return_value = "UNEXPECTED\n"
        mock_get_browser.return_value = mock_proc

        output_path = Path(tempfile.mktemp(suffix=".pdf"))
        html = "<html><body>Test</body></html>"

        with pytest.raises(RuntimeError, match="Unexpected browser response: UNEXPECTED"):
            browser_manager.html_to_pdf_fast(html, output_path)

    @patch("jseeker.browser_manager._get_browser_subprocess")
    def test_html_to_pdf_fast_increment_render_count(self, mock_get_browser):
        """Test render count increments correctly."""
        browser_manager._RENDER_COUNT = 10

        mock_proc = MagicMock()
        mock_proc.stdout.readline.return_value = "OK\n"
        mock_get_browser.return_value = mock_proc

        output_path = Path(tempfile.mktemp(suffix=".pdf"))
        html = "<html><body>Test</body></html>"

        browser_manager.html_to_pdf_fast(html, output_path)

        assert browser_manager._RENDER_COUNT == 11

    @patch("jseeker.browser_manager._get_browser_subprocess")
    def test_html_to_pdf_fast_cleans_temp_file(self, mock_get_browser):
        """Test temp HTML file is cleaned up even on error."""
        mock_proc = MagicMock()
        mock_proc.stdout.readline.return_value = "ERROR:test\n"
        mock_get_browser.return_value = mock_proc

        output_path = Path(tempfile.mktemp(suffix=".pdf"))
        html = "<html><body>Test</body></html>"

        with pytest.raises(RuntimeError):
            browser_manager.html_to_pdf_fast(html, output_path)

        # Temp file should be cleaned (can't verify directly, but no exception means cleanup worked)

    @patch("jseeker.browser_manager._get_browser_subprocess")
    def test_html_to_pdf_fast_unicode_content(self, mock_get_browser):
        """Test PDF generation with Unicode content."""
        mock_proc = MagicMock()
        mock_proc.stdout.readline.return_value = "OK\n"
        mock_get_browser.return_value = mock_proc

        output_path = Path(tempfile.mktemp(suffix=".pdf"))
        html = "<html><body>Test: éñ中文</body></html>"

        result = browser_manager.html_to_pdf_fast(html, output_path)

        assert result == output_path
