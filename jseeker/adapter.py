"""jSeeker Adapter — Claude-powered content adaptation."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from jseeker.block_manager import block_manager
from jseeker.llm import llm
from jseeker.models import AdaptedResume, MatchResult, ParsedJD, TemplateType

logger = logging.getLogger(__name__)


# Location adaptation by market
LOCATIONS_BY_MARKET = {
    "us": "San Diego, CA",
    "mx": "Ciudad de Mexico",
    "ca": "Remote",
    "uk": "Remote / Open to relocation",
    "es": "Remote / Open to relocation",
    "dk": "Remote / Open to relocation",
    "fr": "Remote / Open to relocation",
}


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
    use_learned_patterns: bool = True,
) -> str:
    """Rewrite the summary to match the JD.

    Cost: ~$0.011 per call (Sonnet), or $0 if learned pattern matches.

    Args:
        template: Resume template type.
        parsed_jd: Parsed job description.
        use_learned_patterns: Check learned patterns before LLM call (default: True).

    Returns:
        Adapted summary text.
    """
    original = block_manager.get_summary(template, language=parsed_jd.language)

    # Check learned patterns first
    if use_learned_patterns:
        from jseeker.pattern_learner import find_matching_pattern
        jd_dict = {
            "title": parsed_jd.title,
            "ats_keywords": parsed_jd.ats_keywords,
            "industry": getattr(parsed_jd, "industry", None),
        }
        cached_summary = find_matching_pattern(
            pattern_type="summary_adaptation",
            source_text=original,
            jd_context=jd_dict,
        )
        if cached_summary:
            logger.info("adapt_summary | pattern cache HIT | skipping LLM call")
            return cached_summary

    # No pattern match - use LLM
    logger.info("adapt_summary | pattern cache MISS | calling LLM")
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

    # Add Spanish language instruction if needed
    if parsed_jd.language == "es":
        spanish_instruction = (
            "\n\nIMPORTANT: Write the entire summary in professional Latin American Spanish. "
            "Use natural business Spanish, not a direct translation from English. "
            "The candidate is a native Spanish speaker.\n"
        )
        prompt = prompt + spanish_instruction

    adapted = llm.call_sonnet(prompt, task="summary_adapt").strip()
    logger.info(f"adapt_summary | adapted_length={len(adapted)} | language={parsed_jd.language}")
    return adapted


def adapt_bullets_batch(
    experience_blocks: list[dict],
    template: TemplateType,
    parsed_jd: ParsedJD,
    use_learned_patterns: bool = True,
) -> list[list[str]]:
    """Adapt bullets for multiple experience blocks in a single LLM call.

    This is 75% faster and cheaper than serial calls.
    Cost: ~$0.015 per batch (vs ~$0.007 x N for serial).
    Cost: $0 for blocks matching learned patterns (30-70% hit rate after training).

    Args:
        experience_blocks: List of dicts with 'company', 'role', 'bullets' keys.
        template: Resume template type.
        parsed_jd: Parsed job description.
        use_learned_patterns: Check learned patterns before LLM call (default: True).

    Returns:
        List of adapted bullet lists, one per input block.
    """
    if not experience_blocks:
        return []

    logger.info(f"adapt_bullets_batch | total_blocks={len(experience_blocks)}")

    # Check learned patterns for each block
    if use_learned_patterns:
        from jseeker.pattern_learner import find_matching_pattern

        jd_dict = {
            "title": parsed_jd.title,
            "ats_keywords": parsed_jd.ats_keywords,
            "industry": getattr(parsed_jd, "industry", None),
        }

        results = []
        needs_llm = []  # Blocks that didn't match patterns
        needs_llm_indices = []

        for idx, exp in enumerate(experience_blocks):
            bullets_str = "\n".join(exp.get("bullets", []))
            cached_bullets = find_matching_pattern(
                pattern_type="bullet_adaptation",
                source_text=bullets_str,
                jd_context=jd_dict,
            )

            if cached_bullets:
                # Pattern match - use cached result
                results.append(cached_bullets.split("\n"))
                logger.info(f"adapt_bullets_batch | block {idx} | pattern cache HIT")
            else:
                # No match - will need LLM
                results.append(None)  # Placeholder
                needs_llm.append(exp)
                needs_llm_indices.append(idx)
                logger.info(f"adapt_bullets_batch | block {idx} | pattern cache MISS")

        # If all blocks matched patterns, return cached results
        if not needs_llm:
            logger.info("adapt_bullets_batch | all blocks from pattern cache | skipping LLM")
            return results

        # Some blocks need LLM - batch them
        logger.info(f"adapt_bullets_batch | {len(needs_llm)} blocks need LLM call")
        experience_blocks = needs_llm
    else:
        results = None
        needs_llm_indices = None

    req_text = "\n".join(
        f"- {r.text}" for r in parsed_jd.requirements[:10]
    )
    ats_keywords = ", ".join(parsed_jd.ats_keywords[:15])
    preferences = _load_preferences()

    # Build batched prompt with all experience blocks
    blocks_text = []
    for idx, exp in enumerate(experience_blocks, 1):
        company = exp.get("company", "")
        role = exp.get("role", "")
        bullets = exp.get("bullets", [])
        block_str = f"""
## Experience Block {idx}: {company} — {role}

Original bullets:
{chr(10).join(f"- {b}" for b in bullets)}
"""
        blocks_text.append(block_str)

    batch_prompt = f"""You are adapting resume bullets for multiple experience blocks to match a job description.

Job Title: {parsed_jd.title}
ATS Keywords: {ats_keywords}
Key Requirements:
{req_text}

User Preferences:
{preferences}

{chr(10).join(blocks_text)}

Return a JSON array of arrays. Each inner array contains adapted bullets for the corresponding experience block.
Use action verbs, quantify impact, incorporate ATS keywords naturally.
Output format: [["bullet1", "bullet2", ...], ["bullet1", "bullet2", ...], ...]
"""

    if parsed_jd.language == "es":
        batch_prompt += (
            "\n\nIMPORTANT: Write all bullets in professional Latin American Spanish. "
            "Use natural business Spanish, not a direct translation from English."
        )

    raw = llm.call_sonnet(batch_prompt, task="bullet_adapt_batch")

    # Parse JSON array of arrays
    json_str = raw.strip()
    if json_str.startswith("```"):
        json_str = re.sub(r"^```(?:json)?\n?", "", json_str)
        json_str = re.sub(r"\n?```$", "", json_str)

    try:
        llm_results = json.loads(json_str)
        if not isinstance(llm_results, list) or len(llm_results) != len(experience_blocks):
            # Malformed response: return original bullets
            logger.warning("adapt_bullets_batch | malformed LLM response | using originals")
            llm_results = [exp.get("bullets", []) for exp in experience_blocks]
        else:
            logger.info(f"adapt_bullets_batch | LLM returned {len(llm_results)} bullet sets")
    except json.JSONDecodeError:
        # Fallback: return originals
        logger.error("adapt_bullets_batch | JSON parse failed | using originals")
        llm_results = [exp.get("bullets", []) for exp in experience_blocks]

    # If we used pattern matching, merge cached + LLM results
    if use_learned_patterns and results is not None:
        for original_idx, llm_result in zip(needs_llm_indices, llm_results):
            results[original_idx] = llm_result
        logger.info("adapt_bullets_batch | merged pattern cache + LLM results")
        return results
    else:
        return llm_results


def adapt_bullets(
    experience_block: dict,
    template: TemplateType,
    parsed_jd: ParsedJD,
) -> list[str]:
    """Adapt experience bullets for a single block.

    Kept for backwards compatibility. New code should use adapt_bullets_batch.
    Cost: ~$0.007 per block (Sonnet).
    """
    result_list = adapt_bullets_batch([experience_block], template, parsed_jd)
    return result_list[0] if result_list else experience_block.get("bullets", [])


def adapt_resume(
    match_result: MatchResult,
    parsed_jd: ParsedJD,
) -> AdaptedResume:
    """Full adaptation pipeline: summary + bullets + skills reorder.

    Total cost: ~$0.046 per resume (Sonnet).
    """
    template = match_result.template_type
    corpus = block_manager.load_corpus()

    logger.info(f"adapt_resume | starting adaptation | template={template.value} | jd_title={parsed_jd.title}")

    # 1. Adapt summary
    logger.info("adapt_resume | step 1: adapting summary")
    adapted_summary = adapt_summary(template, parsed_jd)

    # 2. Get tagged experience blocks (priority) and adapt them IN BATCH
    logger.info("adapt_resume | step 2: getting tagged experiences")
    tagged_experiences = block_manager.get_experience_for_template(template)
    tagged_companies = {exp.company for exp in tagged_experiences}

    # Build batch of experience blocks for single LLM call
    experience_blocks = []
    for exp in tagged_experiences:
        bullets = block_manager.get_bullets(exp, template)
        experience_blocks.append({
            "company": exp.company,
            "role": exp.role,
            "bullets": bullets,
        })

    logger.info(f"adapt_resume | step 2: adapting {len(experience_blocks)} experience blocks in batch")
    # Single batched LLM call for all bullets (75% cost reduction)
    all_adapted_bullets = adapt_bullets_batch(experience_blocks, template, parsed_jd)

    # Reconstruct adapted experiences with results
    adapted_experiences = []
    for exp, adapted_bullets in zip(tagged_experiences, all_adapted_bullets):
        adapted_experiences.append({
            "company": exp.company,
            "role": exp.role,
            "start": exp.start,
            "end": exp.end,
            "location": exp.location,
            "bullets": adapted_bullets,
        })

    # 2b. Include non-tagged experiences in condensed form (no LLM cost)
    for exp in corpus.experience:
        if exp.company not in tagged_companies:
            # Use first available bullet set or additional_bullets
            fallback_bullets = exp.additional_bullets or []
            if not fallback_bullets and exp.bullets:
                # Get bullets from any template variant
                for template_key, bullet_list in exp.bullets.items():
                    fallback_bullets = bullet_list[:3]  # Max 3 condensed bullets
                    break
            adapted_experiences.append({
                "company": exp.company,
                "role": exp.role,
                "start": exp.start,
                "end": exp.end,
                "location": exp.location,
                "bullets": fallback_bullets,
                "condensed": True,  # Flag for renderer to style differently if needed
            })

    # 3. Reorder skills to prioritize JD matches
    logger.info("adapt_resume | step 3: reordering skills")
    matched_skills = block_manager.get_skills_matching_keywords(
        parsed_jd.ats_keywords
    )
    logger.info(f"adapt_resume | matched skill categories: {len(matched_skills)}")
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

    # 4. Adapt location for market
    logger.info("adapt_resume | step 4: adapting location for market")
    adapted_contact = corpus.contact.model_copy()
    market = parsed_jd.market
    if market in LOCATIONS_BY_MARKET:
        adapted_contact.locations = [LOCATIONS_BY_MARKET[market]]
        logger.info(f"adapt_resume | location adapted for market={market}")

    logger.info(
        f"adapt_resume | completed | total_experience_blocks={len(adapted_experiences)} | "
        f"skill_categories={len(skills_ordered)}"
    )

    return AdaptedResume(
        summary=adapted_summary,
        experience_blocks=adapted_experiences,
        skills_ordered=skills_ordered,
        contact=adapted_contact,
        education=corpus.education,
        certifications=corpus.certifications,
        awards=corpus.awards,
        early_career=corpus.early_career,
        target_title=parsed_jd.title or "Director",
        template_used=template,
    )
