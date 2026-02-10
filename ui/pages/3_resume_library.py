"""JSEEKER Resume Library - Browse, edit, and manage resume versions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import streamlit as st

from jseeker.resume_sources import load_resume_sources, save_resume_sources
from jseeker.tracker import tracker_db


st.title("Resume Library")

# --- Base Resume References ---
with st.expander("Base Resume References", expanded=True):
    st.caption("Track which source files are used as Base A/B/C and LinkedIn PDF.")

    current_sources = load_resume_sources()

    # Show current status
    st.markdown("**Current Status:**")
    for key, path_str in current_sources.items():
        if path_str:
            p = Path(path_str)
            if p.exists():
                size_kb = p.stat().st_size / 1024
                from datetime import datetime
                modified = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                st.caption(f"  {key}: {size_kb:.1f} KB, modified {modified}")
            else:
                st.caption(f"  {key}: File not found at {path_str}")
        else:
            st.caption(f"  {key}: Not configured")

    col1, col2 = st.columns(2)

    with col1:
        base_a = st.text_input("Base Resume A", value=current_sources["base_a"], key="base_resume_a")
        base_b = st.text_input("Base Resume B", value=current_sources["base_b"], key="base_resume_b")

    with col2:
        base_c = st.text_input("Base Resume C", value=current_sources["base_c"], key="base_resume_c")
        linkedin_pdf = st.text_input(
            "LinkedIn Profile PDF",
            value=current_sources["linkedin_pdf"],
            key="base_resume_linkedin_pdf",
        )

    if st.button("Save Base References", width="stretch"):
        saved = save_resume_sources(
            {
                "base_a": base_a,
                "base_b": base_b,
                "base_c": base_c,
                "linkedin_pdf": linkedin_pdf,
            }
        )
        st.success("Base references saved.")

        for key, value in saved.items():
            if value:
                exists = Path(value).exists()
                icon = "+" if exists else "x"
                status = "found" if exists else "MISSING"
                st.caption(f"  [{icon}] {key}: {status} - {value}")

# --- Resume Table ---
resumes = tracker_db.list_all_resumes()

if not resumes:
    st.info("No resumes generated yet. Go to New Resume to create one.")
else:
    df = pd.DataFrame(resumes)

    display_cols = [
        "id",
        "company_name",
        "role_title",
        "version",
        "ats_score",
        "template_used",
        "pdf_path",
        "docx_path",
        "created_at",
        "generation_cost",
    ]
    available = [c for c in display_cols if c in df.columns]

    column_config = {
        "id": st.column_config.NumberColumn("ID", disabled=True),
        "company_name": st.column_config.TextColumn("Company"),
        "role_title": st.column_config.TextColumn("Role"),
        "version": st.column_config.NumberColumn("Version", disabled=True),
        "ats_score": st.column_config.NumberColumn("ATS Score", disabled=True),
        "template_used": st.column_config.TextColumn("Template", disabled=True),
        "pdf_path": st.column_config.TextColumn("PDF Path", disabled=True),
        "docx_path": st.column_config.TextColumn("DOCX Path", disabled=True),
        "created_at": st.column_config.DatetimeColumn("Created", disabled=True),
        "generation_cost": st.column_config.NumberColumn("Cost ($)", format="%.4f", disabled=True),
    }

    edited_df = st.data_editor(
        df[available],
        column_config=column_config,
        width="stretch",
        hide_index=True,
        key="resume_library_editor",
    )

    if not df[available].equals(edited_df):
        changed_count = 0
        for idx, row in edited_df.iterrows():
            original = df.iloc[idx]
            application_id = int(df.iloc[idx]["application_id"])
            company_id = int(df.iloc[idx]["company_id"])

            if "company_name" in edited_df.columns and "company_name" in original:
                new_val = row.get("company_name")
                old_val = original.get("company_name")
                if pd.notna(new_val) and pd.notna(old_val) and new_val != old_val:
                    tracker_db.update_company_name(company_id, str(new_val))
                    changed_count += 1

            if "role_title" in edited_df.columns and "role_title" in original:
                new_val = row.get("role_title")
                old_val = original.get("role_title")
                if pd.notna(new_val) and pd.notna(old_val) and new_val != old_val:
                    tracker_db.update_application(application_id, role_title=str(new_val))
                    changed_count += 1

        if changed_count > 0:
            st.toast(f"Saved {changed_count} change(s) to backend.")
            st.rerun()

    st.markdown("---")

    selected_id = st.selectbox("Select resume ID", options=[r["id"] for r in resumes])
    selected = next((r for r in resumes if r["id"] == selected_id), None)

    if selected:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"**{selected.get('role_title', '')}** at {selected.get('company_name', '')}")
            st.markdown(f"Version: {selected.get('version', 1)}")
            st.markdown(f"ATS Score: {selected.get('ats_score', 'N/A')}")
            st.markdown(f"Template: {selected.get('template_used', 'N/A')}")
            if selected.get("generation_cost"):
                st.markdown(f"Cost: ${selected['generation_cost']:.4f}")

            pdf_path = selected.get("pdf_path") or ""
            docx_path = selected.get("docx_path") or ""
            st.markdown(f"PDF path: `{pdf_path}`")
            st.markdown(f"DOCX path: `{docx_path}`")

        with col2:
            pdf_path = selected.get("pdf_path")
            if pdf_path and Path(pdf_path).exists():
                with open(pdf_path, "rb") as handle:
                    st.download_button(
                        "Download PDF",
                        data=handle.read(),
                        file_name=Path(pdf_path).name,
                        mime="application/pdf",
                    )

            docx_path = selected.get("docx_path")
            if docx_path and Path(docx_path).exists():
                with open(docx_path, "rb") as handle:
                    st.download_button(
                        "Download DOCX",
                        data=handle.read(),
                        file_name=Path(docx_path).name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )

            if st.button("Delete Resume", type="secondary"):
                st.session_state["confirm_delete"] = selected_id

            if st.session_state.get("confirm_delete") == selected_id:
                st.warning("Are you sure? This will delete the resume and its files.")
                if st.button("Confirm Delete", type="primary"):
                    tracker_db.delete_resume(selected_id)
                    st.session_state.pop("confirm_delete", None)
                    st.success("Resume deleted")
                    st.rerun()
                if st.button("Cancel"):
                    st.session_state.pop("confirm_delete", None)
                    st.rerun()
