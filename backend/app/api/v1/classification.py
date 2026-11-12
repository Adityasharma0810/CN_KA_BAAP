"""Traffic classification routes."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.v1.deps import get_current_user, get_session
from backend.app.ml.classifier import FlowClassifier, TRAFFIC_CLASSES, FEATURE_SCHEMA_VERSION, FEATURE_NAMES, UNKNOWN_THRESHOLD
from backend.app.models.gateway import Gateway
from backend.app.schemas.classification import ClassificationPredictionOut, ClassificationCorrection
from sqlalchemy import select

router = APIRouter()

_CLASSIFIERS: dict[str, FlowClassifier] = {}


def _classifier(gateway_id: str) -> FlowClassifier:
    clf = _CLASSIFIERS.get(gateway_id)
    if clf is None:
        clf = FlowClassifier(version=FEATURE_SCHEMA_VERSION)
        _CLASSIFIERS[gateway_id] = clf
    return clf


@router.get("/gateways/{gateway_id}/classifier/schema")
async def classifier_schema(gateway_id: str, user = Depends(get_current_user)):
    return {
        "gateway_id": gateway_id,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "features": list(FEATURE_NAMES),
        "classes": list(TRAFFIC_CLASSES),
        "unknown_threshold": UNKNOWN_THRESHOLD,
        "trained": _CLASSIFIERS.get(gateway_id, FlowClassifier()).trained,
    }


@router.post("/gateways/{gateway_id}/classify", response_model=ClassificationPredictionOut)
async def classify(
    gateway_id: str,
    packets: list[dict],
    user = Depends(get_current_user),
    session = Depends(get_session),
):
    gateway = await session.scalar(select(Gateway).where(Gateway.gateway_id == gateway_id))
    if not gateway:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_gateway")
    clf = _classifier(gateway_id)
    result = clf.predict(packets)
    return ClassificationPredictionOut(
        client_id="aggregate",
        traffic_class=result["traffic_class"],
        confidence=result["confidence"],
        features=result["features"],
        predicted_at=datetime.now(timezone.utc),
        source="ml",
    )
