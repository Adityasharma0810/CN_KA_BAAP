"""Experiment manifest and result models."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from sqlalchemy import DateTime, Float, Integer, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, CreatedAt, GUID, UpdatedAt


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[GUID]
    household_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    gateway_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    manifest: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    environment: Mapped[str] = mapped_column(String(32), default="production", nullable=False)
    results_summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = CreatedAt
    updated_at: Mapped[datetime] = UpdatedAt
