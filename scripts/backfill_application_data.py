"""
Backfill missing salary and JD text for existing applications.

Run this script to re-parse JD URLs and extract missing fields.
Note: relevance_score is computed during matching, not JD parsing, so it's not backfilled here.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jseeker.tracker import TrackerDB
from jseeker.jd_parser import extract_jd_from_url, process_jd
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backfill_application(app_id: int, tracker_db: TrackerDB):
    """Backfill missing data for a single application."""
    app = tracker_db.get_application(app_id)

    if not app:
        logger.warning(f"Application {app_id} not found")
        return False

    jd_url = app.get("jd_url")
    if not jd_url:
        logger.warning(f"Application {app_id} has no JD URL")
        return False

    logger.info(f"Processing application {app_id}: {app.get('role_title')}")

    try:
        # Extract JD from URL
        jd_text, metadata = extract_jd_from_url(jd_url, timeout=30)

        if not jd_text:
            logger.warning(f"Could not extract JD text from {jd_url}")
            return False

        # Parse JD to extract all fields
        jd_data = process_jd(
            raw_text=jd_text,
            jd_url=jd_url
        )

        # Prepare updates
        updates = {}

        # Only update if fields are missing
        if not app.get("jd_text"):
            updates["jd_text"] = jd_data.jd_text

        if not app.get("salary_min") and jd_data.salary_min:
            updates["salary_min"] = jd_data.salary_min

        if not app.get("salary_max") and jd_data.salary_max:
            updates["salary_max"] = jd_data.salary_max

        if not app.get("salary_currency") and jd_data.salary_currency:
            updates["salary_currency"] = jd_data.salary_currency

        # Note: relevance_score is computed during matching, not available from ParsedJD

        if updates:
            logger.info(f"Updating application {app_id} with: {list(updates.keys())}")
            tracker_db.update_application(app_id, **updates)
            return True
        else:
            logger.info(f"Application {app_id} already has all data")
            return False

    except Exception as e:
        logger.error(f"Error backfilling application {app_id}: {e}")
        return False


def main():
    """Backfill missing data for applications 1-5."""
    tracker_db = TrackerDB()

    # Target applications with missing data
    target_ids = [1, 2, 3, 4, 5]

    success_count = 0
    for app_id in target_ids:
        if backfill_application(app_id, tracker_db):
            success_count += 1

    logger.info(f"\nBackfill complete: {success_count}/{len(target_ids)} applications updated")

    # Show updated data
    print("\n=== UPDATED APPLICATION DATA ===")
    for app_id in target_ids:
        app = tracker_db.get_application(app_id)
        if app:
            print(f"\nID {app_id}: {app.get('role_title')}")
            print(f"  Salary: {app.get('salary_min')} - {app.get('salary_max')} {app.get('salary_currency')}")
            print(f"  JD Text: {'Yes' if app.get('jd_text') else 'No'}")
            print(f"  Location: {app.get('location', 'N/A')}")


if __name__ == "__main__":
    main()
