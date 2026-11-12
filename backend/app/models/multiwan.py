"""Multi-link WAN models."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from sqlalchemy import Boolean, DateTime, ForeignKey, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, CreatedAt, GUID, UpdatedAt


class MultiWANLink(Base):
    __tablename__ = "multi_wan_links"

    id: Mapped[GUID]
    gateway_id: Mapped[str] = mapped_column(ForeignKey("gateways.gateway_id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    link_type: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    capacity_download_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    capacity_upload_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    loss_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_cost_tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    user_limit_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    preferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    backup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = CreatedAt
    updated_at: Mapped[datetime] = UpdatedAt
