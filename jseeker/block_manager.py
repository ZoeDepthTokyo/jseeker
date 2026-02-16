"""jSeeker Block Manager — YAML resume block loading and selection."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

from jseeker.models import (
    Award,
    Certification,
    ContactInfo,
    Education,
    ExperienceBlock,
    ResumeCorpus,
    SkillCategory,
    SkillItem,
    TemplateType,
)

logger = logging.getLogger(__name__)


def _load_yaml(path: Path) -> dict:
    """Load a YAML file and return its contents."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class BlockManager:
    """Manages YAML resume blocks — loading, filtering, and selection."""

    def __init__(self, blocks_dir: Optional[Path] = None):
        if blocks_dir is None:
            from config import settings

            blocks_dir = settings.resume_blocks_dir
        self.blocks_dir = blocks_dir
        self._corpus: Optional[ResumeCorpus] = None

    def load_corpus(self) -> ResumeCorpus:
        """Load all resume blocks into a ResumeCorpus."""
        if self._corpus is not None:
            return self._corpus

        # Contact
        try:
            contact_data = _load_yaml(self.blocks_dir / "contact.yaml")
            contact = ContactInfo(**contact_data.get("contact", {}))
            logger.info("Loaded contact.yaml")
        except Exception as e:
            logger.error(f"Failed to load contact.yaml: {e}")
            raise

        # Summaries
        try:
            summaries_data = _load_yaml(self.blocks_dir / "summaries.yaml")
            summaries = summaries_data.get("summaries", {})
            logger.info(f"Loaded summaries.yaml | count={len(summaries)}")
        except Exception as e:
            logger.error(f"Failed to load summaries.yaml: {e}")
            raise

        # Experience
        try:
            exp_data = _load_yaml(self.blocks_dir / "experience.yaml")
            experience = []
            for entry in exp_data.get("experience", []):
                experience.append(ExperienceBlock(**entry))
            logger.info(f"Loaded experience.yaml | count={len(experience)}")
        except Exception as e:
            logger.error(f"Failed to load experience.yaml: {e}")
            raise

        # Skills
        try:
            skills_data = _load_yaml(self.blocks_dir / "skills.yaml")
            skills = {}
            for cat_key, cat_data in skills_data.get("skills", {}).items():
                items = [SkillItem(**item) for item in cat_data.get("items", [])]
                skills[cat_key] = SkillCategory(
                    display_name=cat_data.get("display_name", cat_key),
                    items=items,
                )
            logger.info(f"Loaded skills.yaml | categories={len(skills)}")
        except Exception as e:
            logger.error(f"Failed to load skills.yaml: {e}")
            raise

        # Awards
        try:
            awards_data = _load_yaml(self.blocks_dir / "awards.yaml")
            awards = [Award(**a) for a in awards_data.get("awards", [])]
            logger.info(f"Loaded awards.yaml | count={len(awards)}")
        except Exception as e:
            logger.error(f"Failed to load awards.yaml: {e}")
            raise

        # Education
        try:
            edu_data = _load_yaml(self.blocks_dir / "education.yaml")
            education = [Education(**e) for e in edu_data.get("education", [])]
            logger.info(f"Loaded education.yaml | count={len(education)}")
        except Exception as e:
            logger.error(f"Failed to load education.yaml: {e}")
            raise

        # Certifications
        try:
            cert_data = _load_yaml(self.blocks_dir / "certifications.yaml")
            certifications = [Certification(**c) for c in cert_data.get("certifications", [])]
            logger.info(f"Loaded certifications.yaml | count={len(certifications)}")
        except Exception as e:
            logger.error(f"Failed to load certifications.yaml: {e}")
            raise

        # Early career
        try:
            early_data = _load_yaml(self.blocks_dir / "early_career.yaml")
            early_career = early_data.get("early_career", {}).get("entries", [])
            logger.info(f"Loaded early_career.yaml | count={len(early_career)}")
        except Exception as e:
            logger.error(f"Failed to load early_career.yaml: {e}")
            raise

        self._corpus = ResumeCorpus(
            contact=contact,
            summaries=summaries,
            experience=experience,
            skills=skills,
            awards=awards,
            education=education,
            certifications=certifications,
            early_career=early_career,
        )
        logger.info("ResumeCorpus loaded successfully")
        return self._corpus

    def get_experience_for_template(self, template: TemplateType) -> list[ExperienceBlock]:
        """Get experience blocks tagged for a specific template."""
        corpus = self.load_corpus()
        template_str = template.value
        matching_blocks = [exp for exp in corpus.experience if template_str in exp.tags]
        logger.info(
            f"get_experience_for_template | template={template_str} | matched={len(matching_blocks)}"
        )
        return matching_blocks

    def get_summary(self, template: TemplateType, language: str = "en") -> str:
        """Get the summary for a specific template variant and language.

        Args:
            template: Template type to select summary variant.
            language: Language code ("en" or "es").

        Returns:
            Summary text in the requested language.
        """
        corpus = self.load_corpus()
        base_key = template.value

        # If Spanish requested, try Spanish variant first
        if language == "es":
            spanish_key = f"{base_key}_es"
            spanish_summary = corpus.summaries.get(spanish_key, "")
            if spanish_summary:
                return spanish_summary

        # Fallback to English variant
        return corpus.summaries.get(base_key, "")

    def get_bullets(self, experience: ExperienceBlock, template: TemplateType) -> list[str]:
        """Get bullets for a specific experience block and template."""
        template_str = template.value
        bullets = experience.bullets.get(template_str, [])
        if not bullets and experience.additional_bullets:
            return experience.additional_bullets
        return bullets

    def get_all_ats_keywords(self) -> list[str]:
        """Get all ATS keywords from the skills taxonomy."""
        corpus = self.load_corpus()
        keywords = []
        for category in corpus.skills.values():
            for item in category.items:
                keywords.extend(item.ats_keywords)
        return keywords

    def get_skills_matching_keywords(self, target_keywords: list[str]) -> dict[str, list[str]]:
        """Find skill items that match target JD keywords.

        Returns dict of {category_name: [matched_skill_names]}.
        """
        corpus = self.load_corpus()
        target_lower = {kw.lower() for kw in target_keywords}
        matches = {}

        for cat_key, category in corpus.skills.items():
            matched = []
            for item in category.items:
                item_keywords_lower = {kw.lower() for kw in item.ats_keywords}
                if target_lower & item_keywords_lower:
                    matched.append(item.name)
            if matched:
                matches[category.display_name] = matched

        return matches


# Module-level singleton
block_manager = BlockManager()
