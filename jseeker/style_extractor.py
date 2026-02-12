"""PDF Style Extractor — Extract visual formatting from PDF templates."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ExtractedStyle(BaseModel):
    """Visual style information extracted from a PDF template.

    This model captures font families, sizes, colors, and layout properties
    that can be applied to HTML/CSS templates during PDF generation.
    """
    # Fonts
    primary_font: str = "Calibri, sans-serif"
    fallback_fonts: str = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

    # Font sizes (in points)
    name_size: float = 22.0
    title_size: float = 13.0
    section_header_size: float = 11.0
    body_size: float = 9.0
    small_size: float = 8.5

    # Colors (hex format without #)
    primary_color: str = "2B5797"  # Blue for headers/name
    text_color: str = "2c2c2c"  # Dark gray for body
    secondary_text_color: str = "555555"  # Medium gray
    muted_text_color: str = "666666"  # Light gray
    bg_color: str = "f0f4f8"  # Light blue-gray for sidebar

    # Font weights
    name_weight: int = 700  # Bold
    header_weight: int = 700  # Bold
    role_weight: int = 700  # Bold
    body_weight: int = 400  # Normal

    # Layout
    column_layout: str = "two_column"  # "two_column" or "single_column"
    left_column_width: str = "2in"  # Width of left sidebar
    spacing_unit: str = "16pt"  # Standard spacing between sections

    # Styling
    header_underline: bool = True
    header_transform: str = "uppercase"
    header_letter_spacing: str = "0.5pt"

    # Metadata
    source_pdf: str = ""
    template_name: str = ""
    language: str = "en"


def extract_style_from_pdf(pdf_path: Path) -> ExtractedStyle:
    """Extract visual formatting information from a PDF template.

    Uses PyMuPDF to analyze the PDF and extract:
    - Font families (primary text font)
    - Font sizes (name, title, headers, body)
    - Colors (primary accent, text, backgrounds)
    - Layout type (two-column vs single-column)

    Args:
        pdf_path: Path to PDF template file.

    Returns:
        ExtractedStyle object with formatting properties.
        Falls back to default style if extraction fails.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF not installed, using default style")
        return ExtractedStyle(source_pdf=str(pdf_path))

    if not pdf_path.exists():
        logger.error(f"PDF not found: {pdf_path}")
        return ExtractedStyle(source_pdf=str(pdf_path))

    try:
        doc = fitz.open(pdf_path)

        if doc.page_count == 0:
            logger.warning(f"PDF has no pages: {pdf_path}")
            doc.close()
            return ExtractedStyle(source_pdf=str(pdf_path), template_name=pdf_path.stem)

        first_page = doc[0]

        # Extract text with font information
        text_dict = first_page.get_text("dict")
        blocks = text_dict.get("blocks", [])

        # Collect font and color samples
        font_samples = []
        color_samples = []
        size_samples = []

        for block in blocks:
            if block.get("type") == 0:  # Text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        font_name = span.get("font", "")
                        font_size = span.get("size", 0)
                        color_tuple = span.get("color", 0)

                        font_samples.append(font_name)
                        size_samples.append(font_size)

                        # Convert color integer to hex
                        if isinstance(color_tuple, int):
                            hex_color = f"{color_tuple:06x}"
                            color_samples.append(hex_color)

        doc.close()

        # Analyze collected data
        style = ExtractedStyle(
            source_pdf=str(pdf_path),
            template_name=pdf_path.stem
        )

        # Extract primary font (most common)
        if font_samples:
            primary_font = _get_most_common(font_samples)
            style.primary_font = _normalize_font_name(primary_font)

        # Extract font sizes (largest = name, second = title, etc.)
        if size_samples:
            unique_sizes = sorted(set(size_samples), reverse=True)
            if len(unique_sizes) >= 1:
                style.name_size = unique_sizes[0]
            if len(unique_sizes) >= 2:
                style.title_size = unique_sizes[1]
            if len(unique_sizes) >= 3:
                style.section_header_size = unique_sizes[2]
            if len(unique_sizes) >= 4:
                style.body_size = unique_sizes[3]
            if len(unique_sizes) >= 5:
                style.small_size = unique_sizes[4]

        # Extract colors (first non-black color = primary accent)
        if color_samples:
            for color in color_samples:
                # Skip black/near-black text colors
                if color not in ["000000", "000001", "000002", "2c2c2c", "333333"]:
                    style.primary_color = color
                    break

        # Detect layout type (rough heuristic: check page width usage)
        try:
            page_rect = first_page.rect
            page_width = page_rect.width

            # If content is concentrated in left 30% of page, likely two-column
            content_rects = [block.get("bbox", [0, 0, 0, 0]) for block in blocks if block.get("type") == 0]
            if content_rects:
                left_content = sum(1 for rect in content_rects if rect[0] < page_width * 0.35)
                if left_content > len(content_rects) * 0.2:  # 20%+ content in left third
                    style.column_layout = "two_column"
                else:
                    style.column_layout = "single_column"
        except Exception as layout_error:
            logger.warning(f"Could not detect layout: {layout_error}")

        logger.info(
            f"Extracted style from {pdf_path.name}: "
            f"font={style.primary_font}, "
            f"name_size={style.name_size}pt, "
            f"primary_color=#{style.primary_color}, "
            f"layout={style.column_layout}"
        )

        return style

    except Exception as e:
        logger.error(f"Failed to extract style from {pdf_path}: {e}")
        return ExtractedStyle(source_pdf=str(pdf_path))


def _get_most_common(items: list) -> str:
    """Get the most frequently occurring item in a list."""
    if not items:
        return ""
    from collections import Counter
    counter = Counter(items)
    return counter.most_common(1)[0][0]


def _normalize_font_name(font_name: str) -> str:
    """Normalize PDF font name to CSS font-family.

    Maps common PDF font names to CSS equivalents:
    - Calibri -> Calibri, sans-serif
    - Arial -> Arial, sans-serif
    - Times -> Times New Roman, serif
    - Helvetica -> Helvetica, Arial, sans-serif
    """
    font_lower = font_name.lower()

    # Common mappings
    if "calibri" in font_lower:
        return "Calibri, sans-serif"
    elif "arial" in font_lower:
        return "Arial, sans-serif"
    elif "helvetica" in font_lower:
        return "Helvetica, Arial, sans-serif"
    elif "times" in font_lower:
        return "Times New Roman, serif"
    elif "georgia" in font_lower:
        return "Georgia, serif"
    elif "verdana" in font_lower:
        return "Verdana, sans-serif"
    elif "courier" in font_lower:
        return "Courier New, monospace"
    else:
        # Return original with sans-serif fallback
        return f"{font_name}, sans-serif"


def generate_css_from_style(style: ExtractedStyle) -> str:
    """Generate CSS stylesheet from extracted style properties.

    Creates a CSS string that can be injected into HTML templates
    to apply the extracted visual formatting.

    Args:
        style: ExtractedStyle object with formatting properties.

    Returns:
        CSS string with custom properties and rules.
    """
    css = f"""/* Auto-generated from template: {style.template_name} */

:root {{
  /* Fonts */
  --font-primary: {style.primary_font};
  --font-fallback: {style.fallback_fonts};

  /* Font Sizes */
  --size-name: {style.name_size}pt;
  --size-title: {style.title_size}pt;
  --size-section-header: {style.section_header_size}pt;
  --size-body: {style.body_size}pt;
  --size-small: {style.small_size}pt;

  /* Colors */
  --color-primary: #{style.primary_color};
  --color-text: #{style.text_color};
  --color-secondary: #{style.secondary_text_color};
  --color-muted: #{style.muted_text_color};
  --color-bg: #{style.bg_color};

  /* Font Weights */
  --weight-bold: {style.name_weight};
  --weight-normal: {style.body_weight};

  /* Layout */
  --column-left-width: {style.left_column_width};
  --spacing: {style.spacing_unit};

  /* Styling */
  --header-transform: {style.header_transform};
  --header-spacing: {style.header_letter_spacing};
}}

/* Apply custom fonts */
body {{
  font-family: var(--font-primary, var(--font-fallback));
  font-size: var(--size-body);
  color: var(--color-text);
}}

/* Header styles */
.header h1 {{
  font-size: var(--size-name);
  font-weight: var(--weight-bold);
  color: var(--color-primary);
}}

.header h2 {{
  font-size: var(--size-title);
  color: var(--color-secondary);
}}

/* Section headers */
h3 {{
  font-size: var(--size-section-header);
  font-weight: var(--weight-bold);
  color: var(--color-primary);
  text-transform: var(--header-transform);
  letter-spacing: var(--header-spacing);
}}

/* Two-column layout */
.resume-grid {{
  grid-template-columns: var(--column-left-width) 1fr;
}}

.left-column {{
  background-color: var(--color-bg);
}}

/* Typography */
.exp-role {{
  font-weight: var(--weight-bold);
}}

.exp-dates,
.location {{
  color: var(--color-muted);
  font-size: var(--size-small);
}}

.exp-company {{
  color: var(--color-secondary);
}}
"""
    return css


def get_available_template_styles() -> list[dict]:
    """Get list of available PDF templates with extracted styles.

    Scans uploaded templates from resume_sources.json and returns
    a list of template options for style selection.

    Returns:
        List of dicts with 'name', 'path', 'language', 'style' keys.
    """
    from jseeker.resume_sources import load_resume_sources

    sources = load_resume_sources()
    uploaded_templates = sources.get("uploaded_templates", [])

    template_styles = []

    for tmpl in uploaded_templates:
        template_styles.append({
            "name": tmpl.get("name", "Unknown"),
            "path": tmpl.get("path", ""),
            "language": tmpl.get("language", "English"),
            "style": None,  # Lazy-loaded when selected
        })

    # Add default built-in style
    template_styles.insert(0, {
        "name": "Built-in Default",
        "path": "",
        "language": "English",
        "style": ExtractedStyle(),  # Default style
    })

    return template_styles


def load_template_style(template_path: str) -> Optional[ExtractedStyle]:
    """Load and extract style from a specific template path.

    Args:
        template_path: Absolute path to PDF template, or empty for default.

    Returns:
        ExtractedStyle object, or None if path is invalid.
    """
    if not template_path:
        return ExtractedStyle()  # Default built-in style

    pdf_path = Path(template_path)
    if not pdf_path.exists():
        logger.warning(f"Template not found: {template_path}")
        return None

    return extract_style_from_pdf(pdf_path)
