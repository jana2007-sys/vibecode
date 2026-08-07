"""Application configuration loaded from environment / .env file.

Uses pydantic-settings so configuration is validated and typed at startup.
"""

from functools import lru_cache
from pathlib import Path

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

    # --- CORS ---
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Gemini API (future integration) ---
    gemini_enabled: bool = False
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

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
    def database_file_path(self) -> Path:
        """Resolve the database path relative to the backend package root."""
        path = Path(self.database_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent.parent / path
        return path


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (single source of truth)."""
    return Settings()
