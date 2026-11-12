"""QoE scoring schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class QoEClientOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str
    traffic_class: str
    score: float | None = Field(default=None, ge=0, le=100)
    band: str
    inputs: dict[str, Any] | None = None
    missing_inputs: list[str] | None = None
    observed_at: datetime | None = None


class QoECurrentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: datetime
    clients: list[QoEClientOut]
