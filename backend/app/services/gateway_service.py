"""Gateway registration, pairing, and heartbeat service."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.settings import settings
from backend.app.models.gateway import Gateway, PairingCode
from backend.app.models.user import Household
from backend.app.schemas.gateway import GatewayRegister, GatewayPair, GatewayHeartbeat


class GatewayError(Exception):
    pass


def _make_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(settings.pairing_code_length))


async def register_gateway(db: AsyncSession, household_id: str, data: GatewayRegister) -> Gateway:
    existing = await db.scalar(
        select(Gateway).where(Gateway.gateway_id == data.gateway_id)
    )
    if existing:
        raise GatewayError("gateway_id_already_registered")

    gateway = Gateway(
        household_id=household_id,
        gateway_id=data.gateway_id,
        name=data.name,
        platform=data.platform,
        version=data.version,
        public_key_fingerprint=data.public_key_fingerprint,
        capabilities=_json(data.capabilities),
        status="unpaired",
        created_at=datetime.now(timezone.utc),
    )
    db.add(gateway)
    await db.commit()
    await db.refresh(gateway)
    return gateway


def _json(value: Any) -> str | None:
    import json

    if value is None:
        return None
    return json.dumps(value)


def _as_aware(value: datetime | None) -> datetime | None:
    """Normalize a datetime read from SQLite (naive) to aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def create_pairing_code(db: AsyncSession, household_id: str, ttl_minutes: int | None = None) -> PairingCode:
    code = _make_code()
    ttl = timedelta(minutes=ttl_minutes or settings.pairing_code_ttl_minutes)
    pairing = PairingCode(
        code=code,
        household_id=household_id,
        expires_at=datetime.now(timezone.utc) + ttl,
    )
    db.add(pairing)
    await db.commit()
    await db.refresh(pairing)
    return pairing


async def pair_gateway(db: AsyncSession, data: GatewayPair) -> Gateway:
    now = datetime.now(timezone.utc)
    pairing = await db.scalar(select(PairingCode).where(PairingCode.code == data.code))
    if not pairing:
        raise GatewayError("invalid_pairing_code")
    if pairing.used_at is not None:
        raise GatewayError("pairing_code_already_used")
    if _as_aware(pairing.expires_at) < now:
        raise GatewayError("pairing_code_expired")

    gateway = await db.scalar(select(Gateway).where(Gateway.gateway_id == data.gateway_id))
    if gateway is None:
        raise GatewayError("unknown_gateway")

    household_id = pairing.household_id
    if gateway.household_id != household_id:
        raise GatewayError("pairing_code_household_mismatch")

    pairing.gateway_id = data.gateway_id
    pairing.used_at = now
    gateway.status = "paired"
    gateway.connected_at = now
    await db.commit()
    await db.refresh(gateway)
    return gateway


async def heartbeat(db: AsyncSession, gateway_id: str, data: GatewayHeartbeat) -> Gateway:
    gateway = await db.scalar(select(Gateway).where(Gateway.gateway_id == gateway_id))
    if not gateway:
        raise GatewayError("unknown_gateway")
    now = datetime.now(timezone.utc)
    gateway.last_heartbeat = now
    gateway.status = "connected"
    gateway.connected_at = gateway.connected_at or now
    if data.version:
        gateway.version = data.version
    if data.platform:
        gateway.platform = data.platform
    if data.capabilities is not None:
        gateway.capabilities = _json(data.capabilities)
    if data.buffered_observations is not None:
        gateway.offline_buffered = data.buffered_observations
    await db.commit()
    await db.refresh(gateway)
    return gateway


async def get_gateway(db: AsyncSession, gateway_id: str) -> Gateway | None:
    return await db.scalar(select(Gateway).where(Gateway.gateway_id == gateway_id))
