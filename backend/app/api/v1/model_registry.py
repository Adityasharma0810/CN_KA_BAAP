"""Model registry routes."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from backend.app.api.v1.deps import get_current_user, get_session
from backend.app.models.model_registry import ModelRegistry
from backend.app.schemas.model_registry import ModelRegistryOut

router = APIRouter()


@router.get("/models", response_model=list[ModelRegistryOut])
async def list_models(
    active_only: bool = Query(False),
    user = Depends(get_current_user),
    session = Depends(get_session),
):
    stmt = select(ModelRegistry)
    if active_only:
        stmt = stmt.where(ModelRegistry.is_active == True)  # noqa: E712
    stmt = stmt.order_by(ModelRegistry.name, ModelRegistry.version)
    result = await session.execute(stmt)
    return [ModelRegistryOut.model_validate(m) for m in result.scalars().all()]


@router.post("/models", response_model=ModelRegistryOut, status_code=201)
async def register_model(
    name: str,
    version: str,
    model_type: str,
    training_dataset_provenance: Optional[str] = None,
    is_active: bool = False,
    user = Depends(get_current_user),
    session = Depends(get_session),
):
    model = ModelRegistry(
        name=name,
        version=version,
        model_type=model_type,
        training_dataset_provenance=training_dataset_provenance,
        is_active=is_active,
        model_health="unknown",
    )
    session.add(model)
    await session.commit()
    await session.refresh(model)
    return ModelRegistryOut.model_validate(model)
