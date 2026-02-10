# jSeeker Testing Guide

## Table of Contents
1. [Quick Start](#quick-start)
2. [Coverage Targets](#coverage-targets)
3. [TDD Workflow](#tdd-workflow)
4. [Running Tests](#running-tests)
5. [Writing Good Tests](#writing-good-tests)
6. [Mocking Strategies](#mocking-strategies)
7. [Test Organization](#test-organization)
8. [CI/CD Integration](#cicd-integration)

---

## Quick Start

### Install Testing Dependencies
```bash
pip install pytest pytest-cov
```

### Run All Tests
```bash
cd X:\Projects\jSeeker
python -m pytest
```

### Run Tests with Coverage
```bash
python -m pytest --cov=jseeker --cov-report=term-missing
```

### Run Specific Test File
```bash
python -m pytest tests/test_tracker.py -v
```

### Run Specific Test Class or Method
```bash
python -m pytest tests/test_tracker.py::TestTrackerConcurrency -v
python -m pytest tests/test_tracker.py::TestTrackerConcurrency::test_connection_pooling_enabled -v
```

---

## Coverage Targets

Each module has specific coverage targets enforced in CI/CD:

| Module | Coverage Target | Priority | Status |
|--------|----------------|----------|--------|
| `adapter.py` | **80%** | HIGH | ✓ Enforced |
| `renderer.py` | **75%** | HIGH | ✓ Enforced |
| `llm.py` | **80%** | HIGH | ✓ Enforced |
| `tracker.py` | **70%** | MEDIUM | ✓ Enforced |
| `jd_parser.py` | **70%** | MEDIUM | Active |
| `ats_scorer.py` | **65%** | MEDIUM | Active |
| `matcher.py` | **65%** | LOW | Active |

### Check Coverage for Specific Module
```bash
# Tracker module
python -m pytest tests/test_tracker.py --cov=jseeker.tracker --cov-report=term-missing

# Adapter module
python -m pytest tests/test_adapter.py --cov=jseeker.adapter --cov-report=term-missing

# All modules with HTML report
python -m pytest --cov=jseeker --cov-report=html
# Opens htmlcov/index.html in browser
```

---

## TDD Workflow

### The Red-Green-Refactor Cycle

jSeeker follows strict Test-Driven Development (TDD) methodology:

```
RED → GREEN → REFACTOR
 ↑                ↓
 ←────────────────
```

### Step 1: RED (Write Failing Test)

Write the test **before** implementing the feature. The test should fail initially.

**Example: Testing Connection Pooling (Task #4)**

```python
# tests/test_tracker.py
def test_connection_pooling_enabled(self, tmp_db):
    """Test that connection pooling is properly configured."""
    db = TrackerDB(tmp_db)

    # Get connection should be configured with timeout and thread safety
    conn = db._get_conn()

    # Connection should be usable (health check passed)
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    assert result[0] == 1

    # Verify connection can be used again (not closed after health check)
    cursor.execute("SELECT 2")
    result2 = cursor.fetchone()
    assert result2[0] == 2

    conn.close()
```

**Run the test - it should FAIL:**
```bash
python -m pytest tests/test_tracker.py::TestTrackerConcurrency::test_connection_pooling_enabled -v
# FAILED: AttributeError: 'TrackerDB' object has no attribute '_get_conn'
```

### Step 2: GREEN (Implement Minimal Code)

Write just enough code to make the test pass. Don't over-engineer.

**Example: Implementing Connection Pooling**

```python
# jseeker/tracker.py
def _get_conn(self) -> sqlite3.Connection:
    """Get a database connection with proper timeout and configuration.

    Configured with:
    - 30 second timeout to prevent "database is locked" errors
    - check_same_thread=False for thread safety
    - Row factory for dict-like access
    """
    conn = sqlite3.connect(
        str(self.db_path),
        timeout=30.0,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row

    # Health check: verify connection is usable
    try:
        conn.execute("SELECT 1")
    except sqlite3.Error:
        conn.close()
        # Retry once if health check fails
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row

    return conn
```

**Run the test - it should PASS:**
```bash
python -m pytest tests/test_tracker.py::TestTrackerConcurrency::test_connection_pooling_enabled -v
# PASSED
```

### Step 3: REFACTOR (Improve Code Quality)

Clean up the code while keeping tests green. Look for:
- Code duplication
- Poor naming
- Missing documentation
- Performance improvements

**Example: Adding Context Manager**

After getting basic connection pooling working, refactor to add transaction safety:

```python
from contextlib import contextmanager

@contextmanager
def _transaction(self):
    """Context manager for atomic transactions.

    Yields:
        Tuple of (connection, cursor) for use within the transaction

    Usage:
        with db._transaction() as (conn, cursor):
            cursor.execute("INSERT INTO ...")
            cursor.execute("UPDATE ...")
        # Auto-commits on success, rolls back on exception
    """
    conn = self._get_conn()
    cursor = conn.cursor()
    try:
        yield conn, cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

**Re-run all tests to ensure no regressions:**
```bash
python -m pytest tests/test_tracker.py -v
# All 36 tests should pass
```

---

## Running Tests

### Basic Commands

```bash
# Run all tests
python -m pytest

# Run with verbose output
python -m pytest -v

# Run specific test file
python -m pytest tests/test_tracker.py

# Run specific test class
python -m pytest tests/test_tracker.py::TestTrackerConcurrency

# Run specific test method
python -m pytest tests/test_tracker.py::TestTrackerDB::test_add_company

# Run tests matching a pattern
python -m pytest -k "concurrency"

# Stop on first failure
python -m pytest -x

# Run last failed tests only
python -m pytest --lf

# Show print statements
python -m pytest -s
```

### Coverage Commands

```bash
# Basic coverage report
python -m pytest --cov=jseeker

# Coverage with missing lines
python -m pytest --cov=jseeker --cov-report=term-missing

# Coverage for specific module
python -m pytest tests/test_tracker.py --cov=jseeker.tracker --cov-report=term-missing

# HTML coverage report (opens in browser)
python -m pytest --cov=jseeker --cov-report=html
start htmlcov/index.html  # Windows
open htmlcov/index.html   # macOS

# Fail if coverage below threshold
python -m pytest --cov=jseeker --cov-fail-under=70
```

### Watch Mode (Auto-rerun on Changes)

```bash
# Install pytest-watch
pip install pytest-watch

# Watch all tests
ptw

# Watch specific test file
ptw tests/test_tracker.py

# Watch with coverage
ptw -- --cov=jseeker --cov-report=term-missing
```

---

## Writing Good Tests

### Test Structure: Arrange-Act-Assert

```python
def test_add_application(self, tmp_db):
    # ARRANGE: Set up test data
    db = TrackerDB(tmp_db)
    company_id = db.get_or_create_company("TestCorp")
    app = Application(
        company_id=company_id,
        role_title="Director of Design",
        location="SF",
    )

    # ACT: Perform the action
    app_id = db.add_application(app)

    # ASSERT: Verify the result
    assert app_id > 0
```

### Test Naming Conventions

Use descriptive names that explain what is being tested:

```python
# Good ✓
def test_connection_health_check(self):
def test_transaction_rollback_on_error(self):
def test_concurrent_updates_no_lock_error(self):

# Bad ✗
def test_conn(self):
def test_transaction(self):
def test_updates(self):
```

### Test Edge Cases

Always test:
1. **Null/Empty Values**
2. **Boundary Conditions**
3. **Error Paths**
4. **Invalid Types**
5. **Concurrent Access**

**Example: Testing Edge Cases**

```python
def test_is_url_known_empty(self, tmp_db):
    """Test that empty URL returns False."""
    db = TrackerDB(tmp_db)
    assert db.is_url_known("") is False

def test_is_url_known_unknown(self, tmp_db):
    """Test that unknown URL returns False."""
    db = TrackerDB(tmp_db)
    assert db.is_url_known("https://unknown.example.com") is False

def test_delete_resume_nonexistent(self, tmp_db):
    """Test deleting a non-existent resume returns False."""
    db = TrackerDB(tmp_db)
    result = db.delete_resume(9999)
    assert result is False
```

### Test Independence

Each test should be completely independent:

```python
# Good ✓ - Uses fixture for clean database
def test_add_company(self, tmp_db):
    db = TrackerDB(tmp_db)
    company = Company(name="TestCorp", industry="Tech")
    company_id = db.add_company(company)
    assert company_id > 0

def test_get_company(self, tmp_db):
    db = TrackerDB(tmp_db)
    # Create company in this test, don't rely on previous test
    company_id = db.get_or_create_company("TestCorp")
    assert company_id > 0

# Bad ✗ - Tests depend on execution order
class_level_company_id = None

def test_add_company(self, tmp_db):
    global class_level_company_id
    db = TrackerDB(tmp_db)
    company_id = db.add_company(Company(name="TestCorp"))
    class_level_company_id = company_id

def test_get_company(self, tmp_db):
    # Fails if test_add_company didn't run first!
    db = TrackerDB(tmp_db)
    company = db.get_company(class_level_company_id)
```

---

## Mocking Strategies

### When to Mock

Mock external dependencies:
- ✓ LLM API calls (expensive, slow, non-deterministic)
- ✓ File system operations (when testing logic, not I/O)
- ✓ External APIs (PubMed, Indeed, etc.)
- ✓ Subprocess calls (ATS scanners, document converters)
- ✗ Database operations (use tmp_db fixture instead)
- ✗ Pure functions (test directly)

### Mock LLM Calls

**Example: Testing Adapter with Mocked LLM**

```python
from unittest.mock import patch

def test_adapt_bullets_malformed_json_raises_error(
    self, mock_parsed_jd, experience_blocks
):
    """Test that malformed JSON response raises AdaptationError."""
    from jseeker.models import AdaptationError

    with patch("jseeker.adapter.llm.call_sonnet") as mock_llm:
        # LLM returns invalid JSON (truncated)
        mock_llm.return_value = '[["bullet1", "bullet2"], ["bullet3"'

        with pytest.raises(AdaptationError) as exc_info:
            adapt_bullets_batch(
                experience_blocks,
                TemplateType.HYBRID,
                mock_parsed_jd,
                use_learned_patterns=False,
            )

        # Verify error message contains context
        error_msg = str(exc_info.value)
        assert "parse" in error_msg.lower() and "json" in error_msg.lower()
```

### Mock Subprocess Calls

**Example: Testing Renderer with Mocked Subprocess**

```python
from unittest.mock import patch, Mock

def test_render_pdf_subprocess_error_raises(self, tmp_path):
    """Test that subprocess error raises RenderError."""
    from jseeker.models import RenderError

    with patch("jseeker.renderer.subprocess.run") as mock_run:
        # Simulate subprocess failure
        mock_run.return_value = Mock(
            returncode=1,
            stderr="weasyprint: command not found"
        )

        with pytest.raises(RenderError) as exc_info:
            render_pdf("test.html", tmp_path / "output.pdf")

        # Verify error context
        assert "weasyprint" in str(exc_info.value).lower()
```

### Mock with Return Values

```python
with patch("jseeker.llm.call_sonnet") as mock_llm:
    # Return fixed value
    mock_llm.return_value = '{"result": "success"}'

    # Call function under test
    result = some_function_that_uses_llm()

    # Verify mock was called correctly
    mock_llm.assert_called_once()
    assert "success" in result
```

### Mock with Side Effects

```python
with patch("jseeker.renderer.subprocess.run") as mock_run:
    # First call succeeds, second fails
    mock_run.side_effect = [
        Mock(returncode=0),
        Mock(returncode=1, stderr="Error")
    ]

    # First call works
    render_pdf("test1.html", "output1.pdf")

    # Second call raises
    with pytest.raises(RenderError):
        render_pdf("test2.html", "output2.pdf")
```

---

## Test Organization

### File Structure

```
tests/
├── conftest.py              # Shared fixtures
├── test_adapter.py          # Adapter module tests
├── test_renderer.py         # Renderer module tests
├── test_llm.py              # LLM module tests
├── test_tracker.py          # Tracker module tests
├── test_jd_parser.py        # JD parser tests
├── test_ats_scorer.py       # ATS scorer tests
├── test_matcher.py          # Matcher tests
├── test_models.py           # Pydantic model tests
├── test_pipeline.py         # End-to-end pipeline tests
└── test_block_manager.py    # Block manager tests
```

### Shared Fixtures (conftest.py)

```python
"""jSeeker test configuration and fixtures."""

import pytest
from pathlib import Path
import tempfile
import uuid
import shutil

@pytest.fixture
def tmp_path():
    """Dedicated temp path to avoid pytest temp permission issues."""
    base = Path(tempfile.gettempdir()) / "jseeker_pytest_tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"tmp_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)

@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_jseeker.db"
    from jseeker.tracker import init_db
    init_db(db_path)
    return db_path

@pytest.fixture
def sample_jd_text():
    """Sample JD text for testing."""
    return """
    Director of Product Design
    Company: TechCorp
    Location: San Francisco, CA (Hybrid)

    Requirements:
    - 10+ years of product design experience
    - Experience leading teams of 10+ designers
    """
```

### Test Class Organization

Group related tests into classes:

```python
class TestTrackerDB:
    """Test basic CRUD operations."""

    def test_add_company(self, tmp_db):
        pass

    def test_get_application(self, tmp_db):
        pass

class TestTrackerConcurrency:
    """Test connection pooling and concurrency management."""

    def test_connection_pooling_enabled(self, tmp_db):
        pass

    def test_concurrent_updates_no_lock_error(self, tmp_db):
        pass
```

---

## CI/CD Integration

### GitHub Actions Workflow

Create `.github/workflows/test.yml`:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: windows-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install pytest pytest-cov
        pip install -r requirements.txt

    - name: Run tests with coverage
      run: |
        python -m pytest --cov=jseeker --cov-report=term-missing --cov-fail-under=70

    - name: Check adapter coverage (80% required)
      run: |
        python -m pytest tests/test_adapter.py --cov=jseeker.adapter --cov-fail-under=80

    - name: Check renderer coverage (75% required)
      run: |
        python -m pytest tests/test_renderer.py --cov=jseeker.renderer --cov-fail-under=75

    - name: Check llm coverage (80% required)
      run: |
        python -m pytest tests/test_llm.py --cov=jseeker.llm --cov-fail-under=80

    - name: Check tracker coverage (70% required)
      run: |
        python -m pytest tests/test_tracker.py --cov=jseeker.tracker --cov-fail-under=70
```

### Pre-commit Hooks

Install pre-commit to run tests before each commit:

```bash
pip install pre-commit
```

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: python -m pytest
        language: system
        pass_filenames: false
        always_run: true

      - id: pytest-coverage
        name: pytest-coverage
        entry: python -m pytest --cov=jseeker --cov-fail-under=70
        language: system
        pass_filenames: false
        always_run: true
```

Install hooks:
```bash
pre-commit install
```

---

## Example: Complete TDD Cycle (Task #4)

### Problem: Database Locked Errors

jSeeker was experiencing "database is locked" errors under concurrent access.

### Step 1: Write Failing Tests (RED)

```python
def test_concurrent_updates_no_lock_error(self, tmp_db):
    """Test that concurrent updates don't cause 'database is locked' errors."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    db = TrackerDB(tmp_db)
    company_id = db.get_or_create_company("TestCorp")

    # Create an application
    app = Application(company_id=company_id, role_title="Test Role")
    app_id = db.add_application(app)

    errors = []

    def update_app(field_val):
        """Update application from thread."""
        try:
            db.update_application(app_id, notes=f"Update {field_val}")
        except Exception as e:
            errors.append(str(e))

    # Run 10 concurrent updates
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(update_app, i) for i in range(10)]
        for future in futures:
            future.result()

    # Verify no "database is locked" errors
    locked_errors = [e for e in errors if "database is locked" in e.lower()]
    assert len(locked_errors) == 0, f"Found lock errors: {locked_errors}"
```

Run test:
```bash
python -m pytest tests/test_tracker.py::TestTrackerConcurrency::test_concurrent_updates_no_lock_error -v
# FAILED: AssertionError: Found lock errors: ['database is locked']
```

### Step 2: Implement Fix (GREEN)

```python
def _get_conn(self) -> sqlite3.Connection:
    """Get a database connection with proper timeout and configuration."""
    conn = sqlite3.connect(
        str(self.db_path),
        timeout=30.0,  # 30 second timeout prevents lock errors
        check_same_thread=False  # Thread safety
    )
    conn.row_factory = sqlite3.Row
    return conn
```

Run test:
```bash
python -m pytest tests/test_tracker.py::TestTrackerConcurrency::test_concurrent_updates_no_lock_error -v
# PASSED
```

### Step 3: Verify Coverage (REFACTOR)

```bash
python -m pytest tests/test_tracker.py --cov=jseeker.tracker --cov-report=term-missing
# Coverage: 86% (exceeds 70% target)
```

Run all tests to ensure no regressions:
```bash
python -m pytest tests/test_tracker.py -v
# 36 passed
```

---

## Best Practices Summary

### DO ✓
- Write tests **before** implementation (TDD)
- Test edge cases (null, empty, invalid, boundaries)
- Use descriptive test names
- Keep tests independent (use fixtures)
- Mock expensive external calls (LLM, APIs)
- Verify coverage targets are met
- Run tests before committing

### DON'T ✗
- Skip writing tests for "simple" functions
- Test implementation details (test behavior, not internals)
- Share state between tests (use fresh fixtures)
- Mock the database (use tmp_db fixture)
- Commit code with failing tests
- Ignore coverage reports

---

## Troubleshooting

### Tests Run but Coverage is Zero

Make sure you're using the correct module path:

```bash
# Wrong ✗
python -m pytest --cov=tracker

# Right ✓
python -m pytest --cov=jseeker.tracker
```

### Import Errors in Tests

Add project root to Python path in `conftest.py`:

```python
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
```

### Database Permission Errors

Use the custom `tmp_path` fixture from conftest.py instead of pytest's default:

```python
def test_my_test(self, tmp_db):  # Uses custom fixture
    db = TrackerDB(tmp_db)
```

### Mock Not Working

Verify the patch path matches the import location:

```python
# If your code does: from jseeker.adapter import llm
with patch("jseeker.adapter.llm.call_sonnet") as mock:

# If your code does: import jseeker.llm
with patch("jseeker.llm.call_sonnet") as mock:
```

---

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [unittest.mock documentation](https://docs.python.org/3/library/unittest.mock.html)
- [Test-Driven Development by Kent Beck](https://www.oreilly.com/library/view/test-driven-development/0321146530/)

---

**Document Version:** 1.0
**Last Updated:** 2026-02-10
**Author:** tracker-fixer (TDD Specialist)
**Related Tasks:** Task #4 (Tracker Concurrency Fixes)
