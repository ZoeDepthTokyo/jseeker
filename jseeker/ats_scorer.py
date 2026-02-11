"""jSeeker ATS Scorer — Platform-aware ATS compliance scoring."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from jseeker.llm import llm
from jseeker.models import ATSPlatform, ATSScore, AdaptedResume, ParsedJD


def _load_prompt(name: str) -> str:
    from config import settings
    path = settings.prompts_dir / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def _load_ats_profile(platform: ATSPlatform) -> dict:
    """Load ATS profile rules for a platform."""
    from config import settings
    profile_path = settings.ats_profiles_dir / f"{platform.value}.yaml"
    if not profile_path.exists():
        return {}
    with open(profile_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _resume_to_text(adapted: AdaptedResume) -> str:
    """Convert adapted resume to plain text for scoring."""
    lines = []

    # Contact
    lines.append(f"{adapted.contact.full_name}")
    lines.append(f"{adapted.contact.email} | {adapted.contact.phone}")
    lines.append(f"{adapted.contact.website} | {adapted.contact.linkedin}")
    lines.append("")

    # Summary
    lines.append("SUMMARY")
    lines.append(adapted.summary)
    lines.append("")

    # Experience
    lines.append("EXPERIENCE")
    for exp in adapted.experience_blocks:
        end = exp.get("end") or "Present"
        lines.append(f"{exp['role']} — {exp['company']} ({exp['start']} – {end})")
        for bullet in exp.get("bullets", []):
            lines.append(f"  - {bullet}")
        lines.append("")

    # Skills
    lines.append("SKILLS")
    for skill_group in adapted.skills_ordered:
        skills_str = ", ".join(skill_group.get("skills", []))
        lines.append(f"{skill_group['category']}: {skills_str}")
    lines.append("")

    # Education
    lines.append("EDUCATION")
    for edu in adapted.education:
        degree = edu.degree or ""
        lines.append(f"{degree} {edu.field} — {edu.institution} ({edu.start}–{edu.end})")
    lines.append("")

    # Awards
    lines.append("AWARDS")
    for award in adapted.awards:
        lines.append(f"  - {award.name}")

    return "\n".join(lines)


def local_format_score(adapted: AdaptedResume, platform: ATSPlatform) -> dict:
    """Quick local format compliance check (no LLM).

    Returns dict of scores and warnings.
    """
    profile = _load_ats_profile(platform)
    rules = profile.get("scoring_rules", {})
    fmt = rules.get("format_requirements", {})
    penalties = rules.get("penalties", {})

    score = 100
    warnings = []

    # Check section presence
    has_summary = bool(adapted.summary)
    has_experience = bool(adapted.experience_blocks)
    has_skills = bool(adapted.skills_ordered)
    has_education = bool(adapted.education)

    if not has_summary:
        score += penalties.get("missing_summary", -5)
        warnings.append("Missing summary section")
    if not has_skills:
        score += penalties.get("missing_skills", -15)
        warnings.append("Missing skills section")

    # Check bullet structure (action verb + metric)
    metric_pattern = re.compile(r"\d+[%MKB+]|\$\d+|\d+\+?\s*(years|projects|people|vehicles)")
    total_bullets = 0
    quantified_bullets = 0
    for exp in adapted.experience_blocks:
        for bullet in exp.get("bullets", []):
            total_bullets += 1
            if metric_pattern.search(bullet):
                quantified_bullets += 1

    if total_bullets > 0 and quantified_bullets / total_bullets < 0.5:
        score += penalties.get("no_quantified_metrics", -10)
        warnings.append("Less than 50% of bullets have quantified metrics")

    section_presence = sum([has_summary, has_experience, has_skills, has_education]) / 4.0

    return {
        "format_score": max(0, min(100, score)),
        "section_presence": section_presence,
        "warnings": warnings,
    }


def score_resume(
    adapted: AdaptedResume,
    parsed_jd: ParsedJD,
    platform: ATSPlatform = ATSPlatform.UNKNOWN,
) -> ATSScore:
    """Full ATS scoring: local checks + LLM evaluation.

    Cost: ~$0.004 (Haiku).
    """
    if platform == ATSPlatform.UNKNOWN:
        platform = parsed_jd.detected_ats

    # Local format check
    local_result = local_format_score(adapted, platform)

    # Build resume text for LLM scoring
    resume_text = _resume_to_text(adapted)

    # Load ATS profile rules
    profile = _load_ats_profile(platform)
    platform_rules = json.dumps(profile.get("scoring_rules", {}), indent=2)

    # LLM-based scoring
    prompt_template = _load_prompt("ats_scorer")
    prompt = (
        prompt_template
        .replace("{ats_platform}", platform.value)
        .replace("{platform_rules}", platform_rules)
        .replace("{ats_keywords}", ", ".join(parsed_jd.ats_keywords))
        .replace("{resume_content}", resume_text)
    )

    raw = llm.call_haiku(prompt, task="ats_score")

    # Parse response
    json_str = raw.strip()
    if json_str.startswith("```"):
        json_str = re.sub(r"^```(?:json)?\n?", "", json_str)
        json_str = re.sub(r"\n?```$", "", json_str)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        data = {}

    # Merge local and LLM results
    all_warnings = local_result["warnings"] + data.get("warnings", [])

    # Recommend format based on platform
    rec = recommend_format(platform)

    return ATSScore(
        overall_score=data.get("overall_score", local_result["format_score"]),
        keyword_match_rate=data.get("keyword_match_rate", 0.0),
        format_compliance=data.get("format_compliance", local_result["format_score"] / 100),
        section_presence=data.get("section_presence", local_result["section_presence"]),
        bullet_structure=data.get("bullet_structure", 0.0),
        matched_keywords=data.get("matched_keywords", []),
        missing_keywords=data.get("missing_keywords", []),
        warnings=list(set(all_warnings)),
        platform=platform,
        recommended_format=rec["primary"],
        format_reason=rec["reason"],
    )


def recommend_format(ats_platform: ATSPlatform) -> dict:
    """Recommend PDF vs DOCX based on ATS platform."""
    if ats_platform in (ATSPlatform.WORKDAY, ATSPlatform.ICIMS, ATSPlatform.TALEO):
        return {"primary": "docx", "reason": "This ATS parses DOCX single-column best"}
    elif ats_platform in (ATSPlatform.GREENHOUSE, ATSPlatform.LEVER, ATSPlatform.ASHBY):
        return {"primary": "pdf", "reason": "Modern ATS handles PDF two-column well"}
    else:
        return {"primary": "both", "reason": "Unknown ATS — submit DOCX for safety"}


def explain_ats_score(
    jd_title: str,
    original_score: int,
    improved_score: int,
    matched_keywords: list[str],
    missing_keywords: list[str],
) -> str:
    """Generate natural language explanation of ATS score improvement.

    Args:
        jd_title: Job title from JD.
        original_score: Score before adaptation (0-100).
        improved_score: Score after adaptation (0-100).
        matched_keywords: Keywords successfully matched.
        missing_keywords: Keywords still missing.

    Returns:
        2-3 sentence plain text explanation.
    """
    prompt = f"""You are an ATS expert explaining resume scores to a job seeker.

Job Title: {jd_title}
Original ATS Score: {original_score}/100
Improved Score: {improved_score}/100
Matched Keywords: {', '.join(matched_keywords[:10])}
Missing Keywords: {', '.join(missing_keywords[:10])}

Write a 2-3 sentence explanation covering:
1. Why the original score was low (or good if 70+)
2. What improved and how (keyword matching, structure, etc.)
3. What could still be improved if applicable

Be encouraging and specific. Focus on actionable insights."""

    explanation = llm.call_haiku(prompt, task="ats_explanation")
    return explanation.strip()
