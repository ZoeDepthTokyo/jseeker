# Design Decisions — jSeeker

Key decisions with rationale and outcome tracking. Decisions are numbered sequentially and never deleted — only superseded.

---

## DEC-001: CI matrix targets Python 3.11+, not 3.10
**Date:** 2026-02-21
**Context:** CI workflow initially set Python matrix to 3.10/3.12.
**Decision:** Changed to 3.11/3.12 to match `requires-python = ">=3.11"` in pyproject.toml.
**Rationale:** 3.10 would fail at install time. Test what you ship.
**Alternatives Considered:** Lower requires-python to >=3.10 — rejected, jSeeker uses 3.11 features.
**Outcome:** CI green on both 3.11 and 3.12.
