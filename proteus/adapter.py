"""PROTEUS Adapter — Claude-powered content adaptation."""

from __future__ import annotations

import json
import re
from pathlib import Path

from proteus.block_manager import block_manager
from proteus.llm import llm
from proteus.models import AdaptedResume, MatchResult, ParsedJD, TemplateType


def _load_prompt(name: str) -> str:
    from config import settings
    path = settings.prompts_dir / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def _load_preferences() -> str:
    """Load user editing preferences if they exist."""
    from config import settings
    prefs_path = settings.data_dir / "preferences.json"
    if prefs_path.exists():
        data = json.loads(prefs_path.read_text(encoding="utf-8"))
        rules = data.get("rules", [])
        if rules:
            return "\n".join(f"- {r}" for r in rules)
    return "No preferences recorded yet."


def adapt_summary(
    template: TemplateType,
    parsed_jd: ParsedJD,
) -> str:
    """Rewrite the summary to match the JD.

    Cost: ~$0.011 per call (Sonnet).
    """
    original = block_manager.get_summary(template)
    prompt_template = _load_prompt("summary_writer")

    req_text = "\n".join(
        f"- {r.text}" for r in parsed_jd.requirements[:10]
    )

    prompt = (
        prompt_template
        .replace("{original_summary}", original)
        .replace("{job_title}", parsed_jd.title)
        .replace("{ats_keywords}", ", ".join(parsed_jd.ats_keywords[:15]))
        .replace("{requirements}", req_text)
        .replace("{preferences}", _load_preferences())
    )

    return llm.call_sonnet(prompt, task="summary_adapt").strip()


def adapt_bullets(
    experience_block: dict,
    template: TemplateType,
    parsed_jd: ParsedJD,
) -> list[str]:
    """Adapt experience bullets for a single block.

    Cost: ~$0.007 per block (Sonnet, batched).
    """
    company = experience_block.get("company", "")
    role = experience_block.get("role", "")
    original_bullets = experience_block.get("bullets", [])

    prompt_template = _load_prompt("bullet_adapter")

    req_text = "\n".join(
        f"- {r.text}" for r in parsed_jd.requirements[:10]
    )

    prompt = (
        prompt_template
        .replace("{original_bullets}", "\n".join(f"- {b}" for b in original_bullets))
        .replace("{company}", company)
        .replace("{role}", role)
        .replace("{ats_keywords}", ", ".join(parsed_jd.ats_keywords[:15]))
        .replace("{requirements}", req_text)
        .replace("{preferences}", _load_preferences())
    )

    raw = llm.call_sonnet(prompt, task="bullet_adapt")

    # Parse JSON array
    json_str = raw.strip()
    if json_str.startswith("```"):
        json_str = re.sub(r"^```(?:json)?\n?", "", json_str)
        json_str = re.sub(r"\n?```$", "", json_str)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Fallback: return originals
        return original_bullets


def adapt_resume(
    match_result: MatchResult,
    parsed_jd: ParsedJD,
) -> AdaptedResume:
    """Full adaptation pipeline: summary + bullets + skills reorder.

    Total cost: ~$0.046 per resume (Sonnet).
    """
    template = match_result.template_type
    corpus = block_manager.load_corpus()

    # 1. Adapt summary
    adapted_summary = adapt_summary(template, parsed_jd)

    # 2. Get and adapt experience blocks
    experience_blocks = block_manager.get_experience_for_template(template)
    adapted_experiences = []

    for exp in experience_blocks:
        bullets = block_manager.get_bullets(exp, template)
        adapted_bullets = adapt_bullets(
            {"company": exp.company, "role": exp.role, "bullets": bullets},
            template,
            parsed_jd,
        )
        adapted_experiences.append({
            "company": exp.company,
            "role": exp.role,
            "start": exp.start,
            "end": exp.end,
            "location": exp.location,
            "bullets": adapted_bullets,
        })

    # 3. Reorder skills to prioritize JD matches
    matched_skills = block_manager.get_skills_matching_keywords(
        parsed_jd.ats_keywords
    )
    skills_ordered = []
    # First: categories with matches
    for cat_name, skill_names in matched_skills.items():
        skills_ordered.append({
            "category": cat_name,
            "skills": skill_names,
            "matched": True,
        })
    # Then: categories without matches
    for cat_key, category in corpus.skills.items():
        if category.display_name not in matched_skills:
            skills_ordered.append({
                "category": category.display_name,
                "skills": [item.name for item in category.items],
                "matched": False,
            })

    return AdaptedResume(
        summary=adapted_summary,
        experience_blocks=adapted_experiences,
        skills_ordered=skills_ordered,
        contact=corpus.contact,
        education=corpus.education,
        certifications=corpus.certifications,
        awards=corpus.awards,
        early_career=corpus.early_career,
        target_title=parsed_jd.title or "Director",
        template_used=template,
    )
