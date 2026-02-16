"""Merge duplicate Insulet applications (IDs 6 and 7).

Keep ID 7 (most recent, has 'applied' status) and delete ID 6.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jseeker.tracker import tracker_db


def merge_duplicates():
    """Merge duplicate Insulet applications."""

    # Get both applications
    app_6 = tracker_db.get_application(6)
    app_7 = tracker_db.get_application(7)

    if not app_6 or not app_7:
        print("❌ One or both applications not found")
        return

    print("=== Application #6 (TO BE DELETED) ===")
    print(f"Role: {app_6['role_title']}")
    print(f"Company: {app_6['company_name']}")
    print(f"URL: {app_6['jd_url']}")
    print(f"Status: {app_6['application_status']}")
    print(f"Created: {app_6['created_at']}")

    print("\n=== Application #7 (TO BE KEPT) ===")
    print(f"Role: {app_7['role_title']}")
    print(f"Company: {app_7['company_name']}")
    print(f"URL: {app_7['jd_url']}")
    print(f"Status: {app_7['application_status']}")
    print(f"Created: {app_7['created_at']}")

    print("\n" + "=" * 60)
    print("MERGE STRATEGY:")
    print("  - Keep ID 7 (most recent, has 'applied' status)")
    print("  - Delete ID 6 (older, 'not_applied' status)")
    print("  - Preserve both URLs in notes field of ID 7")
    print("=" * 60)

    # Prompt for confirmation
    response = input("\nProceed with merge? (yes/no): ")
    if response.lower() != "yes":
        print("❌ Merge cancelled")
        return

    # Update ID 7 notes to include both URLs
    current_notes = app_7.get("notes") or ""
    url_note = f"\n\n[Merged duplicate] LinkedIn URL: {app_6['jd_url']}"

    if url_note not in current_notes:
        new_notes = current_notes + url_note
        tracker_db.update_application(7, notes=new_notes)
        print("✅ Updated ID 7 notes with LinkedIn URL")

    # Delete ID 6
    if tracker_db.delete_application(6):
        print("✅ Deleted application #6")
        print("\n✅ Merge complete!")
    else:
        print("❌ Failed to delete application #6")


if __name__ == "__main__":
    merge_duplicates()
