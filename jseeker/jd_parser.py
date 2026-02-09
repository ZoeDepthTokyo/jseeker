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


def extract_jd_from_url(url: str, timeout: int = 20) -> str:
    """Extract readable JD text from a public job URL.

    Returns empty string when extraction fails so callers can fall back to paste mode.
    """
    if not url or not url.strip():
        return ""

    logger.info(f"extract_jd_from_url | url={url[:100]}...")

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
        return ""

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
        for node in soup.select(selector):
            text = _clean_extracted_text(node.get_text(" ", strip=True))
            if len(text) >= 180:
                candidates.append(text)

    if candidates:
        # Choose the largest candidate block, usually the full JD section.
        best = max(candidates, key=len)
        return best

    fallback = _clean_extracted_text(soup.get_text(" ", strip=True))
    # If fallback is tiny it is usually a blocked page/login shell, treat as failure.
    if len(fallback) < 180:
        logger.warning("JD extraction produced too little text for URL: %s", url)
        return ""
    return fallback


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

    return ParsedJD(
        raw_text=raw_text,
        pruned_text=pruned,
        title=parsed_data.get("title", ""),
        company=parsed_data.get("company", ""),
        seniority=parsed_data.get("seniority", ""),
        location=parsed_data.get("location", ""),
        remote_policy=parsed_data.get("remote_policy", ""),
        salary_range=parsed_data.get("salary_range", ""),
        requirements=requirements,
        ats_keywords=parsed_data.get("ats_keywords", []),
        culture_signals=parsed_data.get("culture_signals", []),
        detected_ats=ats_platform,
        jd_url=jd_url,
        language=detected_language,
    )
