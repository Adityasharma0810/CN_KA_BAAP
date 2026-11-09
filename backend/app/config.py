"""Runtime configuration for the product-facing observation API.

Only non-secret values are read here. Secrets and machine-specific addresses
must be supplied through the environment and must never be committed.
"""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_DATABASE_PATH = "data/experience_budget.sqlite3"

#: An observation older than this is reported as stale by the health API.
STALE_OBSERVATION_AFTER_SECONDS = 300


def database_path() -> Path:
    """Return the configured SQLite path without exposing it through the API."""

    configured = os.environ.get("EB_DATABASE_PATH", "").strip()
    return Path(configured or DEFAULT_DATABASE_PATH)
