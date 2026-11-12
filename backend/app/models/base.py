"""Shared SQLAlchemy declarative base and mixins for control-plane models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

utc_now = func.now()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# Common typed columns.
GUID = Annotated[str, mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))]
CreatedAt = Annotated[
    datetime, mapped_column(DateTime(timezone=True), server_default=utc_now, nullable=False)
]
UpdatedAt = Annotated[
    datetime,
    mapped_column(
        DateTime(timezone=True),
        server_default=utc_now,
        onupdate=utc_now,
        nullable=False,
    ),
]
