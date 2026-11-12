"""Intent lifecycle service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.intent import Intent
from backend.app.schemas.intents import IntentCreate, IntentUpdate


class IntentError(Exception):
    pass


async def create_intent(db: AsyncSession, gateway_id: str, household_id: str, data: IntentCreate) -> Intent:
    now = datetime.now(timezone.utc)
    expires_at = now
    if data.duration_minutes:
        expires_at = now + timedelta(minutes=data.duration_minutes)
    elif data.deadline:
        expires_at = data.deadline

    intent = Intent(
        gateway_id=gateway_id,
        household_id=household_id,
        device_id=data.device_id,
        traffic_class=data.traffic_class,
        objective=data.objective,
        priority=data.priority,
        urgency=data.urgency,
        deadline=data.deadline,
        duration_minutes=data.duration_minutes,
        min_service_floor_mbps=data.min_service_floor_mbps,
        allowed_trade_offs=_json(data.allowed_trade_offs),
        approval_state="pending",
        expires_at=expires_at,
    )
    db.add(intent)
    await db.commit()
    await db.refresh(intent)
    return intent


def _json(value: Any) -> str | None:
    import json

    if value is None:
        return None
    return json.dumps(value)


async def list_intents(db: AsyncSession, gateway_id: str) -> list[Intent]:
    stmt = select(Intent).where(Intent.gateway_id == gateway_id).order_by(Intent.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_intent(db: AsyncSession, intent_id: str, data: IntentUpdate) -> Intent | None:
    intent = await db.scalar(select(Intent).where(Intent.id == intent_id))
    if not intent:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "allowed_trade_offs":
            value = _json(value)
        setattr(intent, field, value)
    intent.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(intent)
    return intent


async def cancel_intent(db: AsyncSession, intent_id: str) -> bool:
    intent = await db.scalar(select(Intent).where(Intent.id == intent_id))
    if not intent:
        return False
    intent.approval_state = "cancelled"
    intent.expires_at = datetime.now(timezone.utc)
    await db.commit()
    return True
