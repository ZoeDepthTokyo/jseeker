"""JSEEKER configuration - inherits from GAIA GaiaSettings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Try GAIA integration, fall back to standalone
try:
    from rag_intelligence.config import GaiaSettings as _BaseSettings
except ImportError:
    _BaseSettings = BaseSettings

_PROJECT_ROOT = Path(__file__).parent


class JseekerSettings(_BaseSettings):
    """JSEEKER configuration with GAIA ecosystem integration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Identity ---
    app_name: str = "JSEEKER"
    app_version: str = "0.3.8.1"

    # --- Paths (computed from project root) ---
    jseeker_root: Path = _PROJECT_ROOT
    data_dir: Path = _PROJECT_ROOT / "data"
    output_dir: Path = _PROJECT_ROOT / "output"
    db_path: Path = _PROJECT_ROOT / "data" / "jseeker.db"
    local_cache_dir: Path = _PROJECT_ROOT / "data" / ".cache"

    # --- API Keys ---
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")

    # --- Model Configuration ---
    haiku_model: str = "claude-haiku-4-5-20251001"
    sonnet_model: str = "claude-sonnet-4-5-20250929"

    # --- Cost Controls ---
    max_monthly_budget_usd: float = 10.0
    cost_warning_threshold_usd: float = 8.0

    # --- Caching ---
    enable_prompt_cache: bool = True
    enable_local_cache: bool = True

    # --- GAIA Integration ---
    gaia_root: Path = Path("X:/Projects/_GAIA")
    argus_log_path: Path = Path("X:/Projects/_GAIA/logs/jseeker_build.jsonl")

    @model_validator(mode="after")
    def _resolve_api_key(self):
        if self.anthropic_api_key is None:
            self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        return self

    @model_validator(mode="after")
    def _migrate_db(self):
        """Auto-migrate proteus.db -> jseeker.db if needed."""
        old_db = self.data_dir / "proteus.db"
        new_db = self.data_dir / "jseeker.db"
        if old_db.exists() and not new_db.exists():
            old_db.rename(new_db)
        return self

    @property
    def resume_blocks_dir(self) -> Path:
        return self.data_dir / "resume_blocks"

    @property
    def templates_dir(self) -> Path:
        return self.data_dir / "templates"

    @property
    def prompts_dir(self) -> Path:
        return self.data_dir / "prompts"

    @property
    def ats_profiles_dir(self) -> Path:
        return self.data_dir / "ats_profiles"


# Singleton
settings = JseekerSettings()
