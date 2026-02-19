"""Verify data consistency between Tracker and Resume Library views.

Checks:
1. All resumes have valid application_id references
2. All applications have valid company_id references
3. Company names match between Tracker and Resume Library for same application
4. No orphaned records or mismatched IDs
"""

import sqlite3
import sys
from pathlib import Path

# Fix Windows console encoding for emojis
if sys.platform == "win32":

    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

from jseeker.tracker import TrackerDB

db = TrackerDB()


def main():
    print("=" * 60)
    print("DATA CONSISTENCY CHECK: Tracker vs Resume Library")
    print("=" * 60)

    conn = sqlite3.connect("data/jseeker.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Check 1: Orphaned resumes (no application_id or invalid application_id)
    print("\n1. Checking for orphaned resumes...")
    c.execute("""
        SELECT r.id, r.application_id
        FROM resumes r
        LEFT JOIN applications a ON r.application_id = a.id
        WHERE r.application_id IS NULL OR a.id IS NULL
    """)
    orphaned_resumes = c.fetchall()

    if orphaned_resumes:
        print(f"  ⚠️  Found {len(orphaned_resumes)} orphaned resume(s):")
        for r in orphaned_resumes[:5]:
            print(f"     Resume ID {r['id']}: application_id={r['application_id']}")
    else:
        print("  ✅ No orphaned resumes")

    # Check 2: Applications with invalid company_id
    print("\n2. Checking for invalid company references...")
    c.execute("""
        SELECT a.id, a.company_id
        FROM applications a
        LEFT JOIN companies c ON a.company_id = c.id
        WHERE a.company_id IS NOT NULL AND c.id IS NULL
    """)
    invalid_companies = c.fetchall()

    if invalid_companies:
        print(f"  ⚠️  Found {len(invalid_companies)} application(s) with invalid company_id:")
        for a in invalid_companies[:5]:
            print(f"     Application ID {a['id']}: company_id={a['company_id']} (missing)")
    else:
        print("  ✅ No invalid company references")

    # Check 3: Compare Tracker vs Resume Library queries for same data
    print("\n3. Comparing Tracker vs Resume Library views...")

    # Tracker query (simplified)
    c.execute("""
        SELECT a.id as app_id, a.company_id, c.name as company_name
        FROM applications a
        LEFT JOIN companies c ON a.company_id = c.id
        ORDER BY a.id
    """)
    tracker_data = {row["app_id"]: dict(row) for row in c.fetchall()}

    # Resume Library query (simplified)
    c.execute("""
        SELECT r.id as resume_id, r.application_id, a.company_id, c.name as company_name
        FROM resumes r
        LEFT JOIN applications a ON r.application_id = a.id
        LEFT JOIN companies c ON a.company_id = c.id
        WHERE r.application_id IS NOT NULL
        ORDER BY r.application_id
    """)
    resume_data = {row["application_id"]: dict(row) for row in c.fetchall()}

    mismatches = []
    for app_id in resume_data:
        if app_id in tracker_data:
            tracker_name = tracker_data[app_id]["company_name"]
            resume_name = resume_data[app_id]["company_name"]
            tracker_cid = tracker_data[app_id]["company_id"]
            resume_cid = resume_data[app_id]["company_id"]

            if tracker_name != resume_name or tracker_cid != resume_cid:
                mismatches.append(
                    {
                        "app_id": app_id,
                        "tracker_name": tracker_name,
                        "resume_name": resume_name,
                        "tracker_cid": tracker_cid,
                        "resume_cid": resume_cid,
                    }
                )

    if mismatches:
        print(f"  ⚠️  Found {len(mismatches)} mismatch(es):")
        for m in mismatches[:5]:
            print(f"     App {m['app_id']}:")
            print(f"       Tracker: {m['tracker_name']} (ID {m['tracker_cid']})")
            print(f"       Resume:  {m['resume_name']} (ID {m['resume_cid']})")
    else:
        print("  ✅ No mismatches found")

    # Check 4: Duplicate company names (should have been merged)
    print("\n4. Checking for duplicate company names...")
    c.execute("""
        SELECT name, COUNT(*) as count
        FROM companies
        GROUP BY name
        HAVING count > 1
    """)
    duplicates = c.fetchall()

    if duplicates:
        print(f"  ⚠️  Found {len(duplicates)} duplicate company name(s):")
        for d in duplicates[:5]:
            print(f"     '{d['name']}': {d['count']} entries")
    else:
        print("  ✅ No duplicate company names")

    # Check 5: Company name formatting issues
    print("\n5. Checking for company name formatting issues...")
    c.execute("SELECT id, name FROM companies ORDER BY id")
    companies = c.fetchall()

    issues = []
    for company in companies:
        name = company["name"]
        if not name or name.strip() != name:
            issues.append((company["id"], name, "whitespace"))
        elif len(name) < 2:
            issues.append((company["id"], name, "too short"))
        elif any(word in name.lower() for word in ["unknown", "not specified", "n/a"]):
            issues.append((company["id"], name, "placeholder"))

    if issues:
        print(f"  ⚠️  Found {len(issues)} formatting issue(s):")
        for cid, name, issue_type in issues[:5]:
            print(f"     Company ID {cid}: '{name}' ({issue_type})")
    else:
        print("  ✅ No formatting issues")

    conn.close()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total_issues = (
        len(orphaned_resumes)
        + len(invalid_companies)
        + len(mismatches)
        + len(duplicates)
        + len(issues)
    )
    if total_issues == 0:
        print("✅ All checks passed! Data is consistent.")
    else:
        print(f"⚠️  Found {total_issues} total issue(s) across all checks.")
        print("\nRecommended actions:")
        if orphaned_resumes:
            print(
                "  - Run 'DELETE FROM resumes WHERE application_id IS NULL' to clean orphaned resumes"
            )
        if duplicates:
            print("  - Run tracker_db.sanitize_existing_companies() to merge duplicates")
        if issues:
            print("  - Run sanitization on company names with formatting issues")


if __name__ == "__main__":
    main()
