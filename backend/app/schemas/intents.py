"""Intent lifecycle schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IntentBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str | None = Field(default=None, max_length=64)
    traffic_class: str | None = Field(default=None, max_length=32)
    objective: str = Field(min_length=1, max_length=200)
    priority: int = Field(default=1, ge=1, le=5)
    urgency: str = Field(default="normal", max_length=32)
    deadline: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=525600)
    min_service_floor_mbps: float | None = Field(default=None, ge=0)
    allowed_trade_offs: dict[str, Any] | None = None


class IntentCreate(IntentBase):
    pass


class IntentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str | None = Field(default=None, min_length=1, max_length=200)
    priority: int | None = Field(default=None, ge=1, le=5)
    urgency: str | None = Field(default=None, max_length=32)
    deadline: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=525600)
    min_service_floor_mbps: float | None = Field(default=None, ge=0)
    allowed_trade_offs: dict[str, Any] | None = None
    approval_state: str | None = Field(default=None, max_length=32)


class IntentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    device_id: str | None = None
    traffic_class: str | None = None
    objective: str
    priority: int
    urgency: str
    deadline: datetime | None = None
    duration_minutes: int | None = None
    min_service_floor_mbps: float | None = None
    allowed_trade_offs: dict[str, Any] | None = None
    approval_state: str
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
