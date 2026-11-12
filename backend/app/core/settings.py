"""Control-plane configuration.

All values are read from the environment. Secrets are never given defaults and
are never serialized by the API. Use a `.env` file only for local development;
production must inject secrets through the platform.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # backend/app/core/settings.py -> repo root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application -----------------------------------------------------
    app_name: str = "Experience Budget"
    app_version: str = "0.8.0"
    environment: str = Field(default="development", description="development|staging|production")
    api_version: str = "v1"
    debug: bool = False

    # --- Database --------------------------------------------------------
    # SQLite for local/standalone; PostgreSQL for the hosted multi-user plane.
    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{_PROJECT_ROOT / 'data' / 'experience_budget.sqlite3'}",
        description="SQLAlchemy async database URL",
    )

    # --- Security --------------------------------------------------------
    # No default: must be set in production (EB_SECRET_KEY).
    secret_key: str = Field(default="", description="JWT signing secret")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    bcrypt_rounds: int = 12

    # --- CORS ------------------------------------------------------------
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="Comma-separated allowed origins",
    )

    # --- Gateway agent / pairing ----------------------------------------
    pairing_code_ttl_minutes: int = 10
    pairing_code_length: int = 8
    agent_heartbeat_timeout_seconds: int = 90
    agent_reconnect_backoff_base_seconds: float = 1.0
    agent_reconnect_backoff_max_seconds: float = 60.0

    # --- Telemetry / ML --------------------------------------------------
    ml_cycle_seconds: int = 30
    telemetry_stale_after_seconds: int = 300
    default_sampling_interval_seconds: int = 5

    # --- Feature flags ---------------------------------------------------
    enable_federated_learning: bool = False
    enable_multi_wan: bool = False


settings = Settings()
