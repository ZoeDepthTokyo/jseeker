"""PROTEUS Tracker — Application CRM with 3 status pipelines."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from proteus.tracker import tracker_db
from proteus.models import (
    Application, ApplicationStatus, ResumeStatus, JobStatus,
)

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

# --- Load Applications ---
kwargs = {}
if app_status_filter != "All":
    kwargs["application_status"] = app_status_filter
if resume_status_filter != "All":
    kwargs["resume_status"] = resume_status_filter
if job_status_filter != "All":
    kwargs["job_status"] = job_status_filter

apps = tracker_db.list_applications(**kwargs)

st.caption(f"Showing {len(apps)} applications")

# --- Table View ---
if apps:
    import pandas as pd
    df = pd.DataFrame(apps)
    display_cols = [
        "id", "company_name", "role_title", "location",
        "resume_status", "application_status", "job_status",
        "ats_score" if "ats_score" in (apps[0].keys() if apps else {}) else "relevance_score",
        "created_at",
    ]
    available_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(df[available_cols], use_container_width=True, hide_index=True)

    # --- Status Update ---
    st.markdown("---")
    st.subheader("Update Status")

    selected_id = st.selectbox("Application ID", options=[a["id"] for a in apps])

    col1, col2, col3 = st.columns(3)

    with col1:
        new_app_status = st.selectbox("Application Status", [s.value for s in ApplicationStatus])
        if st.button("Update App Status"):
            tracker_db.update_application_status(selected_id, "application_status", new_app_status)
            st.success(f"Updated application status to {new_app_status}")
            st.rerun()

    with col2:
        new_resume_status = st.selectbox("Resume Status", [s.value for s in ResumeStatus])
        if st.button("Update Resume Status"):
            tracker_db.update_application_status(selected_id, "resume_status", new_resume_status)
            st.success(f"Updated resume status to {new_resume_status}")
            st.rerun()

    with col3:
        new_job_status = st.selectbox("Job Status", [s.value for s in JobStatus])
        if st.button("Update Job Status"):
            tracker_db.update_application_status(selected_id, "job_status", new_job_status)
            st.success(f"Updated job status to {new_job_status}")
            st.rerun()

else:
    st.info("No applications match your filters.")

# --- Add Manual Application ---
st.markdown("---")
st.subheader("Add Application Manually")

with st.form("add_application"):
    company_name = st.text_input("Company Name")
    role_title = st.text_input("Role Title")
    location = st.text_input("Location")
    jd_url = st.text_input("JD URL")
    notes = st.text_area("Notes")

    if st.form_submit_button("Add Application"):
        if company_name and role_title:
            company_id = tracker_db.get_or_create_company(company_name)
            app = Application(
                company_id=company_id,
                role_title=role_title,
                location=location,
                jd_url=jd_url,
                notes=notes,
            )
            app_id = tracker_db.add_application(app)
            st.success(f"Added application (ID: {app_id})")
            st.rerun()
        else:
            st.error("Company name and role title are required.")

# --- Import/Export ---
st.markdown("---")
st.subheader("Import / Export")

col_a, col_b = st.columns(2)

with col_a:
    if st.button("Export to CSV"):
        from config import settings
        csv_path = settings.output_dir / "tracker_export.csv"
        tracker_db.export_csv(csv_path)
        st.success(f"Exported to `{csv_path}`")

        if csv_path.exists():
            with open(csv_path, "rb") as f:
                st.download_button("Download CSV", data=f.read(), file_name="tracker_export.csv")

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
st.subheader("Job Status Monitor")

if st.button("Check All Active Job URLs"):
    with st.spinner("Checking job URLs..."):
        from proteus.job_monitor import check_all_active_jobs
        changes = check_all_active_jobs()

    if changes:
        for change in changes:
            st.warning(
                f"**{change['company']} — {change['role']}**: "
                f"{change['old_status']} → {change['new_status']}"
            )
    else:
        st.success("All active jobs are still live.")
