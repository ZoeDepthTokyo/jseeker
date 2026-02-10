"""Tests for adapter module."""

import pytest
from unittest.mock import Mock, patch
from jseeker.adapter import LOCATIONS_BY_MARKET, adapt_bullets_batch
from jseeker.models import ParsedJD, TemplateType


class TestLocationsByMarket:
    """Test location adaptation by market."""

    def test_locations_by_market_us(self):
        """Test US market location."""
        assert LOCATIONS_BY_MARKET["us"] == "San Diego, CA"

    def test_locations_by_market_mx(self):
        """Test Mexico market location."""
        assert LOCATIONS_BY_MARKET["mx"] == "Ciudad de Mexico"

    def test_locations_by_market_ca(self):
        """Test Canada market location."""
        assert LOCATIONS_BY_MARKET["ca"] == "Remote"

    def test_locations_by_market_european(self):
        """Test European markets all contain Remote."""
        european_markets = ["uk", "es", "dk", "fr"]
        for market in european_markets:
            assert "Remote" in LOCATIONS_BY_MARKET[market]

    def test_all_markets_present(self):
        """Test all 7 expected markets are present."""
        expected_markets = ["us", "mx", "ca", "uk", "es", "dk", "fr"]
        for market in expected_markets:
            assert market in LOCATIONS_BY_MARKET

        # Verify we have exactly 7 markets
        assert len(LOCATIONS_BY_MARKET) == 7


class TestAdaptBulletsBatchErrorHandling:
    """Test error handling in adapt_bullets_batch - TDD for silent failure fix."""

    @pytest.fixture
    def mock_parsed_jd(self):
        """Create a minimal ParsedJD for testing."""
        return ParsedJD(
            raw_text="Senior Python Developer needed",
            title="Senior Python Developer",
            company="TestCo",
            ats_keywords=["Python", "Django", "REST"],
            language="en",
        )

    @pytest.fixture
    def experience_blocks(self):
        """Sample experience blocks for testing."""
        return [
            {
                "company": "TechCorp",
                "role": "Senior Engineer",
                "bullets": ["Led team of 5", "Shipped product"],
            },
            {
                "company": "StartupXYZ",
                "role": "Engineer",
                "bullets": ["Built API", "Reduced latency by 40%"],
            },
        ]

    def test_adapt_bullets_malformed_json_raises_error(
        self, mock_parsed_jd, experience_blocks
    ):
        """Test that malformed JSON response raises AdaptationError."""
        from jseeker.models import AdaptationError

        with patch("jseeker.adapter.llm.call_sonnet") as mock_llm:
            # LLM returns invalid JSON (truncated)
            mock_llm.return_value = '[["bullet1", "bullet2"], ["bullet3"'

            with pytest.raises(AdaptationError) as exc_info:
                adapt_bullets_batch(
                    experience_blocks,
                    TemplateType.HYBRID,
                    mock_parsed_jd,
                    use_learned_patterns=False,
                )

            # Verify error message contains context
            error_msg = str(exc_info.value)
            assert "parse" in error_msg.lower() and "json" in error_msg.lower()
            assert "TechCorp" in error_msg or "experience" in error_msg.lower()

    def test_adapt_bullets_wrong_array_length_raises_error(
        self, mock_parsed_jd, experience_blocks
    ):
        """Test that wrong array length raises AdaptationError."""
        from jseeker.models import AdaptationError

        with patch("jseeker.adapter.llm.call_sonnet") as mock_llm:
            # LLM returns wrong number of bullet sets (2 blocks but only 1 response)
            mock_llm.return_value = '[["bullet1", "bullet2"]]'

            with pytest.raises(AdaptationError) as exc_info:
                adapt_bullets_batch(
                    experience_blocks,
                    TemplateType.HYBRID,
                    mock_parsed_jd,
                    use_learned_patterns=False,
                )

            # Verify error details
            error_msg = str(exc_info.value)
            assert "expected 2" in error_msg.lower()
            assert "1" in error_msg

    def test_adapt_bullets_non_array_response_raises_error(
        self, mock_parsed_jd, experience_blocks
    ):
        """Test that non-array JSON raises AdaptationError."""
        from jseeker.models import AdaptationError

        with patch("jseeker.adapter.llm.call_sonnet") as mock_llm:
            # LLM returns object instead of array
            mock_llm.return_value = '{"bullets": ["bullet1"]}'

            with pytest.raises(AdaptationError) as exc_info:
                adapt_bullets_batch(
                    experience_blocks,
                    TemplateType.HYBRID,
                    mock_parsed_jd,
                    use_learned_patterns=False,
                )

            assert "Expected array" in str(exc_info.value)

    def test_adapt_bullets_backticks_stripped_before_parse(
        self, mock_parsed_jd, experience_blocks
    ):
        """Test that markdown code fences are properly stripped."""
        with patch("jseeker.adapter.llm.call_sonnet") as mock_llm:
            # LLM returns JSON wrapped in backticks
            mock_llm.return_value = (
                '```json\n[["bullet1", "bullet2"], ["bullet3", "bullet4"]]\n```'
            )

            result = adapt_bullets_batch(
                experience_blocks,
                TemplateType.HYBRID,
                mock_parsed_jd,
                use_learned_patterns=False,
            )

            # Should parse successfully
            assert len(result) == 2
            assert result[0] == ["bullet1", "bullet2"]
            assert result[1] == ["bullet3", "bullet4"]

    def test_adapt_bullets_empty_response_raises_error(
        self, mock_parsed_jd, experience_blocks
    ):
        """Test that empty LLM response raises AdaptationError."""
        from jseeker.models import AdaptationError

        with patch("jseeker.adapter.llm.call_sonnet") as mock_llm:
            mock_llm.return_value = ""

            with pytest.raises(AdaptationError) as exc_info:
                adapt_bullets_batch(
                    experience_blocks,
                    TemplateType.HYBRID,
                    mock_parsed_jd,
                    use_learned_patterns=False,
                )

            assert "empty" in str(exc_info.value).lower()

    def test_adapt_bullets_success_case(self, mock_parsed_jd, experience_blocks):
        """Test successful adaptation with valid JSON."""
        with patch("jseeker.adapter.llm.call_sonnet") as mock_llm:
            mock_llm.return_value = (
                '[["Adapted bullet 1", "Adapted bullet 2"], '
                '["Adapted bullet 3", "Adapted bullet 4"]]'
            )

            result = adapt_bullets_batch(
                experience_blocks,
                TemplateType.HYBRID,
                mock_parsed_jd,
                use_learned_patterns=False,
            )

            assert len(result) == 2
            assert "Adapted" in result[0][0]
            assert "Adapted" in result[1][0]
