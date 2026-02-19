# jSeeker -- The Shape-Shifting Resume Engine

## Role
jSeeker (formerly PROTEUS) adapts structured resume content to match job descriptions, scores ATS compliance per platform, renders PDF + DOCX, generates recruiter outreach, and tracks applications. It is a GAIA ecosystem product.

## UX Principles (STANDING RULE — applies to all UI work)
Every UI decision must optimize for:
- **Progressive cognitive load** — surface only what the user needs at that moment; reveal complexity on demand
- **Progressive transparency** — show outcomes and system state clearly; no silent failures or ambiguous states
- **Least clicks** — default paths require minimum interaction; power options are one level deeper
- **High task success rate** — if a user starts a task, the UI must make it easy to complete it correctly
- **Short time to task completion** — pre-fill from known data (tracker, DB) wherever possible; never make users re-enter what the system already knows
- **Low error rate** — validate early, guide recovery, never leave users at a dead end
- **Low CES (Customer Effort Score)** — every flow should feel effortless; if it feels like work, redesign it

**Practical implications:**
- Always query existing DB data to pre-populate forms (resumes → tracker → companies)
- Multiselect + batch actions over one-by-one workflows
- Inline status and feedback — no page reloads to see what happened
- Collapse advanced options by default (expanders, tabs); primary path is always visible
- Show counts and context in labels ("12 applications available", "WORKDAY · DOCX") so users can decide without clicking through

## Quick Start
1. Setup: `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`
2. Install MYCEL: `pip install -e X:\Projects\_GAIA\_MYCEL`
3. Install browsers: `playwright install`
4. Launch: `python run.py`
5. Open: http://localhost:8502

## Setup & Launch

### Setup
```bash
# Create venv
python -m venv .venv
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
pip install -e X:\Projects\_GAIA\_MYCEL  # MYCEL local package
playwright install  # Browser for PDF rendering
```

### Launch
```bash
# Windows (recommended - clears cache + kills port automatically)
start.bat                    # jSeeker only via run.py

# Standalone launches (choose one)
python run.py                # jSeeker with venv/deps check (recommended)
python launch.py             # jSeeker only on :8502 (quick start)
python launch_jseeker.py     # jSeeker only (explicit)
python launch_argus.py       # ARGUS only on :8501
python launch_both.py        # Co-launch jSeeker + ARGUS together

# Direct Streamlit (no checks)
streamlit run ui/app.py --server.port 8502  # jSeeker only
```

## Constitutional Constraints
1. Never invent or hallucinate experience, metrics, or achievements -- only adapt real content from resume blocks
2. All LLM calls must be cost-tracked and logged
3. Resume blocks are the single source of truth -- adaptation rewrites phrasing, never fabricates
4. ATS scoring must be platform-aware (Greenhouse, Workday, Lever, iCIMS, Ashby, Taleo)
5. User edits are sacred -- the feedback system learns from them, never overrides

## Directory Structure
jseeker/ -- main package (models, llm, jd_parser, matcher, adapter, ats_scorer, renderer, outreach, tracker, job_discovery, job_monitor, feedback)
data/ -- YAML resume blocks, HTML/CSS templates, prompt templates, ATS profiles, SQLite DB
ui/ -- Streamlit app (dashboard, new_resume, editor, tracker, job_discovery, block_manager, analytics)
scripts/ -- maintenance tools (backfill_application_data.py, validation test suites)
tests/ -- pytest suite
docs/ -- PRD, architecture, user guide, ATS research, changelog
output/ -- generated resumes (gitignored)

## Coding Patterns
- All data models in jseeker/models.py (Pydantic v2)
- LLM calls via jseeker/llm.py (Haiku for cheap tasks, Sonnet for quality)
- Resume content in data/resume_blocks/*.yaml (tagged per template A/B/C)
- HTML templates rendered via Jinja2 + Playwright for PDF
- SQLite for persistence (jseeker.db)
- Prompt templates in data/prompts/*.txt with {variable} placeholders

## Integration Points
- **MYCEL**: LLM client via integrations/mycel_bridge.py (fallback to direct Anthropic SDK)
- **ARGUS**: Build + runtime telemetry via integrations/argus_telemetry.py
- **MNEMIS**: Pattern storage via integrations/mnemis_bridge.py (Phase 3+)

## Testing
# Full test suite (642 tests, 640 passing as of v0.3.13)
pytest tests/ --cov=jseeker

# Faster feedback during development (~110s without coverage)
pytest tests/ -q --tb=short

# Pre-commit validation for major releases
python scripts/test_v0_3_2_complete.py

# Known failures (not blockers): 1 E2E test in test_e2e_scenarios.py
# - Language detection edge case (French) — pre-existing, not a blocker

# Backwards compatibility testing
- When adding schema changes (new model fields, DB columns), create tests that load old data without new fields to catch AttributeError/KeyError regressions before production. Example: test old PipelineResult objects without pdf_validation field.

## Key Files
- jseeker/adapter.py -- Core value: Claude-powered resume content adaptation
- jseeker/renderer.py -- PDF (Playwright) + DOCX (python-docx) generation
- jseeker/llm.py -- Claude API wrapper with model routing and caching
- jseeker/models.py -- All Pydantic data types
- ui/pages/2_new_resume.py -- Main user workflow wizard

## Gotchas
- **__pycache__ after renames**: Bulk file renames cause stale bytecode. Clear all `__pycache__/` dirs: `find . -name "__pycache__" -type d -exec rm -rf {} +`
- **MYCEL local install**: Must be installed as editable (`-e`) not from PyPI
- **Job Discovery parsers**: Depend on site markup; may need updates if sites change CSS selectors
- **DB auto-migration**: First run auto-renames `proteus.db` -> `jseeker.db` (safe, keeps data)
- **process_jd() signature**: Only accepts (`raw_text`, `jd_url`, `use_semantic_cache`) - NOT `role_title` or `company_name`
- **ParsedJD model**: Has NO `relevance_score` field (computed during matching phase, not JD parsing)
- **Version management**: Update version in BOTH `config.py` (app_version) AND `jseeker/__init__.py` (__version__)
- **statsmodels dependency**: Required for Performance Trends trendline (ui/pages/7_learning_insights.py). Gracefully degrades to scatter plot if unavailable.
- **Streamlit batch completion**: After setting `st.session_state.batch_running = False`, MUST call `st.rerun()` to trigger UI update showing completion/retry sections - auto-refresh loops stop when batch completes
- **Streamlit background threads & polling**: Background thread callbacks can't trigger reruns - use explicit polling loop BEFORE conditionals: `get_progress()` + `st.rerun()` every 2s. Don't put rerun logic inside `if session_state.x:` blocks that depend on thread updates.
- **Streamlit widget key conflicts**: Can't directly update `st.session_state["widget_key"]` from button callbacks. Use intermediate key pattern: store in `st.session_state["temp_key"]`, copy to widget key before widget renders, call `st.rerun()`. See Fetch JD button (2_new_resume.py lines 73-90).
- **URL company extraction**: `_extract_company_from_url()` in jd_parser.py handles Lever/Greenhouse/Workday + generic `careers.company.com` pattern - add new ATS platforms here when extraction fails
- **New model fields need backwards compatibility**: When adding fields to Pydantic models, always make them `Optional[Type] = None` AND use defensive access in consuming code (`getattr(obj, "attr", None)` or `hasattr()`). UI must check field existence before access. Example: pdf_validation on PipelineResult (v0.3.8).
- **DataFrame column additions need defensive checks**: When adding columns to DB tables, check existence before operations: `if "col" not in df.columns: df["col"] = default`. Old records won't have new columns. Example: domain column in patterns table (v0.3.8).
- **JSON parsing for old DB data**: Wrap JSON parsing in try/except for malformed data from schema migrations: `try: data = json.loads(row["field"]) except json.JSONDecodeError: data = {}`.
- **Recurring errors**: If same bug appears 2+ times, root cause wasn't fixed - investigate state management, lifecycle, or async issues before patching symptoms
- **ApplyVerifier hard proof required**: `applied_verified` needs URL OR DOM OR automation-id signal + no error banners + form gone. Never set without hard proof.
- **ApplyMonitor circuit breaker**: auto-disables platforms after 3 consecutive failures; `BatchSummary.hitl_required=True` flags paused items for user review
- **BatchSummary**: `apply_batch()` now returns `BatchSummary` not `list[AttemptResult]` — update any callers accordingly
- **Python 3.14 + Playwright on Windows**: `SelectorEventLoop` breaks Playwright subprocess launch. Fix: `_loop = asyncio.ProactorEventLoop(); asyncio.set_event_loop(_loop)` BEFORE importing playwright. Do NOT use deprecated `set_event_loop_policy`.
- **Playwright inside Streamlit**: NEVER call `sync_playwright()` in Streamlit's main thread (asyncio conflict). Use `scripts/run_auto_apply_batch.py` as a subprocess via `subprocess.Popen`. See `ui/pages/9_auto_apply.py`.
- **subprocess.Popen stdout deadlock**: If child process writes heavily to stdout, NEVER use `stdout=subprocess.PIPE` without reading it — pipe buffer (~64KB) fills and child blocks. Use `stdout=None` to inherit terminal; poll DB for progress instead.
- **Auto-apply dedup logic**: `check_dedup()` in tracker.py must NOT check the `applications` table — every tracked job lives there. Only block on `applied_verified`/`applied_soft` in `apply_queue`.
- **ATS screening question selectors**: `.field label` and similar broad selectors catch personal info labels (Phone, Email, Name, etc.) as unknown screening questions. Both runners have `_PERSONAL_INFO_LABELS` frozenset — add new labels there, not to the answer bank.
- **Salary extraction: multi-location JDs**: `_extract_salary()` in jd_parser.py prioritizes "Primary Location" section when multiple pay ranges are listed (e.g. PayPal San Jose + Austin). Also handles `$242,000.00` decimal-cent format via pre-normalization.
- **automation/ namespace path depth**: Files in `jseeker/automation/` are one level deeper than the old `jseeker/` root. Any `Path(__file__).parent.parent...` data-path resolvers need one extra `.parent`. answer_bank.py uses `.parent.parent.parent`; ats_runners/*.py use `.parent.parent.parent.parent`.
- **Greenhouse branded URL career subdomains**: `CAREER_SUBDOMAINS` frozenset in jd_parser.py handles `careers.withwaymo.com` → extract `parts[1]` not `parts[0]`. Add new career subdomain prefixes to that frozenset.

## DO NOT
- Invent experience or metrics not in resume_blocks YAML
- Use Opus model at runtime (budget constraint)
- Store API keys anywhere except .env
- Commit .env, output/, or jseeker.db