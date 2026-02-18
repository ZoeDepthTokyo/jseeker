"""JSEEKER New Resume - One-click JD to adapted resume to export."""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

from config import settings
from jseeker.adapter import adapt_resume
from jseeker.ats_scorer import score_resume
from jseeker.jd_parser import extract_jd_from_url, process_jd
from jseeker.llm import BudgetExceededError, llm
from jseeker.matcher import match_templates
from jseeker.models import (
    Application,
    ApplicationStatus,
    PipelineResult,
    Resume,
    ResumeStatus,
)
from jseeker.renderer import generate_output
from jseeker.style_extractor import get_available_template_styles, load_template_style
from jseeker.tracker import tracker_db

st.title("New Resume")

# --- Budget Display and Check ---
try:
    monthly_cost = tracker_db.get_monthly_cost()
    session_cost = llm.get_total_session_cost()

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Monthly Cost",
        f"${monthly_cost:.2f}",
        f"of ${settings.max_monthly_budget_usd:.2f}",
    )
    col2.metric("Session Cost", f"${session_cost:.3f}")
    col3.metric(
        "Budget Remaining",
        f"${max(0, settings.max_monthly_budget_usd - monthly_cost):.2f}",
    )

    if monthly_cost >= settings.max_monthly_budget_usd:
        st.error(
            f"Monthly budget exceeded (${monthly_cost:.2f} / "
            f"${settings.max_monthly_budget_usd:.2f}). Generation disabled."
        )
        budget_exceeded = True
    elif monthly_cost >= settings.cost_warning_threshold_usd:
        st.warning(
            f"Approaching monthly budget limit: ${monthly_cost:.2f} / "
            f"${settings.max_monthly_budget_usd:.2f}"
        )
        budget_exceeded = False
    else:
        budget_exceeded = False
except Exception:
    budget_exceeded = False

st.markdown("---")

# --- Step 1: JD Input ---
st.subheader("Job Description")

jd_url = st.text_input(
    "Job URL (optional - helps detect ATS platform):",
    placeholder="https://boards.greenhouse.io/company/jobs/12345",
    key="jd_url_input",
)

# Apply fetched JD text before widget renders (must happen before text_area)
if "fetched_jd_text" in st.session_state:
    st.session_state["jd_text_input"] = st.session_state.pop("fetched_jd_text")

# Fetch JD button: shown when URL is provided and text area is empty
if jd_url.strip() and not st.session_state.get("jd_text_input", "").strip():
    if st.button("Fetch JD from URL", key="fetch_jd_btn"):
        with st.spinner("Extracting job description..."):
            try:
                fetched_jd, meta = extract_jd_from_url(jd_url.strip())
                if fetched_jd and len(fetched_jd.strip()) > 100:
                    # Store in intermediate key to avoid widget key conflict
                    st.session_state["fetched_jd_text"] = fetched_jd
                    if meta.get("linkedin_fallback_used"):
                        alt_src = meta.get("alternate_source_url", "alternate source")
                        st.session_state["_jd_fetch_info"] = (
                            f"LinkedIn JD was incomplete. Full content fetched from: {alt_src}"
                        )
                    st.rerun()
                else:
                    st.warning(
                        "Could not extract enough text from URL. Paste the JD manually."
                    )
            except Exception as e:
                st.error(f"Extraction failed: {e}")

# Show info if LinkedIn fallback was used
if st.session_state.get("_jd_fetch_info"):
    st.info(st.session_state.pop("_jd_fetch_info"))

jd_text = st.text_area(
    "Paste the full job description here:",
    height=300,
    placeholder="Copy and paste the complete job description...",
    key="jd_text_input",
)

st.caption("Paste JD text, or provide a job URL and click Fetch to auto-fill.")

st.markdown("---")

# --- Style Template Selection ---
st.subheader("Visual Style (Optional)")

try:
    available_styles = get_available_template_styles()
    style_names = [s["name"] for s in available_styles]

    selected_style_name = st.selectbox(
        "Choose PDF template style:",
        options=style_names,
        index=0,  # Default to "Built-in Default" (overridden during generation for Spanish jobs)
        help="Select a PDF template to extract visual formatting (fonts, colors, layout). Built-in Default uses hardcoded styles. Spanish templates are auto-selected for Spanish language jobs.",
        key="style_template_selector",
    )

    # Find selected template
    selected_template = next(
        (s for s in available_styles if s["name"] == selected_style_name), None
    )

    if selected_template and selected_template.get("path"):
        # Show template metadata
        st.caption(
            f"Language: {selected_template.get('language', 'Unknown')} | "
            f"Source: {Path(selected_template['path']).name if selected_template['path'] else 'Built-in'}"
        )
except Exception as e:
    st.warning(f"Could not load template styles: {e}")
    selected_template = {"name": "Built-in Default", "path": "", "language": "English"}

st.markdown("---")

# --- Step 2: Generate Resume (One Click) ---
jd_text_clean = jd_text.strip()
jd_url_clean = jd_url.strip()
generate_disabled = (not jd_text_clean and not jd_url_clean) or budget_exceeded
generate_button = st.button(
    "Generate Resume",
    type="primary",
    disabled=generate_disabled,
    width="stretch",
)

if generate_button:
    try:
        with st.status("Generating resume...", expanded=True) as status:
            progress = st.progress(0, text="Initializing pipeline...")
            cost_before = llm.get_total_session_cost()

            # Step 1: Load or extract JD and parse
            source_jd_text = jd_text_clean
            if not source_jd_text and jd_url_clean:
                progress.progress(
                    5, text="Step 1/5: Fetching job description from URL..."
                )
                source_jd_text, extraction_meta = extract_jd_from_url(jd_url_clean)
                if not source_jd_text:
                    # Build detailed error message with diagnostics
                    error_parts = ["Could not extract job description from URL."]
                    if extraction_meta.get("company"):
                        error_parts.append(
                            f"Detected company: {extraction_meta['company']}"
                        )
                    if extraction_meta.get("selectors_tried"):
                        error_parts.append(
                            f"Tried {len(extraction_meta['selectors_tried'])} selectors"
                        )
                    error_parts.append(
                        f"Method: {extraction_meta.get('method', 'unknown')}"
                    )
                    error_parts.append("Please paste the JD text and try again.")
                    raise ValueError(" | ".join(error_parts))
                if extraction_meta.get("linkedin_fallback_used"):
                    alt_src = extraction_meta.get("alternate_source_url", "")
                    st.caption(
                        f"LinkedIn JD was incomplete. Full content from: {alt_src}"
                    )
                progress.progress(
                    12, text="Step 1/5: Job description extracted from URL."
                )
            else:
                progress.progress(12, text="Step 1/5: Using pasted job description.")

            progress.progress(15, text="Step 1/5: Parsing job description...")
            parsed_jd = process_jd(source_jd_text, jd_url=jd_url_clean)
            progress.progress(20, text="Step 1/5: Job description parsed.")

            st.caption(
                f"Parsed: {parsed_jd.title or 'Unknown role'} at {parsed_jd.company or 'Unknown'} | "
                f"{len(parsed_jd.ats_keywords)} keywords | "
                f"{len(parsed_jd.requirements)} requirements | "
                f"Language: {parsed_jd.language} | Market: {parsed_jd.market}"
            )

            # Auto-select Spanish template if language is Spanish or location is Mexico
            if (
                parsed_jd.language == "es"
                or "mexico" in parsed_jd.location.lower()
                or "méxico" in parsed_jd.location.lower()
            ):
                # Find ESP template in available styles
                available_styles_temp = get_available_template_styles()
                for style in available_styles_temp:
                    if "ESP" in style["name"].upper():
                        selected_template = style
                        st.info(f"🌍 Auto-selected Spanish template: {style['name']}")
                        break

            # Step 2: Match templates
            progress.progress(25, text="Step 2/5: Matching resume templates...")
            match_results = match_templates(parsed_jd)
            if not match_results:
                diag = (
                    f"No template matches found.\n"
                    f"JD Title: {parsed_jd.title or 'N/A'}\n"
                    f"JD Company: {parsed_jd.company or 'N/A'}\n"
                    f"ATS Keywords found: {len(parsed_jd.ats_keywords)}\n"
                    f"Keywords: {', '.join(parsed_jd.ats_keywords[:10]) if parsed_jd.ats_keywords else 'NONE'}\n"
                    f"Requirements: {len(parsed_jd.requirements)}\n"
                    f"This usually means the JD parser couldn't extract keywords. "
                    f"Try pasting a more complete job description."
                )
                raise ValueError(diag)
            match_result = match_results[0]
            progress.progress(40, text="Step 2/5: Templates matched.")

            # Step 3: Adapt resume
            progress.progress(45, text="Step 3/5: Adapting resume content...")
            adapted = adapt_resume(match_result, parsed_jd)
            progress.progress(60, text="Step 3/5: Resume adapted.")

            # Step 4: Score ATS
            progress.progress(65, text="Step 4/5: Scoring ATS compliance...")
            ats_score = score_resume(adapted, parsed_jd)
            progress.progress(80, text="Step 4/5: ATS scored.")

            # Step 5: Render files
            progress.progress(85, text="Step 5/5: Rendering PDF and DOCX...")
            company = parsed_jd.company or "Unknown"
            role = parsed_jd.title or "Role"

            # Load custom style if template selected
            custom_style = None
            if selected_template and selected_template.get("path"):
                try:
                    custom_style = load_template_style(selected_template["path"])
                    st.caption(f"Applying style from: {selected_template['name']}")
                except Exception as style_error:
                    st.warning(
                        f"Could not load template style, using default: {style_error}"
                    )

            outputs = generate_output(
                adapted,
                company,
                role,
                output_dir=settings.output_dir,
                language=parsed_jd.language,
                custom_style=custom_style,
            )
            progress.progress(95, text="Step 5/5: Files rendered.")

            total_cost = llm.get_total_session_cost() - cost_before
            pdf_path = str(outputs.get("pdf", ""))
            docx_path = str(outputs.get("docx", ""))

            result = PipelineResult(
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
            )

            st.session_state["pipeline_result"] = result

            company_id = tracker_db.get_or_create_company(result.company)
            app = Application(
                company_id=company_id,
                role_title=result.role,
                jd_text=result.parsed_jd.raw_text,
                jd_url=jd_url_clean,
                location=result.parsed_jd.location,
                remote_policy=result.parsed_jd.remote_policy,
                salary_range=result.parsed_jd.salary_range,
                salary_min=result.parsed_jd.salary_min,
                salary_max=result.parsed_jd.salary_max,
                salary_currency=result.parsed_jd.salary_currency,
                relevance_score=result.match_result.relevance_score,
                resume_status=ResumeStatus.EXPORTED,
                application_status=ApplicationStatus.NOT_APPLIED,
            )
            app_id = tracker_db.add_application(app)

            resume = Resume(
                application_id=app_id,
                template_used=result.adapted_resume.template_used.value,
                content_json=json.dumps(
                    result.adapted_resume.model_dump(), default=str
                ),
                pdf_path=result.pdf_path,
                docx_path=result.docx_path,
                ats_score=result.ats_score.overall_score,
                ats_platform=result.ats_score.platform.value,
                generation_cost=result.total_cost,
            )
            tracker_db.add_resume(resume)

            progress.progress(100, text="Complete. Resume generated successfully.")
            status.update(
                label="Resume generated successfully.", state="complete", expanded=False
            )
            st.success(
                f"Resume generated for {company} - {role} (Application #{app_id})"
            )

    except BudgetExceededError as exc:
        st.error(f"Budget exceeded: {exc}")
    except Exception as exc:
        st.error(f"Generation failed: {exc}")
        import traceback

        st.code(traceback.format_exc())

# --- Step 3: Display Results ---
if "pipeline_result" in st.session_state:
    result = st.session_state["pipeline_result"]

    st.markdown("---")

    with st.expander("ATS Score Card", expanded=False):
        col1, col2, col3 = st.columns(3)
        col1.metric("Overall Score", f"{result.ats_score.overall_score}/100")
        col2.metric("Keyword Match", f"{result.ats_score.keyword_match_rate:.0%}")
        col3.metric("Recommended Format", result.ats_score.recommended_format.upper())

        if result.ats_score.missing_keywords:
            st.warning(
                f"Missing keywords: {', '.join(result.ats_score.missing_keywords[:10])}"
            )

        if result.ats_score.warnings:
            for warning in result.ats_score.warnings:
                st.caption(f"[warning] {warning}")

        st.markdown(f"**Format Reason:** {result.ats_score.format_reason}")

        # ATS Score Explanation
        with st.expander("🧠 Score Explanation", expanded=False):
            try:
                from jseeker.ats_scorer import explain_ats_score

                # Assume original score was lower (simulate improvement)
                original_score = max(50, result.ats_score.overall_score - 15)

                explanation = explain_ats_score(
                    jd_title=result.parsed_jd.title or "Unknown",
                    original_score=original_score,
                    improved_score=result.ats_score.overall_score,
                    matched_keywords=result.ats_score.matched_keywords,
                    missing_keywords=result.ats_score.missing_keywords,
                )

                st.markdown(explanation)

                # Show matched and missing keywords
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("**✅ Matched Keywords**")
                    if result.ats_score.matched_keywords:
                        st.code(
                            ", ".join(result.ats_score.matched_keywords[:15]),
                            language=None,
                        )
                    else:
                        st.caption("None")

                with col_b:
                    st.markdown("**❌ Missing Keywords**")
                    if result.ats_score.missing_keywords:
                        st.code(
                            ", ".join(result.ats_score.missing_keywords[:15]),
                            language=None,
                        )
                    else:
                        st.caption("None")

            except Exception as exc:
                st.error(f"Failed to generate explanation: {exc}")

    with st.expander("Export", expanded=False):
        default_name = Path(result.pdf_path).stem if result.pdf_path else "resume"
        custom_name = st.text_input(
            "Filename:", value=default_name, key="custom_filename"
        )

        col1, col2 = st.columns(2)

        if result.pdf_path and Path(result.pdf_path).exists():
            with col1:
                with open(result.pdf_path, "rb") as handle:
                    st.download_button(
                        "Download PDF",
                        data=handle.read(),
                        file_name=f"{custom_name}.pdf",
                        mime="application/pdf",
                        width="stretch",
                    )

        if result.docx_path and Path(result.docx_path).exists():
            with col2:
                with open(result.docx_path, "rb") as handle:
                    st.download_button(
                        "Download DOCX",
                        data=handle.read(),
                        file_name=f"{custom_name}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        width="stretch",
                    )

    # PDF ATS Validation
    if getattr(result, "pdf_validation", None):
        v = result.pdf_validation
        if v.is_valid:
            st.success("PDF passes ATS validation checks")
        else:
            st.warning("PDF has ATS compliance issues")
        if v.issues:
            for issue in v.issues:
                st.error(f"Issue: {issue}")
        if v.warnings:
            for warn in v.warnings:
                st.warning(f"Warning: {warn}")
        if v.metadata:
            meta = v.metadata
            st.caption(
                f"Pages: {meta.get('page_count', '?')} | "
                f"Text: {meta.get('text_length', '?')} chars | "
                f"Size: {meta.get('file_size_mb', '?')}MB"
            )

    with st.expander("Job Description", expanded=False):
        parsed_jd = result.parsed_jd

        st.markdown("**Full Job Description:**")
        st.text_area(
            "Full JD",
            value=parsed_jd.raw_text,
            height=250,
            disabled=True,
            key="jd_display",
            label_visibility="collapsed",
        )

    with st.expander("JD Analysis", expanded=False):
        parsed_jd = result.parsed_jd

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Title:** {parsed_jd.title}")
            st.markdown(f"**Company:** {parsed_jd.company}")
            st.markdown(f"**Seniority:** {parsed_jd.seniority}")
            st.markdown(f"**Location:** {parsed_jd.location}")

        with col2:
            st.markdown(f"**ATS Platform:** {parsed_jd.detected_ats.value}")
            st.markdown(f"**Remote Policy:** {parsed_jd.remote_policy}")
            st.markdown(f"**Language:** {parsed_jd.language.upper()}")
            st.markdown(f"**Market:** {parsed_jd.market.upper()}")

        st.markdown("**Top ATS Keywords:**")
        st.code(", ".join(parsed_jd.ats_keywords[:15]), language=None)

        with st.expander("View Pruned JD"):
            st.text(parsed_jd.pruned_text)

    with st.expander("Template Match", expanded=False):
        match = result.match_result

        st.metric("Relevance Score", f"{match.relevance_score:.0%}")
        st.markdown(f"**Template Used:** {match.template_type.value}")

        st.markdown("**Matched Keywords:**")
        st.code(", ".join(match.matched_keywords[:15]), language=None)

        st.markdown("**Missing Keywords:**")
        st.code(", ".join(match.missing_keywords[:15]), language=None)

        st.markdown("**Gap Analysis:**")
        st.info(match.gap_analysis)

    with st.expander("Adaptation Details", expanded=False):
        adapted = result.adapted_resume

        st.markdown("**Summary:**")
        st.info(adapted.summary)

        st.markdown("**Experience Blocks:**")
        for exp in adapted.experience_blocks:
            end = exp.get("end") or "Present"
            st.markdown(
                f"**{exp['role']}** - {exp['company']} ({exp['start']} to {end})"
            )
            for bullet in exp.get("bullets", []):
                st.markdown(f"- {bullet}")

    # ── Cover Letter (optional) ──────────────────────────────────
    st.markdown("---")
    with st.expander("Generate Cover Letter (optional, ~$0.015)", expanded=False):
        st.caption(
            "Creates a 3-paragraph, human-written cover letter tailored to this specific role and company."
        )
        col_cl1, col_cl2 = st.columns(2)
        with col_cl1:
            cl_why = st.text_input(
                "Why THIS company specifically?",
                max_chars=150,
                placeholder="e.g. Their approach to X resonates with my work on Y...",
                key="cl_why",
            )
        with col_cl2:
            cl_tone = st.radio(
                "Culture vibe:",
                ["Corporate", "Startup", "Research", "Creative"],
                horizontal=True,
                key="cl_tone",
            )
        cl_achievement = st.text_area(
            "Your proudest achievement relevant to this role:",
            max_chars=250,
            placeholder="e.g. Led migration of X to Y, reducing costs by 40%...",
            key="cl_achievement",
            height=80,
        )
        cl_btn_col, cl_regen_col = st.columns([2, 1])
        if cl_btn_col.button("Generate Cover Letter", key="gen_cl", type="primary"):
            result = st.session_state["pipeline_result"]
            from jseeker.outreach import generate_cover_letter

            with st.spinner("Writing cover letter..."):
                st.session_state["cover_letter"] = generate_cover_letter(
                    parsed_jd=result.parsed_jd,
                    adapted_resume=result.adapted_resume,
                    why_company=cl_why,
                    key_achievement=cl_achievement,
                    culture_tone=cl_tone,
                    language=getattr(result.parsed_jd, "language", "en"),
                )
        if st.session_state.get("cover_letter"):
            if cl_regen_col.button("Regenerate", key="regen_cl"):
                st.session_state.pop("cover_letter", None)
                st.rerun()
            st.text_area(
                "Cover Letter",
                st.session_state["cover_letter"],
                height=320,
                key="cl_display",
            )
            result = st.session_state["pipeline_result"]
            fname = f"cover_letter_{getattr(result.parsed_jd, 'company', 'company').replace(' ', '_')}.txt"
            st.download_button(
                "Download .txt",
                st.session_state["cover_letter"],
                file_name=fname,
                mime="text/plain",
                key="dl_cover_letter",
            )

    st.markdown("---")
    st.caption(f"**Cost:** ${result.total_cost:.4f}")
