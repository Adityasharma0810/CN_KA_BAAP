"""Strict product-facing topology and gateway response contracts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.api_schemas import HealthState


class GatewayStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    status: HealthState
    source: str = Field(pattern=r"^[a-z_]+$")
    environment: str = Field(pattern=r"^[a-z_]+$")
    observed_at: datetime
    client_count: int = Field(ge=0, le=100)
    message: str | None = Field(default=None, max_length=240)


class TopologyNode(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    node_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    kind: str = Field(pattern=r"^(host|gateway|aggregate|client)$")
    label: str = Field(min_length=1, max_length=64)
    status: str = Field(pattern=r"^(online|offline|unknown|unavailable|measured)$")
    source: str = Field(pattern=r"^[a-z_]+$")
    environment: str = Field(pattern=r"^[a-z_]+$")
    client_id: str | None = None
    observed_at: datetime | None = None


class TopologyLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    target: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    relation: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")


class TopologyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    observed_at: datetime
    nodes: list[TopologyNode] = Field(max_length=105)
    links: list[TopologyLink] = Field(max_length=105)
    physical_hotspot_aggregate: bool
