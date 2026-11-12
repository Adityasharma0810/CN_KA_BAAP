"""Policy preview/apply schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ClientAllocationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(min_length=1, max_length=64)
    download_mbps: float | None = Field(default=None, ge=0)
    upload_mbps: float | None = Field(default=None, ge=0)


class PolicyPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capacity_mbps: float = Field(ge=0)
    allocations: list[ClientAllocationIn] = Field(default_factory=list)
    mode: str = Field(default="auto", max_length=32)


class PolicyPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feasible: bool
    capacity_mbps: float
    allocations: list[dict[str, Any]]
    constraints: dict[str, Any] | None = None
    trade_offs: list[str] | None = None
    warning: str | None = None


class PolicyApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capacity_mbps: float = Field(ge=0)
    allocations: list[ClientAllocationIn]
    mode: str = Field(default="auto", max_length=32)
    verify: bool = Field(default=True)
