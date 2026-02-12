"""jSeeker LLM wrapper — Claude API with model routing, caching, and cost tracking."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from functools import wraps
from pathlib import Path
from typing import Callable, Optional, TypeVar

import anthropic
from anthropic import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from config import settings
from jseeker.models import APICost

logger = logging.getLogger(__name__)

# Type variable for decorator
F = TypeVar("F", bound=Callable)


def retry_on_transient_errors(
    max_retries: int = 2,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
) -> Callable[[F], F]:
    """Decorator to retry on transient API errors with exponential backoff.

    Retries on:
    - RateLimitError (429)
    - APITimeoutError (timeout/connection interrupted)
    - APIConnectionError (network issues)
    - InternalServerError (500)

    Does NOT retry on:
    - AuthenticationError (401) - invalid API key
    - PermissionDeniedError (403) - insufficient permissions
    - BadRequestError (400) - malformed request
    - Other non-transient errors

    Args:
        max_retries: Maximum number of retry attempts (default: 2).
        initial_delay: Initial delay in seconds before first retry (default: 1.0).
        backoff_factor: Multiplier for delay after each retry (default: 2.0).

    Returns:
        Decorated function with retry logic.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (
                    RateLimitError,
                    APITimeoutError,
                    APIConnectionError,
                    InternalServerError,
                ) as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"Transient API error on attempt {attempt + 1}/{max_retries + 1}: "
                            f"{type(e).__name__}: {str(e)[:100]}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        logger.error(
                            f"Max retries ({max_retries}) exceeded for {type(e).__name__}. Giving up."
                        )
                        raise

            # This should never be reached, but keeps type checker happy
            if last_exception:
                raise last_exception

        return wrapper  # type: ignore

    return decorator


# Model pricing per 1M tokens (input/output) — updated 2026
MODEL_PRICING = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00, "cache_read": 0.08},
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00, "cache_read": 0.30},
}


class BudgetExceededError(Exception):
    """Raised when monthly API budget is exceeded."""

    pass


class JseekerLLM:
    """Claude API wrapper with Haiku/Sonnet routing, prompt caching, and cost tracking."""

    def __init__(self):
        self._client: Optional[anthropic.Anthropic] = None
        self._session_costs: list[APICost] = []
        self._local_cache: dict[str, str] = {}
        self._cache_dir = settings.local_cache_dir

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            api_key = settings.anthropic_api_key
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not set. Add it to .env or environment.")
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def call(
        self,
        prompt: str,
        *,
        task: str = "general",
        model: str = "haiku",
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        cache_system: bool = False,
        use_local_cache: bool = True,
    ) -> str:
        """Call Claude API with model routing and cost tracking.

        Args:
            prompt: User message content.
            task: Task name for cost tracking (e.g., "jd_parse", "adapt_bullets").
            model: "haiku" or "sonnet" — routes to correct model ID.
            system: System prompt content.
            temperature: Generation temperature.
            max_tokens: Max output tokens.
            cache_system: If True, adds cache_control to system prompt.
            use_local_cache: If True, checks/stores local SHA256 cache.

        Returns:
            Assistant response text.
        """
        model_id = settings.sonnet_model if model == "sonnet" else settings.haiku_model

        # Local cache check
        if use_local_cache and settings.enable_local_cache:
            cache_key = self._cache_key(model_id, system, prompt)
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached

        # Build messages
        messages = [{"role": "user", "content": prompt}]

        # Build system with optional prompt caching
        system_blocks = []
        if system:
            block = {"type": "text", "text": system}
            if cache_system and settings.enable_prompt_cache:
                block["cache_control"] = {"type": "ephemeral"}
            system_blocks.append(block)

        # Budget enforcement
        try:
            from jseeker.tracker import tracker_db

            monthly_cost = tracker_db.get_monthly_cost()
            if monthly_cost >= settings.max_monthly_budget_usd:
                raise BudgetExceededError(
                    f"Monthly budget exceeded: ${monthly_cost:.2f} / ${settings.max_monthly_budget_usd:.2f}"
                )
        except ImportError:
            pass  # tracker not available yet

        # API call with retry logic
        start_time = time.time()
        response = self._call_anthropic(
            model_id=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_blocks if system_blocks else [],
            messages=messages,
        )
        duration_ms = int((time.time() - start_time) * 1000)

        # Extract text
        result_text = ""
        for block in response.content:
            if block.type == "text":
                result_text += block.text

        # Track cost
        usage = response.usage
        input_tokens = getattr(usage, "input_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", 0)
        cache_tokens = getattr(usage, "cache_read_input_tokens", 0)
        cost = self._calculate_cost(
            model_id,
            input_tokens,
            output_tokens,
            cache_tokens,
        )

        logger.info(
            f"API call completed | model={model_id} | task={task} | "
            f"input_tokens={input_tokens} | output_tokens={output_tokens} | "
            f"cache_tokens={cache_tokens} | cost_usd=${cost:.6f} | duration_ms={duration_ms}"
        )

        self._session_costs.append(
            APICost(
                model=model_id,
                task=task,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_tokens=cache_tokens,
                cost_usd=cost,
            )
        )

        # Auto-persist to DB
        try:
            from jseeker.tracker import tracker_db

            tracker_db.log_cost(self._session_costs[-1])
        except Exception:
            pass  # DB not available or error — don't break the pipeline

        # Local cache store
        if use_local_cache and settings.enable_local_cache:
            cache_key = self._cache_key(model_id, system, prompt)
            self._set_cached(cache_key, result_text)

        return result_text

    def call_haiku(self, prompt: str, *, task: str = "general", system: str = "", **kwargs) -> str:
        """Convenience: call Haiku (cheap tasks)."""
        return self.call(prompt, task=task, model="haiku", system=system, **kwargs)

    def call_sonnet(self, prompt: str, *, task: str = "general", system: str = "", **kwargs) -> str:
        """Convenience: call Sonnet (quality tasks)."""
        return self.call(prompt, task=task, model="sonnet", system=system, **kwargs)

    def get_session_costs(self) -> list[APICost]:
        """Return all costs tracked this session."""
        return self._session_costs

    def get_total_session_cost(self) -> float:
        """Return total USD spent this session."""
        return sum(c.cost_usd for c in self._session_costs)

    # ── Private Helpers ────────────────────────────────────────────────

    @retry_on_transient_errors(max_retries=2, initial_delay=1.0, backoff_factor=2.0)
    def _call_anthropic(
        self,
        model_id: str,
        max_tokens: int,
        temperature: float,
        system: list,
        messages: list,
    ):
        """Make the actual API call to Anthropic with retry logic.

        This method is decorated with retry_on_transient_errors to handle
        transient failures like rate limits, timeouts, and connection errors.
        """
        return self.client.messages.create(
            model=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        )

    @staticmethod
    def _calculate_cost(
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        cache_tokens: int = 0,
    ) -> float:
        """Calculate cost in USD."""
        pricing = MODEL_PRICING.get(model_id, {"input": 3.0, "output": 15.0, "cache_read": 0.3})
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        cache_cost = (cache_tokens / 1_000_000) * pricing.get("cache_read", 0)
        return round(input_cost + output_cost + cache_cost, 6)

    @staticmethod
    def _cache_key(model: str, system: str, prompt: str) -> str:
        """Generate SHA256 cache key."""
        raw = f"{model}|{system}|{prompt}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _get_cached(self, key: str) -> Optional[str]:
        """Check local cache (memory first, then disk)."""
        if key in self._local_cache:
            return self._local_cache[key]
        cache_file = self._cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                self._local_cache[key] = data["response"]
                return data["response"]
            except (json.JSONDecodeError, KeyError):
                return None
        return None

    def _set_cached(self, key: str, response: str) -> None:
        """Store in local cache (memory + disk)."""
        self._local_cache[key] = response
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self._cache_dir / f"{key}.json"
        cache_file.write_text(
            json.dumps({"response": response}, ensure_ascii=False),
            encoding="utf-8",
        )


# Module-level singleton
llm = JseekerLLM()
