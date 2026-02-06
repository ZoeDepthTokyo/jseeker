"""Tests for JD parser module."""

import pytest
from proteus.jd_parser import detect_ats_platform
from proteus.models import ATSPlatform


class TestATSDetection:
    """Test ATS platform detection from URLs."""

    def test_greenhouse_detection(self):
        assert detect_ats_platform("https://boards.greenhouse.io/company/jobs/123") == ATSPlatform.GREENHOUSE

    def test_workday_detection(self):
        assert detect_ats_platform("https://company.wd5.myworkdayjobs.com/jobs") == ATSPlatform.WORKDAY

    def test_lever_detection(self):
        assert detect_ats_platform("https://jobs.lever.co/company/123") == ATSPlatform.LEVER

    def test_ashby_detection(self):
        assert detect_ats_platform("https://jobs.ashbyhq.com/company/123") == ATSPlatform.ASHBY

    def test_taleo_detection(self):
        assert detect_ats_platform("https://company.taleo.net/careersection") == ATSPlatform.TALEO

    def test_unknown_url(self):
        assert detect_ats_platform("https://example.com/jobs") == ATSPlatform.UNKNOWN

    def test_empty_url(self):
        assert detect_ats_platform("") == ATSPlatform.UNKNOWN

    def test_icims_detection(self):
        assert detect_ats_platform("https://careers-company.icims.com/jobs") == ATSPlatform.ICIMS
