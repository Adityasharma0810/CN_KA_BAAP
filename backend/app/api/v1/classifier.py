"""Traffic-classifier routes for the product-facing API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter

from backend.app.models.classifier_schemas import (
    ClassifierStatus,
    LabelCorrectionRequest,
    LabelCorrectionResponse,
)
from backend.app.services.classifier_service import status, store_correction


router = APIRouter(tags=["Classifier"])


@router.get(
    "/classifier/status",
    response_model=ClassifierStatus,
    summary="Classifier status",
    description=(
        "Report the live traffic-classifier availability, held-out F1 vs the "
        "port/rate-rule baseline, and the last fallback reason. When no trained "
        "model exists the status is unavailable (never invented)."
    ),
)
def classifier_status() -> ClassifierStatus:
    return status()


@router.post(
    "/clients/{client_id}/label-correction",
    response_model=LabelCorrectionResponse,
    summary="Submit a label correction",
    description=(
        "Store a user traffic-class correction for a client. Input is validated "
        "and persisted; corrections are NEVER used for automatic re-training."
    ),
)
def label_correction(
    client_id: Annotated[str, "anonymous client identifier"],
    body: LabelCorrectionRequest,
) -> LabelCorrectionResponse:
    return store_correction(client_id, body.corrected_label, body.note)
