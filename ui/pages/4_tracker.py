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
    df_with_salary = df_all[
        (df_all["salary_min"].notna()) | (df_all["salary_max"].notna())
    ].copy()

    if not df_with_salary.empty:
        with st.expander("Salary Analytics", expanded=False):
            # Calculate average salary
            df_with_salary["salary_avg"] = (
                df_with_salary["salary_min"].fillna(0) +
                df_with_salary["salary_max"].fillna(0)
            ) / 2
            df_with_salary["salary_avg"] = df_with_salary["salary_avg"].replace(0, pd.NA)
            df_with_salary = df_with_salary[df_with_salary["salary_avg"].notna()]

            if not df_with_salary.empty:
                # Format hover data
                df_with_salary["hover_text"] = (
                    df_with_salary["role_title"] +
                    "<br>" + df_with_salary["company_name"] +
                    "<br>Salary: " + df_with_salary["salary_currency"].fillna("USD") + " " +
                    df_with_salary["salary_min"].fillna(0).astype(int).astype(str) +
                    " - " +
                    df_with_salary["salary_max"].fillna(0).astype(int).astype(str)
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
                        "application_status": "Status"
                    },
                    title="Salary Distribution Over Time"
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
        "jd_url",
        "salary_min",
        "salary_max",
        "salary_currency",
        "application_status",
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

    column_config = {
        "id": st.column_config.NumberColumn("ID", disabled=True),
        "company_name": st.column_config.TextColumn(
            "Company",
            help="Edit if parser didn't extract correctly",
            disabled=False
        ),
        "role_title": st.column_config.TextColumn(
            "Role",
            help="Job title (click link icon → to view posting)",
            disabled=True,
            width="large"
        ),
        "jd_url": st.column_config.LinkColumn(
            "🔗",
            help="Click to open job posting in new tab",
            max_chars=500,
            disabled=True,
            width="small"
        ),
        "salary_min": st.column_config.NumberColumn(
            "Min Salary",
            help="Minimum salary (optional)",
            format="%d"
        ),
        "salary_max": st.column_config.NumberColumn(
            "Max Salary",
            help="Maximum salary (optional)",
            format="%d"
        ),
        "salary_currency": st.column_config.SelectboxColumn(
            "Currency",
            options=["USD", "EUR", "GBP", "MXN"],
            default="USD"
        ),
        "relevance_score": st.column_config.NumberColumn(
            "Relevance",
            format="%.0f%%",
            disabled=True,
            help="0-25: Low fit | 26-50: Medium fit | 51-75: Good fit | 76-100: Excellent fit. Used for prioritization and success rate analysis."
        ),
        "ats_score": st.column_config.NumberColumn("ATS Score", disabled=True),
        "application_status": st.column_config.SelectboxColumn(
            "App Status", options=[s.value for s in ApplicationStatus], required=True
        ),
        "resume_status": st.column_config.SelectboxColumn(
            "Resume Status", options=[s.value for s in ResumeStatus], required=True
        ),
        "job_status": st.column_config.SelectboxColumn(
            "Job Status", options=[s.value for s in JobStatus], required=True
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

    # Check if there are unsaved changes
    has_changes = not df[available_cols].equals(edited_df)

    if has_changes:
        st.warning("⚠️ You have unsaved changes")

        # Explicit save button
        if st.button("💾 Save All Changes", type="primary"):
            changed_count = 0
            for idx, row in edited_df.iterrows():
                original = df.iloc[idx]
                app_id = int(original["id"])
                changes = {}

                for col in [
                    "company_name",
                    "application_status",
                    "resume_status",
                    "job_status",
                    "notes",
                    "location",
                    "salary_min",
                    "salary_max",
                    "salary_currency",
                ]:
                    if col not in edited_df.columns or col not in original:
                        continue
                    new_val = row.get(col)
                    old_val = original.get(col)
                    if pd.isna(new_val) and pd.isna(old_val):
                        continue
                    if new_val != old_val:
                        changes[col] = None if pd.isna(new_val) else new_val

                if changes:
                    tracker_db.update_application(app_id, **changes)
                    changed_count += 1

            if changed_count > 0:
                st.success(f"✅ Saved {changed_count} change(s)!")
                st.rerun()
            else:
                st.info("No changes detected")
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
                    st.download_button("Download CSV", data=handle.read(), file_name="tracker_export.csv")

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
    st.markdown(
        """
How it works:
1. Checks all applications currently marked as `active` that have a job URL.
2. If URL returns HTTP 404 or closure language, status changes to `closed`.
3. If closure language indicates expiry, status changes to `expired`.
4. If URL is reachable and no closure signal is found, status stays `active`.
        """
    )

    active_with_url = [a for a in tracker_db.list_applications(job_status="active") if a.get("jd_url")]
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
