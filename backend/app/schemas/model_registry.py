"""Model registry schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ModelRegistryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    version: str
    model_type: str
    training_dataset_provenance: str | None = None
    feature_schema: dict[str, Any] | None = None
    trained_at: datetime | None = None
    validation_results: dict[str, Any] | None = None
    inference_latency_ms: float | None = None
    model_health: str
    last_inference_at: datetime | None = None
    confidence: float | None = None
    fallback_behaviour: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
