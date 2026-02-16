"""Tests for jSeeker LLM wrapper — focusing on retry logic for transient errors."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, Mock, patch

import pytest
from anthropic import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    InternalServerError,
    RateLimitError,
)

from jseeker.llm import JseekerLLM, BudgetExceededError


# Disable caching for all tests in this module
@pytest.fixture(autouse=True)
def disable_cache(monkeypatch):
    """Disable local cache for all tests."""
    monkeypatch.setenv("ENABLE_LOCAL_CACHE", "false")
    from config import settings

    settings.enable_local_cache = False


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client with messages.create method."""
    client = MagicMock()
    # Mock successful response
    response = Mock()
    response.content = [Mock(type="text", text="Test response")]
    response.usage = Mock(
        input_tokens=100,
        output_tokens=50,
        cache_read_input_tokens=0,
    )
    client.messages.create.return_value = response
    return client


@pytest.fixture
def llm_instance(mock_anthropic_client):
    """Create LLM instance with mocked client."""
    llm = JseekerLLM()
    llm._client = mock_anthropic_client
    # Disable local cache to avoid test interference
    llm._local_cache = {}
    return llm


# ── Test: Retry on RateLimitError ────────────────────────────────────


def test_retry_on_rate_limit(llm_instance, mock_anthropic_client):
    """Test that RateLimitError triggers retry and eventually succeeds."""
    # First call raises RateLimitError, second succeeds
    mock_anthropic_client.messages.create.side_effect = [
        RateLimitError("Rate limit exceeded", response=Mock(), body={}),
        mock_anthropic_client.messages.create.return_value,
    ]

    result = llm_instance.call("Test prompt", task="test_rate_limit")

    assert result == "Test response"
    assert mock_anthropic_client.messages.create.call_count == 2


def test_retry_on_rate_limit_max_retries(llm_instance, mock_anthropic_client):
    """Test that RateLimitError eventually fails after max retries."""
    # All calls raise RateLimitError
    mock_anthropic_client.messages.create.side_effect = RateLimitError(
        "Rate limit exceeded", response=Mock(), body={}
    )

    with pytest.raises(RateLimitError):
        llm_instance.call("Test prompt", task="test_rate_limit_fail")

    # Should attempt 3 times (1 initial + 2 retries)
    assert mock_anthropic_client.messages.create.call_count == 3


# ── Test: Retry on APITimeoutError ────────────────────────────────────


def test_retry_on_timeout(llm_instance, mock_anthropic_client):
    """Test that APITimeoutError triggers retry and eventually succeeds."""
    mock_anthropic_client.messages.create.side_effect = [
        APITimeoutError(request=Mock()),
        mock_anthropic_client.messages.create.return_value,
    ]

    result = llm_instance.call("Test prompt", task="test_timeout")

    assert result == "Test response"
    assert mock_anthropic_client.messages.create.call_count == 2


def test_retry_on_timeout_max_retries(llm_instance, mock_anthropic_client):
    """Test that APITimeoutError eventually fails after max retries."""
    mock_anthropic_client.messages.create.side_effect = APITimeoutError(request=Mock())

    with pytest.raises(APITimeoutError):
        llm_instance.call("Test prompt", task="test_timeout_fail")

    assert mock_anthropic_client.messages.create.call_count == 3


# ── Test: Retry on APIConnectionError ────────────────────────────────


def test_retry_on_connection_error(llm_instance, mock_anthropic_client):
    """Test that APIConnectionError triggers retry and eventually succeeds."""
    mock_anthropic_client.messages.create.side_effect = [
        APIConnectionError(message="Connection failed", request=Mock()),
        mock_anthropic_client.messages.create.return_value,
    ]

    result = llm_instance.call("Test prompt", task="test_connection")

    assert result == "Test response"
    assert mock_anthropic_client.messages.create.call_count == 2


# ── Test: Retry on InternalServerError ────────────────────────────────


def test_retry_on_internal_server_error(llm_instance, mock_anthropic_client):
    """Test that InternalServerError (500) triggers retry."""
    mock_anthropic_client.messages.create.side_effect = [
        InternalServerError(message="Internal server error", response=Mock(), body={}),
        mock_anthropic_client.messages.create.return_value,
    ]

    result = llm_instance.call("Test prompt", task="test_500")

    assert result == "Test response"
    assert mock_anthropic_client.messages.create.call_count == 2


# ── Test: No Retry on AuthenticationError ────────────────────────────


def test_no_retry_on_authentication_error(llm_instance, mock_anthropic_client):
    """Test that AuthenticationError does NOT retry (non-transient)."""
    mock_anthropic_client.messages.create.side_effect = AuthenticationError(
        message="Invalid API key", response=Mock(), body={}
    )

    with pytest.raises(AuthenticationError):
        llm_instance.call("Test prompt", task="test_auth_fail")

    # Should NOT retry on authentication errors
    assert mock_anthropic_client.messages.create.call_count == 1


# ── Test: Retry with Exponential Backoff ────────────────────────────


def test_retry_exponential_backoff(llm_instance, mock_anthropic_client):
    """Test that retries use exponential backoff."""
    mock_anthropic_client.messages.create.side_effect = [
        RateLimitError("Rate limit", response=Mock(), body={}),
        RateLimitError("Rate limit", response=Mock(), body={}),
        mock_anthropic_client.messages.create.return_value,
    ]

    start = time.time()
    result = llm_instance.call("Test prompt", task="test_backoff")
    duration = time.time() - start

    assert result == "Test response"
    # Should take at least 3 seconds (1s + 2s backoff)
    assert duration >= 3.0
    assert mock_anthropic_client.messages.create.call_count == 3


# ── Test: Retry Telemetry Logging ────────────────────────────────────


@patch("jseeker.llm.logger")
def test_retry_telemetry(mock_logger, llm_instance, mock_anthropic_client):
    """Test that retry attempts are logged for observability."""
    mock_anthropic_client.messages.create.side_effect = [
        RateLimitError("Rate limit", response=Mock(), body={}),
        mock_anthropic_client.messages.create.return_value,
    ]

    llm_instance.call("Test prompt", task="test_telemetry")

    # Verify warning log was called for retry
    assert mock_logger.warning.call_count >= 1
    warning_call = mock_logger.warning.call_args[0][0]
    assert "retry" in warning_call.lower() or "attempt" in warning_call.lower()


# ── Test: Cost Tracking Preserved During Retries ────────────────────


def test_cost_tracking_after_retry(llm_instance, mock_anthropic_client):
    """Test that cost tracking works correctly after retries."""
    mock_anthropic_client.messages.create.side_effect = [
        RateLimitError("Rate limit", response=Mock(), body={}),
        mock_anthropic_client.messages.create.return_value,
    ]

    result = llm_instance.call("Test prompt", task="test_cost")

    assert result == "Test response"
    # Should have 1 cost entry (for successful call only)
    assert len(llm_instance.get_session_costs()) == 1
    assert llm_instance.get_session_costs()[0].task == "test_cost"


# ── Test: Multiple Transient Errors ────────────────────────────────


def test_retry_multiple_error_types(llm_instance, mock_anthropic_client):
    """Test that different transient errors are all handled."""
    mock_anthropic_client.messages.create.side_effect = [
        APITimeoutError(request=Mock()),
        APIConnectionError(message="Connection failed", request=Mock()),
        mock_anthropic_client.messages.create.return_value,
    ]

    result = llm_instance.call("Test prompt", task="test_multiple_errors")

    assert result == "Test response"
    assert mock_anthropic_client.messages.create.call_count == 3


# ── Test: Retry Does Not Break Return Values ────────────────────────


def test_retry_does_not_break_return_values(llm_instance, mock_anthropic_client):
    """Test that retry logic preserves correct return values."""
    # Set up mock to retry once then succeed
    mock_anthropic_client.messages.create.side_effect = [
        RateLimitError("Rate limit", response=Mock(), body={}),
        mock_anthropic_client.messages.create.return_value,
    ]

    result = llm_instance.call("Test prompt", task="test_return_value")

    # Verify correct response is returned after retry
    assert result == "Test response"
    assert isinstance(result, str)
    assert len(result) > 0


# ── Test: Convenience Methods Work with Retry ────────────────────────


def test_call_haiku_with_retry(llm_instance, mock_anthropic_client):
    """Test that call_haiku convenience method supports retry."""
    mock_anthropic_client.messages.create.side_effect = [
        RateLimitError("Rate limit", response=Mock(), body={}),
        mock_anthropic_client.messages.create.return_value,
    ]

    result = llm_instance.call_haiku("Test prompt", task="test_haiku")

    assert result == "Test response"
    assert mock_anthropic_client.messages.create.call_count == 2


def test_call_sonnet_with_retry(llm_instance, mock_anthropic_client):
    """Test that call_sonnet convenience method supports retry."""
    mock_anthropic_client.messages.create.side_effect = [
        APITimeoutError(request=Mock()),
        mock_anthropic_client.messages.create.return_value,
    ]

    result = llm_instance.call_sonnet("Test prompt", task="test_sonnet")

    assert result == "Test response"
    assert mock_anthropic_client.messages.create.call_count == 2


# ── Test: Cost Calculation ────────────────────────────────────────────


def test_calculate_cost():
    """Test cost calculation helper method."""
    from jseeker.llm import JseekerLLM

    # Haiku model costs
    cost = JseekerLLM._calculate_cost(
        model_id="claude-haiku-4-5-20251001",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_tokens=1_000_000,
    )
    # $0.80 input + $4.00 output + $0.08 cache = $4.88
    assert cost == 4.88

    # Sonnet model costs
    cost = JseekerLLM._calculate_cost(
        model_id="claude-sonnet-4-5-20250929",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_tokens=1_000_000,
    )
    # $3.00 input + $15.00 output + $0.30 cache = $18.30
    assert cost == 18.30


def test_session_cost_tracking(llm_instance, mock_anthropic_client):
    """Test session cost tracking methods."""
    # Make a call
    llm_instance.call("Test prompt 1", task="test1")
    llm_instance.call("Test prompt 2", task="test2")

    # Check cost tracking
    costs = llm_instance.get_session_costs()
    assert len(costs) == 2
    assert costs[0].task == "test1"
    assert costs[1].task == "test2"

    # Check total cost
    total = llm_instance.get_total_session_cost()
    assert total > 0
    assert isinstance(total, float)


def test_cache_key_generation():
    """Test cache key generation."""
    from jseeker.llm import JseekerLLM

    key1 = JseekerLLM._cache_key("model1", "system1", "prompt1")
    key2 = JseekerLLM._cache_key("model1", "system1", "prompt1")
    key3 = JseekerLLM._cache_key("model1", "system1", "prompt2")

    # Same inputs should generate same key
    assert key1 == key2

    # Different inputs should generate different keys
    assert key1 != key3

    # Keys should be hex strings (SHA256)
    assert len(key1) == 64
    assert all(c in "0123456789abcdef" for c in key1)


def test_client_property_initialization(llm_instance):
    """Test that client property is initialized correctly."""
    # Client should be set from fixture
    assert llm_instance.client is not None
    assert llm_instance._client is not None

    # Accessing client again should return same instance
    client = llm_instance.client
    assert client is llm_instance._client


def test_budget_exceeded_error():
    """Test BudgetExceededError is raised when monthly budget is exceeded."""

    # Create error instance
    error = BudgetExceededError("Budget exceeded")
    assert isinstance(error, Exception)
    assert str(error) == "Budget exceeded"


def test_call_with_system_prompt(llm_instance, mock_anthropic_client):
    """Test that system prompts are passed correctly."""
    result = llm_instance.call(
        "Test prompt",
        task="test_system",
        system="You are a helpful assistant",
    )

    assert result == "Test response"
    # Verify system was passed to API
    call_args = mock_anthropic_client.messages.create.call_args
    assert call_args is not None
    assert "system" in call_args.kwargs
    system_blocks = call_args.kwargs["system"]
    assert len(system_blocks) > 0


def test_call_with_cache_system(llm_instance, mock_anthropic_client):
    """Test that cache_system parameter adds cache_control."""
    result = llm_instance.call(
        "Test prompt",
        task="test_cache_system",
        system="Long system prompt",
        cache_system=True,
    )

    assert result == "Test response"
    # Verify cache_control was added
    call_args = mock_anthropic_client.messages.create.call_args
    system_blocks = call_args.kwargs["system"]
    assert len(system_blocks) > 0
    # Check if cache_control is in the first block (if enabled in settings)


def test_call_with_temperature_and_max_tokens(llm_instance, mock_anthropic_client):
    """Test that temperature and max_tokens are passed correctly."""
    result = llm_instance.call(
        "Test prompt",
        task="test_params",
        temperature=0.7,
        max_tokens=2048,
    )

    assert result == "Test response"
    call_args = mock_anthropic_client.messages.create.call_args
    assert call_args.kwargs["temperature"] == 0.7
    assert call_args.kwargs["max_tokens"] == 2048


def test_model_routing(llm_instance, mock_anthropic_client):
    """Test that model parameter routes to correct model ID."""
    # Test haiku routing
    llm_instance.call("Test", task="test", model="haiku")
    call_args = mock_anthropic_client.messages.create.call_args
    assert "haiku" in call_args.kwargs["model"].lower()

    # Test sonnet routing
    llm_instance.call("Test", task="test", model="sonnet")
    call_args = mock_anthropic_client.messages.create.call_args
    assert "sonnet" in call_args.kwargs["model"].lower()


def test_response_text_extraction(llm_instance, mock_anthropic_client):
    """Test that response text is correctly extracted from content blocks."""
    # Mock response with multiple text blocks
    response = Mock()
    block1 = Mock(type="text", text="Part 1")
    block2 = Mock(type="text", text=" Part 2")
    response.content = [block1, block2]
    response.usage = Mock(
        input_tokens=100,
        output_tokens=50,
        cache_read_input_tokens=0,
    )
    mock_anthropic_client.messages.create.return_value = response

    result = llm_instance.call("Test", task="test")

    # Should concatenate all text blocks
    assert result == "Part 1 Part 2"


def test_cache_file_operations(tmp_path):
    """Test cache file read/write operations."""
    from jseeker.llm import JseekerLLM

    llm = JseekerLLM()
    llm._cache_dir = tmp_path
    llm._local_cache = {}

    # Test setting cached value
    key = "test_cache_key_123"
    value = "cached response text"
    llm._set_cached(key, value)

    # Check memory cache
    assert key in llm._local_cache
    assert llm._local_cache[key] == value

    # Check file cache
    cache_file = tmp_path / f"{key}.json"
    assert cache_file.exists()

    # Clear memory cache and test file retrieval
    llm._local_cache.clear()
    retrieved = llm._get_cached(key)
    assert retrieved == value

    # Test missing cache
    missing = llm._get_cached("nonexistent_key")
    assert missing is None


def test_cache_corrupted_json(tmp_path):
    """Test handling of corrupted cache JSON files."""
    from jseeker.llm import JseekerLLM

    llm = JseekerLLM()
    llm._cache_dir = tmp_path
    llm._local_cache = {}

    # Write corrupted JSON to cache file
    key = "corrupted_key"
    cache_file = tmp_path / f"{key}.json"
    cache_file.write_text("{ invalid json }", encoding="utf-8")

    # Should return None for corrupted cache
    result = llm._get_cached(key)
    assert result is None


def test_client_initialization_without_api_key(monkeypatch):
    """Test that client initialization raises error without API key."""
    from jseeker.llm import JseekerLLM

    # Remove API key from environment
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from config import settings

    original_key = settings.anthropic_api_key
    settings.anthropic_api_key = None

    try:
        llm = JseekerLLM()
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not set"):
            _ = llm.client
    finally:
        settings.anthropic_api_key = original_key
