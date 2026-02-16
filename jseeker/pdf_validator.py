"""PDF validation for ATS compliance."""
import logging
from pathlib import Path

import fitz  # PyMuPDF

from jseeker.models import PDFValidationResult

logger = logging.getLogger(__name__)


def validate_pdf_ats_compliance(pdf_path: Path) -> PDFValidationResult:
    """Validate generated PDF meets ATS requirements.

    Checks:
    - Text extractability (ATS must be able to parse)
    - Font embedding (ATS needs embedded fonts)
    - Metadata presence (helps ATS categorize)
    - File size (<2MB for most ATS platforms)
    - Page count (target 2 pages)

    Returns:
        PDFValidationResult with pass/fail status and recommendations.
    """
    if not pdf_path.exists():
        return PDFValidationResult(
            is_valid=False,
            error="PDF file not found",
            issues=["File does not exist"],
        )

    try:
        doc = fitz.open(pdf_path)
        issues = []
        warnings = []

        # Check 1: Text extractability
        first_page_text = doc[0].get_text()
        if len(first_page_text) < 100:
            issues.append("Text extraction failed - ATS will not parse correctly")
        elif len(first_page_text) < 500:
            warnings.append("Low text content detected - verify all sections render")

        # Check 2: Font embedding
        fonts = doc.get_page_fonts(0)
        non_embedded = [f[3] for f in fonts if not f[1].startswith("/")]
        if non_embedded:
            issues.append(f"Fonts not embedded: {', '.join(non_embedded[:3])}")

        # Check 3: Metadata
        metadata = doc.metadata
        if not metadata or not metadata.get("title"):
            warnings.append(
                "No PDF metadata - add title/author for better ATS recognition"
            )

        # Check 4: File size
        file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
        if file_size_mb > 2.0:
            issues.append(f"File too large ({file_size_mb:.1f}MB) - compress to <2MB")
        elif file_size_mb > 1.5:
            warnings.append(f"File size {file_size_mb:.1f}MB - consider compression")

        # Check 5: Page count
        page_count = doc.page_count
        if page_count > 3:
            warnings.append(
                f"Resume is {page_count} pages - target 2 pages for ATS"
            )

        doc.close()

        is_valid = len(issues) == 0
        return PDFValidationResult(
            is_valid=is_valid,
            issues=issues,
            warnings=warnings,
            metadata={
                "page_count": page_count,
                "text_length": len(first_page_text),
                "font_count": len(fonts),
                "file_size_mb": round(file_size_mb, 2),
            },
        )

    except Exception as e:
        logger.error(f"PDF validation failed: {e}")
        return PDFValidationResult(
            is_valid=False,
            error=str(e),
            issues=["Validation error - PDF may be corrupt"],
        )
