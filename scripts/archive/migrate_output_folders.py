"""Migrate resume files from "Not_specified" folder to correct company folders.

This script:
1. Finds all resumes with files in "Not_specified" folder
2. Looks up the correct company name from the database
3. Moves files to the correct company folder
4. Updates database paths

Usage:
    python scripts/migrate_output_folders.py [--dry-run]
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from jseeker.tracker import tracker_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _sanitize(text: str, max_len: int = 30) -> str:
    """Sanitize text for use in filenames (matches renderer.py logic)."""
    if not text or not text.strip():
        return "Unknown"
    clean = "".join(c for c in text if c.isalnum() or c in " -_")
    result = clean.strip().replace(" ", "_")[:max_len]
    return result if result else "Unknown"


def migrate_files(dry_run: bool = False):
    """Migrate files from Not_specified folder to correct company folders."""
    not_specified_dir = settings.output_dir / "Not_specified"

    if not not_specified_dir.exists():
        logger.info("No 'Not_specified' folder found - nothing to migrate")
        return 0

    # Get all resumes with files in Not_specified folder
    all_resumes = tracker_db.list_all_resumes()
    resumes_to_migrate = []

    for resume in all_resumes:
        pdf_path = resume.get("pdf_path", "")
        docx_path = resume.get("docx_path", "")

        if "Not_specified" in pdf_path or "Not_specified" in docx_path:
            resumes_to_migrate.append(resume)

    if not resumes_to_migrate:
        logger.info("No resumes found with 'Not_specified' in paths")
        return 0

    logger.info(f"Found {len(resumes_to_migrate)} resumes to migrate")

    migrated_count = 0
    error_count = 0

    for resume in resumes_to_migrate:
        resume_id = resume["id"]
        company_name = resume.get("company_name", "").strip()

        if not company_name or company_name.lower() in ["unknown", "not specified", "n/a"]:
            logger.warning(f"Resume {resume_id}: No valid company name in database, skipping")
            error_count += 1
            continue

        # Build new folder path
        safe_company = _sanitize(company_name)
        new_folder = settings.output_dir / safe_company

        logger.info(f"Resume {resume_id}: Migrating to {safe_company}/")

        # Migrate PDF
        pdf_path = resume.get("pdf_path")
        new_pdf_path = None
        if pdf_path and Path(pdf_path).exists():
            old_pdf = Path(pdf_path)
            new_pdf = new_folder / old_pdf.name

            if dry_run:
                logger.info(f"  [DRY RUN] Would move PDF: {old_pdf.name} -> {safe_company}/")
            else:
                new_folder.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_pdf), str(new_pdf))
                new_pdf_path = str(new_pdf)
                logger.info(f"  ✓ Moved PDF: {old_pdf.name} -> {safe_company}/")
        elif pdf_path:
            logger.warning(f"  PDF not found: {pdf_path}")

        # Migrate DOCX
        docx_path = resume.get("docx_path")
        new_docx_path = None
        if docx_path and Path(docx_path).exists():
            old_docx = Path(docx_path)
            new_docx = new_folder / old_docx.name

            if dry_run:
                logger.info(f"  [DRY RUN] Would move DOCX: {old_docx.name} -> {safe_company}/")
            else:
                new_folder.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_docx), str(new_docx))
                new_docx_path = str(new_docx)
                logger.info(f"  ✓ Moved DOCX: {old_docx.name} -> {safe_company}/")
        elif docx_path:
            logger.warning(f"  DOCX not found: {docx_path}")

        # Update database paths
        if not dry_run and (new_pdf_path or new_docx_path):
            tracker_db.update_resume_paths(
                resume_id, pdf_path=new_pdf_path, docx_path=new_docx_path
            )
            logger.info("  ✓ Updated database paths")
            migrated_count += 1

    # Clean up empty Not_specified folder
    if not dry_run and migrated_count > 0:
        try:
            remaining_files = list(not_specified_dir.glob("*"))
            if not remaining_files:
                not_specified_dir.rmdir()
                logger.info("✓ Removed empty 'Not_specified' folder")
            else:
                logger.info(f"'Not_specified' folder still has {len(remaining_files)} files")
        except Exception as e:
            logger.warning(f"Could not remove 'Not_specified' folder: {e}")

    logger.info(f"\nMigration complete: {migrated_count} resumes migrated, {error_count} errors")
    return migrated_count


def main():
    parser = argparse.ArgumentParser(description="Migrate resume files from Not_specified folder")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without actually moving files",
    )
    args = parser.parse_args()

    if args.dry_run:
        logger.info("=== DRY RUN MODE ===")

    migrated = migrate_files(dry_run=args.dry_run)

    if args.dry_run:
        logger.info("\nTo actually migrate files, run: python scripts/migrate_output_folders.py")

    return 0 if migrated >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
