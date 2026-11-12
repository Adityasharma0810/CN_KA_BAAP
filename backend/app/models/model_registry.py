"""Model registry entries. Accuracy/latency/health figures are real measured
values, never invented."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from sqlalchemy import DateTime, Float, Integer, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, CreatedAt, GUID, UpdatedAt


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    id: Mapped[GUID]
    name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_type: Mapped[str] = mapped_column(String(64), nullable=False)
    training_dataset_provenance: Mapped[str | None] = mapped_column(Text, nullable=True)
    feature_schema: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validation_results: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    inference_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_health: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    last_inference_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    fallback_behaviour: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = CreatedAt
    updated_at: Mapped[datetime] = UpdatedAt
