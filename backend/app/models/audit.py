"""Audit log models for enforcement and access events."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, CreatedAt, GUID


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[GUID]
    gateway_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = CreatedAt
