"""Traffic classification schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ClassificationPredictionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str
    traffic_class: str
    confidence: float | None = None
    features: dict[str, Any] | None = None
    predicted_at: datetime
    source: str = "ml"


class ClassificationCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str
    traffic_class: str = Field(max_length=32)
    confidence: float | None = Field(default=None, ge=0, le=1)
    noted_at: datetime | None = None
