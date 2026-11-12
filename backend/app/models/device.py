"""Device inventory models. Pseudonymous client identifiers only; no raw
MAC/IP/hostname is stored in the cloud telemetry database."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, CreatedAt, GUID, UpdatedAt


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[GUID]
    gateway_id: Mapped[str] = mapped_column(ForeignKey("gateways.gateway_id"), index=True, nullable=False)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # opaque
    local_alias: Mapped[str | None] = mapped_column(String(64), nullable=True)  # gateway-local mapping key
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    member_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    connection_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    upload_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    download_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_upload_rate_mbps: Mapped[float | None] = mapped_column(nullable=True)
    current_download_rate_mbps: Mapped[float | None] = mapped_column(nullable=True)
    current_qoe: Mapped[float | None] = mapped_column(nullable=True)
    traffic_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    classification_confidence: Mapped[float | None] = mapped_column(nullable=True)
    associated_policy: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = CreatedAt
    updated_at: Mapped[datetime] = UpdatedAt

    gateway = relationship("Gateway", back_populates="devices", foreign_keys=[gateway_id])
    household = relationship("Household", back_populates="devices", foreign_keys=[household_id])
