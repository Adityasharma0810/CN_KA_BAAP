"""Decision ledger models. Every automatic or user-approved policy decision is
recorded with its inputs, models, enforcement result, and verification outcome."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from sqlalchemy import DateTime, ForeignKey, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, CreatedAt, GUID, UpdatedAt


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[GUID]
    gateway_id: Mapped[str] = mapped_column(ForeignKey("gateways.gateway_id"), index=True, nullable=False)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True, nullable=False)
    decided_at: Mapped[datetime] = CreatedAt
    input_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    model_versions: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    model_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    capacity_estimate_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    capacity_uncertainty_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    forecast_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    qoe_before: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    qoe_after: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    fairness_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    fairness_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    selected_policy: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    policy_constraints: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    enforcement_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    kernel_readback: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    verification_result: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    rollback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rollback_status: Mapped[str] = mapped_column(String(32), default="not_required", nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    gateway = relationship("Gateway", back_populates="decisions")
