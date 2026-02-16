"""Tests for JD parser module."""

import pytest
import requests
from jseeker.jd_parser import (
    detect_ats_platform,
    detect_language,
    detect_language_from_location,
    detect_market_from_location,
    extract_jd_from_url,
    _extract_salary,
    _extract_company_from_url,
    _extract_company_fallback,
)
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
        extracted, metadata = extract_jd_from_url("https://example.com/job")
        assert "Director of Product Design" in extracted
        assert "Site Header" not in extracted
        assert metadata["success"] is True

    def test_extract_jd_returns_empty_on_request_error(self, monkeypatch):
        def raise_error(*args, **kwargs):
            raise requests.RequestException("network error")

        monkeypatch.setattr("jseeker.jd_parser.requests.get", raise_error)
        extracted, metadata = extract_jd_from_url("https://example.com/job")
        assert extracted == ""
        assert metadata["success"] is False


class TestSalaryExtraction:
    """Test salary extraction from JD text."""

    def test_extract_k_format_with_currency(self):
        """Extract salary in k format like $100k-150k."""
        min_sal, max_sal, currency = _extract_salary("Salary: $100k-150k USD")
        assert min_sal == 100000
        assert max_sal == 150000
        assert currency == "USD"

    def test_extract_k_format_uppercase(self):
        """Extract salary with uppercase K."""
        min_sal, max_sal, currency = _extract_salary("Compensation: $100K-$150K")
        assert min_sal == 100000
        assert max_sal == 150000
        assert currency == "USD"

    def test_extract_euro_format(self):
        """Extract salary with Euro symbol."""
        min_sal, max_sal, currency = _extract_salary("Pay: €80k-€100k")
        assert min_sal == 80000
        assert max_sal == 100000
        assert currency == "EUR"

    def test_extract_comma_separated(self):
        """Extract salary with comma separators."""
        min_sal, max_sal, currency = _extract_salary("Salary range: $120,000 - $150,000")
        assert min_sal == 120000
        assert max_sal == 150000
        assert currency == "USD"

    def test_extract_full_numbers_with_currency(self):
        """Extract salary with full numbers and currency code."""
        min_sal, max_sal, currency = _extract_salary("Compensation: 100000-150000 USD")
        assert min_sal == 100000
        assert max_sal == 150000
        assert currency == "USD"

    def test_extract_gbp_format(self):
        """Extract salary with GBP symbol."""
        min_sal, max_sal, currency = _extract_salary("Pay range: £60,000-£80,000")
        assert min_sal == 60000
        assert max_sal == 80000
        assert currency == "GBP"

    def test_extract_k_no_currency(self):
        """Extract salary in k format without currency."""
        min_sal, max_sal, currency = _extract_salary("Salary: 100k-150k")
        assert min_sal == 100000
        assert max_sal == 150000
        assert currency == "USD"  # defaults to USD

    def test_extract_k_with_eur_code(self):
        """Extract salary with k and EUR code."""
        min_sal, max_sal, currency = _extract_salary("Compensation 80k-100k EUR")
        assert min_sal == 80000
        assert max_sal == 100000
        assert currency == "EUR"

    def test_no_salary_returns_none(self):
        """When no salary is found, return None values."""
        min_sal, max_sal, currency = _extract_salary("No salary information here")
        assert min_sal is None
        assert max_sal is None
        assert currency == "USD"

    def test_empty_string_returns_none(self):
        """Empty string returns None values."""
        min_sal, max_sal, currency = _extract_salary("")
        assert min_sal is None
        assert max_sal is None
        assert currency == "USD"


class TestCompanyExtraction:
    """Test company name extraction from URLs and JD text."""

    def test_extract_company_from_santander_careers_url(self):
        """Santander careers URL should extract 'Santander'."""
        result = _extract_company_from_url("https://careers.santander.com/job/123/design-strategist")
        assert result is not None
        assert result.lower() == "santander"

    def test_extract_company_from_lever_url(self):
        """Lever URL should extract company name."""
        result = _extract_company_from_url("https://jobs.lever.co/acme-corp/123")
        assert result == "Acme Corp"

    def test_extract_company_from_greenhouse_url(self):
        """Greenhouse URL should extract company name."""
        result = _extract_company_from_url("https://boards.greenhouse.io/techcorp/jobs/123")
        assert result == "Techcorp"

    def test_extract_company_from_workday_url(self):
        """Workday URL should extract company name."""
        result = _extract_company_from_url("https://acme.wd5.myworkdayjobs.com/en-US/jobs")
        assert result == "Acme"

    def test_extract_company_fallback_at_pattern(self):
        """'At Santander, we...' pattern should extract Santander."""
        text = """
        Design Strategist - Customer Experience (CX)
        Country: Mexico
        About the job
        At Santander, we're driving innovation in financial services.
        """
        result = _extract_company_fallback(text)
        assert result is not None
        assert result.lower() == "santander"

    def test_extract_company_fallback_about_pattern(self):
        """'About Company' pattern should extract company name."""
        text = "About TechCorp\nWe are a leading technology company."
        result = _extract_company_fallback(text)
        assert result == "TechCorp"

    def test_extract_company_fallback_company_label(self):
        """'Company: Name' pattern should extract company name."""
        text = "Company: Acme Corp\nLocation: NYC"
        result = _extract_company_fallback(text)
        assert result == "Acme Corp"

    def test_extract_company_from_url_empty(self):
        """Empty URL should return None."""
        assert _extract_company_from_url("") is None
        assert _extract_company_from_url(None) is None

    def test_extract_company_fallback_empty(self):
        """Empty text should return None."""
        assert _extract_company_fallback("") is None
        assert _extract_company_fallback(None) is None


class TestMarketDetection:
    """Test market detection from location strings."""

    def test_mexico_country_returns_mx(self):
        """'Country: Mexico' pattern should detect mx market."""
        assert detect_market_from_location("Mexico") == "mx"

    def test_mexico_city_returns_mx(self):
        """Mexico City location should detect mx market."""
        assert detect_market_from_location("Mexico City") == "mx"

    def test_ciudad_de_mexico_returns_mx(self):
        """Ciudad de Mexico should detect mx market."""
        assert detect_market_from_location("Ciudad de Mexico") == "mx"

    def test_cdmx_returns_mx(self):
        """CDMX abbreviation should detect mx market."""
        assert detect_market_from_location("CDMX") == "mx"

    def test_guadalajara_returns_mx(self):
        """Guadalajara should detect mx market."""
        assert detect_market_from_location("Guadalajara, Jalisco") == "mx"

    def test_san_francisco_returns_us(self):
        """San Francisco should detect us market."""
        assert detect_market_from_location("San Francisco, CA") == "us"

    def test_london_returns_uk(self):
        """London should detect uk market."""
        assert detect_market_from_location("London") == "uk"

    def test_toronto_returns_ca(self):
        """Toronto should detect ca market."""
        assert detect_market_from_location("Toronto, ON") == "ca"

    def test_madrid_returns_es(self):
        """Madrid should detect es market."""
        assert detect_market_from_location("Madrid") == "es"

    def test_paris_returns_fr(self):
        """Paris should detect fr market."""
        assert detect_market_from_location("Paris") == "fr"

    def test_copenhagen_returns_dk(self):
        """Copenhagen should detect dk market."""
        assert detect_market_from_location("Copenhagen") == "dk"

    def test_remote_returns_us(self):
        """Remote location should default to us market."""
        assert detect_market_from_location("Remote") == "us"

    def test_empty_returns_us(self):
        """Empty location should default to us market."""
        assert detect_market_from_location("") == "us"

    def test_monterrey_returns_mx(self):
        """Monterrey should detect mx market."""
        assert detect_market_from_location("Monterrey, Mexico") == "mx"


class TestLanguageFromLocation:
    """Test language detection from location strings."""

    def test_mexico_returns_es(self):
        """Mexico location should return 'es'."""
        assert detect_language_from_location("Mexico City") == "es"

    def test_mexico_country_returns_es(self):
        """Country Mexico should return 'es'."""
        assert detect_language_from_location("Mexico") == "es"

    def test_cdmx_returns_es(self):
        """CDMX should return 'es'."""
        assert detect_language_from_location("CDMX") == "es"

    def test_madrid_returns_es(self):
        """Madrid should return 'es'."""
        assert detect_language_from_location("Madrid") == "es"

    def test_paris_returns_fr(self):
        """Paris should return 'fr'."""
        assert detect_language_from_location("Paris") == "fr"

    def test_london_returns_en(self):
        """London should return 'en'."""
        assert detect_language_from_location("London") == "en"

    def test_san_francisco_returns_en(self):
        """San Francisco should return 'en'."""
        assert detect_language_from_location("San Francisco, CA") == "en"

    def test_toronto_returns_en(self):
        """Toronto (English Canada) should return 'en'."""
        assert detect_language_from_location("Toronto") == "en"

    def test_empty_returns_en(self):
        """Empty location should return 'en'."""
        assert detect_language_from_location("") == "en"

    def test_remote_returns_en(self):
        """Remote should return 'en'."""
        assert detect_language_from_location("Remote") == "en"

    def test_copenhagen_returns_en(self):
        """Copenhagen should return 'en' (jobs in Denmark are typically in English)."""
        assert detect_language_from_location("Copenhagen") == "en"

    def test_guadalajara_returns_es(self):
        """Guadalajara should return 'es'."""
        assert detect_language_from_location("Guadalajara") == "es"
