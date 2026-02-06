"""PROTEUS New Resume — JD paste → adapted resume → export."""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from proteus.models import TemplateType, ResumeStatus, ApplicationStatus
from proteus.tracker import tracker_db

st.title("New Resume")

# --- Step 1: JD Input ---
st.subheader("Step 1: Paste Job Description")

jd_text = st.text_area(
    "Paste the full job description here:",
    height=300,
    placeholder="Copy and paste the complete job description...",
)

jd_url = st.text_input(
    "Job URL (optional — helps detect ATS platform):",
    placeholder="https://boards.greenhouse.io/company/jobs/12345",
)

if st.button("Analyze JD", disabled=not jd_text):
    with st.spinner("Pruning boilerplate and parsing JD..."):
        from proteus.jd_parser import process_jd
        parsed_jd = process_jd(jd_text, jd_url)
        st.session_state["parsed_jd"] = parsed_jd

# --- Step 2: JD Analysis ---
if "parsed_jd" in st.session_state:
    parsed_jd = st.session_state["parsed_jd"]
    st.markdown("---")
    st.subheader("Step 2: JD Analysis")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Title:** {parsed_jd.title}")
        st.markdown(f"**Company:** {parsed_jd.company}")
        st.markdown(f"**Seniority:** {parsed_jd.seniority}")
        st.markdown(f"**Location:** {parsed_jd.location}")
        st.markdown(f"**ATS Platform:** {parsed_jd.detected_ats.value}")

    with col2:
        st.markdown("**Top ATS Keywords:**")
        keyword_str = ", ".join(parsed_jd.ats_keywords[:15])
        st.code(keyword_str, language=None)

    with st.expander("View Pruned JD"):
        st.text(parsed_jd.pruned_text)

    # --- Step 3: Template Matching ---
    if st.button("Match Templates"):
        with st.spinner("Scoring template relevance via Sonnet..."):
            from proteus.matcher import match_templates
            results = match_templates(parsed_jd)
            st.session_state["match_results"] = results

if "match_results" in st.session_state:
    results = st.session_state["match_results"]
    parsed_jd = st.session_state["parsed_jd"]

    st.markdown("---")
    st.subheader("Step 3: Template Match")

    for i, result in enumerate(results):
        icon = "1st" if i == 0 else ("2nd" if i == 1 else "3rd")
        with st.expander(f"{icon}: {result.template_type.value} — {result.relevance_score:.0%} match", expanded=(i == 0)):
            st.markdown(f"**Matched Keywords:** {', '.join(result.matched_keywords[:10])}")
            st.markdown(f"**Missing Keywords:** {', '.join(result.missing_keywords[:10])}")
            st.markdown(f"**Gap Analysis:** {result.gap_analysis}")

    selected_template = st.selectbox(
        "Select template:",
        options=[r.template_type.value for r in results],
        index=0,
    )

    # --- Step 4: Adapt ---
    if st.button("Adapt Resume"):
        with st.spinner("Adapting summary and bullets via Sonnet (~20 sec)..."):
            from proteus.adapter import adapt_resume
            template_type = TemplateType(selected_template)
            match_result = next(r for r in results if r.template_type == template_type)
            adapted = adapt_resume(match_result, parsed_jd)
            st.session_state["adapted_resume"] = adapted

if "adapted_resume" in st.session_state:
    adapted = st.session_state["adapted_resume"]
    parsed_jd = st.session_state["parsed_jd"]

    st.markdown("---")
    st.subheader("Step 4: Adapted Resume Preview")

    st.markdown("**Summary:**")
    st.info(adapted.summary)

    for exp in adapted.experience_blocks:
        end = exp.get("end") or "Present"
        st.markdown(f"**{exp['role']}** — {exp['company']} ({exp['start']} – {end})")
        for bullet in exp.get("bullets", []):
            st.markdown(f"- {bullet}")

    # --- Step 5: ATS Score ---
    if st.button("Score ATS Compliance"):
        with st.spinner("Scoring ATS compliance..."):
            from proteus.ats_scorer import score_resume
            ats_score = score_resume(adapted, parsed_jd)
            st.session_state["ats_score"] = ats_score

if "ats_score" in st.session_state:
    ats_score = st.session_state["ats_score"]
    adapted = st.session_state["adapted_resume"]
    parsed_jd = st.session_state["parsed_jd"]

    st.markdown("---")
    st.subheader("Step 5: ATS Score")

    col1, col2, col3 = st.columns(3)
    col1.metric("Overall Score", f"{ats_score.overall_score}/100")
    col2.metric("Keyword Match", f"{ats_score.keyword_match_rate:.0%}")
    col3.metric("Format", ats_score.recommended_format.upper())

    if ats_score.missing_keywords:
        st.warning(f"Missing keywords: {', '.join(ats_score.missing_keywords[:10])}")
    if ats_score.warnings:
        for w in ats_score.warnings:
            st.caption(f"Warning: {w}")

    st.markdown(f"**Recommended format:** {ats_score.recommended_format} — {ats_score.format_reason}")

    # --- Step 6: Export ---
    st.markdown("---")
    st.subheader("Step 6: Export")

    export_formats = st.multiselect(
        "Export formats:",
        options=["pdf", "docx"],
        default=["pdf", "docx"],
    )

    if st.button("Generate & Export"):
        with st.spinner("Rendering PDF and DOCX..."):
            from proteus.renderer import generate_output

            outputs = generate_output(
                adapted,
                company=parsed_jd.company,
                role=parsed_jd.title,
                formats=export_formats,
            )

            # Save to tracker
            company_id = tracker_db.get_or_create_company(parsed_jd.company)
            from proteus.models import Application, Resume
            app = Application(
                company_id=company_id,
                role_title=parsed_jd.title,
                jd_text=parsed_jd.raw_text,
                jd_url=parsed_jd.jd_url,
                location=parsed_jd.location,
                remote_policy=parsed_jd.remote_policy,
                salary_range=parsed_jd.salary_range,
                resume_status=ResumeStatus.EXPORTED,
                application_status=ApplicationStatus.NOT_APPLIED,
            )
            app_id = tracker_db.add_application(app)

            resume = Resume(
                application_id=app_id,
                template_used=adapted.template_used.value,
                content_json=json.dumps(adapted.model_dump(), default=str),
                pdf_path=str(outputs.get("pdf", "")),
                docx_path=str(outputs.get("docx", "")),
                ats_score=ats_score.overall_score,
                ats_platform=ats_score.platform.value,
            )
            tracker_db.add_resume(resume)

            # Log costs
            from proteus.llm import llm
            for cost in llm.get_session_costs():
                tracker_db.log_cost(cost)

            st.success(f"Resume exported! Application saved (ID: {app_id})")

            for fmt, path in outputs.items():
                st.markdown(f"**{fmt.upper()}:** `{path}`")

            # Download buttons
            for fmt, path in outputs.items():
                if Path(path).exists():
                    with open(path, "rb") as f:
                        st.download_button(
                            f"Download {fmt.upper()}",
                            data=f.read(),
                            file_name=Path(path).name,
                            mime="application/pdf" if fmt == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
