"""JSEEKER Resume Library - Browse, edit, and manage resume versions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import streamlit as st

from jseeker.resume_sources import load_resume_sources, save_resume_sources
from jseeker.tracker import tracker_db

st.title("Resume Library")

# --- PDF Template Upload ---
with st.expander("Upload PDF Templates", expanded=False):
    st.caption("Upload base resume PDF templates to use as references.")

    import json
    from datetime import datetime

    # Batch upload support
    uploaded_files = st.file_uploader(
        "Choose PDF template(s)",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_template_uploader",
    )

    if uploaded_files:
        st.info(f"{len(uploaded_files)} file(s) selected")

        # Show file size warnings
        for file in uploaded_files:
            size_mb = len(file.getvalue()) / (1024 * 1024)
            if size_mb > 10:
                st.warning(f"⚠️ {file.name} is {size_mb:.1f} MB (recommended: < 10 MB)")

    col1, col2 = st.columns(2)
    with col1:
        template_name = st.text_input(
            "Template Name",
            placeholder="e.g., Resume_DirectorAI_2026 (leave empty for filename)",
            key="template_name_input",
        )
    with col2:
        template_lang = st.selectbox(
            "Language",
            options=["English", "Spanish", "French", "Other"],
            key="template_lang_select",
        )

    if st.button("Upload Template(s)", width="stretch", disabled=not uploaded_files):
        if uploaded_files:
            save_dir = Path("X:/Projects/jSeeker/docs/Resume References")
            save_dir.mkdir(parents=True, exist_ok=True)

            sources_path = Path("X:/Projects/jSeeker/data/resume_sources.json")
            if sources_path.exists():
                sources_data = json.loads(sources_path.read_text(encoding="utf-8"))
            else:
                sources_data = {}

            if "uploaded_templates" not in sources_data:
                sources_data["uploaded_templates"] = []

            uploaded_count = 0
            for uploaded_file in uploaded_files:
                # Use custom name if provided (single file) or filename (batch)
                if len(uploaded_files) == 1 and template_name:
                    safe_name = "".join(
                        c for c in template_name if c.isalnum() or c in (" ", "-", "_")
                    ).strip()
                else:
                    # Use original filename without extension
                    safe_name = Path(uploaded_file.name).stem
                    safe_name = "".join(
                        c for c in safe_name if c.isalnum() or c in (" ", "-", "_")
                    ).strip()

                pdf_path = save_dir / f"{safe_name}.pdf"

                # Check for duplicates
                if any(t.get("name") == safe_name for t in sources_data["uploaded_templates"]):
                    st.warning(f"⚠️ Template '{safe_name}' already exists - skipping")
                    continue

                # Write PDF
                pdf_path.write_bytes(uploaded_file.getvalue())

                # Add metadata
                sources_data["uploaded_templates"].append(
                    {
                        "name": safe_name,
                        "path": str(pdf_path),
                        "language": template_lang,
                        "uploaded_at": datetime.now().isoformat(),
                        "size_kb": len(uploaded_file.getvalue()) / 1024,
                    }
                )
                uploaded_count += 1

            sources_path.write_text(json.dumps(sources_data, indent=2), encoding="utf-8")

            if uploaded_count > 0:
                st.success(f"{uploaded_count} template(s) uploaded successfully!")
                st.rerun()

    # Display existing uploaded templates with preview and delete
    sources_path = Path("X:/Projects/jSeeker/data/resume_sources.json")
    if sources_path.exists():
        sources_data = json.loads(sources_path.read_text(encoding="utf-8"))
        uploaded_templates = sources_data.get("uploaded_templates", [])

        if uploaded_templates:
            st.markdown("**Existing Templates:**")

            for idx, tmpl in enumerate(uploaded_templates):
                with st.expander(f"📄 {tmpl['name']}", expanded=False):
                    tmpl_path = Path(tmpl["path"])

                    # Metadata display
                    col1, col2, col3 = st.columns([2, 1, 1])
                    with col1:
                        st.caption(f"**Language:** {tmpl['language']}")
                        st.caption(f"**Size:** {tmpl['size_kb']:.1f} KB")
                        st.caption(f"**Uploaded:** {tmpl['uploaded_at'][:10]}")

                    with col2:
                        if tmpl_path.exists():
                            with open(tmpl_path, "rb") as f:
                                st.download_button(
                                    "⬇️ Download",
                                    data=f.read(),
                                    file_name=tmpl_path.name,
                                    mime="application/pdf",
                                    key=f"download_{idx}",
                                )

                    with col3:
                        if st.button("🗑️ Delete", key=f"delete_{idx}", type="secondary"):
                            st.session_state[f"confirm_delete_template_{idx}"] = True
                            st.rerun()

                    # Confirmation dialog
                    if st.session_state.get(f"confirm_delete_template_{idx}"):
                        st.warning(
                            "⚠️ Are you sure? This will permanently delete the template file."
                        )
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button(
                                "✓ Confirm Delete", key=f"confirm_yes_{idx}", type="primary"
                            ):
                                # Delete file
                                if tmpl_path.exists():
                                    tmpl_path.unlink()

                                # Remove from metadata
                                sources_data["uploaded_templates"].pop(idx)
                                sources_path.write_text(
                                    json.dumps(sources_data, indent=2), encoding="utf-8"
                                )

                                st.session_state.pop(f"confirm_delete_template_{idx}", None)
                                st.success("Template deleted")
                                st.rerun()
                        with col_b:
                            if st.button("✗ Cancel", key=f"confirm_no_{idx}"):
                                st.session_state.pop(f"confirm_delete_template_{idx}", None)
                                st.rerun()

                    # PDF Preview (first page)
                    if tmpl_path.exists() and not st.session_state.get(
                        f"confirm_delete_template_{idx}"
                    ):
                        try:
                            import fitz  # PyMuPDF

                            with st.spinner("Rendering preview..."):
                                doc = fitz.open(tmpl_path)
                                page = doc[0]  # First page
                                pix = page.get_pixmap(dpi=150)

                                # Convert to bytes
                                img_bytes = pix.tobytes("png")
                                st.image(
                                    img_bytes,
                                    caption=f"Preview - Page 1/{len(doc)}",
                                    use_container_width=True,
                                )
                                doc.close()
                        except ImportError:
                            st.info("💡 Install PyMuPDF for PDF preview: `pip install PyMuPDF`")
                        except Exception as e:
                            st.warning(f"Could not render preview: {e}")

                    # Edit metadata
                    with st.form(key=f"edit_form_{idx}"):
                        st.markdown("**Edit Metadata**")
                        new_name = st.text_input(
                            "Template Name", value=tmpl["name"], key=f"edit_name_{idx}"
                        )
                        new_lang = st.selectbox(
                            "Language",
                            options=["English", "Spanish", "French", "Other"],
                            index=["English", "Spanish", "French", "Other"].index(tmpl["language"]),
                            key=f"edit_lang_{idx}",
                        )

                        if st.form_submit_button("Save Changes"):
                            # Validate new name
                            safe_new_name = "".join(
                                c for c in new_name if c.isalnum() or c in (" ", "-", "_")
                            ).strip()

                            if safe_new_name != tmpl["name"]:
                                # Rename file
                                new_path = save_dir / f"{safe_new_name}.pdf"
                                if new_path.exists() and new_path != tmpl_path:
                                    st.error(f"Template '{safe_new_name}' already exists")
                                else:
                                    if tmpl_path.exists():
                                        tmpl_path.rename(new_path)
                                    sources_data["uploaded_templates"][idx]["name"] = safe_new_name
                                    sources_data["uploaded_templates"][idx]["path"] = str(new_path)

                            # Update language
                            sources_data["uploaded_templates"][idx]["language"] = new_lang

                            sources_path.write_text(
                                json.dumps(sources_data, indent=2), encoding="utf-8"
                            )
                            st.success("Metadata updated")
                            st.rerun()

# --- Base Resume References ---
with st.expander("Base Resume References", expanded=False):
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
        base_a = st.text_input(
            "Base Resume A", value=current_sources["base_a"], key="base_resume_a"
        )
        base_b = st.text_input(
            "Base Resume B", value=current_sources["base_b"], key="base_resume_b"
        )

    with col2:
        base_c = st.text_input(
            "Base Resume C", value=current_sources["base_c"], key="base_resume_c"
        )
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

# --- Database Maintenance ---
with st.expander("Database Maintenance", expanded=False):
    st.caption(
        "Fix corrupted company names in the database (e.g., sentence fragments from JD parsing)."
    )
    if st.button("Sanitize Company Names", key="sanitize_companies_btn"):
        with st.spinner("Fixing company names..."):
            changes = tracker_db.sanitize_existing_companies()
            if changes:
                for cid, old_name, new_name in changes:
                    st.caption(f"  Fixed: '{old_name}' -> '{new_name}'")
                st.success(f"Fixed {len(changes)} company name(s).")
                st.rerun()
            else:
                st.info("All company names are already clean.")

# --- Resume Table ---
resumes = tracker_db.list_all_resumes()

if not resumes:
    st.info("No resumes generated yet. Go to New Resume to create one.")
else:
    df = pd.DataFrame(resumes)

    # Show single output folder (PDF and DOCX are always in same folder)
    if "pdf_path" in df.columns:
        df["output_folder"] = df["pdf_path"].apply(lambda x: str(Path(x).parent) if x else "")
    elif "docx_path" in df.columns:
        df["output_folder"] = df["docx_path"].apply(lambda x: str(Path(x).parent) if x else "")

    display_cols = [
        "id",
        "company_name",
        "role_title",
        "version",
        "ats_score",
        "template_used",
        "output_folder",
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
        "output_folder": st.column_config.TextColumn("Output Folder", width="medium"),
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

    # Auto-save changes (no button required per user feedback)
    has_changes = not df[available].equals(edited_df)

    if has_changes:
        with st.spinner("💾 Auto-saving changes..."):
            changed_count = 0
            for idx, row in edited_df.iterrows():
                original = df.iloc[idx]
                resume_id = int(original["id"])

                # Handle potential NaN values for foreign keys
                application_id = (
                    int(original["application_id"])
                    if not pd.isna(original.get("application_id"))
                    else None
                )
                company_id = (
                    int(original["company_id"]) if not pd.isna(original.get("company_id")) else None
                )

                # Skip editing if no application_id (orphaned resume)
                if application_id is None:
                    continue

                # Handle company_name edits
                if "company_name" in edited_df.columns and "company_name" in original:
                    new_val = row.get("company_name")
                    old_val = original.get("company_name")
                    if not (pd.isna(new_val) and pd.isna(old_val)) and new_val != old_val:
                        # Create new company to avoid affecting other applications
                        new_company_id = tracker_db.get_or_create_company(str(new_val))
                        conn = tracker_db._conn()
                        c = conn.cursor()
                        c.execute(
                            "UPDATE applications SET company_id = ? WHERE id = ?",
                            (new_company_id, application_id),
                        )
                        conn.commit()
                        conn.close()
                        changed_count += 1

                # Handle role_title edits
                if "role_title" in edited_df.columns and "role_title" in original:
                    new_val = row.get("role_title")
                    old_val = original.get("role_title")
                    if not (pd.isna(new_val) and pd.isna(old_val)) and new_val != old_val:
                        tracker_db.update_application(application_id, role_title=str(new_val))
                        changed_count += 1

                # Handle output_folder edits (update both pdf_path and docx_path)
                if "output_folder" in edited_df.columns and "output_folder" in original:
                    new_folder = row.get("output_folder")
                    old_folder = original.get("output_folder")
                    if (
                        not (pd.isna(new_folder) and pd.isna(old_folder))
                        and new_folder != old_folder
                    ):
                        # Build new paths by replacing folder portion
                        new_folder_str = str(new_folder).strip()
                        old_pdf = original.get("pdf_path", "")
                        old_docx = original.get("docx_path", "")

                        if new_folder_str and (old_pdf or old_docx):
                            new_pdf = (
                                str(Path(new_folder_str) / Path(old_pdf).name) if old_pdf else None
                            )
                            new_docx = (
                                str(Path(new_folder_str) / Path(old_docx).name)
                                if old_docx
                                else None
                            )
                            tracker_db.update_resume_paths(
                                resume_id, pdf_path=new_pdf, docx_path=new_docx
                            )
                            changed_count += 1

        if changed_count > 0:
            st.success(f"✅ Auto-saved {changed_count} change(s)!")
            st.rerun()

    st.markdown("---")

    selected_id = st.selectbox("Select resume ID", options=[r["id"] for r in resumes])
    selected = next((r for r in resumes if r["id"] == selected_id), None)

    if selected:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown(
                f"**{selected.get('role_title', '')}** at {selected.get('company_name', '')}"
            )
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
