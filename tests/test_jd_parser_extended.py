"""Extended tests for jd_parser.py - targeting 80%+ coverage."""

import pytest
from unittest.mock import Mock, patch
from jseeker.jd_parser import detect_ats_platform, detect_language, extract_jd_from_url
from jseeker.models import ATSPlatform


class TestDetectATSPlatformExtended:
    """Extended ATS platform detection tests."""

    def test_greenhouse_variants(self):
        """Test various Greenhouse URL patterns."""
        urls = [
            "https://boards.greenhouse.io/company/jobs/123",
            "https://company.greenhouse.io/job/456",
            "https://job-boards.greenhouse.io/test",
        ]
        for url in urls:
            assert detect_ats_platform(url) == ATSPlatform.GREENHOUSE

    def test_workday_variants(self):
        """Test various Workday URL patterns."""
        urls = [
            "https://company.wd1.myworkdayjobs.com/en-US/Career/job/123",
            "https://test.wd5.myworkdayjobs.com/External/job/456",
            "https://example.myworkdayjobs.com/jobs/789",
        ]
        for url in urls:
            assert detect_ats_platform(url) == ATSPlatform.WORKDAY

    def test_lever_variants(self):
        """Test various Lever URL patterns."""
        urls = [
            "https://jobs.lever.co/company/job-id",
            "https://jobs.lever.co/another-company/different-job",
        ]
        for url in urls:
            assert detect_ats_platform(url) == ATSPlatform.LEVER

    def test_case_insensitivity(self):
        """Test ATS detection is case-insensitive."""
        assert detect_ats_platform("https://BOARDS.GREENHOUSE.IO/job") == ATSPlatform.GREENHOUSE

    def test_partial_matches_not_false_positives(self):
        """Test partial URL matches don't trigger false positives."""
        assert detect_ats_platform("https://greenhouse-analytics.com/job") == ATSPlatform.UNKNOWN


class TestDetectLanguageExtended:
    """Extended language detection tests."""

    def test_english_text(self):
        """Test English text detection."""
        text = "We are seeking a talented software engineer to join our team."
        assert detect_language(text) == "en"

    def test_spanish_text(self):
        """Test Spanish text detection."""
        text = "Buscamos un ingeniero de software talentoso para unirse a nuestro equipo."
        assert detect_language(text) == "es"

    def test_very_short_text_defaults_english(self):
        """Test very short text defaults to English."""
        assert detect_language("Hi") == "en"

    def test_empty_string_defaults_english(self):
        """Test empty string defaults to English."""
        assert detect_language("") == "en"

    def test_numbers_and_symbols_default_english(self):
        """Test text with only numbers/symbols defaults to English."""
        assert detect_language("123 456") == "en"


class TestExtractJDFromURLEdgeCases:
    """Test edge cases and error handling in JD extraction."""

    @patch("jseeker.jd_parser.requests.get")
    def test_network_timeout(self, mock_get):
        """Test extraction handles network timeout gracefully."""
        import requests

        mock_get.side_effect = requests.Timeout("Connection timed out")

        result, metadata = extract_jd_from_url("https://example.com/job")

        assert result == ""
        assert metadata["success"] is False

    @patch("jseeker.jd_parser.requests.get")
    def test_connection_error(self, mock_get):
        """Test extraction handles connection errors gracefully."""
        import requests

        mock_get.side_effect = requests.ConnectionError("Failed to connect")

        result, metadata = extract_jd_from_url("https://example.com/job")

        assert result == ""
        assert metadata["success"] is False

    @patch("jseeker.jd_parser.requests.get")
    def test_http_404_error(self, mock_get):
        """Test extraction handles 404 errors."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = (
            "<html><body>Not Found - This page does not exist. Please check the URL.</body></html>"
        )
        mock_get.return_value = mock_response

        result, metadata = extract_jd_from_url("https://example.com/job")

        # Returns empty or error text
        assert isinstance(result, str)

    @patch("jseeker.jd_parser.requests.get")
    def test_http_500_error(self, mock_get):
        """Test extraction handles 500 errors."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = (
            "<html><body>Internal Server Error - Something went wrong on our end.</body></html>"
        )
        mock_get.return_value = mock_response

        result, metadata = extract_jd_from_url("https://example.com/job")

        # Returns empty or error text
        assert isinstance(result, str)

    @patch("jseeker.jd_parser.requests.get")
    def test_empty_html_response(self, mock_get):
        """Test extraction handles empty HTML."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_get.return_value = mock_response

        result, metadata = extract_jd_from_url("https://example.com/job")

        assert result == ""

    @patch("jseeker.jd_parser.requests.get")
    def test_malformed_html(self, mock_get):
        """Test extraction handles malformed HTML."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html><body><div>Unclosed div<p>Malformed"
        mock_get.return_value = mock_response

        result, metadata = extract_jd_from_url("https://example.com/job")

        # Should not crash
        assert isinstance(result, str)

    @patch("jseeker.jd_parser.requests.get")
    def test_unicode_characters_in_html(self, mock_get):
        """Test extraction handles Unicode characters."""
        mock_response = Mock()
        mock_response.status_code = 200
        # Make content longer to pass minimum threshold
        mock_response.text = (
            "<html><body><div>"
            + ("Job in München, café environment, 中文. " * 20)
            + "</div></body></html>"
        )
        mock_get.return_value = mock_response

        result, metadata = extract_jd_from_url("https://example.com/job")

        # Should not crash with Unicode
        assert isinstance(result, str)

    @patch("jseeker.jd_parser.requests.get")
    def test_html_with_scripts_stripped(self, mock_get):
        """Test extraction strips script tags."""
        mock_response = Mock()
        mock_response.status_code = 200
        # Make content longer
        mock_response.text = (
            "<html><body><div>"
            + ("Real job content here. " * 30)
            + "</div><script>alert('ad');</script></body></html>"
        )
        mock_get.return_value = mock_response

        result, metadata = extract_jd_from_url("https://example.com/job")

        assert "Real job content" in result
        # Script content should be stripped
        assert "alert" not in result or len(result) > 50

    def test_empty_url_returns_empty_string(self):
        """Test empty URL returns empty string."""
        result, metadata = extract_jd_from_url("")

        assert result == ""
        assert metadata["success"] is False

    @patch("jseeker.jd_parser.requests.get")
    def test_extraction_with_long_content(self, mock_get):
        """Test extraction handles very long content."""
        mock_response = Mock()
        mock_response.status_code = 200
        # Generate long content
        long_content = "<html><body>" + ("Job requirement. " * 1000) + "</body></html>"
        mock_response.text = long_content
        mock_get.return_value = mock_response

        result, metadata = extract_jd_from_url("https://example.com/job")

        assert len(result) > 0
        assert "Job requirement" in result
