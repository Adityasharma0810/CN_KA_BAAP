"""Gateway registration and pairing models."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, CreatedAt, GUID, UpdatedAt


class Gateway(Base):
    __tablename__ = "gateways"

    id: Mapped[GUID]
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True, nullable=False)
    gateway_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    public_key_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(32), nullable=True)
    capabilities: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    status: Mapped[str] = mapped_column(String(32), default="unpaired", nullable=False)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_observation_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    offline_buffered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = CreatedAt
    updated_at: Mapped[datetime] = UpdatedAt

    household = relationship("Household", back_populates="gateways")
    devices: Mapped[list["Device"]] = relationship(
        "Device", back_populates="gateway", cascade="all, delete-orphan"
    )
    intents: Mapped[list["Intent"]] = relationship(
        "Intent", back_populates="gateway", cascade="all, delete-orphan"
    )
    decisions: Mapped[list["Decision"]] = relationship(
        "Decision", back_populates="gateway", cascade="all, delete-orphan"
    )


class PairingCode(Base):
    __tablename__ = "pairing_codes"

    id: Mapped[GUID]
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    gateway_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = CreatedAt
