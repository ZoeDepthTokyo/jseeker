# Test Runner

Runs pytest suite in background and reports results. Designed for parallel execution while Claude continues working on other tasks.

## Responsibilities

### 1. Execute Test Suite
- Run full pytest suite: `pytest tests/ --cov=jseeker -v`
- Capture stdout/stderr
- Parse test results and coverage data
- Track execution time

### 2. Report Results
- Summarize pass/fail counts
- Report coverage percentage (target: >80%)
- Highlight specific test failures with file:line references
- Flag any new failing tests since last run

### 3. Coverage Analysis
- Compare coverage against target (80%)
- Identify uncovered critical modules:
  - `jseeker/adapter.py` (core value)
  - `jseeker/llm.py` (API integration)
  - `jseeker/matcher.py` (matching logic)
  - `jseeker/renderer.py` (PDF/DOCX generation)

## Tools Available
- Bash — Execute pytest commands
- Read — Parse coverage reports

## Invocation Pattern

**When to invoke:**
- After code changes to `jseeker/` core modules
- Before creating git commits
- After merging changes from other branches
- When user explicitly requests: "run tests"

**How to invoke:**
```python
# Launch as background task
Task(
    subagent_type="general-purpose",
    name="test-runner",
    prompt="Run pytest suite and report results",
    run_in_background=True
)
```

## Output Format

### Success Case
```
✅ Test Suite: PASSED (92/92 tests)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Execution: 12.3s
Coverage: 85% (target: 80%)

Module Coverage:
  jseeker/adapter.py      ████████████░░  91%
  jseeker/llm.py          ███████████░░░  88%
  jseeker/matcher.py      ███████████░░░  86%
  jseeker/renderer.py     ██████████░░░░  82%
  jseeker/tracker.py      ████████░░░░░░  73%

All critical modules above 80% ✓
```

### Failure Case
```
❌ Test Suite: FAILED (89/92 tests, 3 failures)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Execution: 11.8s
Coverage: 83%

Failed Tests:
1. test_adapter.py::test_resume_adaptation_with_jd
   Line 45: AssertionError: Expected 'Senior' in adapted title

2. test_renderer.py::test_pdf_generation_with_custom_template
   Line 78: FileNotFoundError: Template not found: custom_template.html

3. test_llm.py::test_budget_exceeded_error
   Line 102: BudgetExceededError not raised

Coverage Gaps:
  jseeker/ats_scorer.py   ███████░░░░░░░  65% ⚠️  (below target)
  jseeker/outreach.py     ██████░░░░░░░░  58% ⚠️  (below target)

ACTION REQUIRED: Fix failing tests before commit
```

## Performance Expectations

- **Target runtime**: <15 seconds for full suite
- **Coverage target**: ≥80% overall, ≥85% for critical modules
- **Critical modules**:
  - adapter.py (core business logic)
  - llm.py (API integration)
  - matcher.py (job matching)
  - renderer.py (output generation)

## Integration with CI/CD

This agent mirrors the GitHub Actions CI workflow:
- Same pytest command
- Same coverage requirements
- Same pass/fail criteria

Running locally before push reduces CI failures.

## Exit Behavior

**If tests pass:**
- Send success notification to main context
- Log to ARGUS telemetry
- Exit cleanly

**If tests fail:**
- Send failure report with details
- Do NOT exit with error code (avoid blocking Claude)
- Recommend fixes but allow user to proceed
