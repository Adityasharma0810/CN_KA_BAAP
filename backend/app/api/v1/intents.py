"""Intent lifecycle routes."""

from fastapi import APIRouter, Depends, HTTPException, status, Query

from backend.app.api.v1.deps import get_current_user, get_session
from backend.app.models.gateway import Gateway
from backend.app.models.intent import Intent
from backend.app.models.user import HouseholdMember
from backend.app.schemas.intents import IntentCreate, IntentOut, IntentUpdate
from backend.app.services.intent_service import cancel_intent, create_intent, list_intents, update_intent
from sqlalchemy import select

router = APIRouter()


@router.get("/gateways/{gateway_id}/intents", response_model=list[IntentOut])
async def list_gateway_intents(gateway_id: str, user = Depends(get_current_user), session = Depends(get_session)):
    gateway = await session.scalar(select(Gateway).where(Gateway.gateway_id == gateway_id))
    if not gateway:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_gateway")
    intents = await list_intents(session, gateway_id)
    return [IntentOut.model_validate(i) for i in intents]


@router.post("/gateways/{gateway_id}/intents", response_model=IntentOut, status_code=201)
async def create_gateway_intent(gateway_id: str, data: IntentCreate, user = Depends(get_current_user), session = Depends(get_session)):
    gateway = await session.scalar(select(Gateway).where(Gateway.gateway_id == gateway_id))
    if not gateway:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_gateway")
    try:
        intent = await create_intent(session, gateway_id, gateway.household_id, data)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    return IntentOut.model_validate(intent)


@router.patch("/intents/{intent_id}", response_model=IntentOut)
async def update_gateway_intent(intent_id: str, data: IntentUpdate, user = Depends(get_current_user), session = Depends(get_session)):
    intent = await update_intent(session, intent_id, data)
    if not intent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_intent")
    return IntentOut.model_validate(intent)


@router.post("/intents/{intent_id}/cancel")
async def cancel_gateway_intent(intent_id: str, user = Depends(get_current_user), session = Depends(get_session)):
    ok = await cancel_intent(session, intent_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_intent")
    return {"status": "cancelled"}
