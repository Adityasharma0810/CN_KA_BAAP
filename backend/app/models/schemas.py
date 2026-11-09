"""Shared, privacy-safe observation contracts for Part 1.

These models are deliberately independent of a collector or persistence layer.
They provide one vocabulary for Windows aggregate observations and Linux lab
observations without allowing network identity fields to cross the boundary.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


class ObservationSource(str, Enum):
    """Origin of an observation."""

    WINDOWS_HOST = "windows_host"
    WINDOWS_HOTSPOT = "windows_hotspot"
    LINUX_GATEWAY = "linux_gateway"
    LINUX_NAMESPACE_LAB = "linux_namespace_lab"


class ObservationScope(str, Enum):
    """Whether a sample describes an aggregate or one anonymous client."""

    AGGREGATE_GATEWAY = "aggregate_gateway"
    AGGREGATE_HOTSPOT = "aggregate_hotspot"
    CLIENT = "client"


class ValueQuality(str, Enum):
    """How a reported value was obtained."""

    MEASURED = "measured"
    DERIVED = "derived"
    UNAVAILABLE = "unavailable"


class ObservationEnvironment(str, Enum):
    """Whether the observation is from a host or an emulated lab."""

    PHYSICAL_HOST = "physical_host"
    SIMULATED_LAB = "simulated_lab"


ClientId = Annotated[
    str,
    Field(
        min_length=14,
        max_length=40,
        pattern=r"^client-[a-z0-9]{8,32}$",
        description="Opaque random identifier; never an address or device name.",
    ),
]


class ObservationMetadata(BaseModel):
    """Common provenance and freshness metadata for every observation."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    observed_at: datetime
    source: ObservationSource
    scope: ObservationScope
    quality: ValueQuality
    environment: ObservationEnvironment
    stale: bool = False
    collector_error: str | None = Field(default=None, max_length=500)
    client_id: ClientId | None = None

    @field_validator("observed_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        """Reject naive timestamps and normalize offset timestamps to UTC."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        return value.astimezone(timezone.utc)

    @field_validator("client_id")
    @classmethod
    def validate_scope_identity(cls, value: str | None, info):
        """Only client-scoped observations may carry a client ID."""

        scope = info.data.get("scope")
        if value is not None and scope != ObservationScope.CLIENT:
            raise ValueError("client_id is allowed only for client observations")
        return value

    @field_validator("collector_error")
    @classmethod
    def reject_identity_like_error_text(cls, value: str | None) -> str | None:
        """Keep accidental address leakage out of persisted error metadata."""

        if value is None:
            return None
        lowered = value.lower()
        forbidden = ("mac address", "ip address", "device name", "client name")
        if any(term in lowered for term in forbidden):
            raise ValueError("collector_error contains forbidden identity data")
        return value


class TelemetryObservation(BaseModel):
    """A unified observation record consumed by services, storage, and APIs.

    ``None`` means that a metric was not available; it must not be converted to
    zero. Rates are in Mbps, counters are bytes/packets, and RTT/jitter are ms.
    ``rtt_variation_ms`` is mean absolute difference between successive
    successful RTT samples, not a standardized media-jitter measurement.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    metadata: ObservationMetadata
    download_bytes: StrictInt | None = Field(default=None, ge=0)
    upload_bytes: StrictInt | None = Field(default=None, ge=0)
    download_packets: StrictInt | None = Field(default=None, ge=0)
    upload_packets: StrictInt | None = Field(default=None, ge=0)
    download_mbps: float | None = Field(default=None, ge=0)
    upload_mbps: float | None = Field(default=None, ge=0)
    rtt_ms: float | None = Field(default=None, ge=0)
    packet_loss_percent: float | None = Field(default=None, ge=0, le=100)
    rtt_variation_ms: float | None = Field(default=None, ge=0)
    queue_depth_bytes: StrictInt | None = Field(default=None, ge=0)
    queue_delay_ms: float | None = Field(default=None, ge=0)

    @field_validator(
        "download_bytes",
        "upload_bytes",
        "download_packets",
        "upload_packets",
        "queue_depth_bytes",
    )
    @classmethod
    def reject_boolean_counters(cls, value: int | None) -> int | None:
        if isinstance(value, bool):
            raise ValueError("counter values must be integers, not booleans")
        return value

    @field_validator("metadata")
    @classmethod
    def validate_client_scope(cls, metadata: ObservationMetadata):
        if metadata.scope == ObservationScope.CLIENT and metadata.client_id is None:
            raise ValueError("client observations require an anonymous client_id")
        if metadata.scope != ObservationScope.CLIENT and metadata.client_id is not None:
            raise ValueError("aggregate observations cannot contain client_id")
        return metadata
