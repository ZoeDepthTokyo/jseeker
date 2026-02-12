# Application Tracker Improvements - Feb 11, 2026

## Summary

Enhanced Application Tracker with editable Role column, row deletion capability, and database cleanup utilities.

## Changes Made

### 1. Role Column Editability ✅
**File:** `ui/pages/4_tracker.py`

- Changed `role_title` column config from `disabled=True` to `disabled=False`
- Added `role_title` to autosave fields list
- Users can now edit job titles directly in the tracker table

### 2. Row Deletion Feature ✅
**Files:** `jseeker/tracker.py`, `ui/pages/4_tracker.py`

#### Backend (tracker.py)
- Added `delete_application(app_id: int) -> bool` method to TrackerDB class
- CASCADE delete: removes application + all associated resumes + resume files from disk
- Preserves company record (may be used by other applications)
- Returns True if deleted, False if not found
- Logs deletion with resume count

#### Frontend (4_tracker.py)
- Added "Delete Application" expander below the data editor
- Number input for application ID selection
- Preview of application to be deleted (role, company, status)
- Double confirmation checkbox
- "Delete Permanently" button with primary styling
- Auto-refresh after successful deletion

### 3. Test Coverage ✅
**File:** `tests/test_tracker.py`

Added 4 comprehensive tests:
- `test_delete_application` - Basic delete with resume and file cleanup
- `test_delete_application_with_multiple_resumes` - Delete with 3 resume versions
- `test_delete_application_nonexistent` - Returns False for invalid ID
- `test_delete_application_preserves_company` - Company survives when shared

**All tests pass:** 4/4 ✅

### 4. Duplicate Merge Utility ✅
**File:** `scripts/merge_duplicate_insulet.py`

Interactive script to merge duplicate Insulet applications (IDs 6, 7):
- Shows preview of both applications
- Explains merge strategy (keep ID 7, delete ID 6)
- Preserves both URLs in notes field
- Requires explicit "yes" confirmation
- Safe execution with validation checks

**Strategy:**
- Keep ID 7 (most recent, "applied" status, Workday URL)
- Delete ID 6 (older, "not_applied" status, LinkedIn URL)
- Append LinkedIn URL to notes field of ID 7 before deletion

## Database Analysis

### Salary Data Status
Out of 7 total applications, only 1 has salary data:
- ❌ ID 1: User Experience Strategy Manager - No salary
- ❌ ID 2: Experience Strategist - No salary
- ✅ ID 3: AI Labs PM Director - $205k-$235k USD
- ❌ ID 4: Director of PM, Creator - No salary
- ❌ ID 5: Director, Product Management - No salary
- ❌ ID 6: Sr Director, UX (Insulet) - No salary
- ❌ ID 7: Sr Director, UX (Insulet) - No salary

**Root Cause:** JD parser did not extract salary from job postings. These were likely:
1. Salary not listed in JD
2. JD parser failed to detect salary format
3. Manual entry missing salary data

**No backfill needed** - salary data genuinely missing from source JDs.

### Duplicate Analysis
IDs 6 and 7 are confirmed duplicates:
- Same company: Insulet Corporation
- Same role: "Sr Director, User Experience"
- Different URLs (LinkedIn vs Workday - same posting on different platforms)
- Created 4 minutes apart (22:02:43 vs 22:06:06)
- Different statuses (not_applied vs applied)

**Recommendation:** Run `python scripts/merge_duplicate_insulet.py` to resolve.

## Usage Examples

### Edit Role Title
1. Navigate to Application Tracker
2. Click on Role cell
3. Type new title
4. Auto-saves on blur

### Delete Application
1. Navigate to Application Tracker
2. Expand "🗑️ Delete Application" section
3. Enter ID number (from leftmost column)
4. Review preview
5. Check confirmation box
6. Click "Delete Permanently"

### Merge Duplicates
```bash
cd X:\Projects\jSeeker
python scripts/merge_duplicate_insulet.py
# Review preview
# Type "yes" to confirm
```

## Technical Notes

### Delete Behavior
- **Atomic operation** - uses db._conn() connection management
- **File cleanup** - Calls delete_resume() for each associated resume
- **Orphan prevention** - Company record preserved (may be shared)
- **Logging** - Info-level log with resume count

### Autosave Trigger
The data editor autosave triggers on ANY cell change, including:
- role_title (newly enabled)
- company_name
- application_status, resume_status, job_status
- salary_min, salary_max, salary_currency
- location, notes

### Safety Features
- Delete requires explicit ID input (not checkbox on row)
- Preview shows what will be deleted
- Confirmation checkbox required
- Primary button styling for visibility
- Returns False for non-existent IDs (no exception)

## Files Modified
1. `ui/pages/4_tracker.py` - Role editability + delete UI
2. `jseeker/tracker.py` - delete_application() method
3. `tests/test_tracker.py` - 4 new delete tests

## Files Created
1. `scripts/merge_duplicate_insulet.py` - Duplicate merge utility
2. `docs/tracker_improvements_feb11.md` - This document

## Test Results
```
pytest tests/test_tracker.py::TestTrackerDB::test_delete_* -v
4 passed in 6.60s
```

## Next Steps (Optional)
1. Run merge script to clean up IDs 6,7 duplicate
2. Consider adding bulk delete (select multiple rows)
3. Add "Undo" feature with soft delete flag
4. Export deleted applications to archive table
