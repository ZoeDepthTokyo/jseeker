"""PROTEUS Dashboard — Application pipeline, metrics, quick actions."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from proteus.tracker import tracker_db

st.title("Dashboard")

# --- Metrics Row ---
stats = tracker_db.get_dashboard_stats()
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Applications", stats["total_applications"])
col2.metric("Active Applications", stats["active_applications"])
col3.metric("Avg ATS Score", f"{stats['avg_ats_score']}")
col4.metric("Monthly Cost", f"${stats['monthly_cost_usd']:.2f}")

st.markdown("---")

# --- Recent Applications ---
st.subheader("Recent Applications")

apps = tracker_db.list_applications()

if not apps:
    st.info("No applications yet. Start by creating a new resume from a job description.")
else:
    for app in apps[:10]:
        with st.container():
            cols = st.columns([3, 2, 1, 1, 1])
            cols[0].markdown(f"**{app.get('role_title', 'Unknown')}** — {app.get('company_name', 'Unknown')}")
            cols[1].caption(app.get("location", ""))

            # Status badges
            resume_status = app.get("resume_status", "draft")
            app_status = app.get("application_status", "not_applied")
            job_status = app.get("job_status", "active")

            status_colors = {
                "draft": "gray", "generated": "blue", "exported": "green",
                "submitted": "green", "not_applied": "gray", "applied": "blue",
                "interview": "green", "offer": "green", "rejected": "red",
                "ghosted": "orange", "active": "green", "closed": "red",
                "expired": "orange",
            }

            cols[2].caption(f"Resume: {resume_status}")
            cols[3].caption(f"App: {app_status}")
            cols[4].caption(f"Job: {job_status}")

            st.markdown("---")

# --- Quick Actions ---
st.subheader("Quick Actions")
col_a, col_b, col_c = st.columns(3)

with col_a:
    if st.button("New Resume", use_container_width=True):
        st.switch_page("pages/2_new_resume.py")

with col_b:
    if st.button("View Tracker", use_container_width=True):
        st.switch_page("pages/4_tracker.py")

with col_c:
    if st.button("Discover Jobs", use_container_width=True):
        st.switch_page("pages/5_job_discovery.py")
