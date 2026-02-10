# Changelog

All notable changes to jSeeker will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
