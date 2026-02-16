"""jSeeker Pipeline — Single entry point for JD-to-resume generation."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from jseeker.jd_parser import process_jd
from jseeker.matcher import match_templates
from jseeker.adapter import adapt_resume
from jseeker.ats_scorer import score_resume
from jseeker.renderer import compress_pdf, generate_output
from jseeker.llm import llm
from jseeker.models import PipelineResult
from jseeker.pdf_validator import validate_pdf_ats_compliance


def run_pipeline(
    jd_text: str,
    jd_url: str = "",
    output_dir: Path = None,
) -> PipelineResult:
    """Execute the full resume generation pipeline.

    JD text -> parse -> match -> adapt -> score -> render -> save.
    Single entry point, returns all intermediate results for traceability.

    Args:
        jd_text: Raw job description text.
        jd_url: Optional JD URL for ATS detection and tracker.
        output_dir: Override output directory.

    Returns:
        PipelineResult with all intermediate data and file paths.
    """
    # Track costs for this pipeline run
    cost_before = llm.get_total_session_cost()

    # Step 1: Parse JD
    parsed_jd = process_jd(jd_text)
    if jd_url:
        parsed_jd.jd_url = jd_url

    # Step 2: Match templates (returns ranked list, best first)
    match_results = match_templates(parsed_jd)
    if not match_results:
        raise ValueError("Template matching returned no results — cannot generate resume.")
    match_result = match_results[0]  # Select best match

    # Step 3: Adapt resume
    adapted = adapt_resume(match_result, parsed_jd)

    # Step 4: Score ATS compliance
    ats_score = score_resume(adapted, parsed_jd)

    # Step 5: Generate output files
    company = parsed_jd.company or "Unknown"
    role = parsed_jd.title or "Role"

    outputs = generate_output(
        adapted, company, role, output_dir=output_dir, language=parsed_jd.language
    )

    # Step 6: Auto-compress large PDFs
    pdf_output = outputs.get("pdf")
    if pdf_output and pdf_output.stat().st_size > 1.5 * 1024 * 1024:
        import logging

        logging.getLogger(__name__).info("PDF size >1.5MB, compressing...")
        compress_pdf(pdf_output, quality="medium")

    # Step 7: Calculate total pipeline cost
    total_cost = llm.get_total_session_cost() - cost_before

    # Step 8: Write metadata
    pdf_path = str(outputs.get("pdf", ""))
    docx_path = str(outputs.get("docx", ""))

    if pdf_path:
        _write_metadata(
            Path(pdf_path).parent,
            parsed_jd,
            match_result,
            ats_score,
            total_cost,
        )

    # Step 9: Validate PDF for ATS compliance
    pdf_validation = None
    if pdf_path:
        pdf_validation = validate_pdf_ats_compliance(Path(pdf_path))

    return PipelineResult(
        parsed_jd=parsed_jd,
        match_result=match_result,
        adapted_resume=adapted,
        ats_score=ats_score,
        pdf_path=pdf_path,
        docx_path=docx_path,
        company=company,
        role=role,
        language=parsed_jd.language,
        market=parsed_jd.market,
        total_cost=total_cost,
        generation_timestamp=datetime.now(),
        pdf_validation=pdf_validation,
    )


def _write_metadata(
    output_folder: Path,
    parsed_jd,
    match_result,
    ats_score,
    total_cost: float,
) -> None:
    """Write metadata.json alongside resume files."""
    metadata = {
        "title": parsed_jd.title,
        "company": parsed_jd.company,
        "ats_score": ats_score.overall_score,
        "template": match_result.template_type.value,
        "relevance_score": match_result.relevance_score,
        "cost_usd": round(total_cost, 4),
        "language": parsed_jd.language,
        "market": parsed_jd.market,
        "timestamp": datetime.now().isoformat(),
        "matched_keywords": ats_score.matched_keywords[:20],
        "missing_keywords": ats_score.missing_keywords[:10],
    }
    meta_path = output_folder / "metadata.json"
    meta_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
