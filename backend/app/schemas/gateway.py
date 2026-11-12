"""Gateway registration, pairing, and heartbeat schemas."""

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GatewayRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gateway_id: str = Field(min_length=8, max_length=64)
    name: str | None = Field(default=None, max_length=200)
    platform: str | None = Field(default=None, max_length=32)
    version: str | None = Field(default=None, max_length=32)
    public_key_fingerprint: str | None = Field(default=None, max_length=128)
    capabilities: dict[str, Any] | None = None


class GatewayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    gateway_id: str
    name: str | None = None
    platform: str | None = None
    version: str | None = None
    status: str
    last_heartbeat: datetime | None = None
    last_observation_at: datetime | None = None
    connected_at: datetime | None = None
    capabilities: dict[str, Any] | None = None
    created_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def _deserialize(cls, data: Any) -> Any:
        if isinstance(data, dict):
            capabilities = data.get("capabilities")
            if isinstance(capabilities, str):
                try:
                    data["capabilities"] = json.loads(capabilities)
                except (ValueError, TypeError):
                    data["capabilities"] = None
        return data


class PairingCodeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ttl_minutes: int | None = Field(default=None, ge=1, le=1440)


class PairingCodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    expires_at: datetime


class GatewayPair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=16)
    gateway_id: str = Field(min_length=8, max_length=64)


class GatewayHeartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gateway_id: str
    version: str | None = None
    platform: str | None = None
    capabilities: dict[str, Any] | None = None
    status: str | None = None
    buffered_observations: int | None = Field(default=None, ge=0)


class GatewayStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    gateway_id: str
    status: str
    last_heartbeat: datetime | None = None
    connected: bool
    version: str | None = None
    capabilities: dict[str, Any] | None = None
