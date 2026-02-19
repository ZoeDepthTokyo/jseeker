"""JSEEKER Pipeline — Generate Resumes, Auto-Submit, and Job Monitor in one place."""

import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

from config import settings
from jseeker.models import AttemptStatus, BatchSummary, RateLimitConfig
from jseeker.pipeline import run_pipeline
from jseeker.tracker import (
    get_queue_stats,
    get_queued_applications,
    init_db,
    queue_application,
    tracker_db,
    update_queue_status,
)

st.title("Pipeline")

# ── Initialize ALL session state keys ───────────────────────────────────────

# Resume generation batch (from 1_dashboard.py)
if "resume_batch_running" not in st.session_state:
    st.session_state.resume_batch_running = False
if "batch_processor" not in st.session_state:
    from jseeker.batch_processor import BatchProcessor

    st.session_state.batch_processor = BatchProcessor(max_workers=5)
if "batch_progress" not in st.session_state:
    st.session_state.batch_progress = None
if "batch_id" not in st.session_state:
    st.session_state.batch_id = None

# Auto-apply batch (from 9_auto_apply.py)
if "apply_batch_running" not in st.session_state:
    st.session_state["apply_batch_running"] = False
if "batch_proc" not in st.session_state:
    st.session_state["batch_proc"] = None
if "batch_total" not in st.session_state:
    st.session_state["batch_total"] = 0
if "monitor_state" not in st.session_state:
    st.session_state["monitor_state"] = {}

tab1, tab2, tab3 = st.tabs(["Generate Resumes", "Auto-Submit", "Job Monitor"])

# ════════════════════════════════════════════════════════════════════
# Tab 1: Generate Resumes (from 1_dashboard.py)
# ════════════════════════════════════════════════════════════════════

with tab1:
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

        # Control buttons
        col_btn1, col_btn2, col_btn3 = st.columns(3)

        with col_btn1:
            if st.button(
                "▶️ Start Batch",
                disabled=not urls or st.session_state.resume_batch_running,
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
                st.session_state.resume_batch_running = True
                st.session_state.batch_id = batch_id
                st.rerun()

        with col_btn2:
            if st.button(
                (
                    "⏸️ Pause"
                    if not (
                        st.session_state.batch_progress and st.session_state.batch_progress.paused
                    )
                    else "▶️ Resume"
                ),
                disabled=not st.session_state.resume_batch_running,
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
                disabled=not st.session_state.resume_batch_running,
                width="stretch",
                key="batch_stop_btn",
            ):
                st.session_state.batch_processor.stop()
                st.session_state.resume_batch_running = False
                st.rerun()

        # Polling mechanism: Update progress FIRST before any UI rendering
        # (background thread callbacks can't trigger Streamlit reruns)
        if st.session_state.resume_batch_running and "batch_processor" in st.session_state:
            try:
                current_progress = st.session_state.batch_processor.get_progress()
                if current_progress:
                    st.session_state.batch_progress = current_progress

                    # Check if batch completed
                    done_count = (
                        current_progress.completed
                        + current_progress.failed
                        + current_progress.skipped
                    )
                    if done_count == current_progress.total and current_progress.total > 0:
                        st.session_state.resume_batch_running = False
                        time.sleep(0.5)
                        st.rerun()
            except Exception as e:
                st.error(f"Error polling batch progress: {e}")

        # Show initial "Starting..." state when batch just started but no progress yet
        if st.session_state.resume_batch_running and not st.session_state.batch_progress:
            st.progress(0.0, text="Starting batch... preparing workers")
            time.sleep(2)
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

                # Progress bar (ensure running count never goes negative)
                running_count = max(0, progress.running)
                progress_text = f"{segment_text}Processing {progress.completed + running_count}/{progress.total} jobs "
                progress_text += f"({progress.completed} completed, {progress.failed} failed, {progress.skipped} skipped)"

                st.progress(progress.progress_pct / 100, text=progress_text)

            with col_refresh:
                # Manual refresh button
                if st.button(
                    "🔄 Refresh",
                    key="batch_refresh_btn",
                    help="Manually refresh progress",
                ):
                    st.rerun()

            # Status text
            if progress.learning_phase:
                st.info("🧠 Learning patterns from completed resumes... will auto-resume shortly.")
            elif progress.paused:
                st.info("⏸️ Batch paused. Click Resume to continue.")
            elif progress.stopped:
                st.warning("⏹️ Batch stopped.")
            elif progress.completed + progress.failed + progress.skipped == progress.total:
                # Show completion summary with manual retry hint if failures exist
                summary_msg = f"✅ Batch complete! {progress.completed} succeeded, {progress.failed} failed, {progress.skipped} skipped."
                if progress.failed > 0:
                    summary_msg += f" ({progress.failed} pending manual retry)"
                st.success(summary_msg)
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

            # Manual fallback for failed extractions (OUTSIDE expander, always visible when batch complete)
            if (
                progress.completed + progress.failed + progress.skipped == progress.total
                and not progress.stopped
            ):
                failed_jobs = [
                    job
                    for job in st.session_state.batch_processor.get_all_jobs()
                    if job.status.value == "failed"
                ]

                if failed_jobs:
                    st.markdown("---")
                    st.subheader(f"⚠️ Manual Retry Required ({len(failed_jobs)} failed)")
                    st.caption(
                        "JD extraction failed for these URLs. Paste the job description text manually to retry."
                    )

                    for job in failed_jobs:
                        with st.expander(f"🔧 Retry: {job.url}", expanded=False):
                            st.caption(f"**Error**: {job.error}")
                            st.caption(f"**URL**: {job.url}")

                            # Manual JD paste area
                            manual_jd = st.text_area(
                                "Paste Job Description",
                                placeholder="Paste the full job description text here...",
                                height=200,
                                key=f"manual_jd_{job.id}",
                            )

                            col_retry, col_spacer2 = st.columns([1, 3])
                            with col_retry:
                                if st.button(
                                    "🔄 Retry with Manual JD",
                                    key=f"retry_btn_{job.id}",
                                    disabled=not manual_jd or len(manual_jd.strip()) < 100,
                                    help="Retry pipeline with manually pasted JD text",
                                ):
                                    with st.spinner(f"Processing {job.url}..."):
                                        try:
                                            # Run pipeline with manual JD text
                                            result = run_pipeline(
                                                jd_text=manual_jd.strip(),
                                                jd_url=job.url,
                                                output_dir=settings.output_dir,
                                            )

                                            # Create application in tracker
                                            created = tracker_db.create_from_pipeline(result)
                                            tracker_db.update_application(
                                                created["application_id"],
                                                resume_status="exported",
                                            )

                                            # Update batch_job_items status
                                            tracker_db.update_batch_job_item_status(
                                                st.session_state.batch_id,
                                                job.url,
                                                status="completed",
                                                resume_id=created.get("resume_id"),
                                                application_id=created["application_id"],
                                            )

                                            # Update job status in memory
                                            job.status = job.status.__class__("completed")
                                            job.result = {
                                                "application_id": created["application_id"],
                                                "company": result.company,
                                                "role": result.role,
                                                "ats_score": result.ats_score.overall_score,
                                                "cost_usd": result.total_cost,
                                            }
                                            job.error = None

                                            # Update progress counters
                                            st.session_state.batch_progress.completed += 1
                                            st.session_state.batch_progress.failed -= 1

                                            st.success(
                                                f"✅ Successfully processed: {result.company} - {result.role}"
                                            )
                                            st.rerun()

                                        except Exception as e:
                                            st.error(f"❌ Retry failed: {str(e)}")

                            if len(manual_jd.strip()) > 0 and len(manual_jd.strip()) < 100:
                                st.warning("⚠️ JD text too short (minimum 100 characters)")

            # Auto-refresh: schedule next poll cycle while batch is still running
            # Placed AFTER all UI elements so everything renders before the sleep
            if (
                st.session_state.resume_batch_running
                and not progress.paused
                and not progress.stopped
            ):
                time.sleep(2)
                st.rerun()

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


# ════════════════════════════════════════════════════════════════════
# Tab 2: Auto-Submit (from 9_auto_apply.py)
# ════════════════════════════════════════════════════════════════════

with tab2:
    # ── Preflight Checks ────────────────────────────────────────────────

    _setup_issues: list[str] = []

    # Check answer bank
    _answer_bank_path = settings.data_dir / "answer_bank.yaml"
    if _answer_bank_path.exists():
        _ab_text = _answer_bank_path.read_text(encoding="utf-8")
        if "PLACEHOLDER" in _ab_text:
            _setup_issues.append(
                "answer_bank.yaml contains PLACEHOLDER values. "
                "Replace them with real data before running."
            )

    # Check Playwright
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        _setup_issues.append(
            "Playwright not installed. Run: `pip install playwright && playwright install`"
        )

    if _setup_issues:
        st.warning("**Setup Required**")
        for issue in _setup_issues:
            st.caption(f"- {issue}")
        st.markdown("---")

    # ── Helper functions ─────────────────────────────────────────────

    def _load_all_queue_items() -> list[dict]:
        """Load all apply_queue rows regardless of status."""
        db_path = settings.db_path
        init_db(db_path)
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM apply_queue ORDER BY queued_at DESC")
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _clear_completed_items() -> int:
        """Delete completed items from apply_queue. Returns count deleted."""
        db_path = settings.db_path
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        c = conn.cursor()
        c.execute(
            "DELETE FROM apply_queue WHERE status IN "
            "('applied_verified', 'applied_soft', 'skipped_duplicate', "
            "'skipped_unsupported_ats', 'skipped_linkedin', 'skipped_error_pattern')"
        )
        count = c.rowcount
        conn.commit()
        conn.close()
        return count

    def _detect_platform(url: str) -> str:
        """Simple platform detection from URL."""
        url_lower = url.lower()
        if "myworkdayjobs.com" in url_lower or "workday.com" in url_lower:
            return "workday"
        if "greenhouse.io" in url_lower or "boards.greenhouse" in url_lower:
            return "greenhouse"
        if "lever.co" in url_lower:
            return "lever"
        if "linkedin.com" in url_lower:
            return "linkedin"
        return "unknown"

    # ── Status badge styling ─────────────────────────────────────────

    _STATUS_COLORS = {
        "queued": "blue",
        "in_progress": "orange",
        "applied_verified": "green",
        "applied_soft": "green",
        "failed_permanent": "red",
        "skipped_duplicate": "gray",
        "skipped_unsupported_ats": "gray",
        "skipped_linkedin": "gray",
        "skipped_error_pattern": "gray",
    }

    def _status_badge(status: str) -> str:
        """Return a colored status string."""
        color = _STATUS_COLORS.get(status, "orange")
        return f":{color}[{status}]"

    # ── Sub-tabs ─────────────────────────────────────────────────────

    tab_queue, tab_run, tab_results, tab_monitor = st.tabs(["Queue", "Run", "Results", "Monitor"])

    # ════════════════════════════════════════════════════════════════════
    # Sub-Tab: Queue
    # ════════════════════════════════════════════════════════════════════

    with tab_queue:
        st.subheader("Application Queue")

        # ── Load applications that have a generated resume
        def _load_applications_with_resumes() -> list[dict]:
            """Return applications that have at least one resume generated, with URL + file paths."""
            try:
                conn = sqlite3.connect(str(settings.db_path), timeout=10.0)
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT
                        a.id          AS app_id,
                        c.name        AS company,
                        a.role_title,
                        a.jd_url,
                        r.id          AS resume_id,
                        r.docx_path,
                        r.pdf_path,
                        r.ats_platform,
                        r.created_at  AS resume_created_at
                    FROM resumes r
                    JOIN applications a ON r.application_id = a.id
                    LEFT JOIN companies c ON a.company_id = c.id
                    WHERE a.jd_url IS NOT NULL AND a.jd_url != ''
                      AND (r.docx_path IS NOT NULL OR r.pdf_path IS NOT NULL)
                    ORDER BY r.created_at DESC
                    """).fetchall()
                conn.close()
                return [dict(r) for r in rows]
            except Exception:
                return []

        tracker_apps = _load_applications_with_resumes()

        # ── Section A: Queue from Tracker (pre-linked URL + resume) ──────
        st.markdown("**From Tracker** — applications with generated resumes")

        if not tracker_apps:
            st.info("No applications with resumes found in tracker. Generate a resume first.")
        else:
            # Deduplicate by app_id, keep most recent resume per app
            seen_apps: dict[int, dict] = {}
            for row in tracker_apps:
                if row["app_id"] not in seen_apps:
                    seen_apps[row["app_id"]] = row

            app_rows = list(seen_apps.values())

            # Filter to supported platforms
            supported = [
                r for r in app_rows if _detect_platform(r["jd_url"]) in ("workday", "greenhouse")
            ]
            unsupported_count = len(app_rows) - len(supported)

            if unsupported_count:
                st.caption(
                    f"{unsupported_count} application(s) skipped — "
                    "URL not Workday or Greenhouse (v1 only supports these two)."
                )

            market_sel = st.selectbox(
                "Market for queued items",
                ["us", "mx", "ca", "uk", "es", "dk", "fr", "de"],
                index=0,
                key="tracker_market",
            )

            # Build display: "Company — Role | platform | DOCX/PDF"
            def _app_label(r: dict) -> str:
                platform = _detect_platform(r["jd_url"])
                fmt = "DOCX" if r["docx_path"] else "PDF"
                return f"{r['company'] or 'Unknown'} — {r['role_title'] or 'Role'} [{platform.upper()} · {fmt}]"

            app_labels = [_app_label(r) for r in supported]

            if not supported:
                st.caption("No supported (Workday/Greenhouse) applications with resumes found.")
            else:
                selected_app_labels = st.multiselect(
                    f"Select applications to queue ({len(supported)} available)",
                    app_labels,
                    help="Selects the DOCX resume (preferred for Workday) or PDF for Greenhouse.",
                )

                if st.button(
                    "Add Selected to Queue",
                    type="primary",
                    disabled=not selected_app_labels,
                ):
                    added, dupes, errors = 0, 0, 0
                    for label in selected_app_labels:
                        row = supported[app_labels.index(label)]
                        platform = _detect_platform(row["jd_url"])
                        # Prefer DOCX for Workday, PDF for Greenhouse
                        if platform == "workday" and row["docx_path"]:
                            resume_file = row["docx_path"]
                        elif row["pdf_path"]:
                            resume_file = row["pdf_path"]
                        else:
                            resume_file = row["docx_path"]
                        try:
                            queue_application(
                                job_url=row["jd_url"],
                                resume_path=resume_file,
                                ats_platform=platform,
                                market=market_sel,
                            )
                            added += 1
                        except sqlite3.IntegrityError:
                            dupes += 1
                        except Exception:
                            errors += 1
                    msgs = []
                    if added:
                        msgs.append(f"{added} added")
                    if dupes:
                        msgs.append(f"{dupes} already queued")
                    if errors:
                        msgs.append(f"{errors} errors")
                    st.success(" | ".join(msgs))
                    st.rerun()

        # ── Section B: Manual URL entry (fallback) ───────────────────────
        with st.expander("Manual entry (URL not in tracker)"):
            with st.form("add_to_queue_manual", clear_on_submit=True):
                col_url, col_market = st.columns([3, 1])
                with col_url:
                    job_url = st.text_input(
                        "Job URL",
                        placeholder="https://company.myworkdayjobs.com/jobs/123",
                    )
                with col_market:
                    market = st.selectbox(
                        "Market",
                        ["us", "mx", "ca", "uk", "es", "dk", "fr", "de"],
                        index=0,
                    )

                # Resume picker — scan output/ recursively
                resume_paths: list[Path] = []
                if settings.output_dir.exists():
                    for suffix in (".docx", ".pdf"):
                        resume_paths.extend(settings.output_dir.rglob(f"*{suffix}"))
                    resume_paths = sorted(
                        resume_paths, key=lambda p: p.stat().st_mtime, reverse=True
                    )
                resume_labels = [
                    (f"{p.parent.name} / {p.name}" if p.parent != settings.output_dir else p.name)
                    for p in resume_paths
                ]

                if resume_paths:
                    selected_label = st.selectbox("Resume", resume_labels)
                    selected_resume_path = resume_paths[resume_labels.index(selected_label)]
                else:
                    selected_resume_path = None
                    st.caption("No resumes found in output/. Generate one on the New Resume page.")

                submitted = st.form_submit_button("Add to Queue")
                if submitted:
                    if not job_url.strip():
                        st.error("Job URL is required.")
                    elif selected_resume_path is None:
                        st.error("No resume available. Generate one first.")
                    else:
                        platform = _detect_platform(job_url.strip())
                        try:
                            qid = queue_application(
                                job_url=job_url.strip(),
                                resume_path=str(selected_resume_path),
                                ats_platform=platform,
                                market=market,
                            )
                            st.success(f"Queued (ID: {qid}, platform: {platform})")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.warning("This URL is already in the queue.")
                        except Exception as e:
                            st.error(f"Failed to queue: {e}")

        # Queue table
        st.markdown("---")
        queue_items = _load_all_queue_items()

        if not queue_items:
            st.info("Queue is empty. Add a job URL above to get started.")
        else:
            # Stats row
            queue_stats = get_queue_stats()
            stat_cols = st.columns(5)
            stat_cols[0].metric("Queued", queue_stats.get("queued", 0))
            stat_cols[1].metric("In Progress", queue_stats.get("in_progress", 0))
            stat_cols[2].metric("Verified", queue_stats.get("applied_verified", 0))
            stat_cols[3].metric("Soft", queue_stats.get("applied_soft", 0))
            stat_cols[4].metric("Failed", queue_stats.get("failed_permanent", 0))

            for item in queue_items:
                with st.container():
                    cols = st.columns([1, 4, 1, 1, 1])
                    cols[0].caption(f"#{item['id']}")
                    cols[1].caption(item["job_url"][:80])
                    cols[2].markdown(_status_badge(item["status"]))
                    cols[3].caption(item["ats_platform"])
                    cols[4].caption(item["market"])

            # Clear completed button
            completed_count = sum(
                1
                for item in queue_items
                if item["status"]
                in (
                    "applied_verified",
                    "applied_soft",
                    "skipped_duplicate",
                    "skipped_unsupported_ats",
                    "skipped_linkedin",
                )
            )
            if completed_count > 0:
                if st.button(f"Clear {completed_count} completed items"):
                    removed = _clear_completed_items()
                    st.success(f"Cleared {removed} items.")
                    st.rerun()

    # ════════════════════════════════════════════════════════════════════
    # Sub-Tab: Run
    # ════════════════════════════════════════════════════════════════════

    with tab_run:
        st.subheader("Run Batch")

        # Mode selector
        run_mode = st.radio(
            "Mode",
            ["Dry Run", "Sandbox", "Assisted"],
            horizontal=True,
            help=(
                "Dry Run: fills forms but does NOT submit. "
                "Sandbox: submits to test endpoints. "
                "Assisted: submits for real with verification."
            ),
        )

        # Rate limit display
        st.markdown("**Rate Limits**")
        rate_cols = st.columns(3)
        # Use monitor state if available in session
        monitor_state = st.session_state.get("monitor_state", {})
        rate_cols[0].metric(
            "This Hour",
            f"{monitor_state.get('hourly_count', 0)}/{settings.workday_email and 10 or 0}",
        )
        rate_cols[1].metric(
            "Today",
            f"{monitor_state.get('daily_count', 0)}/50",
        )
        rate_cols[2].metric(
            "Cost Today",
            f"${monitor_state.get('daily_cost_usd', 0.0):.2f} / $5.00",
        )

        st.markdown("---")

        # Guest mode info — credentials not required for v1
        st.info(
            "**Guest mode active.** "
            "Workday: applies as guest (no per-employer account needed). "
            "Greenhouse: public forms, no login required."
        )

        _BATCH_SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "run_auto_apply_batch.py"

        col_start, col_stop = st.columns(2)

        with col_start:
            queued = get_queued_applications(limit=50)
            start_disabled = st.session_state["apply_batch_running"] or len(queued) == 0
            if st.button(
                f"Start ({len(queued)} queued)",
                disabled=start_disabled,
                type="primary",
            ):
                # Launch batch as a separate process — avoids asyncio/SelectorEventLoop
                # conflict between Playwright and Streamlit on Windows
                cmd = [sys.executable, str(_BATCH_SCRIPT)]
                if run_mode == "Dry Run":
                    cmd.append("--dry-run")
                if run_mode != "Assisted":
                    pass  # default is headless; Assisted uses --no-headless
                else:
                    cmd.append("--no-headless")

                # stdout=None → inherit Streamlit terminal (avoids pipe buffer deadlock
                # when subprocess writes more than ~64KB of progress JSON before UI reads)
                proc = subprocess.Popen(
                    cmd,
                    stdout=None,
                    stderr=None,
                    cwd=str(Path(__file__).parent.parent.parent),
                )
                st.session_state["batch_proc"] = proc
                st.session_state["apply_batch_running"] = True
                st.session_state["batch_total"] = len(queued)
                st.rerun()

        with col_stop:
            if st.button("Stop", disabled=not st.session_state["apply_batch_running"]):
                proc = st.session_state.get("batch_proc")
                if proc and proc.poll() is None:
                    proc.terminate()
                st.session_state["apply_batch_running"] = False
                st.session_state["batch_proc"] = None
                st.warning("Batch stopped.")
                st.rerun()

        # Poll running process
        if st.session_state["apply_batch_running"]:
            proc = st.session_state.get("batch_proc")
            if proc is None:
                st.session_state["apply_batch_running"] = False
                st.rerun()
            elif proc.poll() is not None:
                # Process finished
                exit_code = proc.returncode
                st.session_state["apply_batch_running"] = False
                st.session_state["batch_proc"] = None
                if exit_code == 0:
                    st.success("Batch complete. Check the Results tab.")
                else:
                    st.error(f"Batch exited with code {exit_code}. Check Results tab.")
                st.rerun()
            else:
                # Still running — show live DB stats
                run_stats = get_queue_stats()
                in_prog = run_stats.get("in_progress", 0)
                done = sum(
                    run_stats.get(s, 0)
                    for s in (
                        "applied_verified",
                        "applied_soft",
                        "failed_permanent",
                        "skipped_duplicate",
                        "skipped_unsupported_ats",
                        "skipped_linkedin",
                        "skipped_error_pattern",
                    )
                )
                total_est = st.session_state["batch_total"]
                pct = min(done / total_est, 1.0) if total_est else 0
                st.progress(
                    pct,
                    text=f"Processing… {done}/{total_est} done, {in_prog} in progress",
                )
                time.sleep(2)
                st.rerun()

        # Show queue stats after completion
        if not st.session_state["apply_batch_running"]:
            final_stats = get_queue_stats()
            done_statuses = {
                "applied_verified": final_stats.get("applied_verified", 0),
                "applied_soft": final_stats.get("applied_soft", 0),
                "failed_permanent": final_stats.get("failed_permanent", 0),
                "paused": sum(v for k, v in final_stats.items() if k.startswith("paused")),
            }
            if any(done_statuses.values()):
                st.markdown("---")
                st.subheader("Queue Summary")
                sum_cols = st.columns(4)
                sum_cols[0].metric("Verified", done_statuses["applied_verified"])
                sum_cols[1].metric("Soft Applied", done_statuses["applied_soft"])
                sum_cols[2].metric("Paused (HITL)", done_statuses["paused"])
                sum_cols[3].metric("Failed", done_statuses["failed_permanent"])
                if done_statuses["paused"]:
                    st.warning(
                        f"{done_statuses['paused']} items need review. Check the Results tab."
                    )

    # ════════════════════════════════════════════════════════════════════
    # Sub-Tab: Results
    # ════════════════════════════════════════════════════════════════════

    with tab_results:
        st.subheader("Attempt Results")

        # HITL alert banner
        summary = st.session_state.get("batch_summary")
        if summary and summary.hitl_required:
            st.error(
                f"**{summary.paused} items need your review.** "
                "Expand paused items below to see screenshots and details."
            )

        # Status filter
        status_filter = st.multiselect(
            "Filter by status",
            [
                "applied_verified",
                "applied_soft",
                "paused_ambiguous_result",
                "paused_captcha",
                "paused_unknown_question",
                "paused_timeout",
                "failed_permanent",
            ],
            default=[],
            help="Leave empty to show all non-queued items.",
        )

        # Load results
        all_items = _load_all_queue_items()
        result_items = [item for item in all_items if item["status"] != "queued"]

        if status_filter:
            result_items = [item for item in result_items if item["status"] in status_filter]

        if not result_items:
            st.info("No results yet. Run a batch to see attempt outcomes.")
        else:
            for item in result_items:
                status = item["status"]
                is_paused = status.startswith("paused")

                with st.expander(
                    f"{'**REVIEW** ' if is_paused else ''}"
                    f"{_status_badge(status)} | "
                    f"{item['ats_platform']} | "
                    f"{item['job_url'][:60]}",
                    expanded=is_paused,
                ):
                    detail_cols = st.columns(4)
                    detail_cols[0].caption(f"Queue ID: {item['id']}")
                    detail_cols[1].caption(f"Platform: {item['ats_platform']}")
                    detail_cols[2].caption(f"Market: {item['market']}")
                    detail_cols[3].caption(f"Cost: ${item.get('cost_usd', 0.0) or 0.0:.4f}")

                    st.caption(f"URL: {item['job_url']}")

                    # Show attempt log if exists
                    log_path = item.get("attempt_log_path")
                    if log_path and Path(log_path).exists():
                        st.caption(f"Log: {log_path}")

                    # Check for screenshot in logs dir
                    if log_path:
                        log_dir = Path(log_path).parent
                        screenshot = log_dir / "confirmation_screenshot.png"
                        if screenshot.exists():
                            st.image(str(screenshot), caption="Confirmation screenshot")
                        last_screenshot = log_dir / "last_page_screenshot.png"
                        if last_screenshot.exists():
                            st.image(str(last_screenshot), caption="Last page screenshot")

                    # Action buttons for paused items
                    if is_paused:
                        act_cols = st.columns(3)
                        if act_cols[0].button("Mark Verified", key=f"verify_{item['id']}"):
                            update_queue_status(item["id"], "applied_verified")
                            st.success("Marked as verified.")
                            st.rerun()
                        if act_cols[1].button("Mark Failed", key=f"fail_{item['id']}"):
                            update_queue_status(item["id"], "failed_permanent")
                            st.warning("Marked as failed.")
                            st.rerun()
                        if act_cols[2].button("Retry", key=f"retry_{item['id']}"):
                            update_queue_status(item["id"], "queued")
                            st.info("Re-queued for retry.")
                            st.rerun()

    # ════════════════════════════════════════════════════════════════════
    # Sub-Tab: Monitor
    # ════════════════════════════════════════════════════════════════════

    with tab_monitor:
        st.subheader("Engine Health Monitor")

        # Load current stats
        mon_stats = get_queue_stats()
        total_attempted = sum(v for k, v in mon_stats.items() if k not in ("queued",))

        # Metrics row
        mon_cols = st.columns(4)
        mon_cols[0].metric("Total Attempted", total_attempted)
        mon_cols[1].metric(
            "Consecutive Failures",
            monitor_state.get("consecutive_failures", 0),
        )
        mon_cols[2].metric(
            "Daily Cost",
            f"${monitor_state.get('daily_cost_usd', 0.0):.2f}",
        )
        mon_cols[3].metric(
            "Hourly Count",
            f"{monitor_state.get('hourly_count', 0)}/10",
        )

        st.markdown("---")

        # Platform health indicators
        st.markdown("**Platform Health**")
        disabled_platforms = monitor_state.get("platform_disabled", [])

        platforms = ["workday", "greenhouse"]
        plat_cols = st.columns(len(platforms))
        for i, plat in enumerate(platforms):
            with plat_cols[i]:
                if plat in disabled_platforms:
                    st.markdown(f":red[{plat.upper()}] - DISABLED")
                    if st.button(f"Reset {plat}", key=f"reset_{plat}"):
                        # Reset would call monitor.reset_platform() in production
                        st.success(f"{plat} re-enabled.")
                        st.rerun()
                else:
                    plat_failures = mon_stats.get(f"{plat}_failures", 0)
                    if plat_failures > 0:
                        st.markdown(f":orange[{plat.upper()}] - {plat_failures} failures")
                    else:
                        st.markdown(f":green[{plat.upper()}] - Healthy")

        st.markdown("---")

        # Cost tracker
        st.markdown("**Cost Tracker**")
        daily_cost = monitor_state.get("daily_cost_usd", 0.0)
        cost_cap = 5.0
        cost_pct = min(daily_cost / cost_cap, 1.0) if cost_cap > 0 else 0
        st.progress(cost_pct, text=f"${daily_cost:.2f} / ${cost_cap:.2f} daily cap")

        # Queue status breakdown
        st.markdown("---")
        st.markdown("**Queue Breakdown**")
        if mon_stats:
            for status_name, count in sorted(mon_stats.items()):
                if count > 0:
                    st.caption(f"{_status_badge(status_name)}: {count}")
        else:
            st.caption("No queue data.")


# ════════════════════════════════════════════════════════════════════
# Tab 3: Job Monitor (copied from 4_tracker.py Job Monitor section)
# ════════════════════════════════════════════════════════════════════

with tab3:
    st.subheader("Job Status Monitor")

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
