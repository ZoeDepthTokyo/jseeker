"""Clean semantic cache entries with placeholder company names.

This script removes cached JD parse results that have placeholder company names
like "Not specified", "Unknown", etc. This forces re-parsing with the improved
fallback chain that extracts company names from URLs.

Usage:
    python scripts/clean_cache_placeholders.py [--dry-run]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from jseeker.tracker import tracker_db

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


PLACEHOLDER_COMPANIES = {
    "not specified",
    "not_specified",
    "unknown",
    "n/a",
    "not available",
    "tbd",
    "to be determined",
    "company name",
    "",
}


def clean_cache(dry_run: bool = False):
    """Remove cache entries with placeholder company names."""
    # Clean file-based cache (.cache/*.json)
    cache_dir = settings.data_dir / ".cache"

    if not cache_dir.exists():
        logger.info("No .cache directory found")
        return 0

    cache_files = list(cache_dir.glob("*.json"))
    logger.info(f"Scanning {len(cache_files)} cache files...")

    removed_count = 0

    for cache_file in cache_files:
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Extract JSON from LLM response
            response = data.get("response", "")
            if not response:
                continue

            # Parse JSON from response (strip markdown fences if present)
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            else:
                json_str = response.strip()

            try:
                parsed = json.loads(json_str)
            except json.JSONDecodeError:
                continue

            company = parsed.get("company", "").strip().lower()

            if company in PLACEHOLDER_COMPANIES:
                if dry_run:
                    logger.info(f"[DRY RUN] Would remove: {cache_file.name} (company: '{parsed.get('company', '')}')")
                else:
                    cache_file.unlink()
                    logger.info(f"✓ Removed: {cache_file.name} (company: '{parsed.get('company', '')}')")
                removed_count += 1

        except Exception as e:
            logger.warning(f"Error processing {cache_file.name}: {e}")

    # Clean database cache (jd_cache table)
    logger.info("\nScanning database cache...")
    db_removed = 0

    try:
        conn = tracker_db._get_conn()
        c = conn.cursor()

        # Find entries with placeholder companies
        c.execute("SELECT id, company, parsed_json FROM jd_cache")
        rows = c.fetchall()

        for row in rows:
            cache_id = dict(row)["id"]
            company = (dict(row).get("company") or "").strip().lower()

            if company in PLACEHOLDER_COMPANIES:
                try:
                    # Double-check by parsing the JSON
                    parsed = json.loads(dict(row)["parsed_json"])
                    parsed_company = parsed.get("company", "").strip().lower()

                    if parsed_company in PLACEHOLDER_COMPANIES:
                        if dry_run:
                            logger.info(f"[DRY RUN] Would remove DB cache entry #{cache_id} (company: '{parsed.get('company', '')}')")
                        else:
                            c.execute("DELETE FROM jd_cache WHERE id = ?", (cache_id,))
                            logger.info(f"✓ Removed DB cache entry #{cache_id} (company: '{parsed.get('company', '')}')")
                        db_removed += 1
                except json.JSONDecodeError:
                    pass

        if not dry_run and db_removed > 0:
            conn.commit()

        conn.close()

    except Exception as e:
        logger.error(f"Error cleaning database cache: {e}")

    total_removed = removed_count + db_removed
    logger.info(f"\nCache cleanup complete: {removed_count} file cache + {db_removed} DB cache = {total_removed} total")

    return total_removed


def main():
    parser = argparse.ArgumentParser(description="Clean cache entries with placeholder company names")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without actually deleting"
    )
    args = parser.parse_args()

    if args.dry_run:
        logger.info("=== DRY RUN MODE ===\n")

    removed = clean_cache(dry_run=args.dry_run)

    if args.dry_run:
        logger.info("\nTo actually clean cache, run: python scripts/clean_cache_placeholders.py")

    return 0 if removed >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
