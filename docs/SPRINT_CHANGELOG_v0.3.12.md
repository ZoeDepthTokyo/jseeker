# jSeeker v0.3.12 Sprint Changelog

## Date: 2026-02-17

## Summary
Major sprint: architecture audit + 2 new features + bug fixes. Tests: 629 → 639 passing.

## Bug Fixes
- **Greenhouse branded URL resolution**: `gh_jid` param pages (HubSpot, Navan, etc.) now redirect to scrapeable `job-boards.greenhouse.io` canonical URLs. Fixes batch + new_resume JD parsing failures for company-branded pages.
- **DB cleanup**: Deleted records 32, 33 ("Not_provided"/"Unknown_Company") + orphaned output folders.
- **test_dedup_cross_table**: Updated test to document intentional behavior (applications table alone does not block apply_queue insertion).

## Architecture Audit
- **Dead code removed**: `jseeker/feedback.py` deleted (zero callers)
- **Scripts archived**: 7 legacy migration scripts moved to `scripts/archive/`
- **Enum conflict fixed**: `batch_processor.py` `JobStatus` → `BatchJobStatus` (avoids collision with `models.py` `JobStatus`)

## UI Consolidation (8 pages → 6 pages)
- **Analytics (7_analytics.py)**: Merged `7_learning_insights.py` + `8_regional_salary_analytics.py` into 2-tab page
- **Pipeline (1_pipeline.py)**: Merged `1_dashboard.py` + `9_auto_apply.py` into 3-tab page (Generate / Auto-Submit / Job Monitor)
- Session state keys scoped: `batch_running` → `resume_batch_running` / `apply_batch_running`
- Deleted: 1_dashboard.py, 9_auto_apply.py, 7_learning_insights.py, 8_regional_salary_analytics.py

## Feature B: Cover Letter Writer
- **`data/prompts/cover_letter_writer.txt`**: Sonnet prompt template (3 paragraphs, <300 words, tone-matched)
- **`jseeker/outreach.py`**: Added `generate_cover_letter(parsed_jd, adapted_resume, why_company, key_achievement, culture_tone)` — ~$0.015/call
- **`ui/pages/2_new_resume.py`**: Collapsible expander after download buttons — 3-field form (why company, achievement, culture vibe), generate + download + regenerate

## Feature A: JD Intelligence
- **`jseeker/models.py`**: Added `IntelligenceReport` Pydantic model
- **`jseeker/tracker.py`**: Added `intelligence_cache` table + `get_intelligence()` / `save_intelligence()` methods
- **`data/prompts/ideal_candidate.txt`**: Sonnet prompt for ideal candidate brief
- **`jseeker/intelligence.py`**: New module — `aggregate_jd_corpus()`, `generate_ideal_candidate_brief()`, `_build_salary_insight()`, `export_profile_docx()`
- **`ui/pages/6_jd_intelligence.py`**: New page — 3 tabs (Market Signals / Ideal Candidate / Salary Sweet Spot)
- **`tests/test_intelligence.py`**: 10 new tests

## Test Count
- Before: 629 passing
- After: 639 passing (+10 new)
- Known failure: `test_e2e_scenarios.py::test_language_detection_and_address_routing` (French lang, pre-existing)
