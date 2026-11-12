"""Strict, privacy-safe response models for the traffic-classifier API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TrafficClass = Literal["call", "game", "stream", "bulk", "unknown"]
ClassSource = Literal["ml_classifier", "scenario_declared", "unclassified"]


class ClassifierStatus(BaseModel):
    """Live classifier availability and held-out evaluation vs baseline."""

    model_config = ConfigDict(extra="forbid")

    available: bool
    version: str | None = None
    classes: list[TrafficClass] = Field(max_length=8)
    confidence_threshold: float = Field(ge=0, le=1)
    held_out_f1: float | None = Field(default=None, ge=0, le=1)
    baseline_f1: float | None = Field(default=None, ge=0, le=1)
    last_fallback_reason: str | None = Field(default=None, max_length=300)
    training_note: str = Field(min_length=1, max_length=400)


class LabelCorrectionRequest(BaseModel):
    """Untrusted user label correction; never used for auto-training."""

    model_config = ConfigDict(extra="forbid")

    corrected_label: TrafficClass
    note: str | None = Field(default=None, max_length=200)


class LabelCorrectionResponse(BaseModel):
    """Acknowledgement of a stored correction."""

    model_config = ConfigDict(extra="forbid")

    accepted: bool
    stored_at: datetime
    client_id: str = Field(min_length=14, max_length=64)
    corrected_label: TrafficClass
    training_triggered: bool  # always False; corrections are never auto-trained
