"""ARGUS telemetry — build and runtime monitoring for PROTEUS."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config import settings


def log_event(
    agent: str,
    wave: int,
    module: str,
    status: str,
    duration_ms: int = 0,
    details: str = "",
) -> None:
    """Write a telemetry event to the ARGUS build log.

    Args:
        agent: Agent name (e.g., "senior-python-ml-engineer").
        wave: Build wave number (1-4).
        module: File being created/modified.
        status: "started", "completed", or "error".
        duration_ms: Duration in milliseconds.
        details: Additional context.
    """
    log_path = settings.argus_log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "wave": wave,
        "module": module,
        "status": status,
        "duration_ms": duration_ms,
        "details": details,
    }

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def log_runtime_event(
    task: str,
    model: str,
    cost_usd: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    details: str = "",
) -> None:
    """Log a runtime API call event for cost monitoring."""
    log_path = settings.gaia_root / "logs" / "proteus_runtime.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "component": "proteus",
        "task": task,
        "model": model,
        "cost_usd": cost_usd,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "details": details,
    }

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
