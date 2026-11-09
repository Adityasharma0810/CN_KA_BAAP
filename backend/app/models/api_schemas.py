"""Strict response contracts for the product-facing observation API."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ComponentHealth(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_:-]+$")
    status: HealthState
    checked_at: datetime
    last_successful_measurement: datetime | None = None
    error_code: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9_:-]+$")


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    status: HealthState
    checked_at: datetime
    components: list[ComponentHealth] = Field(max_length=16)


class CollectorHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    checked_at: datetime
    collectors: list[ComponentHealth] = Field(max_length=16)
