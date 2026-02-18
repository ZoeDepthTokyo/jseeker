"""Tests for JD parser module."""

import requests
from jseeker.jd_parser import (
    detect_ats_platform,
    detect_language,
    detect_language_from_location,
    detect_market_from_location,
    extract_jd_from_url,
    sanitize_company_name,
    _extract_salary,
    _extract_company_from_url,
    _extract_company_fallback,
    _is_incomplete_jd,
    _search_company_career_site,
    _linkedin_fallback_search,
)
from jseeker.models import ATSPlatform


class TestATSDetection:
    """Test ATS platform detection from URLs."""

    def test_greenhouse_detection(self):
        assert (
            detect_ats_platform("https://boards.greenhouse.io/company/jobs/123")
            == ATSPlatform.GREENHOUSE
        )

    def test_workday_detection(self):
        assert (
            detect_ats_platform("https://company.wd5.myworkdayjobs.com/jobs")
            == ATSPlatform.WORKDAY
        )

    def test_lever_detection(self):
        assert (
            detect_ats_platform("https://jobs.lever.co/company/123")
            == ATSPlatform.LEVER
        )

    def test_ashby_detection(self):
        assert (
            detect_ats_platform("https://jobs.ashbyhq.com/company/123")
            == ATSPlatform.ASHBY
        )

    def test_taleo_detection(self):
        assert (
            detect_ats_platform("https://company.taleo.net/careersection")
            == ATSPlatform.TALEO
        )

    def test_unknown_url(self):
        assert detect_ats_platform("https://example.com/jobs") == ATSPlatform.UNKNOWN

    def test_empty_url(self):
        assert detect_ats_platform("") == ATSPlatform.UNKNOWN

    def test_icims_detection(self):
        assert (
            detect_ats_platform("https://careers-company.icims.com/jobs")
            == ATSPlatform.ICIMS
        )


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

        monkeypatch.setattr(
            "jseeker.jd_parser.requests.get", lambda *args, **kwargs: FakeResponse()
        )
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
        min_sal, max_sal, currency = _extract_salary(
            "Salary range: $120,000 - $150,000"
        )
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
        result = _extract_company_from_url(
            "https://careers.santander.com/job/123/design-strategist"
        )
        assert result is not None
        assert result.lower() == "santander"

    def test_extract_company_from_lever_url(self):
        """Lever URL should extract company name."""
        result = _extract_company_from_url("https://jobs.lever.co/acme-corp/123")
        assert result == "Acme Corp"

    def test_extract_company_from_greenhouse_url(self):
        """Greenhouse URL should extract company name."""
        result = _extract_company_from_url(
            "https://boards.greenhouse.io/techcorp/jobs/123"
        )
        assert result == "Techcorp"

    def test_extract_company_from_workday_url(self):
        """Workday URL should extract company name."""
        result = _extract_company_from_url(
            "https://acme.wd5.myworkdayjobs.com/en-US/jobs"
        )
        assert result == "Acme"

    def test_extract_company_from_viterbit_url(self):
        """Viterbit URL should extract company name from subdomain."""
        result = _extract_company_from_url(
            "https://aviva.viterbit.site/head-of-product-oeCHOj1uiH5H/"
        )
        assert result == "Aviva"

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


class TestSanitizeCompanyName:
    """Test company name sanitization to prevent corrupted names."""

    def test_clean_name_passes_through(self):
        """Valid company names should pass through unchanged."""
        assert sanitize_company_name("PayPal") == "PayPal"
        assert sanitize_company_name("Paramount") == "Paramount"
        assert sanitize_company_name("Stay 22") == "Stay 22"
        assert sanitize_company_name("JPMorgan Chase & Co") == "JPMorgan Chase & Co"

    def test_sentence_fragment_truncated(self):
        """Sentence fragments after company name should be removed."""
        assert (
            sanitize_company_name("PayPal has been revolutionizing payments")
            == "PayPal"
        )
        assert sanitize_company_name("Paramount drives revenue growth") == "Paramount"
        assert sanitize_company_name("Aviva is a leading insurance company") == "Aviva"

    def test_false_positive_rejected(self):
        """Common false-positive words should be rejected."""
        assert sanitize_company_name("revenue") == ""
        assert sanitize_company_name("position") == ""
        assert sanitize_company_name("team") == ""
        assert sanitize_company_name("Remote") == ""

    def test_empty_and_none(self):
        """Empty/None inputs should return empty string."""
        assert sanitize_company_name("") == ""
        assert sanitize_company_name(None) == ""
        assert sanitize_company_name("   ") == ""

    def test_underscore_slugs_cleaned(self):
        """URL-style underscores should become spaces."""
        assert sanitize_company_name("Acme_Corp") == "Acme Corp"

    def test_placeholder_values_rejected(self):
        """Placeholder strings should be rejected."""
        assert sanitize_company_name("Not Specified") == ""
        assert sanitize_company_name("unknown") == ""
        assert sanitize_company_name("N/A") == ""
        assert sanitize_company_name("TBD") == ""

    def test_too_long_rejected(self):
        """Excessively long strings (sentence fragments) should be rejected."""
        long_name = "This is a very long string that is clearly not a company name and should be rejected"
        assert sanitize_company_name(long_name) == ""

    def test_single_char_rejected(self):
        """Single character names should be rejected."""
        assert sanitize_company_name("A") == ""

    def test_real_company_names(self):
        """Real company names from bug reports should work correctly."""
        assert sanitize_company_name("Paramount") == "Paramount"
        assert sanitize_company_name("PayPal") == "PayPal"
        assert sanitize_company_name("Aviva") == "Aviva"
        assert sanitize_company_name("Stay 22") == "Stay 22"
        assert sanitize_company_name("Santander") == "Santander"
        assert sanitize_company_name("Google") == "Google"
        assert sanitize_company_name("McKinsey & Company") == "McKinsey & Company"

    def test_leading_articles_removed(self):
        """Leading articles should be stripped."""
        assert sanitize_company_name("The Acme Corp") == "Acme Corp"
        assert sanitize_company_name("A Big Company") == "Big Company"

    def test_trailing_punctuation_removed(self):
        """Trailing punctuation and conjunctions should be stripped."""
        assert sanitize_company_name("Acme Corp,") == "Acme Corp"
        assert sanitize_company_name("Acme Corp -") == "Acme Corp"
        assert sanitize_company_name("Acme Corp and") == "Acme Corp"

    def test_provides_verb_truncation(self):
        """Company names followed by verbs like 'provides' should be truncated."""
        assert sanitize_company_name("Acme Corp provides solutions") == "Acme Corp"
        assert sanitize_company_name("TechCo offers great benefits") == "TechCo"


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


class TestIncompleteJDDetection:
    """Test _is_incomplete_jd detection logic."""

    def test_empty_text_is_incomplete(self):
        assert _is_incomplete_jd("") is True

    def test_none_text_is_incomplete(self):
        assert _is_incomplete_jd(None) is True

    def test_short_text_is_incomplete(self):
        assert _is_incomplete_jd("Apply now for this exciting role.") is True

    def test_short_text_under_200_chars_is_incomplete(self):
        assert _is_incomplete_jd("a" * 150) is True

    def test_medium_text_without_sections_is_incomplete(self):
        """Text under 500 chars with no JD section keywords is incomplete."""
        text = "We are looking for a software engineer to join our team. " * 5
        assert len(text) < 500
        assert _is_incomplete_jd(text) is True

    def test_medium_text_with_sections_is_complete(self):
        """Text between 200-500 chars with JD section keywords is complete."""
        text = (
            "Software Engineer at Acme Corp. "
            "We are looking for a talented engineer to join our growing team. "
            "Responsibilities: Build and maintain scalable web applications. "
            "Requirements: 3+ years Python experience with cloud platforms. "
            "Qualifications: BS in Computer Science preferred. "
        )
        assert 200 < len(text) < 500
        assert _is_incomplete_jd(text) is False

    def test_long_text_is_complete(self):
        """Text over 500 chars is always complete regardless of sections."""
        text = "We are hiring a great engineer. " * 20
        assert len(text) > 500
        assert _is_incomplete_jd(text) is False

    def test_full_jd_is_complete(self):
        """A realistic full JD should be detected as complete."""
        text = (
            "Senior Software Engineer\n\n"
            "About the Role\n"
            "We are looking for a senior engineer to lead our platform team.\n\n"
            "Responsibilities:\n"
            "- Design and build scalable microservices\n"
            "- Mentor junior engineers\n"
            "- Drive technical decisions\n\n"
            "Requirements:\n"
            "- 5+ years of Python experience\n"
            "- Experience with cloud platforms (AWS/GCP)\n"
            "- Strong communication skills\n"
        )
        assert _is_incomplete_jd(text) is False


class TestLinkedInFallbackSearch:
    """Test LinkedIn JD fallback search chain."""

    def test_fallback_with_no_company_returns_empty(self, monkeypatch):
        """Fallback with no company info should return empty."""
        # Mock _extract_company_from_url to return None (no company from URL)
        monkeypatch.setattr(
            "jseeker.jd_parser._extract_company_from_url", lambda url: None
        )
        metadata = {"company": "", "method": "failed"}
        text, meta = _linkedin_fallback_search(
            "https://linkedin.com/jobs/view/123", "", metadata
        )
        assert text == ""

    def test_fallback_tries_career_site(self, monkeypatch):
        """Fallback should try company career site when company is known."""
        full_jd = (
            "Software Engineer - Full JD with responsibilities and requirements. "
            "Responsibilities: Build software. Requirements: Python. " * 10
        )

        def mock_career_site(company, title="", timeout=15):
            return "https://careers.acme.com/jobs/123"

        def mock_extract(url, timeout=20):
            if "careers.acme" in url:
                return full_jd, {
                    "success": True,
                    "method": "selector",
                    "company": "Acme",
                }
            return "", {"success": False, "method": "failed", "company": ""}

        monkeypatch.setattr(
            "jseeker.jd_parser._search_company_career_site", mock_career_site
        )
        monkeypatch.setattr("jseeker.jd_parser.extract_jd_from_url", mock_extract)

        metadata = {"company": "Acme", "method": "failed"}
        text, meta = _linkedin_fallback_search(
            "https://linkedin.com/jobs/view/123", "", metadata
        )
        assert text == full_jd
        assert meta.get("linkedin_fallback_used") is True
        assert meta.get("alternate_source_url") == "https://careers.acme.com/jobs/123"

    def test_fallback_tries_web_search_when_career_site_fails(self, monkeypatch):
        """Fallback should try web search when career site fails."""
        full_jd = (
            "Data Scientist at BigCo. Responsibilities: Analyze data. "
            "Requirements: ML experience. Qualifications: PhD preferred. " * 8
        )

        def mock_career_site(company, title="", timeout=15):
            return None  # Career site not found

        def mock_search(title, company):
            return "https://boards.greenhouse.io/bigco/jobs/456"

        call_count = {"n": 0}

        def mock_extract(url, timeout=20):
            call_count["n"] += 1
            if "greenhouse" in url:
                return full_jd, {
                    "success": True,
                    "method": "selector",
                    "company": "BigCo",
                }
            return "", {"success": False, "method": "failed", "company": ""}

        monkeypatch.setattr(
            "jseeker.jd_parser._search_company_career_site", mock_career_site
        )
        monkeypatch.setattr("jseeker.jd_parser._search_alternate_posting", mock_search)
        monkeypatch.setattr("jseeker.jd_parser.extract_jd_from_url", mock_extract)

        metadata = {"company": "BigCo", "method": "failed"}
        text, meta = _linkedin_fallback_search(
            "https://linkedin.com/jobs/view/789", "", metadata
        )
        assert text == full_jd
        assert meta.get("linkedin_fallback_used") is True
        assert meta.get("method") == "linkedin_fallback_web_search"


class TestSearchCompanyCareerSite:
    """Test _search_company_career_site function."""

    def test_returns_none_for_empty_company(self):
        assert _search_company_career_site("") is None
        assert _search_company_career_site(None) is None

    def test_tries_career_patterns(self, monkeypatch):
        """Should try common career site URL patterns."""
        tried_urls = []

        def mock_get(url, timeout=15, headers=None, allow_redirects=True):
            tried_urls.append(url)
            raise requests.RequestException("mock")

        monkeypatch.setattr(requests, "get", mock_get)
        result = _search_company_career_site("Acme")
        assert result is None
        assert any("careers.acme.com" in u for u in tried_urls)
        assert any("acme.com/careers" in u for u in tried_urls)

    def test_returns_career_url_on_success(self, monkeypatch):
        """Should return career site URL when it responds successfully."""

        class MockResponse:
            status_code = 200
            text = "<html><body>" + "x" * 600 + "</body></html>"

        def mock_get(url, timeout=15, headers=None, allow_redirects=True):
            if "careers.paramount" in url:
                return MockResponse()
            raise requests.RequestException("not found")

        monkeypatch.setattr(requests, "get", mock_get)
        result = _search_company_career_site("Paramount")
        assert result == "https://careers.paramount.com"


class TestExtractLinkedInFallbackIntegration:
    """Integration tests for LinkedIn fallback in extract_jd_from_url."""

    def test_linkedin_url_triggers_fallback_on_incomplete(self, monkeypatch):
        """When LinkedIn scraping returns incomplete JD, fallback should trigger."""
        incomplete_html = "<html><body><div class='description'>Apply for this job</div></body></html>"
        full_jd = (
            "Senior Engineer at Paramount. "
            "Responsibilities: Lead engineering team. "
            "Requirements: 5+ years experience. " * 10
        )

        def mock_get(url, **kwargs):
            resp = requests.models.Response()
            resp.status_code = 200
            resp._content = incomplete_html.encode()
            return resp

        def mock_resolve(url, timeout=15):
            return None  # No ATS link found on LinkedIn page

        def mock_playwright(url, selectors, platform="generic-fallback", wait_ms=4000):
            return ""  # Playwright also returns nothing

        fallback_called = {"called": False}

        def mock_fallback(original_url, partial_text, metadata, timeout=20):
            fallback_called["called"] = True
            return full_jd, {
                "success": True,
                "method": "linkedin_fallback_career_site",
                "alternate_source_url": "https://careers.paramount.com/jobs/123",
                "linkedin_fallback_used": True,
                "company": "Paramount",
            }

        monkeypatch.setattr(requests, "get", mock_get)
        monkeypatch.setattr("jseeker.jd_parser._resolve_linkedin_url", mock_resolve)
        monkeypatch.setattr(
            "jseeker.jd_parser._extract_with_playwright", mock_playwright
        )
        monkeypatch.setattr(
            "jseeker.jd_parser._linkedin_fallback_search", mock_fallback
        )

        text, meta = extract_jd_from_url("https://www.linkedin.com/jobs/view/12345")
        assert fallback_called["called"] is True
        assert text == full_jd
        assert meta.get("linkedin_fallback_used") is True
        assert (
            meta.get("alternate_source_url") == "https://careers.paramount.com/jobs/123"
        )

    def test_non_linkedin_url_does_not_trigger_fallback(self, monkeypatch):
        """Non-LinkedIn URLs should not trigger LinkedIn fallback."""
        short_html = (
            "<html><body><div class='description'>Short text.</div></body></html>"
        )

        def mock_get(url, **kwargs):
            resp = requests.models.Response()
            resp.status_code = 200
            resp._content = short_html.encode()
            return resp

        def mock_playwright(url, selectors, platform="generic-fallback", wait_ms=4000):
            return ""

        monkeypatch.setattr(requests, "get", mock_get)
        monkeypatch.setattr(
            "jseeker.jd_parser._extract_with_playwright", mock_playwright
        )

        text, meta = extract_jd_from_url("https://example.com/jobs/123")
        assert meta.get("linkedin_fallback_used", False) is False


class TestCompanyExtractionBugReports:
    """Test company extraction for specific bug report URLs (Feb 16 sprint).

    These tests verify that problematic URLs from real user sessions
    correctly extract the company name instead of returning garbage
    like 'Myworkdayjobs', 'Linkedin', or sentence fragments.
    """

    def test_paramount_greenhouse_url(self):
        """Paramount on Greenhouse should extract 'Paramount'."""
        result = _extract_company_from_url(
            "https://boards.greenhouse.io/paramount/jobs/7654321"
        )
        assert result is not None
        assert result.lower() == "paramount"

    def test_paypal_workday_url(self):
        """PayPal on Workday should extract 'Paypal'."""
        result = _extract_company_from_url(
            "https://paypal.wd1.myworkdayjobs.com/jobs/job/Mexico-City/Senior-UX-Designer_R12345"
        )
        assert result is not None
        assert result.lower() == "paypal"

    def test_stay22_lever_url(self):
        """Stay 22 on Lever should extract 'Stay 22'."""
        result = _extract_company_from_url(
            "https://jobs.lever.co/stay-22/abc123-def456"
        )
        assert result is not None
        assert result.lower() == "stay 22"

    def test_aviva_viterbit_url(self):
        """Aviva on Viterbit should extract 'Aviva'."""
        result = _extract_company_from_url(
            "https://aviva.viterbit.site/head-of-product-oeCHOj1uiH5H/"
        )
        assert result is not None
        assert result.lower() == "aviva"

    def test_paramount_fallback_from_jd_text(self):
        """When URL extraction fails, JD text should extract Paramount."""
        text = """
        Senior UX Designer

        At Paramount, we create premium content and experiences for a global audience.
        Join our design team to shape the future of streaming entertainment.

        Responsibilities:
        - Lead UX design for Paramount+ streaming platform
        - Collaborate with product and engineering teams

        Requirements:
        - 8+ years of UX design experience
        - Portfolio demonstrating streaming or media projects
        """
        result = _extract_company_fallback(text)
        assert result is not None
        assert result.lower() == "paramount"

    def test_paypal_fallback_from_jd_text(self):
        """When URL extraction fails, JD text should extract PayPal."""
        text = """
        Director of Product Design

        About PayPal
        PayPal is the global leader in digital payments.

        Responsibilities:
        - Lead design strategy for checkout experiences
        - Manage a team of 15+ designers
        """
        result = _extract_company_fallback(text)
        assert result is not None
        assert result.lower() == "paypal"

    def test_company_name_not_corrupted_by_url_slug(self):
        """Company name should not include URL path segments like job IDs."""
        # Workday URL with complex path
        result = _extract_company_from_url(
            "https://acme.wd5.myworkdayjobs.com/en-US/External/job/Mexico-City/Director-UX_R0012345"
        )
        assert result is not None
        assert "External" not in result
        assert "Mexico" not in result
        assert "Director" not in result

    def test_santander_careers_domain(self):
        """Santander with careers subdomain should extract correctly."""
        result = _extract_company_from_url(
            "https://careers.santander.com/job/mexico-city/design-strategist/123"
        )
        assert result is not None
        assert result.lower() == "santander"

    def test_sanitize_prevents_sentence_as_company(self):
        """Sanitize should prevent sentence fragments from being used as company names."""
        # These are real examples from corrupted extractions
        assert sanitize_company_name("Paramount drives revenue growth") == "Paramount"
        assert sanitize_company_name("PayPal is the global leader") == "PayPal"
        assert sanitize_company_name("") == ""
        assert sanitize_company_name(None) == ""


class TestParsedJDAlternateSource:
    """Test ParsedJD model includes alternate_source_url field."""

    def test_alternate_source_url_default_empty(self):
        from jseeker.models import ParsedJD

        jd = ParsedJD(raw_text="test")
        assert jd.alternate_source_url == ""

    def test_alternate_source_url_can_be_set(self):
        from jseeker.models import ParsedJD

        jd = ParsedJD(
            raw_text="test", alternate_source_url="https://careers.example.com/job/123"
        )
        assert jd.alternate_source_url == "https://careers.example.com/job/123"


def test_resolve_branded_greenhouse_url_hubspot():
    from jseeker.jd_parser import _resolve_branded_greenhouse_url

    result = _resolve_branded_greenhouse_url(
        "https://www.hubspot.com/careers/jobs/7609930?gh_jid=7609930&gh_src=my.greenhouse.search"
    )
    assert result == "https://job-boards.greenhouse.io/hubspot/jobs/7609930"


def test_resolve_branded_greenhouse_url_navan():
    from jseeker.jd_parser import _resolve_branded_greenhouse_url

    result = _resolve_branded_greenhouse_url(
        "https://navan.com/careers/openings/7616887?gh_jid=7616887"
    )
    assert result == "https://job-boards.greenhouse.io/navan/jobs/7616887"


def test_resolve_branded_greenhouse_url_no_gh_jid():
    from jseeker.jd_parser import _resolve_branded_greenhouse_url

    result = _resolve_branded_greenhouse_url("https://hubspot.com/careers/jobs/1234")
    assert result is None
