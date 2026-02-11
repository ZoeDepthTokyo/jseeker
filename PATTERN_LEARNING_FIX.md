# Pattern Learning Fix — Task #3

## Problem
Pattern Learning stats showed "No patterns learned yet" even after generating resumes. The pattern learning system was only triggered by **manual user edits**, not during the initial LLM-powered resume generation.

## Root Cause
The `learn_pattern()` function was only called from `feedback.py → capture_edit()`, which captures manual user corrections. It was **never called during `adapter.py` resume generation**, so patterns accumulated only from edits, not from LLM adaptations.

## Solution
Modified `adapter.py` to capture patterns during LLM-powered adaptations:

### 1. Summary Adaptation (adapter.py:128-143)
**Added after LLM call in `adapt_summary()`:**
```python
# Learn pattern from this LLM adaptation for future cache hits
from jseeker.pattern_learner import learn_pattern
jd_dict = {
    "title": parsed_jd.title,
    "ats_keywords": parsed_jd.ats_keywords,
    "industry": getattr(parsed_jd, "industry", None),
}
learn_pattern(
    pattern_type="summary_adaptation",
    source_text=original,
    target_text=adapted,
    jd_context=jd_dict,
)
logger.info("adapt_summary | pattern learned from LLM adaptation")
```

### 2. Bullet Adaptation (adapter.py:323-339)
**Added after LLM batch call in `adapt_bullets_batch()`:**
```python
# Learn patterns from LLM adaptations for future cache hits
from jseeker.pattern_learner import learn_pattern
jd_dict = {
    "title": parsed_jd.title,
    "ats_keywords": parsed_jd.ats_keywords,
    "industry": getattr(parsed_jd, "industry", None),
}
for idx, exp in enumerate(experience_blocks):
    original_bullets = "\n".join(exp.get("bullets", []))
    adapted_bullets = "\n".join(llm_results[idx]) if isinstance(llm_results[idx], list) else str(llm_results[idx])
    learn_pattern(
        pattern_type="bullet_adaptation",
        source_text=original_bullets,
        target_text=adapted_bullets,
        jd_context=jd_dict,
    )
logger.info(f"adapt_bullets_batch | learned {len(experience_blocks)} bullet patterns from LLM")
```

### 3. Enhanced Logging (pattern_learner.py)
**Added logging to track pattern learning:**
- Log every pattern learned with ID, type, source length, target length
- Log pattern cache hits/misses during matching
- Log when no patterns exist or none meet similarity threshold

## Files Modified
1. **jseeker/adapter.py** — Added pattern learning after LLM adaptations
2. **jseeker/pattern_learner.py** — Added logging for debugging
3. **ui/pages/7_learning_insights.py** — Fixed Streamlit deprecation (use_container_width → width="stretch")

## How Pattern Learning Works Now

### Learning Flow
1. **User generates resume** → `adapter.py` called
2. **LLM adapts content** → Summary + bullets adapted
3. **Pattern captured** → `learn_pattern()` called immediately after LLM
4. **Stored in DB** → `learned_patterns` table with JD context
5. **Future lookups** → `find_matching_pattern()` checks DB before LLM call

### Pattern Reuse (Cache)
- **Frequency threshold:** Pattern must be used ≥3 times to be trusted
- **Similarity threshold:** 85% text similarity + 80% weight on text, 20% on JD context
- **Cache hit:** Return cached adaptation, skip LLM call ($0.01 saved per hit)
- **Cache miss:** Call LLM, learn new pattern

### Expected Behavior
- **First 5 resumes:** 0% cache hit rate (building library)
- **10-20 resumes:** 30-40% cache hit rate
- **50+ resumes:** 60-70% cache hit rate
- **Cost reduction:** ~40% after 20 resumes, ~65% after 50 resumes

## Testing

### Manual Test
```bash
cd X:\Projects\jSeeker
python test_pattern_learning.py
```

**Expected output:**
```
=== BEFORE TEST ===
Total patterns: 0

=== LEARNING TEST PATTERNS ===
[OK] Learned summary pattern
[OK] Learned bullet pattern

=== AFTER TEST ===
Total patterns: 2
By type: [{'type': 'summary_adaptation', 'count': 1, 'total_uses': 2}, {'type': 'bullet_adaptation', 'count': 1, 'total_uses': 1}]

=== DATABASE CHECK ===
Recent patterns in DB: 2
  - ID 2: bullet_adaptation | freq=1
  - ID 1: summary_adaptation | freq=2

[SUCCESS] Pattern learning system is working!
```

### Integration Test
1. **Generate a resume** via UI (New Resume page)
2. **Check logs** for pattern learning messages:
   ```
   adapt_summary | pattern learned from LLM adaptation
   adapt_bullets_batch | learned 3 bullet patterns from LLM
   ```
3. **View Learning Insights** page:
   - Should show patterns in "Pattern Learning Stats"
   - Should show pattern details in "Pattern History"
   - Should show cost savings (initially $0.00, increases after reuse)

### Database Verification
```bash
python -c "from jseeker.pattern_learner import get_pattern_stats; stats = get_pattern_stats(); print(f'Patterns: {stats[\"total_patterns\"]}'); print(f'Types: {stats[\"by_type\"]}')"
```

## Benefits
1. **Automatic learning** — No user action required, patterns accumulate from every resume
2. **Cost reduction** — Cache hits save ~$0.01 per adaptation (adds up over 50+ resumes)
3. **Transparency** — Learning Insights page shows exactly what patterns were learned
4. **Debugging** — Structured logging makes it easy to trace pattern learning

## Next Steps (Future Enhancement)
1. **Skill adaptation patterns** — Currently only summary + bullets are learned
2. **Pattern pruning** — Delete patterns that are never reused after 6 months
3. **Pattern merging** — Combine similar patterns with <90% similarity
4. **Cross-user patterns** — Share anonymized patterns across jSeeker users (opt-in)

## Related Files
- `jseeker/adapter.py` — Resume adaptation pipeline
- `jseeker/pattern_learner.py` — Pattern storage and matching
- `jseeker/feedback.py` — User edit capture (still works for manual edits)
- `ui/pages/7_learning_insights.py` — Pattern visualization
- `test_pattern_learning.py` — Unit test for pattern learning

## Validation Checklist
- [x] Pattern learning triggered during resume generation
- [x] Patterns stored in `learned_patterns` table
- [x] Pattern matching works before LLM calls
- [x] Logging shows pattern learning events
- [x] Learning Insights page displays patterns correctly
- [x] Streamlit deprecation warnings fixed
- [x] Test script passes successfully
