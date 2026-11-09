"""Runtime configuration for the product-facing observation API.

Only non-secret values are read here. Secrets and machine-specific addresses
must be supplied through the environment and must never be committed.
"""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_DATABASE_PATH = "data/experience_budget.sqlite3"

#: Internal read-only gateway observation agent. Never returned by the API.
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8100"
DEFAULT_GATEWAY_TIMEOUT_SECONDS = 2.0
DEFAULT_GATEWAY_SAMPLE_INTERVAL_SECONDS = 2.0

#: An observation older than this is reported as stale by the health API.
STALE_OBSERVATION_AFTER_SECONDS = 300


def database_path() -> Path:
    """Return the configured SQLite path without exposing it through the API."""

    configured = os.environ.get("EB_DATABASE_PATH", "").strip()
    return Path(configured or DEFAULT_DATABASE_PATH)


def gateway_url() -> str:
    """Return the internal observation-agent base URL."""

    configured = os.environ.get("EB_GATEWAY_URL", "").strip()
    return configured or DEFAULT_GATEWAY_URL


def gateway_timeout_seconds() -> float:
    """Return a bounded request timeout for the observation agent."""

    raw = os.environ.get("EB_GATEWAY_TIMEOUT_SECONDS", "").strip()
    try:
        value = float(raw) if raw else DEFAULT_GATEWAY_TIMEOUT_SECONDS
    except ValueError:
        return DEFAULT_GATEWAY_TIMEOUT_SECONDS
    return min(max(value, 0.1), 10.0)


def gateway_token() -> str | None:
    """Return the optional internal agent bearer token, never serialized."""

    configured = os.environ.get("EB_GATEWAY_TOKEN", "").strip()
    return configured or None


def gateway_sample_interval_seconds() -> float:
    """Return a bounded sampling interval for the gateway agent."""

    raw = os.environ.get("EB_GATEWAY_SAMPLE_INTERVAL_SECONDS", "").strip()
    try:
        value = (
            float(raw)
            if raw
            else DEFAULT_GATEWAY_SAMPLE_INTERVAL_SECONDS
        )
    except ValueError:
        return DEFAULT_GATEWAY_SAMPLE_INTERVAL_SECONDS
    return min(max(value, 0.5), 60.0)
