"""Strict response models for observation-backed QoE proxy scores."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.schemas import ClientId


class QoEModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class QoEInput(QoEModel):
    value: float
    unit: Literal["ms", "%", "Mbps", "ratio", "clients"]
    observed_at: datetime


class QoEClientScore(QoEModel):
    client_id: ClientId
    traffic_class: Literal["call", "game", "stream", "bulk", "unknown"]
    class_source: Literal["scenario_declared", "unclassified"]
    score: float | None = Field(default=None, ge=0, le=100)
    band: Literal["green", "amber", "red", "unknown"]
    observed_at: datetime
    inputs: dict[str, QoEInput]
    missing_inputs: list[str]


class QoECurrentResponse(QoEModel):
    observed_at: datetime
    clients: list[QoEClientScore]


class QoEHistoryResponse(QoEModel):
    requested_at: datetime
    client_id: ClientId | None = None
    count: int = Field(ge=0)
    observations: list[QoEClientScore]
