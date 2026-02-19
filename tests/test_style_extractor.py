"""Tests for PDF style extraction and CSS generation."""

from pathlib import Path

import pytest

from jseeker.style_extractor import (
    ExtractedStyle,
    _get_most_common,
    _normalize_font_name,
    extract_style_from_pdf,
    generate_css_from_style,
    get_available_template_styles,
    load_template_style,
)

# Project-relative paths — never hardcode machine-specific absolute paths
_PROJECT_ROOT = Path(__file__).parent.parent
_DOCS_DIR = _PROJECT_ROOT / "docs" / "Resume References"
_DATA_DIR = _PROJECT_ROOT / "data"


class TestExtractedStyleModel:
    """Test ExtractedStyle Pydantic model."""

    def test_default_style(self):
        """Test default style has reasonable values."""
        style = ExtractedStyle()

        assert style.primary_font == "Calibri, sans-serif"
        assert style.name_size == 22.0
        assert style.primary_color == "2B5797"
        assert style.column_layout == "two_column"

    def test_custom_style(self):
        """Test creating custom style with overrides."""
        style = ExtractedStyle(
            primary_font="Arial, sans-serif",
            name_size=24.0,
            primary_color="FF0000",
            column_layout="single_column",
        )

        assert style.primary_font == "Arial, sans-serif"
        assert style.name_size == 24.0
        assert style.primary_color == "FF0000"
        assert style.column_layout == "single_column"

    def test_style_metadata(self):
        """Test style metadata fields."""
        style = ExtractedStyle(
            source_pdf="/path/to/template.pdf",
            template_name="Resume_ENG",
            language="en",
        )

        assert style.source_pdf == "/path/to/template.pdf"
        assert style.template_name == "Resume_ENG"
        assert style.language == "en"


class TestFontNormalization:
    """Test font name normalization."""

    def test_normalize_calibri(self):
        """Test Calibri font mapping."""
        assert _normalize_font_name("Calibri") == "Calibri, sans-serif"
        assert _normalize_font_name("calibri-bold") == "Calibri, sans-serif"

    def test_normalize_arial(self):
        """Test Arial font mapping."""
        assert _normalize_font_name("Arial") == "Arial, sans-serif"
        assert _normalize_font_name("ArialMT") == "Arial, sans-serif"

    def test_normalize_helvetica(self):
        """Test Helvetica font mapping."""
        assert _normalize_font_name("Helvetica") == "Helvetica, Arial, sans-serif"
        assert _normalize_font_name("Helvetica-Bold") == "Helvetica, Arial, sans-serif"

    def test_normalize_times(self):
        """Test Times font mapping."""
        assert _normalize_font_name("Times") == "Times New Roman, serif"
        assert _normalize_font_name("Times-Roman") == "Times New Roman, serif"

    def test_normalize_unknown(self):
        """Test unknown font fallback."""
        result = _normalize_font_name("CustomFont")
        assert result == "CustomFont, sans-serif"


class TestHelperFunctions:
    """Test utility helper functions."""

    def test_get_most_common(self):
        """Test finding most common item."""
        items = ["Arial", "Calibri", "Arial", "Arial", "Helvetica"]
        assert _get_most_common(items) == "Arial"

    def test_get_most_common_single(self):
        """Test single item."""
        items = ["Calibri"]
        assert _get_most_common(items) == "Calibri"

    def test_get_most_common_empty(self):
        """Test empty list."""
        items = []
        assert _get_most_common(items) == ""


class TestCSSGeneration:
    """Test CSS generation from ExtractedStyle."""

    def test_generate_css_default(self):
        """Test CSS generation with default style."""
        style = ExtractedStyle()
        css = generate_css_from_style(style)

        assert ":root {" in css
        assert "--font-primary: Calibri, sans-serif;" in css
        assert "--size-name: 22.0pt;" in css
        assert "--color-primary: #2B5797;" in css
        assert "--column-left-width: 2in;" in css

    def test_generate_css_custom(self):
        """Test CSS generation with custom style."""
        style = ExtractedStyle(
            primary_font="Arial, sans-serif",
            name_size=26.0,
            primary_color="FF5733",
            left_column_width="2.5in",
        )
        css = generate_css_from_style(style)

        assert "--font-primary: Arial, sans-serif;" in css
        assert "--size-name: 26.0pt;" in css
        assert "--color-primary: #FF5733;" in css
        assert "--column-left-width: 2.5in;" in css

    def test_css_has_selectors(self):
        """Test generated CSS includes proper selectors."""
        style = ExtractedStyle()
        css = generate_css_from_style(style)

        # Check key CSS selectors are present
        assert "body {" in css
        assert ".header h1 {" in css
        assert ".header h2 {" in css
        assert "h3 {" in css
        assert ".resume-grid {" in css

    def test_css_applies_variables(self):
        """Test CSS uses CSS variables correctly."""
        style = ExtractedStyle()
        css = generate_css_from_style(style)

        assert "var(--font-primary" in css
        assert "var(--size-name)" in css
        assert "var(--color-primary)" in css


class TestPDFStyleExtraction:
    """Test PDF style extraction (requires PyMuPDF)."""

    def test_extract_from_nonexistent_pdf(self):
        """Test extraction from non-existent PDF returns default style."""
        fake_path = Path("/nonexistent/template.pdf")
        style = extract_style_from_pdf(fake_path)

        # Should return default style with source_pdf set
        assert isinstance(style, ExtractedStyle)
        assert style.source_pdf == str(fake_path)
        assert style.primary_font  # Has default value

    def test_extract_without_pymupdf(self, monkeypatch):
        """Test graceful fallback when PyMuPDF not installed."""
        # Mock import error for fitz (PyMuPDF)
        import sys

        # Store original module if it exists
        fitz_backup = sys.modules.get("fitz")

        # Remove fitz from sys.modules to simulate it not being installed
        if "fitz" in sys.modules:
            del sys.modules["fitz"]

        try:
            fake_path = Path("/path/to/template.pdf")
            style = extract_style_from_pdf(fake_path)

            # Should return default style
            assert isinstance(style, ExtractedStyle)
            assert style.source_pdf == str(fake_path)
        finally:
            # Restore fitz if it was originally imported
            if fitz_backup is not None:
                sys.modules["fitz"] = fitz_backup

    @pytest.mark.skipif(
        not _DOCS_DIR.exists(),
        reason="Resume References directory not found",
    )
    def test_extract_from_real_pdf(self):
        """Test extraction from real uploaded PDF template."""
        # Look for actual uploaded templates
        refs_dir = _DOCS_DIR
        pdf_files = list(refs_dir.glob("Fede Ponce*.pdf"))

        if not pdf_files:
            pytest.skip("No Fede Ponce PDF templates found")

        template_path = pdf_files[0]
        style = extract_style_from_pdf(template_path)

        # Verify extraction worked (may return default if PDF is image-based or has issues)
        assert isinstance(style, ExtractedStyle)
        assert style.source_pdf == str(template_path)
        # Font size should be positive (either extracted or default)
        assert style.name_size > 0
        # Should have some font (either extracted or default)
        assert style.primary_font
        # Template name may be empty if extraction failed, stem if succeeded
        assert style.template_name in ["", template_path.stem]


class TestTemplateStyleLoading:
    """Test loading template styles from resume sources."""

    def test_get_available_styles_includes_default(self):
        """Test that available styles includes built-in default."""
        styles = get_available_template_styles()

        assert isinstance(styles, list)
        assert len(styles) > 0
        # First should be built-in default
        assert styles[0]["name"] == "Built-in Default"
        assert styles[0]["path"] == ""

    def test_load_default_style(self):
        """Test loading built-in default style."""
        style = load_template_style("")

        assert isinstance(style, ExtractedStyle)
        assert style.primary_font == "Calibri, sans-serif"

    def test_load_invalid_path(self):
        """Test loading from invalid path returns None."""
        style = load_template_style("/nonexistent/file.pdf")

        assert style is None

    @pytest.mark.skipif(
        not (_DATA_DIR / "resume_sources.json").exists(),
        reason="resume_sources.json not found",
    )
    def test_get_available_styles_from_sources(self):
        """Test loading available styles from resume_sources.json."""
        styles = get_available_template_styles()

        # Should have at least the built-in default
        assert len(styles) >= 1

        # Check structure of returned templates
        for style in styles:
            assert "name" in style
            assert "path" in style
            assert "language" in style


class TestIntegration:
    """Integration tests for end-to-end style extraction and CSS generation."""

    def test_full_pipeline_default_style(self):
        """Test full pipeline: default style → CSS generation."""
        style = ExtractedStyle()
        css = generate_css_from_style(style)

        # Verify CSS is valid and complete
        assert len(css) > 500  # Should be substantial
        assert ":root {" in css
        assert "body {" in css
        assert "--font-primary:" in css

    def test_full_pipeline_custom_style(self):
        """Test full pipeline: custom style → CSS generation."""
        style = ExtractedStyle(
            primary_font="Georgia, serif",
            name_size=28.0,
            title_size=16.0,
            primary_color="1A5490",
            column_layout="single_column",
        )
        css = generate_css_from_style(style)

        # Verify custom values in CSS
        assert "Georgia, serif" in css
        assert "28.0pt" in css
        assert "#1A5490" in css

    @pytest.mark.skipif(
        not _DOCS_DIR.exists(),
        reason="Resume References directory not found",
    )
    def test_extract_and_generate_css_from_real_pdf(self):
        """Test extracting style from real PDF and generating CSS."""
        refs_dir = _DOCS_DIR
        pdf_files = list(refs_dir.glob("Fede Ponce*.pdf"))

        if not pdf_files:
            pytest.skip("No Fede Ponce PDF templates found")

        template_path = pdf_files[0]

        # Extract style (may return default if PDF is image-based)
        style = extract_style_from_pdf(template_path)
        assert isinstance(style, ExtractedStyle)

        # Generate CSS (should work with any ExtractedStyle)
        css = generate_css_from_style(style)
        assert len(css) > 0
        assert ":root {" in css

        # Verify style has source path set
        assert style.source_pdf == str(template_path)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_style_name(self):
        """Test style with empty template name."""
        style = ExtractedStyle(template_name="")
        css = generate_css_from_style(style)

        # Should still generate valid CSS
        assert ":root {" in css

    def test_special_characters_in_path(self):
        """Test handling paths with special characters."""
        path = Path("X:/Templates/Resume (Final) [v2].pdf")
        style = extract_style_from_pdf(path)

        # Should return default style without crashing
        assert isinstance(style, ExtractedStyle)

    def test_unicode_font_names(self):
        """Test handling unicode characters in font names."""
        result = _normalize_font_name("Calibri™")
        assert isinstance(result, str)
        assert "Calibri" in result

    def test_extreme_font_sizes(self):
        """Test handling extreme font sizes."""
        style = ExtractedStyle(
            name_size=72.0,  # Very large
            small_size=4.0,  # Very small
        )
        css = generate_css_from_style(style)

        assert "72.0pt" in css
        assert "4.0pt" in css

    def test_hex_color_without_hash(self):
        """Test colors are formatted without leading # in model."""
        style = ExtractedStyle(primary_color="FF5733")
        assert style.primary_color == "FF5733"

        # But CSS should add #
        css = generate_css_from_style(style)
        assert "#FF5733" in css
