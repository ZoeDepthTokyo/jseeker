"""Manage base resume reference paths shown in the UI."""

from __future__ import annotations

import json
from pathlib import Path


DEFAULT_RESUME_SOURCES = {
    "base_a": "",
    "base_b": "",
    "base_c": "",
    "linkedin_pdf": "",
}


def _sources_path() -> Path:
    from config import settings

    return settings.data_dir / "resume_sources.json"


def load_resume_sources(path: Path | None = None) -> dict[str, str]:
    """Load saved base resume sources or defaults when missing/invalid."""
    if path is None:
        path = _sources_path()

    if not path.exists():
        return DEFAULT_RESUME_SOURCES.copy()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return DEFAULT_RESUME_SOURCES.copy()

    merged = DEFAULT_RESUME_SOURCES.copy()
    for key in merged:
        value = data.get(key, "")
        merged[key] = str(value).strip() if value is not None else ""
    return merged


def save_resume_sources(values: dict[str, str], path: Path | None = None) -> dict[str, str]:
    """Persist base resume source paths and return normalized values."""
    if path is None:
        path = _sources_path()

    normalized = DEFAULT_RESUME_SOURCES.copy()
    for key in normalized:
        value = values.get(key, "")
        normalized[key] = str(value).strip() if value is not None else ""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    return normalized

