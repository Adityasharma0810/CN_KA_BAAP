"""Typed, privacy-safe response models for the product-facing API.

The models deliberately contain no address, hostname, adapter, namespace,
interface, URL, payload, or credential fields. ``extra="forbid"`` keeps
unexpected internal data from being serialized by accident.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


SafeErrorCode = Annotated[
    str,
    Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_.:-]{0,99}$",
        description="Stable, non-sensitive machine-readable error code.",
    ),
]


class ComponentStatus(str, Enum):
    """Health state shared by every reported component."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class CollectorName(str, Enum):
    """Measurement collectors reported by the observation API."""

    WINDOWS_HOST = "windows_host"
    WINDOWS_HOTSPOT = "windows_hotspot"
    LINUX_GATEWAY = "linux_gateway"


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(timezone.utc)


class ComponentHealth(BaseModel):
    """Health of one component without internal paths or exception text."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    status: ComponentStatus
    error_code: SafeErrorCode | None = None
    last_success_at: datetime | None = None

    @field_validator("last_success_at")
    @classmethod
    def normalize_last_success(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _require_utc(value)


class DatabaseHealth(ComponentHealth):
    """Database health plus the reported schema version."""

    schema_version: int | None = Field(default=None, ge=0)


class RegistryHealth(ComponentHealth):
    """Anonymous client registry health plus its client count."""

    client_count: int | None = Field(default=None, ge=0)


class HealthComponents(BaseModel):
    """Component breakdown returned by ``GET /api/v1/health``."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    application: ComponentHealth
    database: DatabaseHealth
    windows_host_collector: ComponentHealth
    windows_hotspot_collector: ComponentHealth
    gateway: ComponentHealth
    client_registry: RegistryHealth


class HealthResponse(BaseModel):
    """Overall health envelope."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    status: ComponentStatus
    observed_at: datetime
    components: HealthComponents

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _require_utc(value)


class CollectorHealth(BaseModel):
    """One collector's health entry."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    collector: CollectorName
    status: ComponentStatus
    error_code: SafeErrorCode | None = None
    last_success_at: datetime | None = None
    stale: bool = False

    @field_validator("last_success_at")
    @classmethod
    def normalize_last_success(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _require_utc(value)


class CollectorsResponse(BaseModel):
    """Collector health envelope."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    observed_at: datetime
    collectors: list[CollectorHealth]

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _require_utc(value)
