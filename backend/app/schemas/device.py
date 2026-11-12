"""Device inventory schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DeviceBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=200)
    member_id: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=64)


class DeviceCreate(DeviceBase):
    device_id: str = Field(min_length=1, max_length=64)


class DeviceUpdate(DeviceBase):
    pass


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    device_id: str
    local_alias: str | None = None
    display_name: str | None = None
    member_id: str | None = None
    category: str | None = None
    connection_status: str
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    upload_bytes: int
    download_bytes: int
    current_upload_rate_mbps: float | None = None
    current_download_rate_mbps: float | None = None
    current_qoe: float | None = None
    traffic_class: str | None = None
    classification_confidence: float | None = None
    associated_policy: str | None = None
    is_anonymous: bool
    created_at: datetime
    updated_at: datetime


class DeviceListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    count: int
    devices: list[DeviceOut]
