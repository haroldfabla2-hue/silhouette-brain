"""Environment-driven configuration.

All settings are read from the environment (or a ``.env`` file) with the
``SILHOUETTE_`` prefix, e.g. ``SILHOUETTE_NEO4J_URI``. Secrets are never baked
into the code; if a backend's credentials are absent the system degrades to a
local fallback instead of failing.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SILHOUETTE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Paths -------------------------------------------------------------
    data_dir: Path = Field(default=Path("./data"))

    # --- Embeddings --------------------------------------------------------
    # When fastembed is installed and this model is set, it is used; otherwise
    # the system falls back to a deterministic dependency-free embedder.
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dims: int = 384
    use_fastembed: bool = True

    # --- Deep memory (Neo4j) ----------------------------------------------
    neo4j_uri: str | None = None
    neo4j_user: str = "neo4j"
    neo4j_password: str | None = None

    # --- Working memory (Redis) -------------------------------------------
    redis_url: str | None = None
    working_capacity: int = 256
    working_ttl_seconds: int = 3600

    # --- Reasoning / synthesis (optional LLM) -----------------------------
    reasoning_provider: str = "none"  # none | openai | minimax | anthropic
    reasoning_api_key: str | None = None
    reasoning_model: str = "gpt-4o-mini"
    reasoning_base_url: str | None = None

    # --- API ---------------------------------------------------------------
    api_host: str = "127.0.0.1"
    api_port: int = 9876

    # --- Engines (intervals in seconds) -----------------------------------
    curiosity_interval: int = 3600
    janitor_interval: int = 43200
    dreamer_interval: int = 21600
    evolution_interval: int = 21600
    session_sync_interval: int = 120

    # --- Security -----------------------------------------------------------
    injection_guard_enabled: bool = True

    # --- Integrations -------------------------------------------------------
    # When set, the daemon tails OpenClaw session JSONL files into memory.
    openclaw_agents_dir: Path | None = None

    def db_path(self, name: str) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / name


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached settings instance."""
    return Settings()
