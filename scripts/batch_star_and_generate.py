"""Batch workflow: Load search, filter, star top N jobs, generate resumes.

Usage:
    python scripts/batch_star_and_generate.py \
        --search "Director of UX - Worldwide" \
        --location "New York" \
        --top 5 \
        --generate

Example:
    python scripts/batch_star_and_generate.py --search "📌 Director of UX - Worldwide" --location "NY" --top 5 --generate
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import datetime

from jseeker.tracker import tracker_db
from jseeker.job_discovery import generate_resume_from_discovery
from jseeker.batch_processor import BatchProcessor

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def normalize_location(loc: str) -> str:
    """Normalize location string for matching.

    Examples:
        NY, New York, NYC → new york
        San Francisco, CA → san francisco
    """
    loc_lower = loc.lower().strip()

    # NY/NYC normalization
    if loc_lower in ("ny", "nyc", "new york city"):
        return "new york"

    # Remove state abbreviations and extra whitespace
    parts = [p.strip() for p in loc_lower.split(",")]
    return parts[0]  # Return city only


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Batch workflow for starring and generating resumes from job discoveries"
    )
    parser.add_argument(
        "--search",
        required=True,
        help="Name of saved search to load (e.g., 'Director of UX - Worldwide')"
    )
    parser.add_argument(
        "--location",
        required=True,
        help="Location to filter by (e.g., 'New York', 'NY', 'San Francisco')"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Number of top jobs to process (default: 5)"
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Auto-generate resumes for starred jobs (default: False, just star)"
    )
    parser.add_argument(
        "--output-folder",
        default=None,
        help="Output folder name (default: auto-detect from company/role)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run: show what would be done without making changes"
    )

    return parser.parse_args()


def load_saved_search(search_name: str) -> dict:
    """Load saved search configuration by name.

    Args:
        search_name: Name of saved search (with or without 📌 prefix)

    Returns:
        Search configuration dict

    Raises:
        ValueError: If search not found
    """
    # Strip emoji prefix if present
    clean_name = search_name.strip().lstrip("📌 ")

    saved_searches = tracker_db.list_saved_searches()

    for search in saved_searches:
        if search["name"] == clean_name or search["name"] == search_name:
            logger.info(f"✅ Loaded saved search: {search['name']}")
            return search

    # If not found, show available searches
    available = [s["name"] for s in saved_searches]
    raise ValueError(
        f"Search '{search_name}' not found. Available searches:\n" +
        "\n".join(f"  - {name}" for name in available)
    )


def filter_discoveries_by_location(discoveries: list[dict], location: str) -> list[dict]:
    """Filter discoveries by location (city match).

    Args:
        discoveries: List of job discovery dicts
        location: Location to filter by (e.g., "New York", "NY")

    Returns:
        Filtered list of discoveries matching location
    """
    normalized_target = normalize_location(location)

    filtered = []
    for disc in discoveries:
        disc_location = disc.get("location", "")
        if not disc_location:
            continue

        normalized_disc = normalize_location(disc_location)
        if normalized_target in normalized_disc or normalized_disc in normalized_target:
            filtered.append(disc)

    logger.info(f"📍 Filtered to {len(filtered)} jobs in {location}")
    return filtered


def get_top_n_by_relevance(discoveries: list[dict], n: int = 5) -> list[dict]:
    """Get top N discoveries by relevance score.

    Args:
        discoveries: List of job discovery dicts
        n: Number of top jobs to return

    Returns:
        Top N discoveries sorted by relevance (descending)
    """
    # Sort by relevance_score descending
    sorted_discoveries = sorted(
        discoveries,
        key=lambda d: d.get("relevance_score", 0),
        reverse=True
    )

    top_n = sorted_discoveries[:n]

    logger.info(f"📊 Selected top {len(top_n)} jobs by relevance:")
    for i, disc in enumerate(top_n, 1):
        score = disc.get("relevance_score", 0)
        company = disc.get("company", "Unknown")
        title = disc.get("title", "Untitled")
        logger.info(f"  {i}. {company} - {title} ({score}% match)")

    return top_n


def star_jobs(job_ids: list[int], dry_run: bool = False) -> int:
    """Star multiple jobs in the database.

    Args:
        job_ids: List of discovery IDs to star
        dry_run: If True, don't actually update database

    Returns:
        Number of jobs starred
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would star {len(job_ids)} jobs")
        return len(job_ids)

    starred_count = 0
    for job_id in job_ids:
        try:
            tracker_db.update_discovery_status(job_id, "starred")
            starred_count += 1
        except Exception as e:
            logger.error(f"Failed to star job {job_id}: {e}")

    logger.info(f"⭐ Starred {starred_count}/{len(job_ids)} jobs")
    return starred_count


def generate_resumes_batch(discoveries: list[dict], output_folder: str = None, dry_run: bool = False) -> int:
    """Generate resumes for multiple discoveries.

    Args:
        discoveries: List of job discovery dicts
        output_folder: Optional output folder name
        dry_run: If True, don't actually generate resumes

    Returns:
        Number of resumes successfully generated
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would generate {len(discoveries)} resumes")
        return len(discoveries)

    logger.info(f"🚀 Starting batch resume generation for {len(discoveries)} jobs...")

    generated_count = 0
    for i, disc in enumerate(discoveries, 1):
        company = disc.get("company", "Unknown")
        title = disc.get("title", "Untitled")
        url = disc.get("url", "")

        logger.info(f"[{i}/{len(discoveries)}] Generating resume for {company} - {title}...")

        try:
            result = generate_resume_from_discovery(discovery_id=disc["id"])

            if result and result.get("pdf_path"):
                logger.info(f"  ✅ Generated: {result['pdf_path']}")
                generated_count += 1
            else:
                logger.warning(f"  ⚠️ Generation returned no PDF path")

        except Exception as e:
            logger.error(f"  ❌ Failed: {e}")

    logger.info(f"✅ Generated {generated_count}/{len(discoveries)} resumes")
    return generated_count


def main():
    """Main batch workflow execution."""
    args = parse_args()

    logger.info("=" * 60)
    logger.info("BATCH WORKFLOW: Star + Generate Resumes")
    logger.info("=" * 60)
    logger.info(f"Search: {args.search}")
    logger.info(f"Location: {args.location}")
    logger.info(f"Top N: {args.top}")
    logger.info(f"Generate: {args.generate}")
    logger.info(f"Dry Run: {args.dry_run}")
    logger.info("=" * 60)

    # Step 1: Load saved search
    try:
        search_config = load_saved_search(args.search)
    except ValueError as e:
        logger.error(str(e))
        return 1

    # Step 2: Get all discoveries matching the search criteria
    # Note: We assume the search was already run and discoveries are in DB
    # Get new discoveries first
    new_discoveries = tracker_db.list_discoveries(status="new")
    starred_discoveries = tracker_db.list_discoveries(status="starred")

    # Combine new + starred (user might want to re-process starred)
    active_discoveries = new_discoveries + starred_discoveries

    logger.info(f"📦 Found {len(active_discoveries)} active discoveries in database")

    if not active_discoveries:
        logger.error("No active discoveries found. Run the search in UI first to populate discoveries.")
        return 1

    # Step 3: Filter by location
    location_filtered = filter_discoveries_by_location(active_discoveries, args.location)

    if not location_filtered:
        logger.error(f"No jobs found in location: {args.location}")
        return 1

    # Step 4: Get top N by relevance
    top_jobs = get_top_n_by_relevance(location_filtered, args.top)

    if not top_jobs:
        logger.error("No jobs to process after filtering")
        return 1

    # Step 5: Star the top N jobs
    job_ids = [job["id"] for job in top_jobs]
    starred_count = star_jobs(job_ids, dry_run=args.dry_run)

    # Step 6: Generate resumes (if requested)
    if args.generate:
        generated_count = generate_resumes_batch(
            top_jobs,
            output_folder=args.output_folder,
            dry_run=args.dry_run
        )

        logger.info("=" * 60)
        logger.info("SUMMARY")
        logger.info("=" * 60)
        logger.info(f"✅ Starred: {starred_count} jobs")
        logger.info(f"✅ Generated: {generated_count} resumes")
        logger.info("=" * 60)
    else:
        logger.info("=" * 60)
        logger.info("SUMMARY")
        logger.info("=" * 60)
        logger.info(f"✅ Starred: {starred_count} jobs")
        logger.info("ℹ️  Resume generation skipped (use --generate flag)")
        logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
