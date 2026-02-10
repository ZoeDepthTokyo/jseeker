# jSeeker Error Handling Infrastructure

**Version:** 1.0
**Last Updated:** 2026-02-10
**Status:** Production

## Overview

jSeeker follows a **zero silent failures** philosophy. All critical operations that can fail (LLM adaptation, PDF rendering, database operations) must raise explicit exceptions with actionable context instead of silently falling back to default behavior.

### Core Principles

1. **No Silent Failures** - Never log an error and continue as if nothing happened
2. **Contextual Errors** - Include affected entities (companies, files, operations) in error messages
3. **Telemetry Integration** - Log all errors to ARGUS for ecosystem-wide monitoring
4. **User Actionability** - Error messages should help users understand what failed and why

---

## Exception Classes

### AdaptationError

Raised when resume adaptation fails (JSON parsing, LLM response validation, etc.).

**Location:** `jseeker/models.py`

```python
class AdaptationError(Exception):
    """Raised when resume adaptation fails (JSON parse, validation, etc.)."""
    pass
```

**When to use:**
- LLM returns empty response
- JSON parsing fails
- Response structure validation fails (wrong type, wrong length)
- Adaptation logic encounters unrecoverable errors

**Example usage:**

```python
from jseeker.models import AdaptationError

try:
    llm_results = json.loads(json_str)
except json.JSONDecodeError as e:
    companies = ", ".join(exp.get('company', 'Unknown') for exp in experience_blocks)
    raise AdaptationError(
        f"Failed to parse LLM response as JSON for bullet adaptation. "
        f"Affected experiences: {companies}. "
        f"Parse error: {str(e)}. "
        f"Raw response (first 200 chars): {raw[:200]}"
    )
```

### RenderError

Raised when PDF or DOCX rendering fails after retries.

**Location:** `jseeker/models.py`

```python
class RenderError(Exception):
    """Raised when PDF or DOCX rendering fails after retries."""
    pass
```

**When to use:**
- PDF generation fails (Playwright subprocess errors)
- DOCX generation fails (python-docx errors)
- Template rendering fails
- File I/O errors during rendering

**Example usage:**

```python
from jseeker.models import RenderError

if result.returncode != 0:
    raise RenderError(
        f"Failed to render PDF after {max_retries} attempts. "
        f"Output path: {output_path}. "
        f"Error: {result.stderr[:500]}"
    )
```

---

## ARGUS Telemetry Integration

All error paths **must** log to ARGUS telemetry for ecosystem-wide monitoring and debugging.

### log_runtime_event

**Location:** `jseeker/integrations/argus_telemetry.py`

```python
def log_runtime_event(
    task: str,
    model: str,
    cost_usd: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    details: str = "",
) -> None:
    """Log a runtime API call event for cost monitoring."""
```

### Usage Pattern

```python
from jseeker.integrations.argus_telemetry import log_runtime_event

# Log error before raising exception
log_runtime_event(
    task="bullet_adapt_batch",
    model="sonnet",
    cost_usd=0.0,
    details=f"ERROR: JSON parse failed - {str(e)[:100]}",
)

# Then raise exception
raise AdaptationError(...)
```

**Why log before raising?**
- Exception may be caught by caller
- Ensures error is captured in ARGUS logs regardless of exception handling
- Enables cost tracking even for failed operations

---

## Before/After Examples

### Example 1: Silent JSON Parse Failure (BEFORE)

**Old behavior (adapter.py lines 236-247):**

```python
try:
    llm_results = json.loads(json_str)
    if not isinstance(llm_results, list) or len(llm_results) != len(experience_blocks):
        # Malformed response: return original bullets
        logger.warning("adapt_bullets_batch | malformed LLM response | using originals")
        llm_results = [exp.get("bullets", []) for exp in experience_blocks]
    else:
        logger.info(f"adapt_bullets_batch | LLM returned {len(llm_results)} bullet sets")
except json.JSONDecodeError:
    # Fallback: return originals
    logger.error("adapt_bullets_batch | JSON parse failed | using originals")
    llm_results = [exp.get("bullets", []) for exp in experience_blocks]
```

**Problems:**
- User sees original bullets without knowing adaptation failed
- No context about which companies were affected
- No raw LLM response for debugging
- No ARGUS telemetry for ecosystem monitoring

### Example 1: Explicit Error (AFTER)

**New behavior (adapter.py lines 228-304):**

```python
try:
    llm_results = json.loads(json_str)
except json.JSONDecodeError as e:
    from jseeker.integrations.argus_telemetry import log_runtime_event
    log_runtime_event(
        task="bullet_adapt_batch",
        model="sonnet",
        cost_usd=0.0,
        details=f"ERROR: JSON parse failed - {str(e)[:100]}",
    )
    logger.error(f"adapt_bullets_batch | JSON parse failed | error={e}")
    companies = ", ".join(exp.get('company', 'Unknown') for exp in experience_blocks)
    raise AdaptationError(
        f"Failed to parse LLM response as JSON for bullet adaptation. "
        f"Affected experiences: {companies}. "
        f"Parse error: {str(e)}. "
        f"Raw response (first 200 chars): {raw[:200]}"
    )
```

**Benefits:**
- User immediately knows adaptation failed
- Error message includes affected companies (TechCorp, StartupXYZ)
- Includes parse error details for debugging
- Shows first 200 chars of raw response for inspection
- Logged to ARGUS for ecosystem monitoring

### Example 2: Array Length Mismatch (AFTER)

```python
if len(llm_results) != len(experience_blocks):
    from jseeker.integrations.argus_telemetry import log_runtime_event
    log_runtime_event(
        task="bullet_adapt_batch",
        model="sonnet",
        cost_usd=0.0,
        details=f"ERROR: Array length mismatch - expected {len(experience_blocks)}, got {len(llm_results)}",
    )
    logger.error(
        f"adapt_bullets_batch | array length mismatch | "
        f"expected={len(experience_blocks)} got={len(llm_results)}"
    )
    raise AdaptationError(
        f"LLM returned {len(llm_results)} bullet sets, but expected {len(experience_blocks)}. "
        f"Affected experiences: {', '.join(exp.get('company', 'Unknown') for exp in experience_blocks)}"
    )
```

**User sees:**
```
AdaptationError: LLM returned 1 bullet sets, but expected 2.
Affected experiences: TechCorp, StartupXYZ
```

---

## Implementation Guide

### Step 1: Identify Silent Failure Points

Look for patterns like:

```python
try:
    result = risky_operation()
except SomeError:
    logger.error("Operation failed, using fallback")
    result = fallback_value  # ❌ SILENT FAILURE
```

### Step 2: Define Exception Class (if needed)

Add to `jseeker/models.py`:

```python
class YourError(Exception):
    """Raised when [operation] fails."""
    pass
```

### Step 3: Replace Silent Fallback

```python
try:
    result = risky_operation()
except SomeError as e:
    # Log to ARGUS
    from jseeker.integrations.argus_telemetry import log_runtime_event
    log_runtime_event(
        task="operation_name",
        model="model_used",
        cost_usd=0.0,
        details=f"ERROR: {str(e)[:100]}",
    )

    # Log locally
    logger.error(f"operation_name | detailed context | error={e}")

    # Raise with context
    raise YourError(
        f"Failed to perform operation. "
        f"Affected entities: {entities}. "
        f"Error: {str(e)}"
    )
```

### Step 4: Write TDD Tests FIRST

```python
def test_operation_error_raised():
    """Test that operation raises YourError on failure."""
    from jseeker.models import YourError

    with patch("module.risky_operation") as mock_op:
        mock_op.side_effect = SomeError("Failure")

        with pytest.raises(YourError) as exc_info:
            your_function()

        # Verify error message contains context
        assert "Affected entities" in str(exc_info.value)
        assert "Failure" in str(exc_info.value)
```

### Step 5: Verify Coverage

```bash
pytest tests/test_your_module.py --cov=jseeker.your_module --cov-report=term-missing
```

Target: 80%+ coverage on critical error-handling code.

---

## Good Error Message Checklist

✅ **Identifies what failed** - "Failed to parse LLM response as JSON"
✅ **Includes affected entities** - "Affected experiences: TechCorp, StartupXYZ"
✅ **Shows root cause** - "Parse error: Expecting ',' delimiter: line 1 column 36"
✅ **Provides debugging context** - "Raw response (first 200 chars): [["bullet1"..."
✅ **Actionable** - User can understand what went wrong and where to investigate

❌ **Avoid generic messages** - "An error occurred"
❌ **Avoid silent failures** - Logging without raising
❌ **Avoid missing context** - "JSON parse failed" (which JSON? what operation?)

---

## Error Flow Diagram

```
┌─────────────────────────────────────────────┐
│  1. Risky Operation Executed                │
│     (LLM call, JSON parse, file I/O)        │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
         ┌─────────────────────┐
         │  Operation Fails?   │
         └─────────┬───────────┘
                   │
         ┌─────────┴─────────┐
         │                   │
        YES                 NO
         │                   │
         ▼                   ▼
┌─────────────────┐  ┌──────────────────┐
│ 2. Log to ARGUS │  │  Return Success  │
│    telemetry    │  └──────────────────┘
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. Log locally  │
│    (logger)     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ 4. Raise exception with context:    │
│    - What failed                    │
│    - Affected entities              │
│    - Root cause                     │
│    - Debug context (raw data)       │
└──────────────────────────────────────┘
```

---

## Testing Strategy

### Test Coverage Requirements

- **Critical error paths:** 100% (JSON parsing, validation logic)
- **Overall module:** 80%+ target
- **Error messages:** Verify context present in assertions

### Example Test Suite Structure

```python
class TestYourModuleErrorHandling:
    """Test error handling in your_module - TDD approach."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mocks for dependencies."""
        # Setup

    def test_operation_empty_input_raises_error(self, mock_dependencies):
        """Test that empty input raises YourError."""
        # Arrange, Act, Assert

    def test_operation_malformed_data_raises_error(self, mock_dependencies):
        """Test that malformed data raises YourError."""
        # Arrange, Act, Assert

    def test_operation_success_case(self, mock_dependencies):
        """Test successful operation."""
        # Arrange, Act, Assert
```

### Run Tests

```bash
# All tests for module
pytest tests/test_your_module.py -v

# With coverage
pytest tests/test_your_module.py --cov=jseeker.your_module --cov-report=term-missing

# Watch mode (if pytest-watch installed)
ptw tests/test_your_module.py
```

---

## Reference Implementation

### adapter.py (Lines 228-304)

The adapter.py error handling implementation is the reference standard for jSeeker. It demonstrates:

- ✅ Empty response detection
- ✅ JSON parse error handling with context
- ✅ Response structure validation (type, length)
- ✅ ARGUS telemetry integration
- ✅ Contextual error messages with affected entities
- ✅ Raw data snippets for debugging
- ✅ 100% test coverage on error paths

**View implementation:**
```bash
# Read lines 228-304
cat jseeker/adapter.py | sed -n '228,304p'
```

**View tests:**
```bash
# See TestAdaptBulletsBatchErrorHandling class
cat tests/test_adapter.py
```

---

## FAQ

### Q: When should I use logging vs exceptions?

**A:** Use **both**. Log to ARGUS/logger for monitoring, then raise exception to notify caller.

```python
# ✅ CORRECT
log_runtime_event(task="operation", model="sonnet", cost_usd=0.0, details="ERROR: ...")
logger.error("operation | context | error=...")
raise YourError("Detailed message")

# ❌ WRONG (silent failure)
logger.error("operation failed")
return fallback_value
```

### Q: Should I catch and re-raise exceptions?

**A:** Only if you need to add context or transform the exception type. Otherwise, let it propagate.

```python
# ✅ CORRECT (adding context)
try:
    risky_operation()
except LowLevelError as e:
    raise YourError(f"High-level context: {affected_entities}") from e

# ❌ WRONG (no value added)
try:
    risky_operation()
except SomeError as e:
    raise SomeError(str(e))  # Pointless re-raise
```

### Q: How much context should error messages include?

**A:** Enough to debug without reading code. Include:
- What failed (operation name)
- Affected entities (companies, files, IDs)
- Root cause (parse error, validation failure)
- Debug data (first 200 chars of raw response)

### Q: Should I include full stack traces in error messages?

**A:** No. Python automatically includes stack traces when exceptions are raised. Focus on **business context** in the error message.

---

## Migration Checklist

If you're fixing existing silent failures:

- [ ] Write TDD tests first (RED phase)
- [ ] Add exception class to `models.py` if needed
- [ ] Replace silent fallback with exception raising
- [ ] Add ARGUS telemetry logging
- [ ] Include contextual information in error message
- [ ] Run tests to verify they pass (GREEN phase)
- [ ] Check coverage (80%+ target)
- [ ] Update documentation if needed

---

## Related Documentation

- **ARGUS Telemetry:** `jseeker/integrations/argus_telemetry.py`
- **Custom Exceptions:** `jseeker/models.py` (lines 12-21)
- **Test Examples:** `tests/test_adapter.py` (TestAdaptBulletsBatchErrorHandling)
- **jSeeker Testing Guide:** `docs/TESTING_GUIDE.md` (if available)

---

## Contributors

- **adapter-fixer** - Initial implementation (Task #1, 2026-02-10)
- **team-lead** - Error handling standards definition

**Questions?** See `tests/test_adapter.py` for reference implementation or ask in team chat.
