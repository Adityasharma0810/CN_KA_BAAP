"""Intent lifecycle models."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from sqlalchemy import DateTime, ForeignKey, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, CreatedAt, GUID, UpdatedAt


class Intent(Base):
    __tablename__ = "intents"

    id: Mapped[GUID]
    gateway_id: Mapped[str] = mapped_column(ForeignKey("gateways.gateway_id"), index=True, nullable=False)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True, nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    traffic_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    objective: Mapped[str] = mapped_column(String(200), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    urgency: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_service_floor_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    allowed_trade_offs: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    approval_state: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = CreatedAt
    updated_at: Mapped[datetime] = UpdatedAt

    gateway = relationship("Gateway", back_populates="intents")
