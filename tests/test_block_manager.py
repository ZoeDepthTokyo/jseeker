"""Tests for block manager module."""

from jseeker.block_manager import BlockManager
from jseeker.models import TemplateType


class TestBlockManager:
    """Test YAML block loading and filtering."""

    def test_load_corpus(self):
        """Verify corpus loads all sections."""
        bm = BlockManager()
        corpus = bm.load_corpus()

        assert corpus.contact.full_name == "Federico Ponce"
        assert corpus.contact.email == "federimanu@gmail.com"
        assert len(corpus.summaries) == 6  # 3 English + 3 Spanish (v0.2 bilingual)
        assert len(corpus.experience) > 0
        assert len(corpus.skills) > 0
        assert len(corpus.awards) > 0
        assert len(corpus.education) > 0
        assert len(corpus.certifications) > 0

    def test_get_summary_ai_ux(self):
        bm = BlockManager()
        summary = bm.get_summary(TemplateType.AI_UX)
        assert "fifteen years" in summary.lower() or "15" in summary

    def test_get_summary_ai_product(self):
        bm = BlockManager()
        summary = bm.get_summary(TemplateType.AI_PRODUCT)
        assert "product" in summary.lower()

    def test_get_summary_hybrid(self):
        bm = BlockManager()
        summary = bm.get_summary(TemplateType.HYBRID)
        assert len(summary) > 50

    def test_get_experience_for_template(self):
        bm = BlockManager()
        exps = bm.get_experience_for_template(TemplateType.AI_UX)
        assert len(exps) >= 3  # At least Quetzal, Toyota, Fantasy, Ronin

    def test_get_bullets(self):
        bm = BlockManager()
        exps = bm.get_experience_for_template(TemplateType.AI_UX)
        toyota = next(e for e in exps if "Toyota" in e.company)
        bullets = bm.get_bullets(toyota, TemplateType.AI_UX)
        assert len(bullets) >= 3
        assert any("retention" in b.lower() for b in bullets)

    def test_get_all_ats_keywords(self):
        bm = BlockManager()
        keywords = bm.get_all_ats_keywords()
        assert len(keywords) > 20
        assert any("AI" in kw for kw in keywords)

    def test_get_skills_matching_keywords(self):
        bm = BlockManager()
        matches = bm.get_skills_matching_keywords(["AI UX", "Product Strategy"])
        assert len(matches) > 0
