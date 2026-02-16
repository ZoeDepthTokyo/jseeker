"""P0 Hotfix: Harmonize company names across DB + output folders + Resume Library.

This script:
1. Sanitizes company names in the database
2. Renames output folders to match sanitized names
3. Updates resume file paths in the database
4. Ensures tracker/library/folders all use identical names

Usage:
    python scripts/fix_p0_harmonization.py [--dry-run]
"""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Fix company name harmonization across jSeeker")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying them")
    args = parser.parse_args()

    # Import after argparse so --help works without dependencies
    from jseeker.jd_parser import sanitize_company_name
    from jseeker.tracker import TrackerDB

    db = TrackerDB()

    # Step 1: Get all company name changes from sanitization
    conn = sqlite3.connect("data/jseeker.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id, name FROM companies ORDER BY id")
    companies = c.fetchall()

    company_changes = {}  # {old_name: (company_id, new_name)}
    for row in companies:
        cid, old_name = row["id"], row["name"]
        new_name = sanitize_company_name(old_name)
        if new_name and new_name != old_name:
            company_changes[old_name] = (cid, new_name)
            logger.info(f"  Company {cid}: '{old_name}' -> '{new_name}'")

    if not company_changes:
        logger.info("✅ No company name changes needed - all clean!")
        return

    # Step 2: Sanitize database (handles duplicates/merges)
    if not args.dry_run:
        logger.info("\n📊 Sanitizing database...")
        changes = db.sanitize_existing_companies()
        logger.info(f"  Fixed {len(changes)} company name(s) in database")

    # Step 3: Rename output folders
    logger.info("\n📁 Renaming output folders...")
    output_dir = Path("output")
    if not output_dir.exists():
        logger.warning("  Output directory not found, skipping folder rename")
        return

    renamed_count = 0
    for old_name, (cid, new_name) in company_changes.items():
        # Find folders starting with the old company name
        old_pattern = old_name.replace(" ", "_")[:50]  # First 50 chars, spaces as underscores
        matching_folders = list(output_dir.glob(f"{old_pattern}*"))

        for old_folder in matching_folders:
            # Build new folder name by replacing the company prefix
            old_folder_name = old_folder.name
            # Extract the part after company name (e.g., "_Senior_Product_Manager_2024-02-16")
            suffix = old_folder_name[len(old_pattern) :]
            new_folder_name = new_name.replace(" ", "_") + suffix
            new_folder = output_dir / new_folder_name

            if new_folder.exists():
                logger.warning(f"  ⚠️  Skipping: {new_folder_name} already exists")
                continue

            if args.dry_run:
                logger.info(f"  [DRY RUN] Would rename: {old_folder.name} -> {new_folder_name}")
            else:
                old_folder.rename(new_folder)
                logger.info(f"  ✅ Renamed: {old_folder.name} -> {new_folder_name}")

                # Step 4: Update resume file paths in database
                c.execute(
                    "SELECT id, pdf_path, docx_path FROM resumes WHERE company_id = ?", (cid,)
                )
                resumes = c.fetchall()
                for resume in resumes:
                    rid = resume["id"]
                    old_pdf = resume["pdf_path"]
                    old_docx = resume["docx_path"]

                    if old_pdf and str(old_folder) in old_pdf:
                        new_pdf = old_pdf.replace(str(old_folder), str(new_folder))
                        c.execute("UPDATE resumes SET pdf_path = ? WHERE id = ?", (new_pdf, rid))
                        logger.info(f"    Updated resume {rid} PDF path")

                    if old_docx and str(old_folder) in old_docx:
                        new_docx = old_docx.replace(str(old_folder), str(new_folder))
                        c.execute("UPDATE resumes SET docx_path = ? WHERE id = ?", (new_docx, rid))
                        logger.info(f"    Updated resume {rid} DOCX path")

                renamed_count += 1

    if not args.dry_run:
        conn.commit()

    conn.close()

    logger.info("\n✅ Harmonization complete!")
    logger.info(f"  Database: {len(company_changes)} companies sanitized")
    logger.info(f"  Folders: {renamed_count} output folders renamed")
    logger.info("  Resume Library: File paths updated in database")


if __name__ == "__main__":
    main()
