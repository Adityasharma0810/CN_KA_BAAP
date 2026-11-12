"""Cloud-persisted observation records (read-only copies of gateway telemetry)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, CreatedAt, GUID


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[GUID]
    gateway_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    quality: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    client_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON serialised TelemetryObservation
    created_at: Mapped[datetime] = CreatedAt
