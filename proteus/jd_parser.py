"""PROTEUS JD Parser — Paste + auto-prune → ParsedJD."""

from __future__ import annotations

import json
import re
from pathlib import Path

from proteus.llm import llm
from proteus.models import ATSPlatform, JDRequirement, ParsedJD

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


def detect_ats_platform(url: str) -> ATSPlatform:
    """Detect ATS platform from a job URL."""
    if not url:
        return ATSPlatform.UNKNOWN
    url_lower = url.lower()
    for pattern, platform in ATS_DETECTION.items():
        if pattern in url_lower:
            return platform
    return ATSPlatform.UNKNOWN


def prune_jd(raw_text: str) -> str:
    """Strip boilerplate from a pasted JD using Haiku.

    Cost: ~$0.001 per call.
    """
    if not raw_text or len(raw_text.strip()) < 50:
        return raw_text.strip()

    prompt_template = _load_prompt("jd_pruner")
    prompt = prompt_template.replace("{jd_text}", raw_text)

    pruned = llm.call_haiku(prompt, task="jd_prune")
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
        return json.loads(json_str)
    except json.JSONDecodeError:
        return {}


def process_jd(raw_text: str, jd_url: str = "") -> ParsedJD:
    """Full JD processing pipeline: paste → prune → parse → ParsedJD.

    Args:
        raw_text: Raw pasted JD text.
        jd_url: Optional job URL for ATS detection.

    Returns:
        Fully structured ParsedJD.
    """
    # Step 1: Prune boilerplate
    pruned = prune_jd(raw_text)

    # Step 2: Parse into structured data
    parsed_data = parse_jd(pruned)

    # Step 3: Build requirements list
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

    # Step 4: Detect ATS platform
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
    )
