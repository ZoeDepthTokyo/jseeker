"""Clean up database issues found by verify_data_consistency.py.

Fixes:
1. Delete orphaned resumes (no valid application_id)
2. Merge duplicate company names
3. Remove placeholder company names
"""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from jseeker.tracker import TrackerDB

db = TrackerDB()


def main():
    parser = argparse.ArgumentParser(description="Clean up database issues")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying")
    args = parser.parse_args()

    print("=" * 60)
    print("DATABASE CLEANUP")
    print("=" * 60)

    conn = sqlite3.connect("data/jseeker.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Fix 1: Delete orphaned resumes
    print("\n1. Cleaning orphaned resumes...")
    c.execute("""
        SELECT r.id, r.application_id
        FROM resumes r
        LEFT JOIN applications a ON r.application_id = a.id
        WHERE r.application_id IS NOT NULL AND a.id IS NULL
    """)
    orphaned = c.fetchall()

    if orphaned:
        print(f"  Found {len(orphaned)} orphaned resume(s):")
        for r in orphaned:
            print(f"    Resume ID {r['id']} (application_id={r['application_id']})")

        if args.dry_run:
            print("  [DRY RUN] Would delete these resumes")
        else:
            for r in orphaned:
                c.execute("DELETE FROM resumes WHERE id = ?", (r["id"],))
            conn.commit()
            print(f"  ✅ Deleted {len(orphaned)} orphaned resume(s)")
    else:
        print("  ✅ No orphaned resumes")

    # Fix 2: Merge duplicate company names
    print("\n2. Merging duplicate company names...")
    changes = db.sanitize_existing_companies()

    if changes:
        print(f"  Fixed {len(changes)} company name(s):")
        for cid, old_name, new_name in changes:
            print(f"    Company {cid}: '{old_name}' → '{new_name}'")
    else:
        print("  ✅ No duplicates to merge")

    # Fix 3: Remove placeholder companies (but keep their applications)
    print("\n3. Handling placeholder company names...")
    c.execute("""
        SELECT id, name
        FROM companies
        WHERE LOWER(name) IN ('unknown', 'not specified', 'n/a', 'none')
    """)
    placeholders = c.fetchall()

    if placeholders:
        print(f"  Found {len(placeholders)} placeholder company name(s):")
        for p in placeholders:
            c.execute("SELECT COUNT(*) as cnt FROM applications WHERE company_id = ?", (p["id"],))
            app_count = c.fetchone()["cnt"]
            print(f"    Company {p['id']}: '{p['name']}' ({app_count} applications)")

        print("  ⚠️  Manual action required:")
        print("     These companies have applications. Update them in the Tracker UI:")
        print("     Tracker → Edit company_name column → Enter correct company name")
    else:
        print("  ✅ No placeholder companies")

    conn.close()

    print("\n" + "=" * 60)
    print("CLEANUP COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
