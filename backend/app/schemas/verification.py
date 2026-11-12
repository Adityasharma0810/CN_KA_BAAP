"""Verification and rollback schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    reason: str | None = Field(default=None, max_length=500)


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    gateway_id: str
    decided_at: datetime
    model_confidence: float | None = None
    capacity_estimate_mbps: float | None = None
    capacity_uncertainty_mbps: float | None = None
    forecast_mbps: float | None = None
    enforcement_status: str
    verification_result: str
    rollback_status: str
    rollback_reason: str | None = None
    explanation: str | None = None
