"""JSEEKER Tracker - Application CRM with three status pipelines."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from jseeker.models import ApplicationStatus, JobStatus, ResumeStatus
from jseeker.tracker import tracker_db

st.title("Application Tracker")

# --- Filters ---
st.sidebar.subheader("Filters")

app_status_filter = st.sidebar.selectbox(
    "Application Status",
    options=["All"] + [s.value for s in ApplicationStatus],
    index=0,
)
resume_status_filter = st.sidebar.selectbox(
    "Resume Status",
    options=["All"] + [s.value for s in ResumeStatus],
    index=0,
)
job_status_filter = st.sidebar.selectbox(
    "Job Status",
    options=["All"] + [s.value for s in JobStatus],
    index=0,
)

kwargs = {}
if app_status_filter != "All":
    kwargs["application_status"] = app_status_filter
if resume_status_filter != "All":
    kwargs["resume_status"] = resume_status_filter
if job_status_filter != "All":
    kwargs["job_status"] = job_status_filter

apps = tracker_db.list_applications(**kwargs)
st.caption(f"Showing {len(apps)} applications")

# --- Salary Analytics Chart ---
if apps:
    df_all = pd.DataFrame(apps)

    # Only show salary chart if salary data exists
    df_with_salary = df_all[(df_all["salary_min"].notna()) | (df_all["salary_max"].notna())].copy()

    if not df_with_salary.empty:
        with st.expander("Salary Analytics", expanded=False):
            # Calculate average salary
            df_with_salary["salary_avg"] = (
                df_with_salary["salary_min"].fillna(0) + df_with_salary["salary_max"].fillna(0)
            ) / 2
            df_with_salary["salary_avg"] = df_with_salary["salary_avg"].replace(0, pd.NA)
            df_with_salary = df_with_salary[df_with_salary["salary_avg"].notna()]

            if not df_with_salary.empty:
                # Format hover data
                df_with_salary["hover_text"] = (
                    df_with_salary["role_title"]
                    + "<br>"
                    + df_with_salary["company_name"]
                    + "<br>Salary: "
                    + df_with_salary["salary_currency"].fillna("USD")
                    + " "
                    + df_with_salary["salary_min"].fillna(0).astype(int).astype(str)
                    + " - "
                    + df_with_salary["salary_max"].fillna(0).astype(int).astype(str)
                )

                # Create scatter plot
                fig = px.scatter(
                    df_with_salary,
                    x="created_at",
                    y="salary_avg",
                    color="application_status",
                    size="relevance_score",
                    hover_data=["hover_text"],
                    labels={
                        "created_at": "Application Date",
                        "salary_avg": "Average Salary",
                        "application_status": "Status",
                    },
                    title="Salary Distribution Over Time",
                )

                fig.update_traces(
                    hovertemplate="<b>%{customdata[0]}</b><br>Date: %{x}<br>Avg Salary: %{y:,.0f}<extra></extra>"
                )

                st.plotly_chart(fig, use_container_width=True)

                # Summary stats
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Avg Salary", f"${df_with_salary['salary_avg'].mean():,.0f}")
                with col2:
                    st.metric("Min Salary", f"${df_with_salary['salary_avg'].min():,.0f}")
                with col3:
                    st.metric("Max Salary", f"${df_with_salary['salary_avg'].max():,.0f}")
            else:
                st.info("No valid salary data to display.")

    st.markdown("---")

# --- Inline-Editable Table ---
if apps:
    df = pd.DataFrame(apps)

    # Column order: ID, Company, Location, Role, URL, Min Salary, Max Salary, Currency, App Status, Relevance, ATS Score, Resume Status, Job Status, Created, Notes
    display_cols = [
        "id",
        "company_name",
        "location",
        "role_title",
        "application_status",
        "jd_url",
        "salary_min",
        "salary_max",
        "salary_currency",
        "relevance_score",
        "ats_score",
        "resume_status",
        "job_status",
        "created_at",
        "notes",
    ]
    available_cols = [c for c in display_cols if c in df.columns]

    if "relevance_score" in df.columns:
        df["relevance_score"] = df["relevance_score"].fillna(0) * 100

    # Convert None salary values to NaN for proper display
    if "salary_min" in df.columns:
        df["salary_min"] = pd.to_numeric(df["salary_min"], errors="coerce")
    if "salary_max" in df.columns:
        df["salary_max"] = pd.to_numeric(df["salary_max"], errors="coerce")

    # Add emoji indicators for status (visual cue since we can't color cells)
    status_emojis = {
        "rejected": "❌",
        "applied": "✅",
        "not_applied": "⏳",
        "interviewing": "🗣️",
        "offer": "🎉",
    }
    job_emojis = {"closed": "❌", "active": "✅", "paused": "⏸️"}

    if "application_status" in df.columns:
        df["app_status_display"] = df["application_status"].apply(
            lambda x: f"{status_emojis.get(x, '')} {x}" if x else ""
        )
    if "job_status" in df.columns:
        df["job_status_display"] = df["job_status"].apply(
            lambda x: f"{job_emojis.get(x, '')} {x}" if x else ""
        )

    # Apply color coding to application_status
    def style_app_status(val):
        colors = {
            "rejected": "background-color: #ffcccc; color: #990000",  # Red
            "applied": "background-color: #ccffcc; color: #006600",  # Green
            "not_applied": "background-color: #ffffcc; color: #996600",  # Yellow
            "interviewing": "background-color: #cce5ff; color: #004080",  # Blue
            "offer": "background-color: #e6ccff; color: #660099",  # Purple
        }
        return colors.get(val, "")

    column_config = {
        "id": st.column_config.NumberColumn("ID", disabled=True),
        "company_name": st.column_config.TextColumn(
            "Company", help="Edit if parser didn't extract correctly", disabled=False
        ),
        "role_title": st.column_config.TextColumn(
            "Role", help="Job title (editable)", disabled=False, width="large"
        ),
        "jd_url": st.column_config.TextColumn(
            "URL",
            help="Job posting URL (editable - paste new URL to replace)",
            max_chars=500,
            disabled=False,
            width="medium",
        ),
        "salary_min": st.column_config.NumberColumn(
            "Min Salary", help="Minimum salary (optional)", format="%d"
        ),
        "salary_max": st.column_config.NumberColumn(
            "Max Salary", help="Maximum salary (optional)", format="%d"
        ),
        "salary_currency": st.column_config.SelectboxColumn(
            "Currency", options=["USD", "EUR", "GBP", "MXN"], default="USD"
        ),
        "relevance_score": st.column_config.NumberColumn(
            "Relevance",
            format="%.0f%%",
            disabled=False,
            help="0-25: Low fit | 26-50: Medium fit | 51-75: Good fit | 76-100: Excellent fit. Used for prioritization and success rate analysis.",
        ),
        "ats_score": st.column_config.NumberColumn("ATS Score", disabled=False),
        "application_status": st.column_config.SelectboxColumn(
            "App Status",
            options=[s.value for s in ApplicationStatus],
            required=True,
            help="❌ rejected | ✅ applied | ⏳ not_applied | 🗣️ interviewing | 🎉 offer",
        ),
        "resume_status": st.column_config.SelectboxColumn(
            "Resume Status", options=[s.value for s in ResumeStatus], required=True
        ),
        "job_status": st.column_config.SelectboxColumn(
            "Job Status",
            options=[s.value for s in JobStatus],
            required=True,
            help="❌ closed | ✅ active | ⏸️ paused",
        ),
        "location": st.column_config.TextColumn("Location"),
        "created_at": st.column_config.DatetimeColumn("Created", disabled=True),
        "notes": st.column_config.TextColumn("Notes"),
    }

    edited_df = st.data_editor(
        df[available_cols],
        column_config=column_config,
        width="stretch",
        hide_index=True,
        key="tracker_editor",
    )

    # Auto-save changes (no button required per user feedback)
    has_changes = not df[available_cols].equals(edited_df)

    if has_changes:
        with st.spinner("💾 Auto-saving changes..."):
            changed_count = 0
            for idx, row in edited_df.iterrows():
                original = df.iloc[idx]
                app_id = int(original["id"])
                changes = {}

                # Handle company_name separately (create NEW company, don't update existing)
                if "company_name" in edited_df.columns and "company_name" in original:
                    new_company = row.get("company_name")
                    old_company = original.get("company_name")
                    if (
                        not (pd.isna(new_company) and pd.isna(old_company))
                        and new_company != old_company
                    ):
                        # Create a new company and reassign the application to it
                        # This prevents accidentally updating other applications sharing the same company
                        new_company_id = tracker_db.get_or_create_company(new_company)

                        # Update the application to point to the new company
                        conn = tracker_db._conn()
                        c = conn.cursor()
                        c.execute(
                            "UPDATE applications SET company_id = ? WHERE id = ?",
                            (new_company_id, app_id),
                        )
                        conn.commit()
                        conn.close()
                        changed_count += 1

                # Handle other application fields
                for col in [
                    "role_title",
                    "application_status",
                    "resume_status",
                    "job_status",
                    "notes",
                    "location",
                    "jd_url",
                    "salary_min",
                    "salary_max",
                    "salary_currency",
                    "relevance_score",
                ]:
                    if col not in edited_df.columns or col not in original:
                        continue
                    new_val = row.get(col)
                    old_val = original.get(col)
                    if pd.isna(new_val) and pd.isna(old_val):
                        continue
                    if new_val != old_val:
                        save_val = None if pd.isna(new_val) else new_val
                        # Validate URL format
                        if col == "jd_url" and save_val:
                            save_val = str(save_val).strip()
                            if save_val and not save_val.startswith(("http://", "https://")):
                                save_val = "https://" + save_val
                        # relevance_score is displayed as percentage (x100), convert back to 0-1
                        if col == "relevance_score" and save_val is not None:
                            save_val = save_val / 100.0
                        changes[col] = save_val

                # Handle ats_score separately (stored on resumes table, not applications)
                if "ats_score" in edited_df.columns and "ats_score" in original:
                    new_ats = row.get("ats_score")
                    old_ats = original.get("ats_score")
                    if not (pd.isna(new_ats) and pd.isna(old_ats)) and new_ats != old_ats:
                        tracker_db.update_latest_resume_ats(
                            app_id, None if pd.isna(new_ats) else int(new_ats)
                        )
                        changed_count += 1

                if changes:
                    tracker_db.update_application(app_id, **changes)
                    changed_count += 1

        if changed_count > 0:
            st.success(f"✅ Auto-saved {changed_count} change(s)!")
            st.rerun()

    # --- Delete Row ---
    st.markdown("---")
    with st.expander("🗑️ Delete Application", expanded=False):
        st.warning(
            "⚠️ Warning: This will permanently delete the application and all associated resumes and files."
        )

        delete_id = st.number_input(
            "Application ID to delete",
            min_value=1,
            step=1,
            help="Enter the ID from the leftmost column",
        )

        if delete_id:
            # Show preview of what will be deleted
            app_to_delete = next((a for a in apps if a["id"] == delete_id), None)
            if app_to_delete:
                st.info(
                    f"**Preview:** {app_to_delete['role_title']} at {app_to_delete['company_name']} "
                    f"(Status: {app_to_delete['application_status']})"
                )

                # Double confirmation
                confirm = st.checkbox(f"I confirm I want to delete application #{delete_id}")

                if confirm:
                    if st.button("🗑️ Delete Permanently", type="primary"):
                        if tracker_db.delete_application(delete_id):
                            st.success(f"✅ Deleted application #{delete_id}")
                            st.rerun()
                        else:
                            st.error(f"❌ Failed to delete application #{delete_id}")
            else:
                st.error(f"Application ID {delete_id} not found in current filtered view.")

        st.caption(
            "Note: IDs are permanent and never reuse after deletion (standard database behavior)."
        )
else:
    st.info("No applications match your filters.")

# --- Import/Export ---
st.markdown("---")
with st.expander("Import / Export", expanded=False):
    col_a, col_b = st.columns(2)

    with col_a:
        if st.button("Export to CSV"):
            from config import settings

            csv_path = settings.output_dir / "tracker_export.csv"
            tracker_db.export_csv(csv_path)
            st.success(f"Exported to `{csv_path}`")

            if csv_path.exists():
                with open(csv_path, "rb") as handle:
                    st.download_button(
                        "Download CSV", data=handle.read(), file_name="tracker_export.csv"
                    )

    with col_b:
        uploaded = st.file_uploader("Import CSV", type=["csv"])
        if uploaded is not None:
            import tempfile

            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                tmp.write(uploaded.read())
                tmp_path = Path(tmp.name)
            count = tracker_db.import_csv(tmp_path)
            st.success(f"Imported {count} applications")
            st.rerun()

# --- Job Monitor ---
st.markdown("---")
with st.expander("Job Status Monitor", expanded=False):
    st.markdown("""
How it works:
1. Checks all applications currently marked as `active` that have a job URL.
2. If URL returns HTTP 404 or closure language, status changes to `closed`.
3. If closure language indicates expiry, status changes to `expired`.
4. If URL is reachable and no closure signal is found, status stays `active`.
        """)

    active_with_url = [
        a for a in tracker_db.list_applications(job_status="active") if a.get("jd_url")
    ]
    st.caption(f"Active jobs with URLs ready to check: {len(active_with_url)}")

    if st.button("Check All Active Job URLs"):
        with st.spinner("Checking job URLs..."):
            from jseeker.job_monitor import check_all_active_jobs

            changes = check_all_active_jobs()

        if changes:
            st.warning(f"Updated {len(changes)} job status value(s).")
            for change in changes:
                st.caption(
                    f"{change['company']} - {change['role']}: "
                    f"{change['old_status']} -> {change['new_status']}"
                )
        else:
            st.success("No status changes detected. Active URLs still appear live.")
