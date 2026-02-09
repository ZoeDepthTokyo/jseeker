"""Tests for adapter module."""

import pytest
from jseeker.adapter import LOCATIONS_BY_MARKET


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
