"""jSeeker JD Parser — Paste + auto-prune → ParsedJD."""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

from jseeker.llm import llm
from jseeker.models import ATSPlatform, JDRequirement, ParsedJD

logger = logging.getLogger(__name__)

# ATS detection patterns (domain → platform)
ATS_DETECTION = {
    "greenhouse.io": ATSPlatform.GREENHOUSE,
    "boards.greenhouse.io": ATSPlatform.GREENHOUSE,
    "myworkdayjobs.com": ATSPlatform.WORKDAY,
    "wd5.myworkdayjobs.com": ATSPlatform.WORKDAY,
    "lever.co": ATSPlatform.LEVER,
    "jobs.lever.co": ATSPlatform.LEVER,
    "icims.com": ATSPlatform.ICIMS,
    "ashbyhq.com": ATSPlatform.ASHBY,
    "jobs.ashbyhq.com": ATSPlatform.ASHBY,
    "taleo.net": ATSPlatform.TALEO,
    "oracle.com/careers": ATSPlatform.TALEO,
}

# Subdomains that indicate a careers site, not the company name itself
CAREER_SUBDOMAINS: frozenset[str] = frozenset({"careers", "jobs", "hire", "apply", "work", "talent"})


def _load_prompt(name: str) -> str:
    """Load a prompt template from data/prompts/."""
    from config import settings

    path = settings.prompts_dir / f"{name}.txt"
    return path.read_text(encoding="utf-8")


# Location-to-market mapping for automatic market detection
_LOCATION_TO_MARKET = {
    # Mexico
    "mexico": "mx",
    "méxico": "mx",
    "cdmx": "mx",
    "ciudad de mexico": "mx",
    "ciudad de méxico": "mx",
    "guadalajara": "mx",
    "monterrey": "mx",
    "tijuana": "mx",
    "puebla": "mx",
    "queretaro": "mx",
    "querétaro": "mx",
    "leon": "mx",
    "cancun": "mx",
    "merida": "mx",
    "mérida": "mx",
    # Canada
    "toronto": "ca",
    "vancouver": "ca",
    "montreal": "ca",
    "montréal": "ca",
    "ottawa": "ca",
    "calgary": "ca",
    "edmonton": "ca",
    "winnipeg": "ca",
    "canada": "ca",
    # UK
    "london": "uk",
    "manchester": "uk",
    "edinburgh": "uk",
    "birmingham": "uk",
    "bristol": "uk",
    "leeds": "uk",
    "glasgow": "uk",
    "united kingdom": "uk",
    "uk": "uk",
    # Spain
    "madrid": "es",
    "barcelona": "es",
    "valencia": "es",
    "seville": "es",
    "sevilla": "es",
    "bilbao": "es",
    "malaga": "es",
    "málaga": "es",
    "spain": "es",
    "españa": "es",
    # Denmark
    "copenhagen": "dk",
    "aarhus": "dk",
    "odense": "dk",
    "denmark": "dk",
    "danmark": "dk",
    # France
    "paris": "fr",
    "lyon": "fr",
    "marseille": "fr",
    "toulouse": "fr",
    "nice": "fr",
    "nantes": "fr",
    "strasbourg": "fr",
    "france": "fr",
    # US states/cities (common ones)
    "new york": "us",
    "san francisco": "us",
    "los angeles": "us",
    "chicago": "us",
    "seattle": "us",
    "austin": "us",
    "boston": "us",
    "denver": "us",
    "san diego": "us",
    "miami": "us",
    "atlanta": "us",
    "dallas": "us",
    "houston": "us",
    "portland": "us",
    "phoenix": "us",
    "united states": "us",
    "usa": "us",
}

# Market-to-language mapping
_MARKET_TO_LANGUAGE = {
    "mx": "es",
    "es": "es",
    "fr": "fr",
    "us": "en",
    "ca": "en",
    "uk": "en",
    "dk": "en",
}


def detect_market_from_location(location: str) -> str:
    """Detect market code from a location string.

    Args:
        location: Location string (e.g., "Mexico City", "London", "Remote").

    Returns:
        Market code: "us", "mx", "ca", "uk", "es", "dk", "fr".
    """
    if not location or location.strip().lower() in (
        "remote",
        "anywhere",
        "flexible",
        "",
    ):
        return "us"

    location_lower = location.lower().strip()

    # Check for US/CA state/province abbreviations (e.g., "San Diego, CA")
    state_match = re.search(r",\s*([A-Z]{2})\s*$", location.strip())
    if state_match:
        ca_provinces = {
            "ON",
            "BC",
            "QC",
            "AB",
            "MB",
            "SK",
            "NB",
            "NS",
            "PE",
            "NL",
            "YT",
            "NT",
            "NU",
        }
        if state_match.group(1) in ca_provinces:
            return "ca"
        return "us"

    # Check each pattern against the location string
    for pattern, market in _LOCATION_TO_MARKET.items():
        if pattern in location_lower:
            return market

    return "us"


def detect_language_from_location(location: str) -> str:
    """Detect the expected resume language from a job location.

    Used to override text-based language detection when the JD is written
    in English but the job is in a Spanish/French-speaking market.

    Args:
        location: Location string from parsed JD.

    Returns:
        Language code: "en", "es", or "fr".
    """
    market = detect_market_from_location(location)
    return _MARKET_TO_LANGUAGE.get(market, "en")


def detect_language(text: str) -> str:
    """Detect language of JD text using heuristic word frequency.

    Args:
        text: JD text to analyze.

    Returns:
        Language code: "en" or "es".
    """
    if not text or len(text.strip()) < 50:
        return "en"

    text_lower = text.lower()
    words = text_lower.split()
    total_words = len(words)

    if total_words == 0:
        return "en"

    # Common Spanish words
    spanish_words = [
        "de",
        "en",
        "para",
        "con",
        "los",
        "las",
        "del",
        "una",
        "por",
        "que",
        "como",
        "sobre",
        "experiencia",
        "responsabilidades",
        "requisitos",
        "empresa",
        "puesto",
        "trabajo",
        "años",
        "área",
        "desarrollo",
    ]

    # Common English words
    english_words = [
        "the",
        "and",
        "for",
        "with",
        "our",
        "you",
        "this",
        "that",
        "from",
        "have",
        "will",
        "are",
        "your",
        "requirements",
        "responsibilities",
        "experience",
        "position",
        "company",
        "years",
        "team",
        "work",
    ]

    spanish_count = sum(1 for word in words if word in spanish_words)
    english_count = sum(1 for word in words if word in english_words)

    spanish_ratio = spanish_count / total_words
    english_ratio = english_count / total_words

    # If Spanish word ratio > 0.15, classify as Spanish
    if spanish_ratio > 0.15:
        return "es"

    # If English ratio is significantly higher, classify as English
    if english_ratio > spanish_ratio * 1.5:
        return "en"

    # Default to English
    return "en"


def detect_jd_language(jd_text: str) -> str:
    """Detect language of JD text (alias for detect_language).

    Args:
        jd_text: Job description text to analyze.

    Returns:
        Language code: "en" or "es".
    """
    return detect_language(jd_text)


def detect_ats_platform(url: str) -> ATSPlatform:
    """Detect ATS platform from a job URL."""
    if not url:
        return ATSPlatform.UNKNOWN
    url_lower = url.lower()
    for pattern, platform in ATS_DETECTION.items():
        if pattern in url_lower:
            return platform
    return ATSPlatform.UNKNOWN


def _clean_extracted_text(text: str) -> str:
    """Normalize whitespace and remove obvious junk from extracted HTML text."""
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_with_playwright(
    url: str, selectors: list[str], platform: str = "generic", wait_ms: int = 3000
) -> str:
    """Extract JD text from a JS-rendered page using Playwright.

    Launches a headless browser, navigates to the URL, tries each selector
    in order, and returns the first match with sufficient text content.

    Args:
        url: Job posting URL.
        selectors: CSS selectors to try in priority order.
        platform: Name for logging (e.g., "workday", "ashby").
        wait_ms: Extra wait after page load for JS rendering (ms).

    Returns:
        Extracted JD text, or empty string if extraction fails.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning(f"_extract_with_playwright[{platform}] | Playwright not installed")
        return ""

    try:
        logger.info(
            f"_extract_with_playwright[{platform}] | launching browser for url={url[:100]}..."
        )
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=20000, wait_until="domcontentloaded")

            # Try each selector with a wait
            text = ""
            for selector in selectors:
                try:
                    page.wait_for_selector(selector, timeout=8000)
                    el = page.query_selector(selector)
                    if el:
                        candidate = el.inner_text()
                        if len(candidate) >= 180:
                            text = candidate
                            logger.info(
                                f"_extract_with_playwright[{platform}] | selector '{selector}' matched {len(text)} chars"
                            )
                            break
                except Exception:
                    continue

            # If no selector worked, wait for JS and try body content
            if len(text) < 180:
                logger.debug(
                    f"_extract_with_playwright[{platform}] | selectors failed, waiting {wait_ms}ms for JS render"
                )
                page.wait_for_timeout(wait_ms)
                # Try main/article/section before full body
                for fallback_sel in ["main", "article", "[role='main']", "body"]:
                    el = page.query_selector(fallback_sel)
                    if el:
                        candidate = el.inner_text()
                        if len(candidate) >= 180:
                            text = candidate
                            logger.info(
                                f"_extract_with_playwright[{platform}] | fallback '{fallback_sel}' matched {len(text)} chars"
                            )
                            break

            browser.close()
            return text.strip()
    except Exception as e:
        logger.warning(f"_extract_with_playwright[{platform}] | failed: {e}")
        return ""


# Platform-specific selectors (ordered by priority)
_WORKDAY_SELECTORS = [
    '[data-automation-id="jobPostingDescription"]',
    '[data-automation-id="jobPostingRequirements"]',
    ".css-cygeeu",
    '[class*="jobDescription"]',
    '[class*="JobDescription"]',
    '[class*="job-description"]',
    'div[data-automation-id="jobPostingPage"]',
]

_ASHBY_SELECTORS = [
    '[class*="ashby-job-posting-brief-description"]',
    '[data-testid="job-posting-description"]',
    '[class*="job-posting-description"]',
    '[class*="posting-page"]',
    '[class*="job-details"]',
    '[class*="JobDescription"]',
    "div.ashby-job-posting-description",
    "main",
]


_VITERBIT_SELECTORS = [
    '[class*="description"]',
    '[class*="job-description"]',
    '[class*="offer"]',
    '[class*="posting"]',
    "main",
    "article",
    '[role="main"]',
]


def _extract_workday_jd(url: str) -> str:
    """Extract JD from Workday pages using Playwright for JS rendering."""
    return _extract_with_playwright(url, _WORKDAY_SELECTORS, platform="workday", wait_ms=4000)


def _extract_ashby_jd(url: str) -> str:
    """Extract JD from Ashby pages using Playwright for JS rendering."""
    return _extract_with_playwright(url, _ASHBY_SELECTORS, platform="ashby", wait_ms=3000)


def _extract_viterbit_jd(url: str) -> str:
    """Extract JD from Viterbit pages using Playwright for JS rendering."""
    return _extract_with_playwright(url, _VITERBIT_SELECTORS, platform="viterbit", wait_ms=4000)


def sanitize_company_name(name: str | None) -> str:
    """Sanitize and validate a company name extracted from any source.

    Cleans up common extraction artifacts:
    - Sentence fragments ("PayPal has been revolutionizing...")
    - Random words from JD text ("revenue", "position", "team")
    - Excessive length or special characters
    - Underscores from URL slugs

    Args:
        name: Raw company name from LLM, regex, or URL extraction.

    Returns:
        Cleaned company name, or empty string if invalid.
    """
    if not name or not name.strip():
        return ""

    cleaned = name.strip()

    # Replace underscores with spaces (URL slug artifacts)
    cleaned = cleaned.replace("_", " ")

    # Truncate at common sentence-starting words (catches "PayPal has been revolutionizing...")
    sentence_breakers = re.compile(
        r"\b(?:has|have|had|is|are|was|were|will|would|shall|should|can|could|"
        r"may|might|must|do|does|did|been|being|that|which|where|when|while|"
        r"offers|provides|delivers|drives|seeks|looking|hiring|building|"
        r"specializes|focuses|creates|develops|enables|powers|helps|"
        r"revolutioniz\w*|transform\w*)\b",
        re.IGNORECASE,
    )
    match = sentence_breakers.search(cleaned)
    if match:
        cleaned = cleaned[: match.start()].strip()

    # Remove trailing punctuation and conjunctions
    cleaned = re.sub(r"[\s,;:\-–—]+$", "", cleaned)
    cleaned = re.sub(r"\s+(?:and|or|the|a|an|at|in|for|of)\s*$", "", cleaned, flags=re.IGNORECASE)

    # Remove leading articles/prepositions
    cleaned = re.sub(r"^(?:the|a|an)\s+", "", cleaned, flags=re.IGNORECASE)

    # Strip any remaining leading/trailing whitespace
    cleaned = cleaned.strip()

    # Reject if result is a common false-positive word (not a company name)
    false_positives = {
        "revenue",
        "position",
        "team",
        "company",
        "role",
        "job",
        "career",
        "opportunity",
        "department",
        "division",
        "group",
        "office",
        "location",
        "salary",
        "compensation",
        "benefits",
        "about",
        "overview",
        "description",
        "requirements",
        "responsibilities",
        "qualifications",
        "experience",
        "skills",
        "education",
        "apply",
        "submit",
        "click",
        "here",
        "more",
        "details",
        "information",
        "contact",
        "email",
        "phone",
        "address",
        "remote",
        "hybrid",
        "onsite",
        "full-time",
        "part-time",
        "contract",
        "not specified",
        "unknown",
        "n/a",
        "tbd",
        "this",
        "that",
        "these",
        "those",
        "we",
        "our",
        "they",
        "their",
    }
    if cleaned.lower() in false_positives:
        return ""

    # Reject if too short (single char) or too long (likely a sentence fragment)
    if len(cleaned) < 2 or len(cleaned) > 60:
        return ""

    # Reject if it contains too many words (likely a sentence, not a name)
    # Most company names are 1-5 words (e.g., "JPMorgan Chase & Co")
    word_count = len(cleaned.split())
    if word_count > 6:
        return ""

    return cleaned


def _extract_company_from_url(url: str) -> str | None:
    """Extract company name from URL patterns (Lever, Greenhouse, Workday, plain domains).

    Args:
        url: Job posting URL

    Returns:
        Company name if detected, else None
    """
    if not url:
        return None

    # Branded Greenhouse page: extract company slug from domain
    if "gh_jid=" in url:
        from urllib.parse import urlparse

        domain = urlparse(url).netloc.lower().replace("www.", "")
        parts = domain.split(".")
        if len(parts) >= 3 and parts[0] in CAREER_SUBDOMAINS:
            slug = parts[1]  # "withwaymo" from "careers.withwaymo.com"
        else:
            slug = parts[0]  # "hubspot" from "hubspot.com"
        return slug.replace("-", " ").title()

    # Lever: jobs.lever.co/company-name/
    lever_match = re.search(r"jobs\.lever\.co/([^/]+)", url)
    if lever_match:
        return lever_match.group(1).replace("-", " ").title()

    # Greenhouse: boards.greenhouse.io/company-name/
    greenhouse_match = re.search(r"boards\.greenhouse\.io/([^/]+)", url)
    if greenhouse_match:
        return greenhouse_match.group(1).replace("-", " ").title()

    # Viterbit: company.viterbit.site/job-slug/
    viterbit_match = re.search(r"([a-zA-Z0-9_-]+)\.viterbit\.(?:site|com)", url)
    if viterbit_match:
        return viterbit_match.group(1).replace("-", " ").title()

    # Workday: company.wd5.myworkdayjobs.com/ or company.myworkdayjobs.com/
    workday_match = re.search(r"([a-zA-Z0-9_-]+)(?:\.wd\d+)?\.myworkdayjobs\.com", url)
    if workday_match:
        return workday_match.group(1).replace("-", " ").title()

    # Generic careers sites: careers.company.com or company-careers.com
    # Include hyphens in company name pattern
    careers_match = re.search(r"(?:careers?\.)?([a-zA-Z0-9-]+?)(?:-?careers?)?\.com", url)
    if careers_match:
        company = careers_match.group(1)
        # Skip generic words that aren't company names
        if company.lower() not in [
            "www",
            "jobs",
            "apply",
            "talent",
            "recruiting",
            "careers",
            "career",
        ]:
            # Handle hyphenated compound names: "activision-blizzard" -> "Activision Blizzard"
            if "-" in company:
                parts = company.split("-")
                return " ".join(p.capitalize() for p in parts if p and len(p) > 1)
            # Handle camelCase compound names: "activisionblizzard" -> "Activision Blizzard"
            parts = re.findall(r"[A-Z][a-z]*|[0-9]+|[a-z]+", company)
            return " ".join(p.capitalize() for p in parts if p)

    # Plain domain fallback: https://company.com or https://www.company.com
    # Handles cases like santander.com, microsoft.com, etc.
    domain_match = re.search(
        r"https?://(?:www\.)?([a-zA-Z0-9-]+)\.(?:com|co|io|net|org|edu|gov)", url
    )
    if domain_match:
        company = domain_match.group(1)
        # Skip generic words
        if company.lower() not in [
            "www",
            "jobs",
            "apply",
            "talent",
            "recruiting",
            "careers",
            "career",
        ]:
            # Split hyphenated names: "activision-blizzard" -> "Activision Blizzard"
            parts = company.split("-")
            return " ".join(p.capitalize() for p in parts if p and len(p) > 1)

    return None


def _extract_company_fallback(text: str) -> str | None:
    """Extract company name from raw JD text using regex patterns.

    Handles common patterns like:
    - "Company: Acme Corp"
    - "Join the team at Acme Corp"
    - "About Acme Corp\nWe are..."
    - "We are hiring at Acme Corp"

    Args:
        text: JD text to extract company from

    Returns:
        Company name if detected, else None
    """
    if not text:
        return None

    # Pattern 1: "Company: Name" or "Company Name:"
    company_label_match = re.search(
        r"(?:Company|Organization|Employer)(?:\s*name)?[\s:]+([A-Z][A-Za-z0-9\s&.,\'-]+?)(?:\n|$|\.(?:\s|$))",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    if company_label_match:
        company = company_label_match.group(1).strip()
        # Filter out common false positives
        if len(company) > 3 and not company.lower().startswith(
            ("about", "overview", "description")
        ):
            return company

    # Pattern 2: "About [Company]" at start of section
    about_match = re.search(
        r"About\s+([A-Z][A-Za-z0-9\s&.,\'-]{2,40}?)(?:\n|$|:)", text, re.MULTILINE
    )
    if about_match:
        company = about_match.group(1).strip()
        # Filter out generic phrases
        if not any(
            word in company.lower()
            for word in ["the role", "this position", "the job", "us", "the company"]
        ):
            return company

    # Pattern 3: "Join [Company]" or "Work at [Company]"
    join_match = re.search(
        r"(?:Join|Work at|Apply to)\s+(?:the\s+team\s+at\s+)?([A-Z][A-Za-z0-9\s&.,\'-]{2,40}?)(?:\n|$|\.|!)",
        text,
        re.MULTILINE,
    )
    if join_match:
        company = join_match.group(1).strip()
        if len(company) > 3:
            return company

    # Pattern 4: "At [Company], we..." or "At [Company] we..."
    at_match = re.search(r"\bAt\s+([A-Z][A-Za-z0-9\s&\'-]{1,40}?)\s*,?\s+we\b", text, re.MULTILINE)
    if at_match:
        company = at_match.group(1).strip()
        if len(company) >= 2 and not any(
            word in company.lower() for word in ["the", "this", "our"]
        ):
            return company

    # Pattern 5: First capitalized name after "We are" at document start
    we_are_match = re.search(
        r"(?:^|^\n)([A-Z][A-Za-z0-9\s&.,\'-]{2,40}?)\s+(?:is|are)\s+(?:hiring|looking|seeking)",
        text[:500],  # Only check first 500 chars
        re.MULTILINE,
    )
    if we_are_match:
        company = we_are_match.group(1).strip()
        if len(company) > 3:
            return company

    return None


def _is_incomplete_jd(text: str) -> bool:
    """Detect when extracted JD content is too thin to be useful.

    Checks text length and presence of key JD sections (requirements,
    responsibilities, qualifications) to determine if the content is
    a stub or incomplete extraction.

    Args:
        text: Extracted JD text to evaluate.

    Returns:
        True if the JD appears incomplete and a fallback search is warranted.
    """
    if not text or len(text.strip()) < 200:
        return True

    text_lower = text.lower()
    # Key sections that a complete JD typically contains
    section_keywords = [
        "responsibilities",
        "requirements",
        "qualifications",
        "what you'll do",
        "what we're looking for",
        "about the role",
        "job description",
        "about this role",
        "role overview",
        "key responsibilities",
        "minimum qualifications",
    ]
    found_sections = sum(1 for kw in section_keywords if kw in text_lower)

    # If text is short AND missing typical JD sections, it's incomplete
    if len(text.strip()) < 500 and found_sections == 0:
        return True

    return False


def _search_company_career_site(company: str, title: str = "", timeout: int = 15) -> Optional[str]:
    """Search a company's career site for the job posting.

    Tries common career site URL patterns (careers.{company}.com, etc.)
    and searches for the job title on those pages.

    Args:
        company: Company name (e.g., "Paramount").
        title: Job title to search for (optional, improves matching).
        timeout: Request timeout in seconds.

    Returns:
        URL of matching job posting on company career site, or None.
    """
    if not company:
        return None

    # Normalize company name to domain-friendly format
    company_slug = re.sub(r"[^a-zA-Z0-9]", "", company.lower())

    # Common career site patterns to try
    career_patterns = [
        f"https://careers.{company_slug}.com",
        f"https://www.{company_slug}.com/careers",
        f"https://jobs.{company_slug}.com",
        f"https://{company_slug}.com/careers",
    ]

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    for career_url in career_patterns:
        try:
            resp = requests.get(career_url, timeout=timeout, headers=headers, allow_redirects=True)
            if resp.status_code == 200 and len(resp.text) > 500:
                logger.info(f"_search_company_career_site | found career site: {career_url}")
                # If we have a title, search for it on the page
                if title:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    title_lower = title.lower()
                    for link in soup.find_all("a", href=True):
                        link_text = link.get_text(strip=True).lower()
                        if title_lower in link_text or any(
                            word in link_text for word in title_lower.split() if len(word) > 3
                        ):
                            href = link["href"]
                            # Make absolute URL if relative
                            if href.startswith("/"):
                                from urllib.parse import urlparse

                                parsed = urlparse(career_url)
                                href = f"{parsed.scheme}://{parsed.netloc}{href}"
                            logger.info(
                                f"_search_company_career_site | matched job link: {href[:100]}"
                            )
                            return href
                # Return the career site URL even without title match
                return career_url
        except requests.RequestException:
            continue

    logger.debug(f"_search_company_career_site | no career site found for company={company}")
    return None


def _resolve_branded_greenhouse_url(url: str) -> str | None:
    """Resolve company-branded Greenhouse pages (gh_jid param) to scrapeable job-boards.greenhouse.io URL.

    hubspot.com/careers/jobs/7609930?gh_jid=7609930 → job-boards.greenhouse.io/hubspot/jobs/7609930
    navan.com/careers/openings/7616887?gh_jid=7616887 → job-boards.greenhouse.io/navan/jobs/7616887

    Args:
        url: Branded Greenhouse job URL containing gh_jid query parameter.

    Returns:
        Canonical job-boards.greenhouse.io URL, or None if gh_jid not present.
    """
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    gh_jid = params.get("gh_jid", [None])[0]
    if not gh_jid:
        return None
    # Extract company slug from domain, handling careers.* subdomains
    domain = parsed.netloc.lower().replace("www.", "")
    parts = domain.split(".")
    if len(parts) >= 3 and parts[0] in CAREER_SUBDOMAINS:
        company_slug = parts[1]  # "withwaymo" from "careers.withwaymo.com"
    else:
        company_slug = parts[0]  # "hubspot" from "hubspot.com"
    return f"https://job-boards.greenhouse.io/{company_slug}/jobs/{gh_jid}"


def _resolve_linkedin_url(url: str, timeout: int = 15) -> Optional[str]:
    """Follow a LinkedIn job URL to find the original company posting URL.

    LinkedIn job pages often link to the original ATS posting (Workday,
    Greenhouse, Lever, etc.) via the Apply button. This function fetches
    the LinkedIn page and extracts that external URL.

    Args:
        url: LinkedIn job URL (e.g., https://www.linkedin.com/jobs/view/...).
        timeout: Request timeout in seconds.

    Returns:
        External ATS URL if found, None otherwise.
    """
    if not url:
        return None

    logger.debug(f"_resolve_linkedin_url | fetching url={url[:100]}...")

    try:
        response = requests.get(
            url.strip(),
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.debug("_resolve_linkedin_url | failed to fetch LinkedIn page")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # Known ATS domain patterns to look for in links
    ats_domains = [
        "myworkdayjobs.com",
        "workday.com",
        "boards.greenhouse.io",
        "greenhouse.io",
        "jobs.lever.co",
        "lever.co",
        "icims.com",
        "ashbyhq.com",
        "taleo.net",
        "careers.",
        "jobs.",
    ]

    # Strategy 1: Look for apply links with class hints
    apply_selectors = [
        'a[class*="apply"]',
        'a[class*="Apply"]',
        'a[class*="original"]',
        'a[data-tracking-control-name*="apply"]',
        "a.apply-button",
    ]
    for selector in apply_selectors:
        for link in soup.select(selector):
            href = link.get("href", "")
            if href and any(domain in href.lower() for domain in ats_domains):
                logger.debug(f"_resolve_linkedin_url | found apply link: {href[:100]}")
                return href

    # Strategy 2: Scan all links for ATS domain matches
    for link in soup.find_all("a", href=True):
        href = link["href"]
        href_lower = href.lower()
        # Skip LinkedIn internal links
        if "linkedin.com" in href_lower:
            continue
        if any(domain in href_lower for domain in ats_domains):
            logger.debug(f"_resolve_linkedin_url | found ATS link: {href[:100]}")
            return href

    # Strategy 3: Check for redirect URLs embedded in query params
    for link in soup.find_all("a", href=True):
        href = link["href"]
        # LinkedIn sometimes wraps external URLs in redirect params
        url_match = re.search(r"[?&]url=([^&]+)", href)
        if url_match:
            from urllib.parse import unquote

            decoded = unquote(url_match.group(1))
            if any(domain in decoded.lower() for domain in ats_domains):
                logger.debug(f"_resolve_linkedin_url | found redirect URL: {decoded[:100]}")
                return decoded

    logger.debug("_resolve_linkedin_url | no external ATS URL found")
    return None


def _search_alternate_posting(title: str, company: str) -> Optional[str]:
    """Search for an alternate job posting URL via web search.

    Best-effort fallback when JD extraction returns too little data.
    Uses a simple Google search to find the same job on other boards.

    Args:
        title: Job title from the original posting.
        company: Company name.

    Returns:
        URL of an alternate posting, or None if not found.
    """
    if not title or not company:
        return None

    from urllib.parse import quote_plus

    query = quote_plus(f"{title} {company} job posting")
    search_url = f"https://www.google.com/search?q={query}"

    logger.debug(f"_search_alternate_posting | query={title} {company}")

    try:
        response = requests.get(
            search_url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.debug("_search_alternate_posting | search request failed")
        return None

    # Known job board domains to look for in search results
    job_board_domains = [
        "myworkdayjobs.com",
        "boards.greenhouse.io",
        "jobs.lever.co",
        "indeed.com/viewjob",
        "glassdoor.com/job-listing",
        "ashbyhq.com",
        "icims.com",
    ]

    soup = BeautifulSoup(response.text, "html.parser")
    for link in soup.find_all("a", href=True):
        href = link["href"]
        # Google wraps results in /url?q=...
        url_match = re.search(r"/url\?q=([^&]+)", href)
        if url_match:
            from urllib.parse import unquote

            candidate = unquote(url_match.group(1))
            if any(domain in candidate.lower() for domain in job_board_domains):
                logger.debug(f"_search_alternate_posting | found: {candidate[:100]}")
                return candidate

    logger.debug("_search_alternate_posting | no alternate posting found")
    return None


def _linkedin_fallback_search(
    original_url: str, partial_text: str, metadata: dict, timeout: int = 20
) -> tuple[str, dict]:
    """Fallback chain when LinkedIn JD extraction produces incomplete content.

    Tries in order:
    1. Company career site (careers.{company}.com patterns)
    2. Web search for alternate posting on job boards

    Args:
        original_url: Original LinkedIn URL (preserved for application tracking).
        partial_text: Whatever text was extracted so far (may be empty).
        metadata: Current extraction metadata dict.
        timeout: Request timeout in seconds.

    Returns:
        Tuple of (jd_text, metadata) if alternate source found,
        or ("", metadata) if all fallbacks fail.
    """
    company = metadata.get("company", "")
    if not company:
        company = _extract_company_from_url(original_url)

    logger.info(
        f"_linkedin_fallback_search | triggered for company={company} | "
        f"partial_text_len={len(partial_text)}"
    )

    # Strategy 1: Try company career site directly
    if company:
        career_url = _search_company_career_site(company, timeout=timeout)
        if career_url:
            logger.info(f"_linkedin_fallback_search | trying career site: {career_url[:100]}")
            alt_text, alt_meta = extract_jd_from_url(career_url, timeout=timeout)
            if alt_text and not _is_incomplete_jd(alt_text):
                alt_meta["alternate_source_url"] = career_url
                alt_meta["linkedin_fallback_used"] = True
                alt_meta["method"] = "linkedin_fallback_career_site"
                logger.info(
                    f"_linkedin_fallback_search | career site success | "
                    f"text_len={len(alt_text)} | source={career_url[:80]}"
                )
                return alt_text, alt_meta

    # Strategy 2: Web search for alternate posting
    if company:
        alt_url = _search_alternate_posting(title="", company=company)
        if alt_url and alt_url.lower() != original_url.lower():
            logger.info(f"_linkedin_fallback_search | trying web search result: {alt_url[:100]}")
            alt_text, alt_meta = extract_jd_from_url(alt_url, timeout=timeout)
            if alt_text and not _is_incomplete_jd(alt_text):
                alt_meta["alternate_source_url"] = alt_url
                alt_meta["linkedin_fallback_used"] = True
                alt_meta["method"] = "linkedin_fallback_web_search"
                logger.info(
                    f"_linkedin_fallback_search | web search success | "
                    f"text_len={len(alt_text)} | source={alt_url[:80]}"
                )
                return alt_text, alt_meta

    logger.warning(f"_linkedin_fallback_search | all fallbacks failed for company={company}")
    return "", metadata


def extract_jd_from_url(url: str, timeout: int = 20) -> tuple[str, dict]:
    """Extract readable JD text from a public job URL.

    Returns:
        Tuple of (text, metadata) where metadata contains:
        - success: bool
        - company: str | None (extracted from URL)
        - selectors_tried: list[str]
        - method: str (workday | selector | fallback | failed)
    """
    # Redirect branded Greenhouse pages to scrapeable job-boards.greenhouse.io
    if "gh_jid=" in url:
        resolved = _resolve_branded_greenhouse_url(url)
        if resolved:
            logger.info("Redirecting branded Greenhouse URL to: %s", resolved)
            return extract_jd_from_url(resolved, timeout=timeout)

    metadata = {
        "success": False,
        "company": _extract_company_from_url(url),
        "selectors_tried": [],
        "method": "failed",
        "alternate_source_url": "",
        "linkedin_fallback_used": False,
    }

    if not url or not url.strip():
        return "", metadata

    logger.info(f"extract_jd_from_url | url={url[:100]}...")

    is_linkedin = "linkedin.com/jobs/view/" in url.lower()

    # LinkedIn URLs: try to resolve to original company posting first
    if is_linkedin:
        resolved_url = _resolve_linkedin_url(url)
        if resolved_url:
            logger.info(f"extract_jd_from_url | LinkedIn resolved to: {resolved_url[:100]}")
            text, alt_meta = extract_jd_from_url(resolved_url, timeout=timeout)
            if text and not _is_incomplete_jd(text):
                alt_meta["alternate_source_url"] = resolved_url
                return text, alt_meta
            logger.info(
                "extract_jd_from_url | LinkedIn resolved URL produced incomplete JD, trying fallback"
            )
        logger.debug("extract_jd_from_url | LinkedIn resolve failed, falling through to scrape")

    # Workday sites require JS rendering
    if "workday" in url.lower() or "myworkdayjobs" in url.lower():
        workday_text = _extract_workday_jd(url)
        if workday_text:
            metadata["success"] = True
            metadata["method"] = "workday"
            return workday_text, metadata
        # Fall through to regular extraction if Workday extraction fails

    # Ashby sites require JS rendering (both native Ashby URLs and embedded Ashby on company sites)
    if "ashbyhq.com" in url.lower() or "ashby_jid=" in url.lower():
        ashby_text = _extract_ashby_jd(url)
        if ashby_text:
            metadata["success"] = True
            metadata["method"] = "ashby"
            return ashby_text, metadata
        # Fall through to regular extraction if Ashby extraction fails

    # Viterbit sites require JS rendering
    if "viterbit.site" in url.lower() or "viterbit.com" in url.lower():
        viterbit_text = _extract_viterbit_jd(url)
        if viterbit_text:
            metadata["success"] = True
            metadata["method"] = "viterbit"
            return viterbit_text, metadata
        # Fall through to regular extraction if Viterbit extraction fails

    try:
        response = requests.get(
            url.strip(),
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        response.raise_for_status()
        logger.info(
            f"extract_jd_from_url | status={response.status_code} | content_length={len(response.text)}"
        )
    except requests.RequestException:
        logger.exception("Failed to fetch JD URL: %s", url)
        metadata["method"] = "request_failed"
        return "", metadata

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove high-noise elements before text extraction.
    for tag in soup.select("script, style, noscript, header, footer, nav, form, svg"):
        tag.decompose()

    candidate_selectors = [
        "[data-testid*=description]",
        "[class*=description]",
        "[id*=description]",
        "[class*=job-description]",
        "[class*=posting]",
        "[class*=content]",
        "div[role='main']",
        "main",
        "article",
        "section",
    ]

    candidates = []
    for selector in candidate_selectors:
        metadata["selectors_tried"].append(selector)
        for node in soup.select(selector):
            text = _clean_extracted_text(node.get_text(" ", strip=True))
            if len(text) >= 180:
                candidates.append(text)

    if candidates:
        # Choose the largest candidate block, usually the full JD section.
        best = max(candidates, key=len)
        metadata["success"] = True
        metadata["method"] = "selector"
        # LinkedIn fallback: if selector result is incomplete, try alternate sources
        if is_linkedin and _is_incomplete_jd(best):
            alt_text, alt_meta = _linkedin_fallback_search(url, best, metadata)
            if alt_text:
                return alt_text, alt_meta
        return best, metadata

    fallback = _clean_extracted_text(soup.get_text(" ", strip=True))
    # If fallback is tiny it is usually a JS-rendered page or blocked/login shell.
    if len(fallback) < 180:
        logger.warning("JD extraction produced too little text for URL: %s", url)

        # Last resort: try Playwright generic extraction for any JS-rendered page
        generic_text = _extract_with_playwright(
            url,
            [
                "main",
                "article",
                "[role='main']",
                "[class*='description']",
                "[class*='content']",
            ],
            platform="generic-fallback",
            wait_ms=4000,
        )
        if generic_text and len(generic_text) >= 180:
            metadata["success"] = True
            metadata["method"] = "playwright_fallback"
            # LinkedIn fallback on Playwright result too
            if is_linkedin and _is_incomplete_jd(generic_text):
                alt_text, alt_meta = _linkedin_fallback_search(url, generic_text, metadata)
                if alt_text:
                    return alt_text, alt_meta
            return generic_text, metadata

        # LinkedIn-specific fallback chain before generic alternate search
        if is_linkedin:
            alt_text, alt_meta = _linkedin_fallback_search(url, "", metadata)
            if alt_text:
                return alt_text, alt_meta

        # Try alternate posting search if we have a company name
        if metadata["company"]:
            alt_url = _search_alternate_posting(
                title="",  # No title yet at extraction stage
                company=metadata["company"],
            )
            if alt_url and alt_url.lower() != url.lower():
                logger.info(f"extract_jd_from_url | trying alternate posting: {alt_url[:100]}")
                return extract_jd_from_url(alt_url, timeout=timeout)
        metadata["method"] = "too_short"
        return "", metadata

    metadata["success"] = True
    metadata["method"] = "fallback"
    # LinkedIn fallback: if full-page fallback is incomplete, try alternate sources
    if is_linkedin and _is_incomplete_jd(fallback):
        alt_text, alt_meta = _linkedin_fallback_search(url, fallback, metadata)
        if alt_text:
            return alt_text, alt_meta
    return fallback, metadata


def prune_jd(raw_text: str) -> str:
    """Strip boilerplate from a pasted JD using Haiku.

    Cost: ~$0.001 per call.
    """
    if not raw_text or len(raw_text.strip()) < 50:
        return raw_text.strip()

    input_length = len(raw_text)
    logger.info(f"prune_jd | input_length={input_length}")

    prompt_template = _load_prompt("jd_pruner")
    prompt = prompt_template.replace("{jd_text}", raw_text)

    pruned = llm.call_haiku(prompt, task="jd_prune")
    output_length = len(pruned)
    logger.info(
        f"prune_jd | output_length={output_length} | reduction={input_length - output_length}"
    )
    return pruned.strip()


def parse_jd(pruned_text: str) -> dict:
    """Parse pruned JD into structured data using Haiku.

    Cost: ~$0.003 per call.
    Returns raw dict from LLM JSON response.
    """
    prompt_template = _load_prompt("jd_parser")
    prompt = prompt_template.replace("{pruned_jd}", pruned_text)

    raw_response = llm.call_haiku(prompt, task="jd_parse")

    # Extract JSON from response (handle markdown code blocks)
    json_str = raw_response.strip()
    if json_str.startswith("```"):
        json_str = re.sub(r"^```(?:json)?\n?", "", json_str)
        json_str = re.sub(r"\n?```$", "", json_str)

    try:
        parsed = json.loads(json_str)
        logger.info(f"parse_jd | JSON parse succeeded | keys={list(parsed.keys())}")
        return parsed
    except json.JSONDecodeError:
        logger.error("parse_jd | JSON parse failed | returning empty dict")
        return {}


def _extract_salary(text: str) -> tuple[Optional[int], Optional[int], str]:
    """Extract salary information from JD text.

    Handles various formats:
    - "$100k-150k", "$100K-$150K"
    - "100000-150000 USD", "100,000 - 150,000"
    - "€80k-€100k", "£60,000-£80,000"
    - "$120,000 - $150,000", "$120K-$150K USD"
    - "100000 - 150000" (no symbol)
    - "Up to $150k", "Starting at $100k"

    Args:
        text: JD text to extract salary from.

    Returns:
        Tuple of (min_salary, max_salary, currency).
        Returns (None, None, "USD") if no salary found.
    """
    if not text:
        return None, None, "USD"

    # If the JD has labeled location blocks (Primary Location / Additional Location),
    # isolate the Primary Location section so we don't accidentally pick up a
    # secondary-market range (e.g. PayPal lists San Jose + Austin separately).
    primary_match = re.search(
        r"primary\s+location\b[^\n]*\n(.*?)(?=additional\s+location|\Z)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if primary_match:
        text = primary_match.group(1)

    # Normalize decimal-cent suffixes before pattern matching:
    # "$242,000.00" → "$242,000", "$359,150.00" → "$359,150"
    text = re.sub(r"(\d),(\d{3})\.\d{2}", r"\1,\2", text)

    # Currency symbol to code mapping
    currency_map = {
        "$": "USD",
        "€": "EUR",
        "£": "GBP",
        "¥": "JPY",
        "₹": "INR",
        "C$": "CAD",
        "A$": "AUD",
    }

    # Patterns to match salary ranges
    patterns = [
        # "$120,000 - $150,000", "£60,000-£80,000" (with comma separators)
        r"([€£¥₹$]|C\$|A\$)\s*(\d{1,3}),(\d{3}),?(\d{3})?\s*[-–—to]+\s*\1?\s*(\d{1,3}),(\d{3}),?(\d{3})?",
        # "$100k-150k", "$100K-$150K", "€80k-€100k"
        r"([€£¥₹$]|C\$|A\$)\s*(\d+)[\.,]?(\d*)\s*k?\s*[-–—to]+\s*\1?\s*(\d+)[\.,]?(\d*)\s*k",
        # "100000-150000 USD", "100,000-150,000 EUR"
        r"(\d{2,3})[\.,]?(\d{3})[\.,]?(\d{3})?\s*[-–—to]+\s*(\d{2,3})[\.,]?(\d{3})[\.,]?(\d{3})?\s*(USD|EUR|GBP|CAD|AUD|JPY|INR)",
        # "100k-150k USD", "80k-100k"
        r"(\d+)[\.,]?(\d*)\s*k\s*[-–—to]+\s*(\d+)[\.,]?(\d*)\s*k\s*(USD|EUR|GBP|CAD|AUD|JPY|INR)?",
        # "100000 - 150000" (no currency symbol, assume USD if 5+ digits)
        r"(?<![€£¥₹$\d])(\d{5,7})\s*[-–—to]+\s*(\d{5,7})(?!\d)",
        # "Up to $150k", "Up to 150000 USD"
        r"(?:up\s+to|maximum|max)\s+(?:of\s+)?([€£¥₹$]|C\$|A\$)?\s*(\d+)[\.,]?(\d*)\s*k?\s*(USD|EUR|GBP|CAD|AUD|JPY|INR)?",
        # "Starting at $100k", "Starting from 100000 USD"
        r"(?:starting\s+(?:at|from)|minimum|min)\s+(?:of\s+)?([€£¥₹$]|C\$|A\$)?\s*(\d+)[\.,]?(\d*)\s*k?\s*(USD|EUR|GBP|CAD|AUD|JPY|INR)?",
    ]

    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            groups = match.groups()

            try:
                # Pattern 1: "$120,000 - $150,000" (comma-separated)
                if len(groups) >= 7 and groups[0] in currency_map and "," in match.group():
                    currency = currency_map.get(groups[0], "USD")
                    # Join all digit groups for min and max, ignoring None values
                    min_parts = [g for g in groups[1:4] if g and g.isdigit()]
                    max_parts = [g for g in groups[4:7] if g and g.isdigit()]

                    if min_parts and max_parts:
                        min_sal = int("".join(min_parts))
                        max_sal = int("".join(max_parts))
                        return min_sal, max_sal, currency

                # Pattern 2: "$100k-150k"
                elif len(groups) >= 5 and groups[0] in currency_map:
                    currency = currency_map.get(groups[0], "USD")
                    # Handle None and empty string
                    min_sal = (
                        int(groups[1]) * 1000
                        if (not groups[2] or groups[2] == "")
                        else int(groups[1] + (groups[2] or ""))
                    )
                    max_sal = (
                        int(groups[3]) * 1000
                        if (not groups[4] or groups[4] == "")
                        else int(groups[3] + (groups[4] or ""))
                    )

                    # Multiply by 1000 if values look like "k" format (< 10000)
                    if min_sal < 10000:
                        min_sal *= 1000
                    if max_sal < 10000:
                        max_sal *= 1000

                    return min_sal, max_sal, currency

                # Pattern 3: "100000-150000 USD"
                elif (
                    len(groups) >= 7
                    and groups[-1]
                    and groups[-1] in ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "INR"]
                ):
                    currency = groups[-1]
                    # Join digits without separators
                    min_parts = [g for g in groups[:3] if g and g.isdigit()]
                    max_parts = [g for g in groups[3:6] if g and g.isdigit()]

                    if min_parts and max_parts:
                        min_sal = int("".join(min_parts))
                        max_sal = int("".join(max_parts))
                        return min_sal, max_sal, currency

                # Pattern 4: "100k-150k" or "100k-150k USD"
                elif len(groups) >= 4:
                    min_sal = int(groups[0]) * 1000
                    max_sal = int(groups[2]) * 1000
                    currency = groups[4] if len(groups) > 4 and groups[4] else "USD"
                    return min_sal, max_sal, currency

                # Pattern 5: "100000 - 150000" (no currency symbol)
                elif len(groups) == 2 and all(g and g.isdigit() and len(g) >= 5 for g in groups):
                    min_sal = int(groups[0])
                    max_sal = int(groups[1])
                    return min_sal, max_sal, "USD"

                # Pattern 6: "Up to $150k" or "Up to 150000 USD"
                elif len(groups) >= 2 and "up" in match.group().lower():
                    currency_symbol = groups[0] if groups[0] in currency_map else None
                    amount_str = groups[1] if groups[1] and groups[1].isdigit() else None

                    if amount_str:
                        amount = int(amount_str)
                        # Check if 'k' format
                        if "k" in match.group().lower() and amount < 10000:
                            amount *= 1000
                        # Determine currency
                        if currency_symbol:
                            currency = currency_map.get(currency_symbol, "USD")
                        elif len(groups) > 3 and groups[3]:
                            currency = groups[3]
                        else:
                            currency = "USD"
                        # "Up to" means max only, no min
                        return None, amount, currency

                # Pattern 7: "Starting at $100k" or "Starting from 100000 USD"
                elif len(groups) >= 2 and (
                    "starting" in match.group().lower() or "minimum" in match.group().lower()
                ):
                    currency_symbol = groups[0] if groups[0] in currency_map else None
                    amount_str = groups[1] if groups[1] and groups[1].isdigit() else None

                    if amount_str:
                        amount = int(amount_str)
                        # Check if 'k' format
                        if "k" in match.group().lower() and amount < 10000:
                            amount *= 1000
                        # Determine currency
                        if currency_symbol:
                            currency = currency_map.get(currency_symbol, "USD")
                        elif len(groups) > 3 and groups[3]:
                            currency = groups[3]
                        else:
                            currency = "USD"
                        # "Starting at" means min only, no max
                        return amount, None, currency

            except (ValueError, IndexError, TypeError) as e:
                # Skip malformed matches
                logger.debug(f"_extract_salary | pattern match failed: {e}")
                continue

    # Log if no salary was extracted
    salary_keywords = [
        "salary",
        "compensation",
        "pay",
        "$",
        "€",
        "£",
        "k",
        "usd",
        "eur",
        "gbp",
    ]
    if any(keyword in text.lower() for keyword in salary_keywords):
        logger.debug(
            f"_extract_salary | salary keywords found but no match | text_sample: {text[:200]}"
        )

    return None, None, "USD"


def _compute_jd_similarity(text1: str, text2: str) -> float:
    """Compute similarity between two JD texts using keyword overlap.

    Fast local similarity (no LLM) based on normalized token overlap.

    Returns:
        Float between 0.0 (no match) and 1.0 (exact match).
    """
    import re

    def normalize_and_tokenize(text: str) -> set[str]:
        """Normalize and extract meaningful tokens."""
        # Lowercase and extract words (alphanumeric + hyphen)
        tokens = re.findall(r"\b[a-z0-9]+(?:-[a-z0-9]+)?\b", text.lower())
        # Filter stopwords
        stopwords = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
        }
        return {t for t in tokens if t not in stopwords and len(t) > 2}

    tokens1 = normalize_and_tokenize(text1)
    tokens2 = normalize_and_tokenize(text2)

    if not tokens1 or not tokens2:
        return 0.0

    # Jaccard similarity
    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)
    return intersection / union if union > 0 else 0.0


def _get_cached_jd(pruned_text: str) -> Optional[dict]:
    """Get exact-match cached JD parse result.

    Args:
        pruned_text: Pruned JD text.

    Returns:
        Cached parsed_data dict if exists, otherwise None.
    """
    import hashlib
    from jseeker.tracker import tracker_db

    text_hash = hashlib.sha256(pruned_text.encode()).hexdigest()

    conn = tracker_db._conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT parsed_json FROM jd_cache
        WHERE pruned_text_hash = ?
    """,
        (text_hash,),
    )
    row = c.fetchone()

    if row:
        # Update hit count and last_used
        c.execute(
            """
            UPDATE jd_cache
            SET hit_count = hit_count + 1, last_used_at = CURRENT_TIMESTAMP
            WHERE pruned_text_hash = ?
        """,
            (text_hash,),
        )
        conn.commit()
        conn.close()
        logger.info(f"_get_cached_jd | cache HIT | hash={text_hash[:16]}...")
        return json.loads(row["parsed_json"])

    conn.close()
    logger.info(f"_get_cached_jd | cache MISS | hash={text_hash[:16]}...")
    return None


def _cache_jd(pruned_text: str, parsed_data: dict) -> None:
    """Store parsed JD in cache for future reuse.

    Args:
        pruned_text: Pruned JD text.
        parsed_data: Parsed JD dict from LLM.
    """
    import hashlib
    from jseeker.tracker import tracker_db

    text_hash = hashlib.sha256(pruned_text.encode()).hexdigest()

    conn = tracker_db._conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO jd_cache
        (pruned_text_hash, parsed_json, title, company, ats_keywords)
        VALUES (?, ?, ?, ?, ?)
    """,
        (
            text_hash,
            json.dumps(parsed_data),
            parsed_data.get("title", ""),
            parsed_data.get("company", ""),
            json.dumps(parsed_data.get("ats_keywords", [])),
        ),
    )
    conn.commit()
    conn.close()


def process_jd(raw_text: str, jd_url: str = "", use_semantic_cache: bool = True) -> ParsedJD:
    """Full JD processing pipeline: paste → prune → parse → ParsedJD.

    Args:
        raw_text: Raw pasted JD text.
        jd_url: Optional job URL for ATS detection.
        use_semantic_cache: Check for similar JDs before parsing (default: True).

    Returns:
        Fully structured ParsedJD.
    """
    # Step 1: Prune boilerplate
    pruned = prune_jd(raw_text)

    # Step 1.5: Check exact-match cache (saves ~$0.003 + 1-2s per hit)
    cached_parsed_data = None
    if use_semantic_cache:
        cached_parsed_data = _get_cached_jd(pruned)

    # Step 2: Detect language
    detected_language = detect_language(pruned)
    logger.info(f"process_jd | detected_language={detected_language}")

    # Step 3: Parse into structured data (or use cache)
    if cached_parsed_data:
        parsed_data = cached_parsed_data
        logger.info("process_jd | using cached parsed data")
    else:
        parsed_data = parse_jd(pruned)
        # Cache the result for future use
        if use_semantic_cache:
            _cache_jd(pruned, parsed_data)

    logger.info(
        f"process_jd | title={parsed_data.get('title', 'N/A')} | "
        f"company={parsed_data.get('company', 'N/A')} | "
        f"keywords_count={len(parsed_data.get('ats_keywords', []))} | "
        f"language={detected_language}"
    )

    # Step 4: Build requirements list
    requirements = []
    for req in parsed_data.get("hard_requirements", []):
        requirements.append(
            JDRequirement(
                text=req.get("text", ""),
                category="hard_skill",
                priority="required",
                keywords=req.get("keywords", []),
            )
        )
    for req in parsed_data.get("soft_requirements", []):
        requirements.append(
            JDRequirement(
                text=req.get("text", ""),
                category="soft_skill",
                priority="preferred",
                keywords=req.get("keywords", []),
            )
        )

    # Step 5: Detect ATS platform
    ats_platform = detect_ats_platform(jd_url)

    # Step 6: Extract structured salary data from raw and pruned text
    salary_min, salary_max, salary_currency = _extract_salary(raw_text + " " + pruned)
    logger.info(
        f"process_jd | salary_extraction | min={salary_min} | max={salary_max} | currency={salary_currency}"
    )

    # Step 7: Company name fallback chain (LLM → Regex → URL → Manual)
    company_name = sanitize_company_name(parsed_data.get("company", ""))

    # If sanitization emptied the name, trigger fallback chain
    if not company_name:
        logger.info(
            f"process_jd | LLM company extraction failed or returned invalid '{parsed_data.get('company', '')}', trying fallback chain"
        )

        # Try regex fallback on text
        raw_fallback = sanitize_company_name(_extract_company_fallback(raw_text))
        pruned_fallback = sanitize_company_name(_extract_company_fallback(pruned))
        company_name = raw_fallback or pruned_fallback
        if company_name:
            logger.info(f"process_jd | company extracted from text: {company_name}")

        # Try URL fallback if text extraction failed
        if not company_name and jd_url:
            company_name = sanitize_company_name(_extract_company_from_url(jd_url))
            if company_name:
                logger.info(f"process_jd | company extracted from URL: {company_name}")

        # If all fail, leave empty (manual entry in UI)
        if not company_name:
            logger.warning("process_jd | all company extraction strategies failed")
            company_name = ""

    # Step 8: Detect market and override language from location
    jd_location = parsed_data.get("location", "")
    detected_market = detect_market_from_location(jd_location)
    location_language = detect_language_from_location(jd_location)

    # Override language if location implies a non-English market
    # (handles English JDs posted for Mexico/Spain/France jobs)
    if location_language != "en" and detected_language == "en":
        logger.info(
            f"process_jd | language override: text={detected_language} -> "
            f"location={location_language} (market={detected_market}, location='{jd_location}')"
        )
        detected_language = location_language

    logger.info(f"process_jd | final: language={detected_language} market={detected_market}")

    return ParsedJD(
        raw_text=raw_text,
        pruned_text=pruned,
        title=parsed_data.get("title", ""),
        company=company_name,
        seniority=parsed_data.get("seniority", ""),
        location=jd_location,
        remote_policy=parsed_data.get("remote_policy", ""),
        salary_range=parsed_data.get("salary_range", ""),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
        role_exp=parsed_data.get("role_exp", ""),
        management_exp=parsed_data.get("management_exp", ""),
        requirements=requirements,
        ats_keywords=parsed_data.get("ats_keywords", []),
        culture_signals=parsed_data.get("culture_signals", []),
        detected_ats=ats_platform,
        jd_url=jd_url,
        language=detected_language,
        market=detected_market,
    )
