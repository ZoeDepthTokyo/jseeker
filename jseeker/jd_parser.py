"""jSeeker JD Parser — Paste + auto-prune → ParsedJD."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
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


def _load_prompt(name: str) -> str:
    """Load a prompt template from data/prompts/."""
    from config import settings
    path = settings.prompts_dir / f"{name}.txt"
    return path.read_text(encoding="utf-8")


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
        "de", "en", "para", "con", "los", "las", "del", "una", "por", "que",
        "como", "sobre", "experiencia", "responsabilidades", "requisitos",
        "empresa", "puesto", "trabajo", "años", "área", "desarrollo",
    ]

    # Common English words
    english_words = [
        "the", "and", "for", "with", "our", "you", "this", "that", "from",
        "have", "will", "are", "your", "requirements", "responsibilities",
        "experience", "position", "company", "years", "team", "work",
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


def _extract_workday_jd(url: str) -> str:
    """Extract JD from Workday pages using Playwright for JS rendering.

    Workday job sites are JavaScript-rendered single-page apps that don't
    work with simple requests.get(). This function uses Playwright to render
    the page and extract the job description content.

    Args:
        url: Workday job URL (e.g., myworkdayjobs.com).

    Returns:
        Extracted JD text, or empty string if extraction fails.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("_extract_workday_jd | Playwright not installed, cannot extract Workday JDs")
        return ""

    try:
        logger.info(f"_extract_workday_jd | launching browser for url={url[:100]}...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=15000)

            # Wait for Workday job description to render
            # Workday uses data-automation-id="jobPostingDescription" for the main JD content
            try:
                page.wait_for_selector('[data-automation-id="jobPostingDescription"]', timeout=10000)
                desc_el = page.query_selector('[data-automation-id="jobPostingDescription"]')
                text = desc_el.inner_text() if desc_el else ""
            except Exception as selector_error:
                # Fallback: try alternative selectors
                logger.warning(f"_extract_workday_jd | primary selector failed, trying fallbacks: {selector_error}")
                desc_el = page.query_selector('.css-cygeeu') or page.query_selector('[class*="jobDescription"]')
                text = desc_el.inner_text() if desc_el else ""

            browser.close()
            logger.info(f"_extract_workday_jd | extracted {len(text)} chars from Workday")
            return text.strip()
    except Exception as e:
        logger.warning(f"_extract_workday_jd | failed: {e}")
        return ""


def _extract_company_from_url(url: str) -> str | None:
    """Extract company name from URL patterns (Lever, Greenhouse, Workday).

    Args:
        url: Job posting URL

    Returns:
        Company name if detected, else None
    """
    if not url:
        return None

    # Lever: jobs.lever.co/company-name/
    lever_match = re.search(r"jobs\.lever\.co/([^/]+)", url)
    if lever_match:
        return lever_match.group(1).replace("-", " ").title()

    # Greenhouse: boards.greenhouse.io/company-name/
    greenhouse_match = re.search(r"boards\.greenhouse\.io/([^/]+)", url)
    if greenhouse_match:
        return greenhouse_match.group(1).replace("-", " ").title()

    # Workday: company.wd5.myworkdayjobs.com/ or company.myworkdayjobs.com/
    workday_match = re.search(r"([a-zA-Z0-9_-]+)(?:\.wd\d+)?\.myworkdayjobs\.com", url)
    if workday_match:
        return workday_match.group(1).replace("-", " ").title()

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
        r'(?:Company|Organization|Employer)(?:\s*name)?[\s:]+([A-Z][A-Za-z0-9\s&.,\'-]+?)(?:\n|$|\.(?:\s|$))',
        text,
        re.IGNORECASE | re.MULTILINE
    )
    if company_label_match:
        company = company_label_match.group(1).strip()
        # Filter out common false positives
        if len(company) > 3 and not company.lower().startswith(("about", "overview", "description")):
            return company

    # Pattern 2: "About [Company]" at start of section
    about_match = re.search(
        r'About\s+([A-Z][A-Za-z0-9\s&.,\'-]{2,40}?)(?:\n|$|:)',
        text,
        re.MULTILINE
    )
    if about_match:
        company = about_match.group(1).strip()
        # Filter out generic phrases
        if not any(word in company.lower() for word in ["the role", "this position", "the job", "us", "the company"]):
            return company

    # Pattern 3: "Join [Company]" or "Work at [Company]"
    join_match = re.search(
        r'(?:Join|Work at|Apply to)\s+(?:the\s+team\s+at\s+)?([A-Z][A-Za-z0-9\s&.,\'-]{2,40}?)(?:\n|$|\.|!)',
        text,
        re.MULTILINE
    )
    if join_match:
        company = join_match.group(1).strip()
        if len(company) > 3:
            return company

    # Pattern 4: First capitalized name after "We are" at document start
    we_are_match = re.search(
        r'(?:^|^\n)([A-Z][A-Za-z0-9\s&.,\'-]{2,40}?)\s+(?:is|are)\s+(?:hiring|looking|seeking)',
        text[:500],  # Only check first 500 chars
        re.MULTILINE
    )
    if we_are_match:
        company = we_are_match.group(1).strip()
        if len(company) > 3:
            return company

    return None


def extract_jd_from_url(url: str, timeout: int = 20) -> tuple[str, dict]:
    """Extract readable JD text from a public job URL.

    Returns:
        Tuple of (text, metadata) where metadata contains:
        - success: bool
        - company: str | None (extracted from URL)
        - selectors_tried: list[str]
        - method: str (workday | selector | fallback | failed)
    """
    metadata = {
        "success": False,
        "company": _extract_company_from_url(url),
        "selectors_tried": [],
        "method": "failed"
    }

    if not url or not url.strip():
        return "", metadata

    logger.info(f"extract_jd_from_url | url={url[:100]}...")

    # Workday sites require JS rendering
    if "workday" in url.lower() or "myworkdayjobs" in url.lower():
        workday_text = _extract_workday_jd(url)
        if workday_text:
            metadata["success"] = True
            metadata["method"] = "workday"
            return workday_text, metadata
        # Fall through to regular extraction if Workday extraction fails

    try:
        response = requests.get(
            url.strip(),
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        )
        response.raise_for_status()
        logger.info(f"extract_jd_from_url | status={response.status_code} | content_length={len(response.text)}")
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
        return best, metadata

    fallback = _clean_extracted_text(soup.get_text(" ", strip=True))
    # If fallback is tiny it is usually a blocked page/login shell, treat as failure.
    if len(fallback) < 180:
        logger.warning("JD extraction produced too little text for URL: %s", url)
        metadata["method"] = "too_short"
        return "", metadata

    metadata["success"] = True
    metadata["method"] = "fallback"
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
    logger.info(f"prune_jd | output_length={output_length} | reduction={input_length - output_length}")
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
        r'([€£¥₹$]|C\$|A\$)\s*(\d{1,3}),(\d{3}),?(\d{3})?\s*[-–—to]+\s*\1?\s*(\d{1,3}),(\d{3}),?(\d{3})?',
        # "$100k-150k", "$100K-$150K", "€80k-€100k"
        r'([€£¥₹$]|C\$|A\$)\s*(\d+)[\.,]?(\d*)\s*k?\s*[-–—to]+\s*\1?\s*(\d+)[\.,]?(\d*)\s*k',
        # "100000-150000 USD", "100,000-150,000 EUR"
        r'(\d{2,3})[\.,]?(\d{3})[\.,]?(\d{3})?\s*[-–—to]+\s*(\d{2,3})[\.,]?(\d{3})[\.,]?(\d{3})?\s*(USD|EUR|GBP|CAD|AUD|JPY|INR)',
        # "100k-150k USD", "80k-100k"
        r'(\d+)[\.,]?(\d*)\s*k\s*[-–—to]+\s*(\d+)[\.,]?(\d*)\s*k\s*(USD|EUR|GBP|CAD|AUD|JPY|INR)?',
        # "100000 - 150000" (no currency symbol, assume USD if 5+ digits)
        r'(?<![€£¥₹$\d])(\d{5,7})\s*[-–—to]+\s*(\d{5,7})(?!\d)',
        # "Up to $150k", "Up to 150000 USD"
        r'(?:up\s+to|maximum|max)\s+(?:of\s+)?([€£¥₹$]|C\$|A\$)?\s*(\d+)[\.,]?(\d*)\s*k?\s*(USD|EUR|GBP|CAD|AUD|JPY|INR)?',
        # "Starting at $100k", "Starting from 100000 USD"
        r'(?:starting\s+(?:at|from)|minimum|min)\s+(?:of\s+)?([€£¥₹$]|C\$|A\$)?\s*(\d+)[\.,]?(\d*)\s*k?\s*(USD|EUR|GBP|CAD|AUD|JPY|INR)?',
    ]

    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            groups = match.groups()

            try:
                # Pattern 1: "$120,000 - $150,000" (comma-separated)
                if len(groups) >= 7 and groups[0] in currency_map and ',' in match.group():
                    currency = currency_map.get(groups[0], "USD")
                    # Join all digit groups for min and max, ignoring None values
                    min_parts = [g for g in groups[1:4] if g and g.isdigit()]
                    max_parts = [g for g in groups[4:7] if g and g.isdigit()]

                    if min_parts and max_parts:
                        min_sal = int(''.join(min_parts))
                        max_sal = int(''.join(max_parts))
                        return min_sal, max_sal, currency

                # Pattern 2: "$100k-150k"
                elif len(groups) >= 5 and groups[0] in currency_map:
                    currency = currency_map.get(groups[0], "USD")
                    # Handle None and empty string
                    min_sal = int(groups[1]) * 1000 if (not groups[2] or groups[2] == '') else int(groups[1] + (groups[2] or ''))
                    max_sal = int(groups[3]) * 1000 if (not groups[4] or groups[4] == '') else int(groups[3] + (groups[4] or ''))

                    # Multiply by 1000 if values look like "k" format (< 10000)
                    if min_sal < 10000:
                        min_sal *= 1000
                    if max_sal < 10000:
                        max_sal *= 1000

                    return min_sal, max_sal, currency

                # Pattern 3: "100000-150000 USD"
                elif len(groups) >= 7 and groups[-1] and groups[-1] in ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "INR"]:
                    currency = groups[-1]
                    # Join digits without separators
                    min_parts = [g for g in groups[:3] if g and g.isdigit()]
                    max_parts = [g for g in groups[3:6] if g and g.isdigit()]

                    if min_parts and max_parts:
                        min_sal = int(''.join(min_parts))
                        max_sal = int(''.join(max_parts))
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
                elif len(groups) >= 2 and 'up' in match.group().lower():
                    currency_symbol = groups[0] if groups[0] in currency_map else None
                    amount_str = groups[1] if groups[1] and groups[1].isdigit() else None

                    if amount_str:
                        amount = int(amount_str)
                        # Check if 'k' format
                        if 'k' in match.group().lower() and amount < 10000:
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
                elif len(groups) >= 2 and ('starting' in match.group().lower() or 'minimum' in match.group().lower()):
                    currency_symbol = groups[0] if groups[0] in currency_map else None
                    amount_str = groups[1] if groups[1] and groups[1].isdigit() else None

                    if amount_str:
                        amount = int(amount_str)
                        # Check if 'k' format
                        if 'k' in match.group().lower() and amount < 10000:
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
    salary_keywords = ["salary", "compensation", "pay", "$", "€", "£", "k", "usd", "eur", "gbp"]
    if any(keyword in text.lower() for keyword in salary_keywords):
        logger.debug(f"_extract_salary | salary keywords found but no match | text_sample: {text[:200]}")

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
        tokens = re.findall(r'\b[a-z0-9]+(?:-[a-z0-9]+)?\b', text.lower())
        # Filter stopwords
        stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"}
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
    c.execute("""
        SELECT parsed_json FROM jd_cache
        WHERE pruned_text_hash = ?
    """, (text_hash,))
    row = c.fetchone()

    if row:
        # Update hit count and last_used
        c.execute("""
            UPDATE jd_cache
            SET hit_count = hit_count + 1, last_used_at = CURRENT_TIMESTAMP
            WHERE pruned_text_hash = ?
        """, (text_hash,))
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
    c.execute("""
        INSERT OR REPLACE INTO jd_cache
        (pruned_text_hash, parsed_json, title, company, ats_keywords)
        VALUES (?, ?, ?, ?, ?)
    """, (
        text_hash,
        json.dumps(parsed_data),
        parsed_data.get("title", ""),
        parsed_data.get("company", ""),
        json.dumps(parsed_data.get("ats_keywords", [])),
    ))
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
        requirements.append(JDRequirement(
            text=req.get("text", ""),
            category="hard_skill",
            priority="required",
            keywords=req.get("keywords", []),
        ))
    for req in parsed_data.get("soft_requirements", []):
        requirements.append(JDRequirement(
            text=req.get("text", ""),
            category="soft_skill",
            priority="preferred",
            keywords=req.get("keywords", []),
        ))

    # Step 5: Detect ATS platform
    ats_platform = detect_ats_platform(jd_url)

    # Step 6: Extract structured salary data from raw and pruned text
    salary_min, salary_max, salary_currency = _extract_salary(raw_text + " " + pruned)
    logger.info(
        f"process_jd | salary_extraction | min={salary_min} | max={salary_max} | currency={salary_currency}"
    )

    # Step 7: Company name fallback chain (LLM → Regex → URL → Manual)
    company_name = parsed_data.get("company", "")
    if not company_name or company_name.strip() == "":
        logger.info("process_jd | LLM company extraction failed, trying fallback chain")

        # Try regex fallback on text
        company_name = _extract_company_fallback(raw_text) or _extract_company_fallback(pruned)
        if company_name:
            logger.info(f"process_jd | company extracted from text: {company_name}")

        # Try URL fallback if text extraction failed
        if not company_name and jd_url:
            company_name = _extract_company_from_url(jd_url)
            if company_name:
                logger.info(f"process_jd | company extracted from URL: {company_name}")

        # If all fail, leave empty (manual entry in UI)
        if not company_name:
            logger.warning("process_jd | all company extraction strategies failed")
            company_name = ""

    return ParsedJD(
        raw_text=raw_text,
        pruned_text=pruned,
        title=parsed_data.get("title", ""),
        company=company_name,
        seniority=parsed_data.get("seniority", ""),
        location=parsed_data.get("location", ""),
        remote_policy=parsed_data.get("remote_policy", ""),
        salary_range=parsed_data.get("salary_range", ""),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
        requirements=requirements,
        ats_keywords=parsed_data.get("ats_keywords", []),
        culture_signals=parsed_data.get("culture_signals", []),
        detected_ats=ats_platform,
        jd_url=jd_url,
        language=detected_language,
    )
