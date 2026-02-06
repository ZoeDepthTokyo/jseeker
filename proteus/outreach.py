"""PROTEUS Outreach — Recruiter finder + message generator."""

from __future__ import annotations

import json
import re

from proteus.llm import llm
from proteus.models import OutreachMessage, ParsedJD


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
        prompt_template
        .replace("{channel}", channel)
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
        prompt_template
        .replace("{company}", company)
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
