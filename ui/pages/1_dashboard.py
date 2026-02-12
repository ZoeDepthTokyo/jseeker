"""JSEEKER Dashboard - Application pipeline, metrics, and quick actions."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

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
    st.caption(
        "Paste up to 20 job URLs (one per line). jSeeker will process them in parallel with learning pauses every 10 resumes."
    )

    # Import Starred Jobs button
    col_import, col_spacer = st.columns([2, 3])
    with col_import:
        if st.button("⭐ Import Starred Jobs", help="Load URLs from starred job discoveries"):
            starred_jobs = tracker_db.list_discoveries(status="starred")
            if starred_jobs:
                starred_urls = [job["url"] for job in starred_jobs if job.get("url")]
                if starred_urls:
                    st.session_state["dashboard_batch_urls_value"] = "\n".join(starred_urls)
                    st.success(f"Loaded {len(starred_urls)} starred job URLs")
                    st.rerun()
                else:
                    st.warning("No URLs found in starred jobs")
            else:
                st.info("No starred jobs found. Go to Job Discovery and star some jobs first.")

    # Initialize batch URLs from session state if available
    default_urls = st.session_state.pop("dashboard_batch_urls_value", "")

    url_blob = st.text_area(
        "Job URLs",
        placeholder="https://boards.greenhouse.io/company/jobs/123\nhttps://jobs.lever.co/company/456",
        height=140,
        key="dashboard_batch_urls",
        value=default_urls,
    )

    raw_urls = [line.strip() for line in url_blob.splitlines() if line.strip()]
    urls = [u for u in raw_urls if u.startswith("http://") or u.startswith("https://")]

    if raw_urls and len(urls) != len(raw_urls):
        st.warning("Some lines were ignored because they are not valid http(s) URLs.")

    # Show warning if exceeding max batch size
    if len(urls) > 20:
        st.warning(
            f"⚠️ You have {len(urls)} URLs. Only the first 20 will be processed (batch limit)."
        )

    # Initialize batch processor in session state
    if "batch_processor" not in st.session_state:
        from jseeker.batch_processor import BatchProcessor

        st.session_state.batch_processor = BatchProcessor(max_workers=5)

    if "batch_progress" not in st.session_state:
        st.session_state.batch_progress = None

    if "batch_running" not in st.session_state:
        st.session_state.batch_running = False

    # Control buttons
    col_btn1, col_btn2, col_btn3 = st.columns(3)

    with col_btn1:
        if st.button(
            "▶️ Start Batch",
            disabled=not urls or st.session_state.batch_running,
            width="stretch",
            key="batch_start_btn",
        ):
            # Progress callback to update session state
            def on_progress(progress):
                st.session_state.batch_progress = progress

            # Submit batch
            batch_id = st.session_state.batch_processor.submit_batch(
                urls, progress_callback=on_progress
            )
            st.session_state.batch_running = True
            st.session_state.batch_id = batch_id
            st.rerun()

    with col_btn2:
        if st.button(
            (
                "⏸️ Pause"
                if not (st.session_state.batch_progress and st.session_state.batch_progress.paused)
                else "▶️ Resume"
            ),
            disabled=not st.session_state.batch_running,
            width="stretch",
            key="batch_pause_btn",
        ):
            if st.session_state.batch_progress and st.session_state.batch_progress.paused:
                st.session_state.batch_processor.resume()
            else:
                st.session_state.batch_processor.pause()
            st.rerun()

    with col_btn3:
        if st.button(
            "⏹️ Stop",
            disabled=not st.session_state.batch_running,
            width="stretch",
            key="batch_stop_btn",
        ):
            st.session_state.batch_processor.stop()
            st.session_state.batch_running = False
            st.rerun()

    # Progress display
    if st.session_state.batch_progress:
        progress = st.session_state.batch_progress

        # Auto-refresh control
        col_progress, col_refresh = st.columns([4, 1])

        with col_progress:
            # Segment info
            segment_text = ""
            if progress.total_segments > 1:
                segment_text = f"Batch {progress.current_segment}/{progress.total_segments} "
                segment_range_start = (progress.current_segment - 1) * 10 + 1
                segment_range_end = min(progress.current_segment * 10, progress.total)
                segment_text += f"({segment_range_start}-{segment_range_end}) • "

            # Progress bar
            progress_text = f"{segment_text}Processing {progress.completed + progress.running}/{progress.total} jobs "
            progress_text += f"({progress.completed} completed, {progress.failed} failed, {progress.skipped} skipped)"

            st.progress(progress.progress_pct / 100, text=progress_text)

        with col_refresh:
            # Manual refresh button
            if st.button("🔄 Refresh", key="batch_refresh_btn", help="Manually refresh progress"):
                st.rerun()

        # Auto-refresh every 2 seconds while batch is running
        if st.session_state.batch_running and not progress.paused and not progress.stopped:
            if progress.completed + progress.failed + progress.skipped < progress.total:
                import time

                st.empty()  # Placeholder for rerun trigger
                time.sleep(2)
                st.rerun()

        # Status text
        if progress.learning_phase:
            st.info("🧠 Learning patterns from completed resumes... will auto-resume shortly.")
        elif progress.paused:
            st.info("⏸️ Batch paused. Click Resume to continue.")
        elif progress.stopped:
            st.warning("⏹️ Batch stopped.")
        elif progress.completed + progress.failed + progress.skipped == progress.total:
            st.success(
                f"✅ Batch complete! {progress.completed} succeeded, {progress.failed} failed, {progress.skipped} skipped."
            )
            st.session_state.batch_running = False
        else:
            status_text = f"Running: {progress.running} active workers"
            if progress.estimated_remaining_seconds:
                mins = int(progress.estimated_remaining_seconds / 60)
                secs = int(progress.estimated_remaining_seconds % 60)
                status_text += f" • ETA: {mins}m {secs}s"
            st.caption(status_text)

        # Worker status expander
        with st.expander(
            f"Worker Status ({len([w for w in progress.workers.values() if w.is_active])} active)",
            expanded=False,
        ):
            for worker_id, worker in sorted(progress.workers.items()):
                if worker.is_active:
                    st.caption(f"**Worker {worker_id}**: {worker.current_url or 'idle'}")
                else:
                    st.caption(
                        f"Worker {worker_id}: {worker.jobs_completed} completed, {worker.jobs_failed} failed"
                    )

        # Detailed results (after completion)
        if (
            progress.completed + progress.failed + progress.skipped == progress.total
            and not progress.stopped
        ):
            with st.expander("Detailed Results", expanded=False):
                jobs = st.session_state.batch_processor.get_all_jobs()
                for job in jobs:
                    if job.status.value == "completed":
                        st.success(
                            f"✅ {job.url}: {job.result.get('company')} - {job.result.get('role')}"
                        )
                    elif job.status.value == "failed":
                        st.error(f"❌ {job.url}: {job.error}")
                    elif job.status.value == "skipped":
                        st.info(f"⏭️ {job.url}: {job.error}")

st.markdown("---")

# --- Quick Actions ---
st.subheader("Quick Actions")
col_a, col_b, col_c = st.columns(3)

with col_a:
    if st.button("New Resume", width="stretch"):
        st.switch_page("pages/2_new_resume.py")

with col_b:
    if st.button("View Tracker", width="stretch"):
        st.switch_page("pages/4_tracker.py")

with col_c:
    if st.button("Discover Jobs", width="stretch"):
        st.switch_page("pages/5_job_discovery.py")
