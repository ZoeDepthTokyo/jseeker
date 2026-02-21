# jSeeker — Engineering Handover Document

**Version**: v0.3.15 (target: v0.4.0)
**Last updated**: 2026-02-20
**Repo**: github.com/ZoeDepthTokyo/jseeker
**Ecosystem**: GAIA (alongside ARGUS, AURORA, MYCEL, RAVEN)

---

## North Star

**jSeeker adapts your resume to every job you apply to — automatically.**

Core success metric: **be the highest-quality, earliest applicant**. Every feature is judged by whether it reduces time-to-apply or increases application quality. Speed and quality compound: early applications are seen by more reviewers; tailored resumes pass ATS filters.

---

## Current State (v0.3.15)

| Metric | Value |
|--------|-------|
| Tests | 641 passing (500 core + 141 autojs), 1 pre-existing skip |
| Core pipeline | End-to-end working: JD → resume → DOCX/PDF → tracker |
| Job discovery | LinkedIn (rate-limited), Indeed/Wellfound (broken scrapers) |
| Auto-apply | Workday + Greenhouse (autojs package, v1.0) |
| Known limitations | ~50% JD extraction failure on ATS URLs; PDF formatting gaps |

---

## How It Works — System Architecture

### Data Flow

```
User provides JD URL or text
        │
        ▼
┌─────────────────┐
│  jd_parser.py   │  Extract: title, company, location, market,
│  process_jd()   │  language, requirements, keywords, salary
└────────┬────────┘
         │ ParsedJD
         ▼
┌─────────────────┐
│  matcher.py     │  Score resume blocks against JD requirements
│  match_resume() │  Returns: ResumeMatch (template A/B/C + score)
└────────┬────────┘
         │ ResumeMatch
         ▼
┌─────────────────┐
│  adapter.py     │  Claude rewrites bullet points to match JD
│  adapt_resume() │  Location/language adapted to job market
└────────┬────────┘
         │ AdaptedResume
         ▼
┌─────────────────┐
│  ats_scorer.py  │  Score ATS compliance per platform
│  score_resume() │  Greenhouse/Workday/Lever/iCIMS/Ashby/Taleo
└────────┬────────┘
         │ ATSScore
         ▼
┌─────────────────┐
│  renderer.py    │  Render PDF (Playwright+Jinja2) + DOCX
│  render()       │  Output to output/{Company}/Fede_Ponce_*.pdf/docx
└────────┬────────┘
         │ RenderResult
         ▼
┌─────────────────┐
│  tracker.py     │  Save application to SQLite (jseeker.db)
│  add_application│  Track status, resume path, ATS score
└─────────────────┘
```

### Package Structure

```
jseeker/          Core package — parse, adapt, score, render, track
autojs/           Automation sibling — form-filling, verification, monitoring
  autojs/         Inner package (pip install -e autojs/)
    auto_apply.py         Batch submission orchestrator
    answer_bank.py        Q&A lookup for ATS forms
    apply_verifier.py     Hard verification (URL/DOM signals)
    apply_monitor.py      Circuit breaker (3-strike platform disable)
    ats_runners/
      workday.py          Workday Playwright automation
      greenhouse.py       Greenhouse Playwright automation
ui/               Streamlit frontend
  app.py          Entry point + sidebar
  pages/
    2_new_resume.py       Main workflow: URL → resume → export
    3_resume_library.py   Browse and manage generated resumes
    4_tracker.py          Application CRM
    5_job_discovery.py    Tag-based job search
    6_jd_intelligence.py  JD analysis + ideal candidate brief
    7_analytics.py        Cost, performance, learning trends
data/
  resume_blocks/          YAML resume content (single source of truth)
    contact.yaml          Name, locations, languages
    experience/*.yaml     Work experience blocks (tagged A/B/C)
    skills.yaml           Technical + soft skills
  templates/              Jinja2 HTML templates for PDF
  prompts/                LLM prompt templates
  ats_runners/            ATS-specific YAML selectors (Workday)
  answer_bank.yaml        Default answers for ATS form fields
tests/            Pytest suite (500 core tests)
autojs/tests/     Automation tests (141 tests)
scripts/          Maintenance and batch tools
docs/             PRD, architecture docs, changelog
output/           Generated resumes (gitignored)
```

### Database Schema (jseeker.db — SQLite)

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `applications` | Application CRM | id, company, role, jd_url, application_status, resume_path, ats_score |
| `job_discoveries` | Raw job search results | id, title, company, url, source, status, market, posting_date, auto_queued |
| `jd_cache` | Parsed JD cache | pruned_text_hash, title, company, location, market, language, requirements_json |
| `api_costs` | Per-call LLM cost log | model, task, input_tokens, output_tokens, cost_usd, timestamp |
| `learned_patterns` | Pattern learning | pattern_type, source_text, target_text, frequency, confidence |
| `saved_searches` | Discovery search configs | name, tag_weights_json, market, location |
| `apply_queue` | Auto-apply queue | discovery_id, status, applied_verified, attempt_count |

### LLM Call Map

| Operation | Model | Why | ~Cost |
|-----------|-------|-----|-------|
| Resume adaptation (bullets) | Haiku | High volume, repetitive | $0.002/resume |
| Resume summary adaptation | Sonnet | Quality matters | $0.008/resume |
| ATS scoring | Haiku | Simple classification | $0.001/resume |
| JD parsing | Haiku | Structured extraction | $0.002/JD |
| Cover letter | Sonnet | Quality matters | $0.015/letter |
| Ideal candidate brief | Sonnet | Analysis quality | $0.010/report |
| Outreach email | Haiku | Template-like | $0.003/email |

All LLM calls tracked in `api_costs` table. Session cost shown in sidebar.

---

## Design Decisions & Rationale

**Why Streamlit (not FastAPI/React)?**
Solo operator, not a product. Streamlit gives interactive UI in Python with zero frontend work. Acceptable performance tradeoff for <5 concurrent users.

**Why SQLite (not Postgres)?**
Single-user, local-first, zero ops overhead. The DB file travels with the project. When this scales to multi-user, migration to Postgres is straightforward — all queries use standard SQL.

**Why autojs/ is a sibling package (not inside jseeker/)?**
Boundary rule: automation imports jseeker (reads the DB, uses models). jseeker must never import from autojs. One-way dependency prevents circular imports and lets autojs be installed or replaced independently. Rule: `jseeker/ and ui/ MUST NEVER import from autojs/`.

**Why Haiku for cheap tasks / Sonnet for quality?**
Cost discipline. Haiku = $0.80/M input tokens. Sonnet = $3.00/M. Repetitive tasks (ATS scoring, JD parsing) get Haiku. Judgment tasks (resume adaptation, cover letters) get Sonnet. **Opus is banned at runtime** — too expensive for interactive use.

**Why pattern learning?**
Each time a user edits an adapted bullet, the original→edited pair is stored as a learned pattern. Future adaptations for similar roles see the pattern and replicate the user's style. This reduces editing time and improves consistency across applications.

**Why YAML for resume blocks?**
Human-editable, version-controlled, structured. Each block has tags (A/B/C) indicating which template it belongs to. The adapter picks the right blocks for each job and rewrites them — never inventing content, only adapting phrasing.

---

## Constitutional Rules (Non-Negotiable)

1. **Never invent experience** — Only adapt content from `resume_blocks/*.yaml`. No hallucinated metrics, achievements, or roles.
2. **All LLM calls must be cost-tracked** — `tracker_db.log_cost()` after every API call.
3. **Resume blocks are the single source of truth** — Adaptation rewrites phrasing, never fabricates.
4. **ATS scoring must be platform-aware** — Greenhouse, Workday, Lever, iCIMS, Ashby, Taleo each have different requirements.
5. **User edits are sacred** — The feedback/learning system records edits and never overrides them.

---

## Version History

| Version | Date | Key Change | Tests |
|---------|------|-----------|-------|
| v0.4.0 | 2026-02-20 | PROJECT.md, multi-location rule, Pipeline→autojs, analytics dashboard | TBD |
| v0.3.15 | 2026-02-20 | Easy Apply status, dedup badges, recency sort/filter | 641 |
| v0.3.14 | 2026-02-19 | autojs/ sibling package decoupling, 8 root issue fixes | 641 |
| v0.3.11 | 2026-02-17 | Apply verification, circuit breaker, BatchSummary | 627 |
| v0.3.10 | 2026-02-16 | Auto-apply engine v1.0 (Answer Bank, Workday+Greenhouse runners) | 583 |
| v0.3.6 | 2026-02-13 | 22 fixes: LinkedIn→ATS resolution, generate_resume_from_discovery(), 4 ATS profiles | 400 |
| v0.3.0 | 2026-02-10 | PROTEUS→jSeeker rename, structured logging, DB migration | ~300 |
| v0.2.1 | 2026-02-09 | NoneType fix, Workday JD, deprecation, location defaults | ~250 |
| v0.1.0 | 2025-12-15 | Initial release as PROTEUS | ~100 |

See `CHANGELOG.md` for full detail per version.

---

## Active Roadmap

### v0.4.0 (in progress)
- PROJECT.md (this file)
- Fix: resume location uses source market (Barcelona→Spanish, not Toronto)
- Fix: JD Intelligence selector filters null entries
- Fix: Remove Italian/Japanese from resume languages
- Feature: Progress bar for Generate Resume in Discovery
- Feature: "Hide already tracked" toggle in Discovery
- Feature: Pipeline UI → autojs (keeps jSeeker nav clean)
- Feature: Star → auto-queue for batch resume generation
- Feature: Cover letter upgraded prompt (Sonnet, anti-buzzwords)
- Feature: Ideal Candidate glassbox (matched/missed keywords)
- Feature: Analytics — cost trend, cache hit rate, model mix

### v0.5.0 (planned)
- Dual-variant resume generation for multi-market jobs (Spanish+English)
- Scheduled discovery search (every 2h, auto-generate top N matches)
- Speed queue: <5min from new posting → resume ready
- Greenhouse.io direct search

### v0.6.0+ (automation)
- Full submission pipeline with HITL review
- Real-time job alert → resume → apply loop
- Resume performance analytics (response rate by template/company/role)

---

## Key Gotchas (Critical for New Engineers)

**Playwright on Windows (Python 3.14+)**
`SelectorEventLoop` breaks Playwright subprocess launch. Fix required before any Playwright call:
```python
_loop = asyncio.ProactorEventLoop()
asyncio.set_event_loop(_loop)
```
Do NOT use deprecated `set_event_loop_policy`.

**Playwright inside Streamlit**
NEVER call `sync_playwright()` in Streamlit's main thread (asyncio conflict). Use `subprocess.Popen` to run automation scripts. See `ui/pages/9_auto_apply.py`.

**Streamlit background threads & polling**
Background thread callbacks cannot trigger reruns. Use explicit polling loop BEFORE conditionals: `get_progress()` + `st.rerun()` every 0.5s. Never put rerun logic inside `if session_state.x:` blocks that depend on thread updates.

**Streamlit widget key conflicts**
Can't directly update `st.session_state["widget_key"]` from button callbacks. Use intermediate key pattern: store in temp key → copy to widget key before widget renders → `st.rerun()`.

**subprocess.Popen stdout deadlock**
If child process writes heavily to stdout, NEVER use `stdout=subprocess.PIPE` without reading it. Pipe buffer (~64KB) fills and child blocks. Use `stdout=None` to inherit terminal; poll DB for progress instead.

**autojs/ path depth**
Files in `autojs/autojs/` resolve data paths to repo root:
- `answer_bank.py`: `.parent.parent.parent`
- `ats_runners/*.py`: `.parent.parent.parent.parent`
Add one `.parent` per additional directory level.

**CAREER_SUBDOMAINS frozenset**
`careers.withwaymo.com` → extract `parts[1]` not `parts[0]`. Add new career subdomain prefixes to `CAREER_SUBDOMAINS` frozenset in `jd_parser.py`.

**Dedup logic**
`check_dedup()` in `tracker.py` must NOT check the `applications` table — every tracked job lives there. Only block on `applied_verified`/`applied_soft` in `apply_queue`.

**New model fields = always Optional**
When adding fields to Pydantic models: always `Optional[Type] = None`. Use `getattr(obj, "attr", None)` in consuming code. Old DB records won't have new columns.

**Version management**
Update version in BOTH `config.py` (app_version) AND `jseeker/__init__.py` (__version__) every release.

---

## How to Run

```bash
# 1. Setup (first time)
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
pip install -e X:\Projects\_GAIA\_MYCEL   # MYCEL local package
pip install -e autojs/                     # autojs automation package
playwright install                          # Browser for PDF rendering

# 2. Launch jSeeker (port 8502)
python run.py

# 3. Launch autojs automation dashboard (port 8503) — optional
python autojs/launch.py
```

**Tests**:
```bash
python -m pytest tests/ -q --tb=short          # Core (500 tests)
python -m pytest autojs/tests/ -q --tb=short   # Automation (141 tests)
python -m pytest tests/ autojs/tests/ -q       # Full suite (641 tests)
```

**Known non-blocking test failure**: `test_language_detection_and_address_routing` — French edge case, pre-existing, not a regression blocker.

---

## Team & Contacts

- **GitHub**: github.com/ZoeDepthTokyo/jseeker
- **Ecosystem org**: github.com/ZoeDepthTokyo/gaia-{warden,argus,mycel,vulcan}
- **Co-authored commits**: `Co-Authored-By: SuperGalaxyAlien <noreply@anthropic.com>`
