"""JSEEKER Dashboard - Application pipeline, metrics, and quick actions."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

from config import settings
from jseeker.jd_parser import extract_jd_from_url
from jseeker.pipeline import run_pipeline
from jseeker.tracker import tracker_db


st.title("Dashboard")

# --- Metrics Row ---
stats = tracker_db.get_dashboard_stats()
apps_all = tracker_db.list_applications()
week_ago = datetime.now() - timedelta(days=7)

this_week_count = 0
for app in apps_all:
    created_raw = app.get("created_at")
    if not created_raw:
        continue
    try:
        created_at = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
    except ValueError:
        continue
    if created_at >= week_ago:
        this_week_count += 1

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Applications", stats["total_applications"])
col2.metric("Active Applications", stats["active_applications"])
col3.metric("This Week", this_week_count)
col4.metric("Avg ATS Score", f"{stats['avg_ats_score']}")
col5.metric("Monthly Cost", f"${stats['monthly_cost_usd']:.2f}")

st.markdown("---")

# --- Recent Applications ---
with st.expander("Recent Applications", expanded=True):
    apps = tracker_db.list_applications()

    if not apps:
        st.info("No applications yet. Start by creating a new resume from a job description.")
    else:
        for app in apps[:10]:
            with st.container():
                cols = st.columns([3, 2, 1, 1, 1])
                cols[0].markdown(
                    f"**{app.get('role_title', 'Unknown')}** - {app.get('company_name', 'Unknown')}"
                )
                cols[1].caption(app.get("location", ""))
                cols[2].caption(f"Resume: {app.get('resume_status', 'draft')}")
                cols[3].caption(f"App: {app.get('application_status', 'not_applied')}")
                cols[4].caption(f"Job: {app.get('job_status', 'active')}")
                st.markdown("---")

# --- Batch URL Intake ---
with st.expander("Batch Generate From Job URLs", expanded=False):
    st.caption("Paste one job URL per line. jSeeker will extract each JD and generate resumes in sequence.")
    url_blob = st.text_area(
        "Job URLs",
        placeholder="https://boards.greenhouse.io/company/jobs/123\nhttps://jobs.lever.co/company/456",
        height=140,
        key="dashboard_batch_urls",
    )

    raw_urls = [line.strip() for line in url_blob.splitlines() if line.strip()]
    urls = [u for u in raw_urls if u.startswith("http://") or u.startswith("https://")]

    if raw_urls and len(urls) != len(raw_urls):
        st.warning("Some lines were ignored because they are not valid http(s) URLs.")

    if st.button("Generate Resumes For URLs", disabled=not urls, use_container_width=True):
        successes = []
        skipped = []
        failures = []

        progress = st.progress(0, text="Starting batch generation...")

        for idx, url in enumerate(urls, start=1):
            progress_pct = int(((idx - 1) / len(urls)) * 100)
            progress.progress(progress_pct, text=f"Processing {idx}/{len(urls)}: {url}")

            if tracker_db.is_url_known(url):
                skipped.append((url, "URL already exists in discoveries/applications"))
                continue

            try:
                jd_text = extract_jd_from_url(url)
                if not jd_text:
                    raise ValueError("Could not extract job description from URL")

                result = run_pipeline(jd_text=jd_text, jd_url=url, output_dir=settings.output_dir)
                created = tracker_db.create_from_pipeline(result)
                tracker_db.update_application(created["application_id"], resume_status="exported")

                successes.append(
                    {
                        "url": url,
                        "application_id": created["application_id"],
                        "company": result.company,
                        "role": result.role,
                    }
                )
            except Exception as exc:
                failures.append((url, str(exc)))

        progress.progress(100, text="Batch generation complete.")

        st.success(f"Generated {len(successes)} resume(s).")
        if skipped:
            st.info(f"Skipped {len(skipped)} URL(s) already known to the tracker.")
        if failures:
            st.error(f"Failed on {len(failures)} URL(s).")

        for item in successes:
            st.caption(
                f"Created application #{item['application_id']}: "
                f"{item['company'] or 'Unknown'} - {item['role'] or 'Role'}"
            )

        for url, reason in skipped:
            st.caption(f"Skipped: {url} ({reason})")

        for url, reason in failures:
            st.caption(f"Failed: {url} ({reason})")

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
