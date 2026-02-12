# Task #7: Job Discovery Enhancements

**Status**: ✅ Complete
**Date**: 2026-02-12
**Agent**: Job Discovery Enhancer

## Summary

Enhanced jSeeker's Job Discovery feature with result limits, improved ranking by relevance + freshness, and prominent freshness display in the UI.

## Requirements Implemented

### 1. ✅ Max Results Per Country (100 per market)
- Added `max_results_per_country=100` parameter to `search_jobs_async()`
- Per-market tracking ensures no single market dominates results
- Logs debug messages when market limits are reached
- Falls back gracefully when a market hits its limit

**Files Changed**:
- `jseeker/job_discovery.py:554-625` - Updated `search_jobs_async()` function

### 2. ✅ Improved Ranking (Relevance + Freshness)
- Updated `rank_discoveries_by_tag_weight()` to sort by:
  1. **Primary**: Sum of tag weights (relevance score)
  2. **Secondary**: Posting date (freshness, most recent first)
- Added optional `max_per_country` parameter to ranking function
- Maintains existing tag weight system (weights from `tracker_db`)

**Files Changed**:
- `jseeker/job_discovery.py:515-551` - Enhanced `rank_discoveries_by_tag_weight()`

### 3. ✅ Posting Date Extraction & Display
- Existing `_parse_relative_date()` function already extracts dates from job boards
- Added `format_freshness()` helper function to convert dates to human-readable strings
  - "Posted today"
  - "Posted 3 days ago"
  - "Posted 2 weeks ago"
  - "Posted 2 months ago"
- Updated UI to display freshness prominently with clock emoji 🕒

**Files Changed**:
- `jseeker/job_discovery.py:514-585` - Added `format_freshness()` function
- `ui/pages/5_job_discovery.py:566-636` - Updated job card rendering with freshness display

### 4. ✅ Database Schema (Already Complete)
- `posting_date DATE` field already exists in `job_discoveries` table
- `market TEXT` field already exists and is populated
- No schema migration needed

### 5. ✅ UI Improvements
- Freshness displayed prominently: "🕒 Posted 3 days ago"
- Location and source grouped together: "📍 San Francisco · linkedin"
- Cleaner 3-column layout: Title/Company | Freshness | Location/Source
- Results now ranked by relevance + freshness (not just discovered_at)

**Files Changed**:
- `ui/pages/5_job_discovery.py:336` - Pass `max_results_per_country=100` to search
- `ui/pages/5_job_discovery.py:465-476` - Apply ranking to filtered results

### 6. ✅ Tests (15/15 passing)
- Added `test_format_freshness()` - Tests relative date formatting
- Added `test_rank_by_relevance_then_freshness()` - Tests 2-tier sorting
- Added `test_per_country_limit()` - Tests ranking with per-country cap
- Added `test_search_with_per_country_limit()` - Tests search enforcement
- Fixed existing `test_integration_search_save_filter_group()` to work with new logic

**Files Changed**:
- `tests/test_job_discovery_v2.py` - Added 4 new tests (15 total, all passing)

## Technical Details

### Ranking Algorithm
```python
# Sort by:
# 1. Sum of tag weights (descending) - relevance to user's search tags
# 2. Posting date (descending) - freshness, most recent first
sorted_discoveries = sorted(
    discoveries,
    key=lambda d: (
        sum(d.search_tag_weights.values()),  # Relevance score
        d.posting_date or date.min           # Freshness (tie-breaker)
    ),
    reverse=True
)
```

### Per-Country Limit Enforcement
- Tracks `market_counts = {market: count}` during search
- Skips search combinations when market limit reached
- Logs progress: `"Search progress: 12/24 combinations, 58 total results (us: 30)"`
- Global limit (250) still enforced as final safeguard

### Freshness Calculation
```python
delta = (today - posting_date).days
if delta == 0: return "Posted today"
elif delta < 7: return f"Posted {delta} days ago"
elif delta < 30: return f"Posted {weeks} weeks ago"
else: return f"Posted {months} months ago"
```

## Files Modified (Summary)

| File | Lines Changed | Purpose |
|------|--------------|---------|
| `jseeker/job_discovery.py` | +72 lines | Per-country limits, freshness formatting |
| `ui/pages/5_job_discovery.py` | +15 lines | UI display improvements |
| `tests/test_job_discovery_v2.py` | +146 lines | 4 new tests + integration fix |

## Backward Compatibility

✅ **Fully backward compatible**
- `posting_date` field already in DB (no migration)
- New parameters have sensible defaults:
  - `max_results_per_country=100` (default)
  - `max_per_country=None` in ranking (unlimited by default)
- Existing search calls work unchanged

## Performance Impact

- **Minimal**: Per-market tracking adds O(1) dict lookup per result
- **Improved**: Skips unnecessary searches when market limit reached
- **Database**: No new queries; existing indexes work efficiently

## Next Steps (Future Enhancements)

1. ✅ Task #7 complete - all requirements delivered
2. Consider adding configurable per-country limits in UI (currently hardcoded to 100)
3. Consider persisting `search_tag_weights` to DB for historical ranking
4. Consider adding "Sort by" dropdown (Relevance, Freshness, Company)

## Testing Verification

Run tests:
```bash
python -m pytest tests/test_job_discovery_v2.py -v
```

Expected: **15/15 passing** ✅

## User-Facing Changes

### Search Results Page
- **Before**: "2024-02-10 | linkedin | new"
- **After**: "🕒 Posted 2 days ago" + "📍 San Francisco · linkedin"

### Result Quality
- **Before**: First 250 results from all markets combined
- **After**: Top 100 from each market, ranked by relevance + freshness

### Search Performance
- **Before**: Could return 250 results from one market, leaving others empty
- **After**: Balanced distribution across markets (max 100 each)
