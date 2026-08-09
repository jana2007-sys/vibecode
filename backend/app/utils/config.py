"""Application configuration loaded from environment / .env file.

Uses pydantic-settings so configuration is validated and typed at startup.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings.

    All values can be overridden through environment variables or a .env file.
    """

    # --- Runtime ---
    app_name: str = "InterVue AI"
    app_version: str = "0.1.0"
    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000

    # --- Database ---
    database_path: str = "data/intervue.db"
    #: PostgreSQL DSN (e.g. postgres://user:pass@host:5432/dbname). When set to
    #: a postgres:// URL the app uses PostgreSQL; otherwise SQLite at
    #: ``database_path`` is used (local development).
    database_url: str = ""
    #: Separate "private" database that archives enrolled candidates and their
    #: completed interview reports (opaque to the public API contract). In
    #: production it lives in the same PostgreSQL instance as the public tables.
    private_database_path: str = "data/private.db"

    # --- CORS ---
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Gemini API (future integration) ---
    gemini_enabled: bool = False
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # --- AI verifier ensemble (multi-AI answer verification) ---
    # Comma-separated model ids that independently verify every candidate answer
    # before it is marked (e.g. "gemini-2.0-flash,gemini-2.5-pro"). Requires
    # GEMINI_ENABLED=true and GEMINI_API_KEY; empty disables the ensemble.
    ai_verifier_models: str = ""
    # Minimum fraction of verifier AIs that must confirm an answer for it to be
    # marked correct. 0.5 = majority consensus.
    ai_verifier_agreement: float = Field(default=0.5, ge=0.0, le=1.0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse the comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def ai_verifier_model_list(self) -> list[str]:
        """Parse the comma-separated verifier model ids into a non-empty list."""
        return [model.strip() for model in self.ai_verifier_models.split(",") if model.strip()]

    @property
    def database_file_path(self) -> Path:
        """Resolve the database path relative to the backend package root."""
        path = Path(self.database_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent.parent / path
        return path

    @property
    def private_database_file_path(self) -> Path:
        """Resolve the private database path relative to the backend package root."""
        path = Path(self.private_database_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent.parent / path
        return path


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (single source of truth)."""
    return Settings()
