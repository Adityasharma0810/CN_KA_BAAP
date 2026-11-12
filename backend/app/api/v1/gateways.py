"""Gateway registration, pairing, and heartbeat routes."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.v1.deps import get_current_user, get_session
from backend.app.core.settings import settings
from backend.app.database import AsyncSessionLocal
from backend.app.models.gateway import Gateway, PairingCode
from backend.app.models.user import HouseholdMember
from backend.app.schemas.gateway import (
    GatewayHeartbeat,
    GatewayOut,
    GatewayPair,
    GatewayRegister,
    GatewayStatusOut,
    PairingCodeOut,
)
from backend.app.services.gateway_service import (
    GatewayError,
    create_pairing_code,
    get_gateway,
    heartbeat,
    pair_gateway,
    register_gateway,
)
from sqlalchemy import select

router = APIRouter()


def _gateway_out(gateway: Gateway) -> dict:
    import json
    from datetime import datetime

    capabilities = gateway.capabilities
    if isinstance(capabilities, str):
        try:
            capabilities = json.loads(capabilities)
        except (ValueError, TypeError):
            capabilities = None

    created_at = gateway.created_at
    if not isinstance(created_at, datetime):
        created_at = None

    return {
        "id": str(gateway.id),
        "gateway_id": gateway.gateway_id,
        "name": gateway.name,
        "platform": gateway.platform,
        "version": gateway.version,
        "status": gateway.status,
        "last_heartbeat": gateway.last_heartbeat,
        "last_observation_at": gateway.last_observation_at,
        "connected_at": gateway.connected_at,
        "capabilities": capabilities,
        "created_at": created_at,
    }


@router.post("/gateways/register", response_model=GatewayOut, status_code=201)
async def register(data: GatewayRegister, user = Depends(get_current_user), session = Depends(get_session)):
    from backend.app.models.user import Household
    membership = await session.scalar(select(HouseholdMember).where(HouseholdMember.user_id == user.id))
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_household")
    try:
        gateway = await register_gateway(session, membership.household_id, data)
    except GatewayError as error:
        message = str(error)
        if message == "gateway_id_already_registered":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="gateway_id_already_registered")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="registration_failed")
    return _gateway_out(gateway)


@router.post("/gateways/pairing-code", response_model=PairingCodeOut)
async def pairing_code(user = Depends(get_current_user), session = Depends(get_session), ttl_minutes: int | None = None):
    from backend.app.models.user import HouseholdMember
    membership = await session.scalar(select(HouseholdMember).where(HouseholdMember.user_id == user.id))
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_household")
    pairing = await create_pairing_code(session, membership.household_id, ttl_minutes)
    return pairing


@router.post("/gateways/pair", response_model=GatewayOut)
async def pair(data: GatewayPair, user = Depends(get_current_user), session = Depends(get_session)):
    from backend.app.models.user import HouseholdMember
    membership = await session.scalar(select(HouseholdMember).where(HouseholdMember.user_id == user.id))
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_household")
    try:
        gateway = await pair_gateway(session, data)
    except GatewayError as error:
        message = str(error)
        if message == "invalid_pairing_code":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_pairing_code")
        if message == "pairing_code_already_used":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="pairing_code_already_used")
        if message == "pairing_code_expired":
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="pairing_code_expired")
        if message == "pairing_code_household_mismatch":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="pairing_code_household_mismatch")
        if message == "pairing_code_awaiting_gateway":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="pairing_code_awaiting_gateway")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="pairing_failed")
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="pairing_failed")
    return _gateway_out(gateway)


@router.post("/gateways/{gateway_id}/heartbeat", response_model=GatewayStatusOut)
async def gateway_heartbeat(gateway_id: str, data: GatewayHeartbeat, session = Depends(get_session)):
    try:
        gateway = await heartbeat(session, gateway_id, data)
    except GatewayError as error:
        if str(error) == "unknown_gateway":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_gateway")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="heartbeat_failed")
    return GatewayStatusOut(
        gateway_id=gateway.gateway_id,
        status=gateway.status,
        last_heartbeat=gateway.last_heartbeat,
        connected=gateway.status == "connected",
        version=gateway.version,
        capabilities=gateway.capabilities and __import__("json").loads(gateway.capabilities),
    )


@router.get("/gateways/{gateway_id}/status", response_model=GatewayStatusOut)
async def gateway_status(gateway_id: str, user = Depends(get_current_user), session = Depends(get_session)):
    gateway = await get_gateway(session, gateway_id)
    if not gateway:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_gateway")
    return GatewayStatusOut(
        gateway_id=gateway.gateway_id,
        status=gateway.status,
        last_heartbeat=gateway.last_heartbeat,
        connected=(gateway.status == "connected" and gateway.last_heartbeat is not None
                   and (datetime.now(timezone.utc) - gateway.last_heartbeat).total_seconds() < settings.agent_heartbeat_timeout_seconds),
        version=gateway.version,
        capabilities=gateway.capabilities and __import__("json").loads(gateway.capabilities),
    )
