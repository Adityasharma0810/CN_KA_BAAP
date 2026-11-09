"""Strict privacy-safe response models for anonymous client routes."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.schemas import (
    ClientId,
    ObservationEnvironment,
    ObservationSource,
    TelemetryObservation,
)
from backend.app.services.client_registry import ClientStatus


class AnonymousClientResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    client_id: ClientId
    display_label: str = Field(pattern=r"^Client [0-9]{2,}$")
    status: ClientStatus
    environment: ObservationEnvironment
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    stale: bool
    latest_observation: TelemetryObservation | None = None


class AnonymousClientsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    count: int = Field(ge=0, le=100)
    available: bool
    clients: list[AnonymousClientResponse] = Field(max_length=100)
    source: ObservationSource
    environment: ObservationEnvironment
    message: str | None = Field(default=None, max_length=160)


class AnonymousClientDetailResponse(AnonymousClientResponse):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    available: bool
    source: ObservationSource
    message: str | None = Field(default=None, max_length=160)
