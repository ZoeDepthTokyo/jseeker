"""JSEEKER Tracker - Application CRM with three status pipelines."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
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

# --- Inline-Editable Table ---
if apps:
    df = pd.DataFrame(apps)

    display_cols = [
        "id",
        "company_name",
        "role_title",
        "jd_url",
        "relevance_score",
        "ats_score",
        "resume_status",
        "application_status",
        "job_status",
        "location",
        "created_at",
        "notes",
    ]
    available_cols = [c for c in display_cols if c in df.columns]

    if "relevance_score" in df.columns:
        df["relevance_score"] = df["relevance_score"].fillna(0) * 100

    column_config = {
        "id": st.column_config.NumberColumn("ID", disabled=True),
        "company_name": st.column_config.TextColumn("Company", disabled=True),
        "role_title": st.column_config.TextColumn("Role", disabled=True),
        "jd_url": st.column_config.LinkColumn("URL"),
        "relevance_score": st.column_config.NumberColumn("Relevance", format="%.0f%%", disabled=True),
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
        use_container_width=True,
        hide_index=True,
        key="tracker_editor",
    )

    if not df[available_cols].equals(edited_df):
        changed_count = 0
        for idx, row in edited_df.iterrows():
            original = df.iloc[idx]
            app_id = int(original["id"])
            changes = {}

            for col in [
                "application_status",
                "resume_status",
                "job_status",
                "notes",
                "jd_url",
                "location",
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
            st.toast(f"Saved {changed_count} change(s)!")
            st.rerun()
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
