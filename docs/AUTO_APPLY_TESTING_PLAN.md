# jSeeker Auto-Apply Engine -- User Testing Plan

**Version**: v1.0 Sprint 1+
**Last updated**: 2026-02-16
**Audience**: Developer/user performing manual validation at each sprint gate

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Phase 1 Testing: Answer Bank + Unit Tests (Level 1)](#2-phase-1-testing)
3. [Phase 2 Testing: Dry-Run Forms (Level 2)](#3-phase-2-testing)
4. [Phase 3 Testing: Sandbox Submissions (Level 3)](#4-phase-3-testing)
5. [Phase 4 Testing: Assisted Real Applications (Level 4)](#5-phase-4-testing)
6. [How to Run Each Component](#6-how-to-run)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Prerequisites

### Environment Setup

```bash
# Activate venv
cd X:\projects\jSeeker
.venv\Scripts\activate

# Verify dependencies
pip install -r requirements.txt
pip install -e X:\Projects\_GAIA\_MYCEL
playwright install
```

### Required Configuration

**`.env` file** (add these for auto-apply):
```env
# Existing
ANTHROPIC_API_KEY=sk-ant-...

# NEW for auto-apply (add when ready for dry-run testing)
WORKDAY_EMAIL=your-workday-email@example.com
WORKDAY_PASSWORD=your-workday-password
GREENHOUSE_EMAIL=your-greenhouse-email@example.com
GREENHOUSE_PASSWORD=your-greenhouse-password
```

### Answer Bank Setup

Before any testing, populate `data/answer_bank.yaml` with your real data:

```bash
# Open the answer bank file
notepad data\answer_bank.yaml
```

Replace ALL `PLACEHOLDER` values with real information for each market you use.
At minimum, fill out the `us` and `mx` markets completely. Other markets can stay
as placeholders if not actively used.

**Fields to fill per market:**
- `first_name`, `last_name` -- your legal name
- `email` -- the email you use for job applications
- `phone` -- phone number in international format
- `address`, `city`, `state`, `zip`, `country` -- your address for that market
- `work_authorization` -- "authorized" or "requires_sponsorship"
- `requires_sponsorship` -- true/false
- `linkedin_url` -- your LinkedIn profile URL
- `start_date` -- "immediately" or "2 weeks" etc.

**Screening patterns to review:**
- `years of experience` -- update the number (currently "7")
- `notice period` -- update if not "2 weeks"
- `education` -- update if not "Bachelor's degree"
- All `salary|compensation` patterns are set to PAUSE (never auto-answered)

---

## 2. Phase 1 Testing: Answer Bank + Unit Tests (Level 1)

**Goal**: Verify all code works correctly, answer bank loads with your real data,
ATS detection routes properly.

**When**: After Sprint 1 code delivery (NOW)

### Step 1: Run the Full Unit Test Suite

```bash
cd X:\projects\jSeeker
.venv\Scripts\activate

# Run ALL tests (expect ~583 passing, 1 known failure)
python -m pytest tests/ -q --tb=short

# Run ONLY auto-apply tests (expect 98 passing)
python -m pytest tests/test_answer_bank.py tests/test_auto_apply_models.py tests/test_site_runner_base.py tests/test_workday_runner.py tests/test_greenhouse_runner.py tests/test_auto_apply.py -v
```

**Pass criteria**: 98/98 new tests pass. No regressions in existing tests.

### Step 2: Validate Your Answer Bank

```bash
# Quick validation -- should print without errors
python -c "from jseeker.answer_bank import load_answer_bank; bank = load_answer_bank(); print(f'Loaded {len(bank.personal_info)} markets, {len(bank.screening_patterns)} patterns')"

# Detailed check -- inspect each market
python -c "
from jseeker.answer_bank import load_answer_bank, get_personal_info
bank = load_answer_bank()
for market in ['us', 'mx', 'uk', 'ca', 'fr', 'es', 'dk']:
    info = get_personal_info(bank, market)
    print(f'{market}: {info.first_name} {info.last_name} | {info.email} | {info.city}, {info.country}')
"
```

**What to check**:
- [ ] All 7 markets load without error
- [ ] Your real name/email/phone appear for markets you use
- [ ] Placeholder data is acceptable for markets you don't use
- [ ] No empty required fields (email, phone, first_name, last_name)

### Step 3: Test Screening Question Matching

```bash
python -c "
from jseeker.answer_bank import load_answer_bank, answer_screening_question
bank = load_answer_bank()

# Test common questions
questions = [
    'How many years of experience do you have in software engineering?',
    'Are you willing to relocate?',
    'What is your desired salary?',
    'How did you hear about this position?',
    'Are you authorized to work in the United States?',
    'Do you require visa sponsorship?',
    'What is your earliest start date?',
    'What is your highest level of education?',
    'Have you ever been convicted of a felony?',
    'Are you at least 18 years old?',
    'What is your gender?',
    'Tell me about a time you solved a complex problem',  # Should PAUSE (unknown)
]

for q in questions:
    answer, is_pause = answer_screening_question(bank, q)
    status = 'PAUSE' if is_pause else f'ANSWER: {answer}'
    print(f'  Q: {q[:60]:<60} -> {status}')
"
```

**What to check**:
- [ ] Salary questions -> PAUSE (never auto-answered)
- [ ] Unknown/open-ended questions -> PAUSE
- [ ] Work authorization -> correct answer for your situation
- [ ] Years of experience -> correct number
- [ ] EEO/diversity questions -> "Decline to self-identify"
- [ ] All answers are accurate for your profile

### Step 4: Test ATS Platform Detection

```bash
python -c "
from jseeker.ats_runners.workday import WorkdayRunner
from jseeker.ats_runners.greenhouse import GreenhouseRunner

wd = WorkdayRunner()
gh = GreenhouseRunner()

test_urls = [
    ('https://company.wd5.myworkdayjobs.com/careers/job/role', 'Workday'),
    ('https://boards.greenhouse.io/company/jobs/12345', 'Greenhouse'),
    ('https://job-boards.greenhouse.io/company/jobs/67890', 'Greenhouse'),
    ('https://jobs.lever.co/company/12345', 'Neither'),
    ('https://www.linkedin.com/jobs/view/12345', 'Neither'),
    ('https://company.myworkdayjobs.com/en-US/careers', 'Workday'),
]

for url, expected in test_urls:
    detected = 'Workday' if wd.detect(url) else ('Greenhouse' if gh.detect(url) else 'Neither')
    match = 'OK' if detected == expected else 'MISMATCH'
    print(f'  [{match}] {url[:65]:<65} -> {detected} (expected {expected})')
"
```

**What to check**:
- [ ] Workday URLs detected correctly (myworkdayjobs.com, wd1-wd5)
- [ ] Greenhouse URLs detected correctly (boards.greenhouse.io, job-boards.greenhouse.io)
- [ ] Non-supported URLs return Neither (Lever, LinkedIn, etc.)

### Step 5: Test Queue + Dedup System

```bash
python -c "
from pathlib import Path
import tempfile
from jseeker.tracker import init_db, queue_application, get_queued_applications, get_queue_stats, check_dedup

# Use temp DB
db = Path(tempfile.mktemp(suffix='.db'))
init_db(db)

# Queue 3 test jobs
q1 = queue_application('https://company.wd5.myworkdayjobs.com/job1', '/fake/resume.docx', 'workday', 'us', db_path=db)
q2 = queue_application('https://boards.greenhouse.io/company/job2', '/fake/resume.pdf', 'greenhouse', 'us', db_path=db)
q3 = queue_application('https://company.wd3.myworkdayjobs.com/job3', '/fake/resume.docx', 'workday', 'mx', db_path=db)
print(f'Queued 3 jobs: IDs {q1}, {q2}, {q3}')

# Check stats
stats = get_queue_stats(db_path=db)
print(f'Queue stats: {stats}')

# Test dedup
is_dup = check_dedup('https://company.wd5.myworkdayjobs.com/job1', db_path=db)
print(f'Dedup check (existing URL): {is_dup} (should be True)')

is_new = check_dedup('https://example.com/new-job', db_path=db)
print(f'Dedup check (new URL): {is_new} (should be False)')

# Get queued items
items = get_queued_applications(limit=10, db_path=db)
print(f'Queued items: {len(items)} (should be 3)')
for item in items:
    print(f'  #{item[\"id\"]}: {item[\"ats_platform\"]} | {item[\"market\"]} | {item[\"status\"]}')

# Cleanup
db.unlink(missing_ok=True)
print('All queue tests passed!')
"
```

**What to check**:
- [ ] Queuing works, returns sequential IDs
- [ ] Stats show correct counts
- [ ] Dedup blocks duplicate URLs
- [ ] Dedup allows new URLs
- [ ] Queued items retrievable with correct data

### Step 6: Test AutoApplyEngine Routing

```bash
python -c "
from jseeker.auto_apply import AutoApplyEngine
from jseeker.ats_runners.workday import WorkdayRunner
from jseeker.ats_runners.greenhouse import GreenhouseRunner

engine = AutoApplyEngine()
engine.register_runner(WorkdayRunner())
engine.register_runner(GreenhouseRunner())

test_urls = [
    'https://company.wd5.myworkdayjobs.com/careers/job/123',
    'https://boards.greenhouse.io/company/jobs/456',
    'https://jobs.lever.co/company/789',
    'https://www.linkedin.com/jobs/view/000',
    'https://random-careers-site.com/apply',
]

for url in test_urls:
    runner = engine.detect_platform(url)
    name = type(runner).__name__ if runner else 'None (unsupported)'
    print(f'  {url[:60]:<60} -> {name}')
"
```

**What to check**:
- [ ] Workday URLs route to WorkdayRunner
- [ ] Greenhouse URLs route to GreenhouseRunner
- [ ] Unknown URLs return None

### Phase 1 Sign-Off Checklist

After completing all 6 steps:

- [ ] All 98 unit tests pass
- [ ] No regressions in existing 484+ tests
- [ ] Answer bank loads with my real data for all markets I use
- [ ] Screening questions match correctly for common patterns
- [ ] Salary/unknown questions correctly PAUSE
- [ ] ATS detection routes Workday and Greenhouse correctly
- [ ] Queue system works (CRUD + dedup)
- [ ] Engine routes URLs to correct runners

**Signed off by**: _____________ **Date**: _____________

---

## 3. Phase 2 Testing: Dry-Run Forms (Level 2)

**Goal**: Fill real ATS forms without submitting. Verify every field is correct.

**When**: After Sprint 2 + Sprint 3 code delivery

**Requires**: `.env` credentials for Workday and Greenhouse

### Prerequisites

1. Sprint 2 COMPLETE ✅ (ApplyVerifier + ApplyMonitor + integration wiring — v0.3.11)
2. Sprint 3 COMPLETE ✅ (UI dashboard: `ui/pages/9_auto_apply.py` — v0.3.11)
3. `.env` has real ATS credentials (WORKDAY_EMAIL, WORKDAY_PASSWORD, GREENHOUSE_EMAIL, GREENHOUSE_PASSWORD)
4. `data/answer_bank.yaml` has real personal data (no PLACEHOLDER values)

**Workday known fields now handled**: SMS consent checkbox, FCRA background check ack, reasons-for-leaving, phone extension, skills tags

### How to Run: CLI Dry-Run

```bash
cd X:\projects\jSeeker
.venv\Scripts\activate

# Single Workday dry-run (fill form, screenshot, don't submit)
python -c "
from jseeker.auto_apply import AutoApplyEngine
from jseeker.ats_runners.workday import WorkdayRunner
from jseeker.ats_runners.greenhouse import GreenhouseRunner
from pathlib import Path

engine = AutoApplyEngine()
engine.register_runner(WorkdayRunner())
engine.register_runner(GreenhouseRunner())

# Replace with a REAL Workday job URL you want to test
result = engine.apply_single(
    job_url='https://company.wd5.myworkdayjobs.com/en-US/careers/job/role-title/JR12345',
    resume_path=Path('output/latest_resume.docx'),  # Your generated resume
    market='us',
    dry_run=True,  # IMPORTANT: dry_run=True means NO submit
)
print(f'Status: {result.status.value}')
print(f'Fields filled: {result.fields_filled}')
print(f'Screenshots: {result.screenshots}')
print(f'Errors: {result.errors}')
"
```

### How to Run: Dashboard Dry-Run

```bash
# Launch jSeeker
python run.py

# Open browser to http://localhost:8502
# Navigate to "Auto Apply" page (page 9)
# Select dry-run mode
# Queue jobs and click "Start Dry-Run"
```

### Dry-Run Test Matrix

Run 10 Workday + 10 Greenhouse dry-runs on real job postings:

| # | Platform | Company | URL | Fields OK? | Screenshot OK? | Notes |
|---|----------|---------|-----|-----------|---------------|-------|
| 1 | Workday | | | | | |
| 2 | Workday | | | | | |
| 3 | Workday | | | | | |
| 4 | Workday | | | | | |
| 5 | Workday | | | | | |
| 6 | Workday | | | | | |
| 7 | Workday | | | | | |
| 8 | Workday | | | | | |
| 9 | Workday | | | | | |
| 10 | Workday | | | | | |
| 11 | Greenhouse | | | | | |
| 12 | Greenhouse | | | | | |
| 13 | Greenhouse | | | | | |
| 14 | Greenhouse | | | | | |
| 15 | Greenhouse | | | | | |
| 16 | Greenhouse | | | | | |
| 17 | Greenhouse | | | | | |
| 18 | Greenhouse | | | | | |
| 19 | Greenhouse | | | | | |
| 20 | Greenhouse | | | | | |

### What to Inspect Per Dry-Run

1. **Open the screenshot** in `data/apply_logs/{attempt_id}/form_before_submit.png`
2. Check every field:
   - [ ] First name correct
   - [ ] Last name correct
   - [ ] Email correct
   - [ ] Phone correct
   - [ ] Address/city/state/zip correct for market
   - [ ] Resume uploaded (file name visible)
   - [ ] Screening questions answered correctly
   - [ ] No error banners or validation messages visible
3. Check the attempt log: `data/apply_logs/{attempt_id}/attempt_log.json`
   - [ ] All steps show "success"
   - [ ] No timeout errors
   - [ ] Fields filled dict matches what's visible in screenshot

### Finding Test URLs

Search your existing jSeeker database for Workday/Greenhouse jobs:

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/jseeker.db')
c = conn.cursor()

# Find Workday jobs
print('=== WORKDAY JOBS ===')
c.execute(\"\"\"SELECT jd_url, role_title, location FROM applications
    WHERE jd_url LIKE '%workday%' OR jd_url LIKE '%myworkdayjobs%'
    ORDER BY created_at DESC LIMIT 10\"\"\")
for row in c.fetchall():
    print(f'  {row[1]} | {row[2]} | {row[0][:80]}')

# Find Greenhouse jobs
print('\\n=== GREENHOUSE JOBS ===')
c.execute(\"\"\"SELECT jd_url, role_title, location FROM applications
    WHERE jd_url LIKE '%greenhouse%'
    ORDER BY created_at DESC LIMIT 10\"\"\")
for row in c.fetchall():
    print(f'  {row[1]} | {row[2]} | {row[0][:80]}')

conn.close()
"
```

Or use Job Discovery (page 5) to find fresh postings and filter by ATS.

### Phase 2 Sign-Off Checklist

- [ ] 10 Workday dry-runs completed
- [ ] 10 Greenhouse dry-runs completed
- [ ] 0 field errors across all 20 dry-runs
- [ ] All screenshots reviewed and data accurate
- [ ] Screening questions answered correctly on every form
- [ ] Salary/unknown questions correctly paused
- [ ] Resume uploaded successfully on every form
- [ ] No unexpected popups or errors

**Signed off by**: _____________ **Date**: _____________

---

## 4. Phase 3 Testing: Sandbox Submissions (Level 3)

**Goal**: Submit to real jobs you would NEVER accept. Verify end-to-end.

**When**: After Phase 2 sign-off

**IMPORTANT**: Use throwaway jobs only -- wrong seniority, wrong city, wrong industry.

### How to Run

```bash
# Via dashboard (recommended -- shows live progress)
python run.py
# Open http://localhost:8502 -> Auto Apply page
# Queue throwaway jobs
# Select "Sandbox" mode
# Click "Start"

# Or via CLI
python -c "
from jseeker.auto_apply import AutoApplyEngine
from jseeker.ats_runners.workday import WorkdayRunner
from jseeker.ats_runners.greenhouse import GreenhouseRunner
from pathlib import Path

engine = AutoApplyEngine()
engine.register_runner(WorkdayRunner())
engine.register_runner(GreenhouseRunner())

result = engine.apply_single(
    job_url='https://throwaway-company.wd5.myworkdayjobs.com/job',
    resume_path=Path('output/latest_resume.docx'),
    market='us',
    dry_run=False,  # REAL SUBMISSION
)
print(f'Status: {result.status.value}')
print(f'Confirmation: {result.confirmation_text}')
print(f'Confirmation URL: {result.confirmation_url}')
"
```

### Sandbox Test Matrix

| # | Platform | Job (throwaway) | Submitted? | Verified? | Confirmation? | Cost |
|---|----------|----------------|-----------|-----------|--------------|------|
| 1 | Workday | | | | | $0 |
| 2 | Workday | | | | | $0 |
| 3 | Workday | | | | | $0 |
| 4 | Workday | | | | | $0 |
| 5 | Workday | | | | | $0 |
| 6 | Greenhouse | | | | | $0 |
| 7 | Greenhouse | | | | | $0 |
| 8 | Greenhouse | | | | | $0 |
| 9 | Greenhouse | | | | | $0 |
| 10 | Greenhouse | | | | | $0 |
| 11 | Workday | | | | | $0 |
| 12 | Greenhouse | | | | | $0 |
| 13 | Workday | | | | | $0 |
| 14 | Greenhouse | | | | | $0 |
| 15 | Workday | | | | | $0 |

### What to Verify Per Submission

1. **Status = `applied_verified`** (hard proof)
   - If `applied_soft` -- review screenshot manually, may be OK
   - If `paused_*` -- investigate the pause reason
2. **Confirmation screenshot** exists in `data/apply_logs/{id}/confirmation.png`
3. **Check your email** for "application received" confirmation
4. **No account warnings** -- check Workday/Greenhouse account pages
5. **No CAPTCHAs triggered** -- if so, note which site

### Phase 3 Sign-Off Checklist

- [ ] 15 submissions attempted across both platforms
- [ ] Hard-verified rate >= 85% (at least 13 of 15 `applied_verified`)
- [ ] Confirmation screenshots captured for every submission
- [ ] Confirmation emails received (check inbox)
- [ ] No account bans or warnings
- [ ] No CAPTCHAs blocking submissions
- [ ] Cost: $0.00 (Playwright-only, no LLM costs)

**Signed off by**: _____________ **Date**: _____________

---

## 5. Phase 4 Testing: Assisted Real Applications (Level 4)

**Goal**: Apply to real target jobs while you watch the process live.

**When**: After Phase 3 sign-off

### How to Run

```bash
# Launch jSeeker
python run.py

# Open http://localhost:8502 -> Auto Apply page
# Queue 10 REAL target jobs from your starred/generated list
# Select "Assisted" mode
# Click "Start"
# WATCH every application in the live progress view
# Use "Pause" or "Cancel" if anything looks wrong
```

### Assisted Test Matrix

| # | Company | Role | Platform | Submitted? | Quality OK? | Would you do same manually? |
|---|---------|------|----------|-----------|-------------|---------------------------|
| 1 | | | | | | |
| 2 | | | | | | |
| 3 | | | | | | |
| 4 | | | | | | |
| 5 | | | | | | |
| 6 | | | | | | |
| 7 | | | | | | |
| 8 | | | | | | |
| 9 | | | | | | |
| 10 | | | | | | |

### Phase 4 Sign-Off Checklist

- [ ] 10 real applications attempted
- [ ] Submission rate >= 90% (at least 9 of 10 verified)
- [ ] Every application reviewed in real-time
- [ ] Application quality matches what I would do manually
- [ ] No incorrect data submitted
- [ ] No account issues
- [ ] Ready for version bump to v1.0.0

**Signed off by**: _____________ **Date**: _____________

---

## 6. How to Run Each Component

### Quick Reference: Key Scripts and Commands

| Task | Command |
|------|---------|
| **Launch jSeeker** | `python run.py` or `start.bat` |
| **Run all tests** | `python -m pytest tests/ -q --tb=short` |
| **Run auto-apply tests only** | `python -m pytest tests/test_answer_bank.py tests/test_auto_apply_models.py tests/test_site_runner_base.py tests/test_workday_runner.py tests/test_greenhouse_runner.py tests/test_auto_apply.py -v` |
| **Validate answer bank** | `python -c "from jseeker.answer_bank import load_answer_bank; print(load_answer_bank())"` |
| **Check ATS detection** | `python -c "from jseeker.auto_apply import AutoApplyEngine; ..."` (see Phase 1 Step 6) |
| **Find Workday/Greenhouse jobs in DB** | See Phase 2 "Finding Test URLs" section |
| **View attempt logs** | Browse `data/apply_logs/{attempt_id}/` |
| **View screenshots** | Open `data/apply_logs/{attempt_id}/*.png` |
| **Black format check** | `python -m black --check jseeker/ tests/` |
| **Reset queue (testing)** | Delete rows from `apply_queue` table in `data/jseeker.db` |

### File Locations

| What | Where |
|------|-------|
| Answer bank config | `data/answer_bank.yaml` |
| ATS credentials | `.env` (WORKDAY_EMAIL, WORKDAY_PASSWORD, etc.) |
| Workday selectors | `data/ats_runners/workday.yaml` |
| Greenhouse selectors | `data/ats_runners/greenhouse.yaml` |
| Attempt logs | `data/apply_logs/{attempt_id}/attempt_log.json` |
| Screenshots | `data/apply_logs/{attempt_id}/*.png` |
| Database | `data/jseeker.db` |
| Auto-apply dashboard | `ui/pages/9_auto_apply.py` (Sprint 3) |

### Architecture: What Calls What

```
User clicks "Start" (UI) or runs CLI
    |
    v
AutoApplyEngine.apply_single() or .apply_batch()
    |
    +--> check_dedup() via tracker.py
    +--> _check_rate_limit()
    +--> detect_platform() -> WorkdayRunner or GreenhouseRunner
    |
    v
SiteRunner.fill_and_submit(page, url, resume, answers, dry_run)
    |
    +--> Navigate to job URL
    +--> _check_for_overlay() (dismiss cookies/GDPR)
    +--> _try_selectors() for Apply button
    +--> _login() if needed (Workday only)
    +--> _try_upload() resume file
    +--> _fill_personal_info() from answer bank
    +--> _fill_screening_questions() from answer bank
    |     (PAUSE if unknown question or salary)
    +--> _screenshot() form before submit
    |
    +--> if dry_run: STOP here
    +--> if not dry_run: click Submit
    |
    v
_verify_submission() -- check URL/DOM for confirmation signals
    |
    +--> applied_verified (hard proof)
    +--> applied_soft (likely but unproven)
    +--> paused_ambiguous_result (unclear, needs user review)
    |
    v
_save_artifacts() -- attempt_log.json + screenshots to data/apply_logs/
```

---

## 7. Troubleshooting

### Common Issues

**"Missing markets in answer bank"**
- Your `data/answer_bank.yaml` is missing one or more of: us, mx, uk, ca, fr, es, dk
- Fix: Add the missing market section, even with placeholder data

**"Invalid email format" / "Invalid phone format"**
- A market entry in answer_bank.yaml has empty or malformed email/phone
- Fix: Fill in valid values

**Tests fail with ImportError**
- Missing dependency. Run `pip install -r requirements.txt`
- If `playwright` errors: run `playwright install`

**"No runner for URL"**
- The URL is not Workday or Greenhouse. v1 only supports these two.
- Check: URL should contain `myworkdayjobs.com` or `greenhouse.io`

**Dry-run fills nothing**
- Selectors may have changed on that specific site
- Check `data/apply_logs/{id}/attempt_log.json` for "all_selectors_failed" entries
- Fix: Update fallback selectors in `data/ats_runners/{platform}.yaml`

**Screening question pauses when it shouldn't**
- The question didn't match any pattern in answer_bank.yaml
- Fix: Add a new pattern to `data/answer_bank.yaml` under `screening_patterns`

**"Rate limit exceeded"**
- You've hit hourly (10) or daily (50) caps
- Fix: Wait, or adjust limits in code (RateLimitConfig defaults in models.py)

### How to Reset

```bash
# Clear all attempt logs
rm -rf data/apply_logs/*/

# Reset apply queue (clears queue, keeps applications)
python -c "
import sqlite3
conn = sqlite3.connect('data/jseeker.db')
conn.execute('DELETE FROM apply_errors')
conn.execute('DELETE FROM apply_queue')
conn.commit()
conn.close()
print('Queue and errors cleared')
"

# Full DB re-init (safe -- creates missing tables, doesn't drop existing)
python -c "from jseeker.tracker import init_db; init_db(); print('DB initialized')"
```
