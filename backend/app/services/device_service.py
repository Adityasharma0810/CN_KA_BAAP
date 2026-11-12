"""Device inventory service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.device import Device
from backend.app.schemas.device import DeviceCreate, DeviceUpdate


class DeviceError(Exception):
    pass


async def list_devices(db: AsyncSession, gateway_id: str | None = None, household_id: str | None = None) -> list[Device]:
    stmt = select(Device)
    if gateway_id:
        stmt = stmt.where(Device.gateway_id == gateway_id)
    if household_id:
        stmt = stmt.where(Device.household_id == household_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_device(db: AsyncSession, device_id: str) -> Device | None:
    return await db.scalar(select(Device).where(Device.device_id == device_id))


async def upsert_device(
    db: AsyncSession,
    *,
    gateway_id: str,
    household_id: str,
    device_id: str,
    data: dict[str, Any],
) -> Device:
    device = await get_device(db, device_id)
    now = datetime.now(timezone.utc)
    if device is None:
        device = Device(
            gateway_id=gateway_id,
            household_id=household_id,
            device_id=device_id,
            first_seen_at=now,
        )
        db.add(device)
    device.last_seen_at = now
    for field in (
        "display_name",
        "member_id",
        "category",
        "connection_status",
        "upload_bytes",
        "download_bytes",
        "current_upload_rate_mbps",
        "current_download_rate_mbps",
        "current_qoe",
        "traffic_class",
        "classification_confidence",
        "associated_policy",
    ):
        if field in data:
            setattr(device, field, data[field])
    await db.commit()
    await db.refresh(device)
    return device
