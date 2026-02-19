"""One-time script: audit and clean up Navan duplicate application/resume records.

Usage:
    python scripts/check_dedup_navan.py          # dry-run (inspect only)
    python scripts/check_dedup_navan.py --delete  # execute deletes

Targets:
    application_id=34 (Navan duplicate)
    resume_id=33      (associated with app 34, if linked)
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Resolve project root
ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "jseeker.db"


def main(do_delete: bool = False) -> None:
    if not DB_PATH.exists():
        print(f"ERROR: DB not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # -- 1. Inspect target records --
    print("=" * 60)
    print("INSPECTION: Target records")
    print("=" * 60)

    c.execute("SELECT id, company_id, role_title, jd_url, created_at FROM applications WHERE id = 34")
    app34 = c.fetchone()
    if app34:
        print(f"Application 34: id={app34['id']} company_id={app34['company_id']} role={app34['role_title']!r} url={app34['jd_url']} created={app34['created_at']}")
    else:
        print("Application 34: NOT FOUND (already deleted?)")

    c.execute("SELECT id, application_id, version, template_used, ats_platform, created_at FROM resumes WHERE id = 33")
    res33 = c.fetchone()
    if res33:
        print(f"Resume 33: id={res33['id']} app_id={res33['application_id']} v={res33['version']} template={res33['template_used']} platform={res33['ats_platform']}")
    else:
        print("Resume 33: NOT FOUND (already deleted?)")

    # Check linkage
    c.execute("SELECT id FROM resumes WHERE application_id = 34")
    linked_resumes = [row[0] for row in c.fetchall()]
    print(f"\nResumes linked to application 34: {linked_resumes}")
    if 33 in linked_resumes:
        print("  -> Resume 33 IS linked to application 34 -- cascade delete will handle it")
    elif res33:
        print("  -> Resume 33 is NOT linked to application 34 -- needs separate delete")

    # -- 2. Orphan audit --
    print("\n" + "=" * 60)
    print("ORPHAN AUDIT")
    print("=" * 60)

    # Orphaned resumes (no matching application)
    c.execute("""
        SELECT r.id, r.application_id, r.version, r.ats_platform
        FROM resumes r
        LEFT JOIN applications a ON r.application_id = a.id
        WHERE a.id IS NULL
    """)
    orphan_resumes = c.fetchall()
    if orphan_resumes:
        print(f"\nOrphaned resumes ({len(orphan_resumes)} found -- application deleted but resume remains):")
        for r in orphan_resumes:
            print(f"  resume.id={r['id']} app_id={r['application_id']} v={r['version']} platform={r['ats_platform']}")
    else:
        print("\nOrphaned resumes: none found (OK)")

    # Resumeless applications
    c.execute("""
        SELECT a.id, a.company_id, a.role_title, a.application_status
        FROM applications a
        LEFT JOIN resumes r ON r.application_id = a.id
        WHERE r.id IS NULL
    """)
    resumeless_apps = c.fetchall()
    if resumeless_apps:
        print(f"\nResumeless applications ({len(resumeless_apps)} found -- tracked but no resume generated):")
        for a in resumeless_apps:
            print(f"  app.id={a['id']} company_id={a['company_id']} role={a['role_title']!r} status={a['application_status']}")
    else:
        print("\nResumeless applications: none found (OK)")

    # -- 3. Delete (if --delete flag) --
    if not do_delete:
        print("\n" + "=" * 60)
        print("DRY RUN -- no changes made. Re-run with --delete to execute.")
        print("=" * 60)
        conn.close()
        return

    print("\n" + "=" * 60)
    print("EXECUTING DELETES")
    print("=" * 60)

    if app34:
        # Cascade: delete all resumes linked to app 34, then the app
        for rid in linked_resumes:
            # Check for PDF/DOCX files to clean up
            c.execute("SELECT pdf_path, docx_path FROM resumes WHERE id = ?", (rid,))
            row = c.fetchone()
            if row:
                for fpath in [row["pdf_path"], row["docx_path"]]:
                    if fpath:
                        p = Path(fpath)
                        if p.exists():
                            p.unlink()
                            print(f"  Deleted file: {fpath}")
            c.execute("DELETE FROM resumes WHERE id = ?", (rid,))
            print(f"  Deleted resume {rid}")

        c.execute("DELETE FROM applications WHERE id = 34")
        conn.commit()
        print(f"  Deleted application 34 (cascade: {len(linked_resumes)} resume(s))")

    # Delete resume 33 separately if it wasn't already cascaded
    if res33 and 33 not in linked_resumes:
        c.execute("SELECT pdf_path, docx_path FROM resumes WHERE id = 33")
        row = c.fetchone()
        if row:
            for fpath in [row["pdf_path"], row["docx_path"]]:
                if fpath:
                    p = Path(fpath)
                    if p.exists():
                        p.unlink()
                        print(f"  Deleted file: {fpath}")
        c.execute("DELETE FROM resumes WHERE id = 33")
        conn.commit()
        print("  Deleted resume 33 (standalone)")

    conn.close()
    print("\nDone. Verify with: python scripts/check_dedup_navan.py (dry-run should show NOT FOUND)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Navan dedup cleanup script")
    parser.add_argument("--delete", action="store_true", help="Execute deletes (default: dry-run)")
    args = parser.parse_args()
    main(do_delete=args.delete)
