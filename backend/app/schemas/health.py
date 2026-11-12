"""Health schemas for the control plane."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ComponentHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: str  # healthy|degraded|unavailable
    checked_at: datetime
    last_success: datetime | None = None
    error_code: str | None = None


class HealthOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    checked_at: datetime
    gateway_id: str | None = None
    components: list[ComponentHealth]
    version: str | None = None
