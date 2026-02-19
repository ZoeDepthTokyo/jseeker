# jSeeker Root Issue Report — 2026-02-19

**Version at session start:** v0.3.12
**Version at session end:** v0.3.14
**Tests at start:** 640 total, 639 passing
**Tests at end:** 500 core + 141 autojs = 641 total, 641 passing (1 pre-existing French lang)
**Commits:** `cdd3cc0` → `555e03d` → `2622d3c` → `68e8698` → `17c669a` → `acefd88` → `f428659`

---

## Issue Index

| # | ID | Severity | Category | Status |
|---|----|----------|----------|--------|
| 1 | P0 | High | Architecture | Fixed |
| 2 | P1 | High | Bug | Fixed |
| 3 | P2 | Medium | Performance | Fixed |
| 4 | P3 | Low | UX | Fixed |
| 5 | P4 | Medium | Data Integrity | Fixed |
| 6 | JD-1 | High | Bug | Fixed |
| 7 | JD-2 | High | Bug | Fixed |
| 8 | TEST-1 | Medium | Test Regression | Fixed |

---

## P0 — Automation Pipeline Not Truly Decoupled

**Symptom:** Automation code (auto-apply engine, ATS runners, answer bank) lived inside `jseeker/` — same package, same version, same install. Changes to automation risked breaking core resume generation. No way to develop, version, or release them independently.

**Root Cause:** Initial decoupling attempt (`jseeker/automation/` namespace) was a cosmetic reorganization, not true project separation. Still one Python package, one `pyproject.toml`, shared import graph. Scope creep and bloat risk remained.

**Fix:** Promoted automation to `autojs/` — a sibling Python package at the repo root with its own `pyproject.toml`. Reads shared `data/` and `jseeker.db` from parent. Imports `jseeker.models`, `jseeker.tracker`, `jseeker.llm` as dependencies. Zero automation references remain in `jseeker/`.

**Structure after fix:**
```
jSeeker/ (repo root)
├── jseeker/           ← parent package (resume engine, unchanged)
├── autojs/            ← sibling package (automation)
│   ├── pyproject.toml (depends on jseeker)
│   ├── autojs/
│   └── tests/         ← 141 isolated tests
└── data/              ← shared YAML/DB
```

**Install:** `pip install -e autojs/` (after jseeker is installed)

**Files moved (git mv, history preserved):**
- `jseeker/automation/auto_apply.py` → `autojs/autojs/auto_apply.py`
- `jseeker/automation/apply_verifier.py` → `autojs/autojs/apply_verifier.py`
- `jseeker/automation/apply_monitor.py` → `autojs/autojs/apply_monitor.py`
- `jseeker/automation/answer_bank.py` → `autojs/autojs/answer_bank.py`
- `jseeker/automation/ats_runners/` → `autojs/autojs/ats_runners/`
- 8 automation test files moved to `autojs/tests/`

**Gotcha logged:** When moving Python files deeper in a namespace, every `Path(__file__).parent...` data-path resolver needs one extra `.parent` per nesting level added. `autojs/autojs/answer_bank.py` uses `.parent.parent.parent`; `autojs/autojs/ats_runners/*.py` use `.parent.parent.parent.parent` — both resolve to repo root.

---

## P1 — Greenhouse Branded URL Fails for `careers.*` Subdomains

**Symptom:** Parsing a Waymo job URL (`careers.withwaymo.com/jobs/...?gh_jid=7404570`) extracted `careers` as the company slug instead of `withwaymo`, producing a broken Greenhouse API URL.

**Root Cause:** Two functions in `jseeker/jd_parser.py` did `domain.split(".")[0]` unconditionally:
- `_resolve_branded_greenhouse_url()` (~line 855)
- `_extract_company_from_url()` (~line 581)

For `hubspot.com`, `split(".")[0]` → `"hubspot"` ✓
For `careers.withwaymo.com`, `split(".")[0]` → `"careers"` ✗

**Fix:** Added `CAREER_SUBDOMAINS` frozenset at module level. Both functions now check if `parts[0]` is a career subdomain and use `parts[1]` instead:

```python
CAREER_SUBDOMAINS = frozenset({"careers", "jobs", "hire", "apply", "work", "talent"})
parts = domain.split(".")
company_slug = parts[1] if len(parts) >= 3 and parts[0] in CAREER_SUBDOMAINS else parts[0]
```

**Tests added:** `test_waymo_greenhouse_url_resolves`, `test_hubspot_greenhouse_url_resolves`

**Pattern:** Any ATS with a `careers.company.com` domain structure hits this. Add new career subdomain prefixes to `CAREER_SUBDOMAINS` in `jd_parser.py` if new variants appear.

---

## P2 — Pattern Cache Hit Rate Too Low, No Visibility

**Symptom:** Resume generation speed not improving as expected after 10–20 resumes. Pattern cache hit rate was 30–40% due to conservative thresholds. No logging to confirm cache was active.

**Root Cause:** Default thresholds in `jseeker/pattern_learner.py` `find_matching_pattern()` were too strict:
- `similarity_threshold = 0.85` — required near-identical text to match
- `min_frequency = 3` — patterns needed 3 occurrences before activating

**Fix:**
1. `pattern_learner.py`: Lowered defaults to `similarity_threshold=0.75`, `min_frequency=2`
2. `adapter.py`: Added cache hit/miss instrumentation — logs `"Generation: N/M blocks from cache, K LLM calls, X.Xs"` after each resume
3. `ui/pages/2_new_resume.py`: Added cache tip in results section

**Expected impact:** Hit rate should reach 50–60% after 15+ resumes vs the previous 30–40%.

---

## P3 — Job Monitor Status Changes Show No Application ID

**Symptom:** "Check All Active Job URLs" listed changed statuses as `Company - Role: old -> new` with no ID reference. Users couldn't cross-reference with the Tracker without manually searching.

**Root Cause:** `ui/pages/1_pipeline.py` formatted the caption without the `app_id` key, even though `check_all_active_jobs()` in `job_monitor.py` already included `app_id` in its return dict.

**Fix:**
- Caption now shows `[#42] Company – Role: old → new`
- Added `st.info("Tracker page will reflect updated statuses...")` after the changes list
- Used `.get("app_id", "?")` for safety

---

## P4 — Navan Duplicate Application + Resume in DB

**Symptom:** Application ID 34 (Navan, `jd_url=https://navan.com/careers/openings/7616887?gh_jid=...`) had `role_title="Not provided"` and a malformed resume (summary was an LLM error message asking for missing JD data). Resume ID 33 was linked to this application.

**Root Cause:** JD was fetched without valid content (empty JD text passed to LLM), creating a junk record. A clean Navan application (app 36, resume 35) already existed with proper JD data.

**Fix:** Wrote and ran `scripts/check_dedup_navan.py` (dry-run → delete):
- Deleted application 34 (cascade deleted resume 33)
- Confirmed zero orphaned resumes and zero resumeless applications post-delete
- Script retained at `scripts/check_dedup_navan.py` for future audits

---

## JD-1 — JD Intelligence Page Crash on Load

**Symptom:**
```
sqlite3.OperationalError: no such column: market
File "jseeker/intelligence.py", line 76, in aggregate_jd_corpus
    salary_rows = conn.execute(
        "SELECT salary_min, salary_max, market FROM applications ..."
```

**Root Cause:** `intelligence.py` queried a `market` column that was never added to the `applications` table. The DB schema has `salary_currency` (e.g., `"USD"`) not `market` (e.g., `"us"`). The column was referenced in the original code but the corresponding DB migration was never written.

**Fix:** Replace `market` with `salary_currency` in both the SELECT query and the grouping key (line 77, 91). Default fallback changed from `"unknown"` to `"USD"`.

**Side effect:** `_build_salary_insight()` uses `parsed_jd.market` (e.g., `"us"`) to look up `salary_by_market`, but the dict now keys by currency (`"USD"`). The lookup will fall through to global percentiles — acceptable since `market` was never being populated from the DB anyway. A currency→market mapping can be added later if market-level breakdowns are needed.

**Verified:** Page loads with 50 cached JDs, `salary_by_market: ['USD']`.

---

## JD-2 — "Generate Ideal Candidate Profile" Pydantic Validation Error

**Symptom:**
```
ValidationError: 1 validation error for ParsedJD
raw_text
  Field required [type=missing, input_value={'title': 'Senior UX Engi...'}]
```
Triggered when selecting any JD from the intelligence page dropdown.

**Root Cause:** `ParsedJD.raw_text` was defined as `raw_text: str` (required, no default). Old `jd_cache` records were serialized before `raw_text` was added to the model and do not contain this field. `ParsedJD(**json.loads(row["parsed_json"]))` crashed on any cached record without `raw_text`.

**Fix:** Changed `raw_text: str` → `raw_text: str = ""` in `jseeker/models.py`. Old records load with an empty string; new records populate it normally. Per CLAUDE.md pattern: new model fields must always have a default for backwards compatibility.

**Pattern:** This is the same class of bug as `pdf_validation` on `PipelineResult` (v0.3.8). Any new required field added to a Pydantic model that is persisted to DB or cache will break on old records. **Always default new fields.**

---

## TEST-1 — test_intelligence.py Fixture Schema Mismatch

**Symptom:** After fixing JD-1 (market → salary_currency), 7 `test_intelligence.py` tests began failing:
```
sqlite3.OperationalError: no such column: salary_currency
```

**Root Cause:** The test fixtures created in-memory/tmp SQLite DBs with `market TEXT` column (matching the old broken schema). When `aggregate_jd_corpus()` was fixed to query `salary_currency`, the test DBs didn't have that column.

**Fix:** Updated all three places in `tests/test_intelligence.py`:
1. `CREATE TABLE applications` — `market TEXT` → `salary_currency TEXT`
2. `INSERT INTO applications` — values `'us'` → `'USD'`
3. Assertion — `.get("us", {})` → `.get("USD", {})`

**Pattern:** When fixing a column name in production code, always grep test fixtures for the old column name and update them in the same commit.

---

## Recurring Patterns / Cross-Cutting Findings

### 1. Pydantic backwards compatibility always needs defaults
Every field added to a persisted model (`ParsedJD`, `PipelineResult`, etc.) must have a default value. Failing to do so causes silent breakage on existing DB records. **Rule: new field → `Optional[Type] = None` or `str = ""`.**

### 2. Test fixture DBs must mirror production schema
Three separate incidents this session where test DBs had stale column names. Fixtures should be kept in sync when columns are renamed or added. Consider a shared `create_test_db()` helper that uses the real `init_db()` to avoid drift.

### 3. Path depth breaks on namespace moves
Moving a Python file one level deeper in a package requires adding one `.parent` to every `Path(__file__).parent...` data resolver. This is invisible until tests run against the real filesystem.

### 4. Background task results can be stale
Several task notifications delivered results from before fixes were applied. Always check the git log or run a fresh test when a background result conflicts with the known current state.

---

## Commits (this session)

| Commit | Description |
|--------|-------------|
| `cdd3cc0` | feat: v0.3.13 — automation namespace, Greenhouse URL fix, cache tuning, monitor UI |
| `555e03d` | docs: add v0.3.13 gotchas for automation namespace path depth |
| `2622d3c` | docs: update test count to 642/640 for v0.3.13 |
| `68e8698` | fix(intelligence): replace non-existent market column with salary_currency |
| `17c669a` | fix(models): make ParsedJD.raw_text optional (default empty string) |
| `acefd88` | fix(tests): update test_intelligence fixtures market→salary_currency |
| `f428659` | fix(autojs): complete P0 decoupling — update all imports to autojs.* namespace |

---

*Generated: 2026-02-19 | jSeeker v0.3.14*
