# Changelog

All notable changes to jSeeker will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.15] — 2026-02-20

### Added
- Easy Apply (`🟦`) status added to `ApplicationStatus` enum and tracker status display
- Dedup badges in Job Discovery: shows `✅ Applied`, `🟦 Easy Apply`, or `📥 In Tracker` for already-tracked jobs
- Recency time window filter in Job Discovery: `[All time] [Today] [24h] [48h] [7 days]` radio bar above results
- `get_known_application_urls()` method in `TrackerDB` for cross-table URL→status lookup

### Changed
- Freshness weight in discovery ranking: 5% → 20% (recency matters more)
- Composite score rebalanced: tag_weight 35%→30%, resume_match 65%→50%, freshness 5%→20%
- Sort order in discovery: newest postings ranked first (recency-first, composite score as tiebreaker)

### Fixed
- Tag toggle weight calculation (int cast + `scope="app"`)
- Market loading from saved search (versioned widget key prevents stale state)
- Update button on saved searches now works correctly
- Saved search load filters junk tags from `tag_weights`

---

## [0.3.14] — 2026-02-19

### Added
- `autojs/` promoted to sibling package with its own `pyproject.toml` (P0 decoupling)
- All automation imports migrated to `autojs.*` namespace

### Fixed
- `CAREER_SUBDOMAINS` frozenset in `jd_parser.py` for branded career subdomains
- Cache thresholds: 0.85→0.75 (similarity), 3→2 (min hits)
- `[#app_id]` prefix handling in job monitor
- Navan duplicate cleanup
- `salary_currency` field name in `intelligence.py`
- `ParsedJD.raw_text` defaults to empty string

---

## [0.3.11] — 2026-02-17

### Added
- Apply verification (`apply_verifier.py`): hard proof required for `applied_verified` status
- Apply monitor (`apply_monitor.py`): circuit breaker, auto-disables platforms after 3 consecutive failures
- `BatchSummary` model replaces `list[AttemptResult]` from `apply_batch()`
- Workday runner: SMS consent, FCRA ack, phone extension, skills tags

---

## [0.3.10] — 2026-02-16

### Added
- Auto-Apply Engine v1.0: Answer Bank, ATS site runners (Workday, Greenhouse), Orchestrator
- 98 new tests for automation package

---

## [0.3.6] — 2026-02-13

### Added
- LinkedIn→ATS URL resolution with Google fallback
- `generate_resume_from_discovery()` full pipeline
- 4 ATS form JSON profiles in `ats_scorer.py`
- Sidebar-driven model selection

---

## [0.3.0] - 2026-02-10

### Fixed
- **Adapter JSON Parse Failures**: Added `AdaptationError` exception for explicit error handling instead of silent fallbacks to original bullets. Errors now include affected companies, parse error details, and raw response snippets for debugging (X:\Projects\jSeeker\jseeker\adapter.py:228-304)
- **Renderer Retry Logic**: Implemented exponential backoff retry mechanism (3 attempts, 1s/2s/4s delays) for PDF/DOCX generation to handle transient subprocess failures. Added `RenderError` exception for unrecoverable rendering failures (X:\Projects\jSeeker\jseeker\renderer.py)
- **LLM API Retry Logic**: Added retry logic with exponential backoff for transient API errors (rate limits, network timeouts). Prevents silent failures on temporary LLM service disruptions (X:\Projects\jSeeker\jseeker\llm.py)
- **Tracker Concurrency Issues**: Implemented connection pooling with 30-second timeout and `check_same_thread=False` to eliminate "database is locked" errors under concurrent access. Added transaction context manager for atomic operations (X:\Projects\jSeeker\jseeker\tracker.py)
- **Zero Silent Failures**: Replaced all silent error fallbacks with explicit exceptions. All critical errors now raise exceptions with actionable context instead of logging and continuing

### Added
- **Error Handling Documentation**: Created comprehensive ERROR_HANDLING.md guide documenting exception classes (`AdaptationError`, `RenderError`), ARGUS telemetry integration, before/after examples, implementation guide, and TDD workflow (X:\Projects\jSeeker\docs\ERROR_HANDLING.md)
- **Testing Documentation**: Created TESTING_GUIDE.md with TDD workflow (Red-Green-Refactor), coverage targets (adapter: 80%, renderer: 75%, llm: 80%, tracker: 70%), pytest commands, mocking strategies, and CI/CD integration examples (X:\Projects\jSeeker\docs\TESTING_GUIDE.md)
- **ARGUS Telemetry Integration**: All error paths now log to ARGUS ecosystem monitoring via `log_runtime_event()` for cost tracking and debugging (X:\Projects\jSeeker\jseeker\integrations\argus_telemetry.py)
- **RAVEN Research Agent**: Built autonomous research agent (v0.2.0) as GAIA ecosystem shared service for deep codebase exploration and multi-round queries

### Changed
- **Test Coverage**: Achieved 85% average coverage across critical modules (adapter: 87%, renderer: 81%, llm: 89%, tracker: 86%). All 137 tests passing with zero regressions
- **Error Philosophy**: Adopted "zero silent failures" principle across entire codebase. All critical operations that can fail now raise explicit exceptions with contextual information
- **Connection Management**: Refactored database connections to use connection pooling pattern with health checks and automatic retry on connection failure

### Dependencies
- pytest ≥7.0.0 - Test framework
- pytest-cov ≥4.0.0 - Coverage reporting
- ARGUS ≥0.5.1 - Telemetry integration
- RAVEN ≥0.2.0 - Research agent integration

---

## [0.2.1] - 2026-02-08

### Fixed
- Resolved NoneType crash in resume adaptation pipeline
- Fixed Workday job description parsing issues
- UI layout fixes for better user experience

### Changed
- Complete PROTEUS rename to jSeeker branding
- Implemented structured logging across all modules

---

## [0.1.0] - 2025-12-15

### Added
- Initial release as PROTEUS - The Shape-Shifting Resume Engine
- Automated resume adaptation for job descriptions
- ATS optimization engine
- Multi-format resume rendering (PDF, DOCX, HTML)
- Application tracking database
- LLM-powered bullet point adaptation
- Pattern learning from user feedback

[0.3.0]: https://github.com/yourusername/jSeeker/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/yourusername/jSeeker/compare/v0.1.0...v0.2.1
[0.1.0]: https://github.com/yourusername/jSeeker/releases/tag/v0.1.0
