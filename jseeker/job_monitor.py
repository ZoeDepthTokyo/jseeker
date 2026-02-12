"""jSeeker Job Monitor — Job URL status monitoring (active/closed/expired)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

import requests

from jseeker.models import JobStatus
from jseeker.tracker import tracker_db

# Signals that a job is closed/filled
CLOSURE_SIGNALS = [
    "position has been filled",
    "no longer accepting applications",
    "this job is no longer available",
    "this position has been closed",
    "this role has been filled",
    "job expired",
    "this listing has expired",
    "we are no longer accepting",
    "this opening is closed",
    "this job posting is no longer active",
]

EXPIRY_SIGNALS = [
    "no longer accepting",
    "expired",
    "posting is closed",
]


def check_url_status(url: str) -> JobStatus:
    """Check a job URL and determine its status.

    Returns:
        JobStatus: active, closed, expired, or reposted.
    """
    if not url:
        return JobStatus.ACTIVE

    try:
        response = requests.get(
            url,
            timeout=15,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
    except requests.RequestException:
        return JobStatus.ACTIVE  # Can't reach — assume still active

    # 404 or server error → closed
    if response.status_code == 404:
        return JobStatus.CLOSED
    if response.status_code >= 500:
        return JobStatus.ACTIVE  # Server issue, not necessarily closed

    # Check page content for closure signals
    page_text = response.text.lower()

    for signal in CLOSURE_SIGNALS:
        if signal in page_text:
            return JobStatus.CLOSED

    for signal in EXPIRY_SIGNALS:
        if signal in page_text:
            return JobStatus.EXPIRED

    return JobStatus.ACTIVE


def check_all_active_jobs() -> list[dict]:
    """Check all active job URLs and update their status.

    Returns list of {app_id, old_status, new_status, url} for changes.
    """
    apps = tracker_db.list_applications(job_status="active")
    changes = []

    for app in apps:
        url = app.get("jd_url", "")
        if not url:
            continue

        new_status = check_url_status(url)
        old_status = app.get("job_status", "active")

        if new_status.value != old_status:
            tracker_db.update_application_status(app["id"], "job_status", new_status.value)
            tracker_db.update_application(
                app["id"],
                job_status_checked_at=datetime.now().isoformat(),
            )
            changes.append(
                {
                    "app_id": app["id"],
                    "company": app.get("company_name", ""),
                    "role": app.get("role_title", ""),
                    "old_status": old_status,
                    "new_status": new_status.value,
                    "url": url,
                }
            )
        else:
            # Update check timestamp even if no change
            tracker_db.update_application(
                app["id"],
                job_status_checked_at=datetime.now().isoformat(),
            )

    return changes


def get_ghost_candidates(days: int = 14) -> list[dict]:
    """Find applications with no activity for N+ days that might be ghosted."""
    apps = tracker_db.list_applications(application_status="applied")
    cutoff = datetime.now() - timedelta(days=days)
    ghosts = []

    for app in apps:
        last_activity = app.get("last_activity") or app.get("applied_date")
        if last_activity:
            try:
                activity_date = datetime.fromisoformat(str(last_activity))
                if activity_date < cutoff:
                    ghosts.append(app)
            except ValueError:
                continue

    return ghosts
