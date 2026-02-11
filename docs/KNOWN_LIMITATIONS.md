# jSeeker Known Limitations

This document tracks known limitations that cannot be fixed due to framework or technical constraints.

## Streamlit Framework Limitations

### 1. Column Width Persistence
**Issue**: Application Tracker column widths and row sizes do not persist across sessions.

**Root Cause**: Streamlit's `st.data_editor` does not support saving column width state. This is a framework limitation, not a bug in jSeeker.

**Workaround**: Users must manually resize columns each session. Column order is fixed in code and will remain consistent.

**Related**: [Streamlit Issue #4979](https://github.com/streamlit/streamlit/issues/4979)

---

### 2. Cell Background Colors
**Issue**: Cannot add background colors to cells based on status values (e.g., red for "rejected", green for "applied").

**Root Cause**: Streamlit's `st.data_editor` does not support cell-level styling or background colors.

**Workaround**: We use emoji indicators in column help text:
- App Status: ❌ rejected, ✅ applied, ⏳ not_applied, 🗣️ interviewing, 🎉 offer
- Job Status: ❌ closed, ✅ active, ⏸️ paused

**Related**: [Streamlit Issue #7068](https://github.com/streamlit/streamlit/issues/7068)

---

## Resume Generation Limitations

### 3. Retroactive Path Fixes
**Issue**: Existing resumes with "Not_specified" folder paths cannot be automatically fixed.

**Root Cause**: Resume file paths are baked into the database at generation time. Changing folder names would break PDF/DOCX references.

**Workaround**:
- v0.3.1+ uses company name fallback extraction - NEW resumes will have correct paths
- For existing resumes with bad paths:
  - Option A: Regenerate the resume (will use new path)
  - Option B: Manually rename folders and update DB paths (advanced users only)

---

## Performance Limitations

### 4. Resume Generation Speed
**Issue**: Resume generation takes 10-30 seconds per resume.

**Root Cause**: Multiple factors:
1. Claude API calls for content adaptation (3-5 seconds each)
2. Playwright browser launch for PDF rendering (2-4 seconds)
3. ATS scoring and keyword analysis (1-2 seconds)

**Mitigation**:
- v0.3.2+ uses prompt caching to reduce LLM costs
- Batch generation uses parallel workers
- Progress indicators show current step

**Cannot be eliminated**: API latency and browser rendering are inherent to the technology stack.

---

## Data Extraction Limitations

### 5. Job Board Anti-Bot Protection
**Issue**: Indeed and Wellfound often return 403 errors or empty results.

**Root Cause**: Job boards use anti-bot protection that blocks automated scraping.

**Workaround**:
- LinkedIn generally works better (60-80% success rate)
- Use multiple job boards to increase coverage
- Manual copy-paste is always an option for specific jobs

---

## Update History
- **v0.3.2** (2026-02-11): Initial documentation of known limitations
