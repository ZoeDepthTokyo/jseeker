"""jSeeker Outreach — Recruiter finder + message generator."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from jseeker.llm import llm
from jseeker.models import OutreachMessage, ParsedJD

if TYPE_CHECKING:
    from jseeker.models import AdaptedResume


def _load_prompt(name: str) -> str:
    from config import settings

    path = settings.prompts_dir / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def generate_outreach(
    parsed_jd: ParsedJD,
    recruiter_name: str = "",
    recruiter_email: str = "",
    channel: str = "email",
    top_qualifications: list[str] = None,
) -> OutreachMessage:
    """Generate a personalized outreach message.

    Cost: ~$0.003 (Haiku).
    """
    if top_qualifications is None:
        top_qualifications = [
            "15+ years leading AI/UX teams globally (Toyota, BMW, Mercedes-Benz)",
            "Increased user retention from 12% to 45% at Toyota (10M+ vehicles)",
            "CES Best in Show, MIT/Art Center educated",
        ]

    prompt_template = _load_prompt("outreach_writer")
    prompt = (
        prompt_template.replace("{channel}", channel)
        .replace("{recruiter_name}", recruiter_name or "Hiring Team")
        .replace("{company}", parsed_jd.company)
        .replace("{role_title}", parsed_jd.title)
        .replace("{qualifications}", "\n".join(f"- {q}" for q in top_qualifications))
    )

    raw = llm.call_haiku(prompt, task="outreach_write")
    body = raw.strip()

    # Extract subject if email
    subject = ""
    if channel == "email" and body.startswith("Subject:"):
        lines = body.split("\n", 1)
        subject = lines[0].replace("Subject:", "").strip()
        body = lines[1].strip() if len(lines) > 1 else body

    return OutreachMessage(
        recruiter_name=recruiter_name,
        recruiter_email=recruiter_email,
        subject=subject,
        body=body,
        channel=channel,
    )


def _load_resume_blocks_context() -> str:
    """Load additional resume context from YAML blocks (experience highlights, skills).

    Returns:
        Condensed string with key experience bullets and top skills for cover letter context.
    """
    import yaml

    blocks_dir = Path(__file__).parent.parent / "data" / "resume_blocks"
    context_parts: list[str] = []

    # Load experience highlights (top 3 bullets from first 2 roles)
    exp_path = blocks_dir / "experience.yaml"
    if exp_path.exists():
        try:
            data = yaml.safe_load(exp_path.read_text(encoding="utf-8"))
            roles = data.get("experience", []) if isinstance(data, dict) else []
            for role in roles[:2]:
                bullets = role.get("bullets", [])
                for b in bullets[:2]:
                    text = b.get("text", b) if isinstance(b, dict) else str(b)
                    if text:
                        context_parts.append(f"- {text[:150]}")
        except Exception:
            pass

    # Load top skills
    skills_path = blocks_dir / "skills.yaml"
    if skills_path.exists():
        try:
            data = yaml.safe_load(skills_path.read_text(encoding="utf-8"))
            skill_names: list[str] = []
            for cat_data in (data.get("skills", {}) if isinstance(data, dict) else {}).values():
                for item in cat_data.get("items", [])[:5]:
                    name = item.get("name", "") if isinstance(item, dict) else str(item)
                    if name:
                        skill_names.append(name)
            if skill_names:
                context_parts.append(f"Skills: {', '.join(skill_names[:15])}")
        except Exception:
            pass

    return "\n".join(context_parts) if context_parts else "See candidate summary above."


def generate_cover_letter(
    parsed_jd: "ParsedJD",
    adapted_resume: "AdaptedResume",
    why_company: str = "",
    key_achievement: str = "",
    culture_tone: str = "Professional",
    language: str = "en",
) -> str:
    """Generate a targeted, human-feeling cover letter using Sonnet.

    Args:
        parsed_jd: Parsed job description with role/company/requirements.
        adapted_resume: Adapted resume with summary and skills.
        why_company: User's specific reason for wanting this company.
        key_achievement: User's most relevant achievement for this role.
        culture_tone: One of Corporate, Startup, Research, Creative.
        language: Language code ("en" or "es").

    Returns:
        Cover letter body text (3 paragraphs, under 200 words).
    """
    prompt_path = Path(__file__).parent.parent / "data" / "prompts" / "cover_letter_writer.txt"
    template = prompt_path.read_text(encoding="utf-8")

    # Build requirements summary (top 5)
    requirements = ""
    if hasattr(parsed_jd, "requirements") and parsed_jd.requirements:
        reqs = [r.text for r in parsed_jd.requirements[:5]]
        requirements = "\n".join(f"- {r}" for r in reqs)
    else:
        requirements = parsed_jd.ats_keywords[:5] if parsed_jd.ats_keywords else ""
        if isinstance(requirements, list):
            requirements = "\n".join(f"- {k}" for k in requirements)

    culture_signals = ""
    if hasattr(parsed_jd, "culture_signals") and parsed_jd.culture_signals:
        culture_signals = ", ".join(parsed_jd.culture_signals[:5])

    adapted_summary = ""
    if hasattr(adapted_resume, "summary"):
        adapted_summary = adapted_resume.summary or ""

    # Load additional context from resume blocks beyond just the summary
    additional_context = _load_resume_blocks_context()

    prompt = template.format(
        role_title=parsed_jd.title or "this role",
        company=parsed_jd.company or "this company",
        market=parsed_jd.market or "us",
        requirements=requirements or "See job description",
        culture_signals=culture_signals or "Professional, collaborative",
        adapted_summary=(adapted_summary[:400] if adapted_summary else "Experienced professional"),
        key_achievement=key_achievement or "Multiple successful projects in this domain",
        why_company=why_company
        or "Strong alignment with the company mission and growth trajectory",
        culture_tone=culture_tone,
        language=language,
        additional_context=additional_context,
    )

    return llm.call_sonnet(prompt, task="cover_letter")


def generate_recruiter_search(
    company: str,
    role_title: str,
    location: str = "",
) -> dict:
    """Generate a LinkedIn search query to find the recruiter.

    Cost: ~$0.001 (Haiku).
    Returns dict with search_url, query, suggested_titles.
    """
    prompt_template = _load_prompt("recruiter_finder")
    prompt = (
        prompt_template.replace("{company}", company)
        .replace("{role_title}", role_title)
        .replace("{location}", location or "")
    )

    raw = llm.call_haiku(prompt, task="recruiter_search")

    json_str = raw.strip()
    if json_str.startswith("```"):
        json_str = re.sub(r"^```(?:json)?\n?", "", json_str)
        json_str = re.sub(r"\n?```$", "", json_str)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return {
            "search_query": f"recruiter {company} {role_title}",
            "suggested_titles": ["Technical Recruiter", "Talent Acquisition"],
        }
