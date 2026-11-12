"""Strict, privacy-safe gateway status and topology response contracts."""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models.schemas import ValueQuality


class TopologyState(str, Enum):
    MISSING = "missing"
    STALE = "stale"
    OFFLINE = "offline"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    ONLINE = "online"


class GatewayOverallStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class TopologySource(str, Enum):
    APPLICATION = "application"
    WINDOWS_HOST = "windows_host"
    WINDOWS_HOTSPOT = "windows_hotspot"
    LINUX_GATEWAY = "linux_gateway"
    LINUX_LAB = "linux_lab"
    LINUX_HOTSPOT = "linux_hotspot"
    ANONYMOUS_REGISTRY = "anonymous_registry"


class TopologyNodeKind(str, Enum):
    APPLICATION = "application"
    WINDOWS_HOST = "windows_host"
    HOTSPOT = "hotspot"
    LINUX_LAB = "linux_lab"
    CLIENT = "client"


class TopologyEdgeType(str, Enum):
    CONFIGURED = "configured"
    OBSERVED = "observed"
    DERIVED = "derived"
    UNKNOWN = "unknown"


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(timezone.utc)


class SourceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    state: TopologyState = Field(
        description=(
            "'online' means recently measured with measured or derived "
            "quality; it does not assert network connectivity."
        )
    )
    last_observed_at: datetime | None = None
    data_quality: ValueQuality

    @field_validator("last_observed_at")
    @classmethod
    def normalize_last_observed_at(
        cls, value: datetime | None
    ) -> datetime | None:
        return None if value is None else _require_utc(value)


class GatewayStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    observed_at: datetime
    status: GatewayOverallStatus
    application: SourceStatus
    windows_host: SourceStatus
    hotspot: SourceStatus
    linux_lab: SourceStatus

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _require_utc(value)


class TopologyNode(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    node_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    kind: TopologyNodeKind
    label: str = Field(min_length=1, max_length=64)
    state: TopologyState = Field(
        description=(
            "'online' means recently measured with measured or derived "
            "quality; it does not assert network connectivity."
        )
    )
    source: TopologySource
    data_quality: ValueQuality
    last_observed_at: datetime | None = None
    client_id: str | None = Field(
        default=None,
        min_length=14,
        max_length=40,
        pattern=r"^client-[a-z0-9]{8,32}$",
    )

    @field_validator("last_observed_at")
    @classmethod
    def normalize_last_observed_at(
        cls, value: datetime | None
    ) -> datetime | None:
        return None if value is None else _require_utc(value)


class TopologyLink(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    source: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    target: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    relation: TopologyEdgeType


class TopologySourceStatus(SourceStatus):
    source: TopologySource


class TopologyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    observed_at: datetime
    nodes: list[TopologyNode] = Field(max_length=105)
    links: list[TopologyLink] = Field(max_length=105)
    sources: list[TopologySourceStatus] = Field(max_length=7)

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _require_utc(value)
