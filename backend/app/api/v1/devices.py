"""Device inventory routes."""

from fastapi import APIRouter, Depends, HTTPException, status, Query

from backend.app.api.v1.deps import get_current_user, get_session
from backend.app.models.device import Device
from backend.app.models.gateway import Gateway
from backend.app.models.user import HouseholdMember
from backend.app.schemas.device import DeviceCreate, DeviceOut, DeviceListOut, DeviceUpdate
from backend.app.services.device_service import list_devices, get_device, upsert_device
from sqlalchemy import select

router = APIRouter()


@router.get("/devices", response_model=DeviceListOut)
async def list_all_devices(user = Depends(get_current_user), session = Depends(get_session)):
    from backend.app.models.user import HouseholdMember
    membership = await session.scalar(
        select(HouseholdMember).where(HouseholdMember.user_id == user.id)
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_household")
    devices = await list_devices(session, household_id=membership.household_id)
    return DeviceListOut(count=len(devices), devices=[DeviceOut.model_validate(d) for d in devices])


@router.get("/gateways/{gateway_id}/devices", response_model=DeviceListOut)
async def gateway_devices(gateway_id: str, user = Depends(get_current_user), session = Depends(get_session)):
    gateway = await session.scalar(select(Gateway).where(Gateway.gateway_id == gateway_id))
    if not gateway:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_gateway")
    devices = await list_devices(session, gateway_id=gateway_id)
    return DeviceListOut(count=len(devices), devices=[DeviceOut.model_validate(d) for d in devices])


@router.get("/devices/{device_id}", response_model=DeviceOut)
async def device_detail(device_id: str, user = Depends(get_current_user), session = Depends(get_session)):
    device = await get_device(session, device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_device")
    return DeviceOut.model_validate(device)


@router.patch("/devices/{device_id}", response_model=DeviceOut)
async def device_update(device_id: str, data: DeviceUpdate, user = Depends(get_current_user), session = Depends(get_session)):
    device = await get_device(session, device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_device")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(device, field, value)
    await session.commit()
    await session.refresh(device)
    return DeviceOut.model_validate(device)


@router.post("/gateways/{gateway_id}/devices", response_model=DeviceOut, status_code=201)
async def device_upsert(gateway_id: str, data: DeviceCreate, user = Depends(get_current_user), session = Depends(get_session)):
    gateway = await session.scalar(select(Gateway).where(Gateway.gateway_id == gateway_id))
    if not gateway:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_gateway")
    device = await upsert_device(
        session,
        gateway_id=gateway_id,
        household_id=gateway.household_id,
        device_id=data.device_id,
        data={"display_name": data.display_name},
    )
    return DeviceOut.model_validate(device)
