"""Strict, privacy-safe runtime capability response models."""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SystemPlatform(str, Enum):
    LINUX = "linux"
    WINDOWS = "windows"
    OTHER = "other"


class LabIngestState(str, Enum):
    RUNNING = "running"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    STOPPED = "stopped"


class SystemCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    platform: SystemPlatform
    windows_collectors_supported: bool
    lab_ingest_enabled: bool
    lab_ingest_state: LabIngestState
    lab_ingest_interval_seconds: float = Field(ge=1, le=3600)
    lab_ingest_last_success: datetime | None
    lab_ingest_last_error_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_.:-]{0,99}$",
    )
    observation_freshness_threshold_seconds: int = Field(ge=1)

    @field_validator("lab_ingest_last_success")
    @classmethod
    def normalize_last_success(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(timezone.utc)
