"""jSeeker Matcher — Block-to-JD relevance scoring."""

from __future__ import annotations

import json
import logging
import re

from jseeker.block_manager import block_manager
from jseeker.llm import llm
from jseeker.models import MatchResult, ParsedJD, TemplateType

logger = logging.getLogger(__name__)


def _load_prompt(name: str) -> str:
    """Load a prompt template from data/prompts/."""
    from config import settings

    path = settings.prompts_dir / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def local_keyword_score(
    template: TemplateType, parsed_jd: ParsedJD
) -> tuple[float, list[str], list[str]]:
    """Quick local keyword matching (no LLM call).

    Returns (score, matched_keywords, missing_keywords).
    """
    # Get all keywords from the template's experience bullets
    experience_blocks = block_manager.get_experience_for_template(template)
    resume_text = ""
    for exp in experience_blocks:
        bullets = block_manager.get_bullets(exp, template)
        resume_text += " ".join(bullets) + " "

    summary = block_manager.get_summary(template)
    resume_text += summary

    resume_lower = resume_text.lower()
    matched = []
    missing = []

    for keyword in parsed_jd.ats_keywords:
        if keyword.lower() in resume_lower:
            matched.append(keyword)
        else:
            missing.append(keyword)

    total = len(parsed_jd.ats_keywords)
    score = len(matched) / total if total > 0 else 0.0

    logger.info(
        f"local_keyword_score | template={template.value} | "
        f"matched={len(matched)} | missing={len(missing)} | total={total} | score={score:.2f}"
    )

    return score, matched, missing


def llm_relevance_score(parsed_jd: ParsedJD) -> list[MatchResult]:
    """Use Sonnet for deeper relevance scoring across all templates.

    Cost: ~$0.024 per call.
    Returns ranked list of MatchResults.
    """
    prompt_template = _load_prompt("block_scorer")

    # Format requirements
    req_text = "\n".join(f"- [{r.priority}] {r.text}" for r in parsed_jd.requirements)
    keywords_text = ", ".join(parsed_jd.ats_keywords)

    prompt = prompt_template.replace("{ats_keywords}", keywords_text).replace(
        "{requirements}", req_text
    )

    # Use resume blocks as cached system context
    corpus = block_manager.load_corpus()
    system_context = f"Resume summaries: {json.dumps(corpus.summaries)}"

    try:
        raw_response = llm.call_sonnet(
            prompt,
            task="block_scoring",
            system=system_context,
            cache_system=True,
        )
        logger.info(f"llm_relevance_score | raw_response_length={len(raw_response)}")
    except Exception:
        logger.exception("LLM ranking failed in llm_relevance_score.")
        return []

    # Parse JSON response
    json_str = raw_response.strip()
    if json_str.startswith("```"):
        json_str = re.sub(r"^```(?:json)?\n?", "", json_str)
        json_str = re.sub(r"\n?```$", "", json_str)

    try:
        data = json.loads(json_str)
        logger.info(
            f"llm_relevance_score | JSON parse succeeded | rankings_count={len(data.get('rankings', []))}"
        )
    except json.JSONDecodeError:
        logger.warning("LLM ranking response was not valid JSON. Falling back to local ranking.")
        data = {"rankings": []}

    results = []
    for ranking in data.get("rankings", []):
        template_str = ranking.get("template", "hybrid")
        try:
            template_type = TemplateType(template_str)
        except ValueError:
            template_type = TemplateType.HYBRID

        results.append(
            MatchResult(
                template_type=template_type,
                relevance_score=ranking.get("relevance_score", 0.0),
                matched_keywords=ranking.get("matched_keywords", []),
                missing_keywords=ranking.get("missing_keywords", []),
                gap_analysis=ranking.get("gap_analysis", ""),
                recommended_experiences=ranking.get("recommended_experiences", []),
            )
        )

    # Sort by relevance score descending
    results.sort(key=lambda r: r.relevance_score, reverse=True)
    return results


def _build_local_fallback_rankings(parsed_jd: ParsedJD) -> list[MatchResult]:
    """Build deterministic rankings using local keyword overlap only."""
    fallback_results: list[MatchResult] = []
    for template in (TemplateType.AI_UX, TemplateType.AI_PRODUCT, TemplateType.HYBRID):
        score, matched, missing = local_keyword_score(template, parsed_jd)
        logger.info(
            f"_build_local_fallback_rankings | template={template.value} | score={score:.2f}"
        )
        fallback_results.append(
            MatchResult(
                template_type=template,
                relevance_score=score,
                matched_keywords=matched,
                missing_keywords=missing,
                gap_analysis=("LLM ranking unavailable, using local keyword overlap fallback."),
            )
        )

    fallback_results.sort(key=lambda r: r.relevance_score, reverse=True)
    return fallback_results


def match_templates(parsed_jd: ParsedJD) -> list[MatchResult]:
    """Full matching pipeline: local keyword + LLM relevance.

    Returns ranked list of MatchResults (best first).
    """
    logger.info(
        f"match_templates | ats_keywords_count={len(parsed_jd.ats_keywords)} | "
        f"title={parsed_jd.title} | company={parsed_jd.company}"
    )

    # Get LLM-based rankings
    results = llm_relevance_score(parsed_jd)

    if not results:
        logger.warning("No LLM template rankings returned. Using local fallback ranking.")
        return _build_local_fallback_rankings(parsed_jd)

    logger.info(f"match_templates | LLM returned {len(results)} match results")

    # Enrich with local keyword scores
    for result in results:
        local_score, matched, missing = local_keyword_score(result.template_type, parsed_jd)
        # Merge keyword data (LLM keywords + local keywords)
        all_matched = list(set(result.matched_keywords + matched))
        all_missing = list(set(result.missing_keywords) | set(missing))
        result.matched_keywords = all_matched
        result.missing_keywords = all_missing

    # Guardrail: never return an empty list to the UI/pipeline.
    final_results = results or _build_local_fallback_rankings(parsed_jd)
    logger.info(f"match_templates | returning {len(final_results)} final results")
    return final_results
