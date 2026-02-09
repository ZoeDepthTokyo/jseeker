"""Tests for JD parser module."""

import pytest
import requests
from jseeker.jd_parser import detect_ats_platform, detect_language, extract_jd_from_url
from jseeker.models import ATSPlatform


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


class TestLanguageDetection:
    """Test language detection from JD text."""

    def test_english_jd_returns_en(self, sample_jd_text):
        """English JD should return 'en'."""
        result = detect_language(sample_jd_text)
        assert result == "en"

    def test_spanish_jd_returns_es(self):
        """Spanish JD should return 'es'."""
        spanish_jd = """
        Buscamos un Director de Producto con experiencia en los sectores de tecnología e innovación.
        El puesto requiere liderazgo de equipos de diseño y desarrollo de productos digitales.

        Requisitos:
        - Experiencia mínima de 10 años en gestión de productos
        - Conocimiento de metodologías ágiles
        - Capacidad para trabajar con equipos multidisciplinarios

        Responsabilidades:
        - Liderar el equipo de diseño
        - Desarrollar estrategias de producto
        - Colaborar con los stakeholders
        """
        result = detect_language(spanish_jd)
        assert result == "es"

    def test_very_short_text_defaults_to_en(self):
        """Very short text should default to 'en'."""
        result = detect_language("Director of Design")
        assert result == "en"

    def test_empty_string_defaults_to_en(self):
        """Empty string should default to 'en'."""
        result = detect_language("")
        assert result == "en"

    def test_mixed_language_mostly_english_returns_en(self):
        """Mixed language text with mostly English words should return 'en'."""
        mixed_text = """
        We are looking for a Director of Product Design to lead our team.
        The position requires experience with design systems and AI/ML.
        You will work with cross-functional teams and stakeholders.
        We also work con algunos clientes en Mexico.
        """
        result = detect_language(mixed_text)
        assert result == "en"


class TestExtractJDFromURL:
    """Test URL-based JD extraction."""

    def test_extract_jd_prefers_description_blocks(self, monkeypatch):
        html = """
        <html><body>
            <header>Site Header</header>
            <main>
                <section id="job-description">
                    Director of Product Design at TestCorp.
                    This role leads design systems, AI UX strategy, and cross-functional delivery.
                    Requirements include 10+ years of product design leadership and stakeholder management.
                </section>
            </main>
        </body></html>
        """

        class FakeResponse:
            text = html
            status_code = 200

            @staticmethod
            def raise_for_status():
                return None

        monkeypatch.setattr("jseeker.jd_parser.requests.get", lambda *args, **kwargs: FakeResponse())
        extracted = extract_jd_from_url("https://example.com/job")
        assert "Director of Product Design" in extracted
        assert "Site Header" not in extracted

    def test_extract_jd_returns_empty_on_request_error(self, monkeypatch):
        def raise_error(*args, **kwargs):
            raise requests.RequestException("network error")

        monkeypatch.setattr("jseeker.jd_parser.requests.get", raise_error)
        extracted = extract_jd_from_url("https://example.com/job")
        assert extracted == ""
