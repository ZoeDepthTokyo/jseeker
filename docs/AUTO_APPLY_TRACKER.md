# jSeeker Auto-Apply Engine v1.0 -- Progress Tracker

**Started**: 2026-02-16
**Current Sprint**: Sprint 2+3 (COMPLETE -- pending Phase 2 dry-run testing)
**Confidence Level**: 1 (Unit Tests Pass)
**Version**: v0.3.11
**Next Gate**: Level 2 (Dry-Run -- fill forms, don't submit) — HITL required

---

## Sprint Progress Overview

| Sprint | Scope | Code | Unit Tests | User Testing | Gate |
|--------|-------|------|------------|--------------|------|
| **1** | Foundation: Answer Bank + Runners + Orchestrator | DONE | 98/98 PASS | Phase 1 ✅ | Level 1 |
| **2** | Verification + Monitoring | DONE | 44/44 PASS | PENDING | Level 1+ |
| **3** | UI Dashboard | DONE | N/A | PENDING | Level 2 |
| 4 | Sandbox + Assisted | -- | -- | -- | Level 3-4 |

---

## Sprint 1: Foundation (COMPLETE -- Code Only)

**Date completed**: 2026-02-16
**Agents used**: 4 parallel (A: Answer Bank, B: Models+DB, C: Runners, D: Orchestrator)
**Test baseline**: 484 -> 583 passing (+98 new, 0 regressions)
**Known failure**: 1 pre-existing (French language detection edge case)

### Files Delivered

**New files (11):**

| File | Lines | Purpose |
|------|-------|---------|
| `data/answer_bank.yaml` | ~80 | Personal info (7 markets) + 17 screening patterns |
| `jseeker/answer_bank.py` | ~150 | Load, validate, query answer bank |
| `jseeker/ats_runners/__init__.py` | 0 | Package init |
| `jseeker/ats_runners/base.py` | ~120 | SiteRunner ABC + shared Playwright helpers |
| `jseeker/ats_runners/workday.py` | ~200 | Workday multi-step form filler |
| `jseeker/ats_runners/greenhouse.py` | ~180 | Greenhouse single-page form filler |
| `jseeker/auto_apply.py` | ~350 | AutoApplyEngine: routing, rate limiting, batch, artifacts |
| `data/ats_runners/workday.yaml` | ~60 | Workday selectors, confirmation signals, field mappings |
| `data/ats_runners/greenhouse.yaml` | ~60 | Greenhouse selectors, confirmation signals, field mappings |
| `tests/fixtures/ats_pages/workday_form.html` | ~30 | Mock Workday form fixture |
| `tests/fixtures/ats_pages/greenhouse_form.html` | ~40 | Mock Greenhouse form fixture |

**Modified files (4):**

| File | Changes |
|------|---------|
| `jseeker/models.py` | +AttemptStatus enum (26 states), +AttemptResult, +RateLimitConfig |
| `jseeker/tracker.py` | +apply_queue table, +apply_errors table, +recurring_errors view, +7 queue functions |
| `config.py` | +ATS credential fields (from .env), +apply_logs_dir, +ats_runners_dir |
| `.gitignore` | +data/apply_logs/ |

### Unit Test Coverage

| Test File | Tests | Status |
|-----------|-------|--------|
| `test_answer_bank.py` | 28 | ALL PASS |
| `test_auto_apply_models.py` | 16 | ALL PASS |
| `test_site_runner_base.py` | 7 | ALL PASS |
| `test_workday_runner.py` | 14 | ALL PASS |
| `test_greenhouse_runner.py` | 15 | ALL PASS |
| `test_auto_apply.py` | 18 | ALL PASS |
| **Total new** | **98** | **ALL PASS** |

### What Sprint 1 Does NOT Include (by design)

- No ApplyVerifier (Sprint 2)
- No ApplyMonitor / health checks (Sprint 2)
- No UI dashboard (Sprint 3)
- No real form submissions (Sprint 4)
- No cover letters, LinkedIn, Computer Use
- No intelligence/learning loop (post-v1)

---

## Sprint 2+3: Verification + Monitoring + UI (COMPLETE)

**Date completed**: 2026-02-17
**Agents used**: 3 parallel Wave 1 (Verifier‖Monitor‖Workday gaps) → Wave 2 (Integration) → Wave 3 (UI) → CI gate
**Test baseline**: 583 → 627 passing (+44 new, 0 regressions, same 1 pre-existing French lang failure)
**Version**: v0.3.10 → v0.3.11

### New Files (3)

| File | Purpose |
|------|---------|
| `jseeker/apply_verifier.py` | Hard verification: URL/DOM/automation-id signals, VerificationResult model |
| `jseeker/apply_monitor.py` | Circuit breaker: consecutive failures, platform disable, HITL alerts, MonitorDecision model |
| `ui/pages/9_auto_apply.py` | 4-tab dashboard: Queue / Run / Results / Monitor |

### Modified Files (6)

| File | Changes |
|------|---------|
| `jseeker/models.py` | +VerificationResult, +MonitorDecision, +BatchSummary |
| `jseeker/auto_apply.py` | Verifier wired post-submit, monitor wired per-attempt, apply_batch() returns BatchSummary |
| `jseeker/ats_runners/workday.py` | +_handle_sms_consent, +_handle_fcra_ack, +_fill_phone_extension, +_fill_skills_tags |
| `jseeker/answer_bank.py` | +phone_extension, +resume_skills to PersonalInfo |
| `data/answer_bank.yaml` | +reasons-for-leaving pattern, +resume_skills for US market |
| `data/ats_runners/workday.yaml` | +sms_consent, +fcra_ack, +phone_extension, +skills_input selectors |

### Unit Test Coverage

| Test File | Tests | Status |
|-----------|-------|--------|
| `test_apply_verifier.py` | 13 | ALL PASS |
| `test_apply_monitor.py` | 21 | ALL PASS |
| `test_auto_apply.py` | 22 (+4) | ALL PASS |
| `test_workday_runner.py` | 19 (+5) | ALL PASS |
| **Total new** | **44** | **ALL PASS** |

### Workday Gaps Fixed (from GEICO ATS form analysis)
- SMS consent checkbox — auto-accept
- FCRA background check acknowledgement — auto-check
- "Reasons for leaving" — answer bank pattern added
- Phone extension field — PersonalInfo.phone_extension
- Skills tag-based UI — _fill_skills_tags() with 10-tag limit
- Full integration tests (mock pipeline end-to-end)

---

## Sprint 3: UI Dashboard (NOT STARTED)

**Scope**: Streamlit auto-apply page, manual dry-run testing
**Agents planned**: H (Dashboard), I (Manual Testing)
**Blocked by**: Sprint 2 completion

### Planned deliverables
- `ui/pages/9_auto_apply.py` -- Queue table, controls, health bar, attempt log
- 10 real dry-runs (5 Workday + 5 Greenhouse) with screenshots

---

## Sprint 4: Sandbox + Assisted (NOT STARTED)

**Scope**: Real submissions on throwaway jobs, assisted mode polish
**Blocked by**: Sprint 3 completion + user dry-run approval

### Planned deliverables
- 15 throwaway submissions across both platforms
- Live progress view + mid-flow cancel in UI
- 10 real target applications under user supervision
- Version bump to v1.0.0

---

## Confidence Ladder Status

| Level | Name | Threshold | Status |
|-------|------|-----------|--------|
| 1 | Unit Tests | 100% pass rate | IN PROGRESS (see testing plan) |
| 2 | Dry Run | 20 forms filled, 0 field errors | NOT STARTED |
| 3 | Sandbox | 15 submissions, >85% rate | NOT STARTED |
| 4 | Assisted | 10 real apps, >90% rate | NOT STARTED |
| 5 | Autopilot | 50+ apps, user sign-off | NOT IN V1 |

---

## Risk Log

| Risk | Status | Notes |
|------|--------|-------|
| Selector drift (Workday) | MITIGATED | YAML-based selectors with fallback chains |
| Selector drift (Greenhouse) | MITIGATED | Same approach |
| False verified state | NOT YET TESTED | Verifier module in Sprint 2 |
| Rate limiting by ATS | MITIGATED | Per-platform limits + randomized cooldown |
| Credential storage | OK | .env file, not committed |
| Scope creep | CONTROLLED | Hard NOT lists per sprint in PRD |

---

## Appendix: PRD Cross-Reference

| PRD Section | Status | Sprint |
|-------------|--------|--------|
| 1. Scope Contract | Implemented | 1 |
| 2. Terminal States & Verification | Enum defined, verifier pending | 1+2 |
| 3. Safety & Stopping Rules | Rate limits in engine, monitor pending | 1+2 |
| 4. Engine Architecture | SiteRunner + Orchestrator done | 1 |
| 5. Data Models | All models + DB schema done | 1 |
| 6. Idempotency & Retry | Dedup done, retry logic in batch | 1 |
| 7. Observability | Attempt logs done, health checks pending | 1+2 |
| 8. Cost Model | $0.00/attempt (Playwright-only) confirmed | 1 |
| 9. Testing & Promotion | Unit tests done, dry-runs pending | 1 |
| 10-14. Verification Checklist | See testing plan below | -- |
