"""Per-client QoE proxy score endpoints."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from backend.app.models.qoe_schemas import QoECurrentResponse, QoEHistoryResponse
from backend.app.models.schemas import ClientId
from backend.app.services.observation_query_service import (
    InvalidFilterError,
    ObservationQueryError,
    UnknownClientError,
)
from backend.app.services.qoe_service import build_current_qoe, build_qoe_history


router = APIRouter(tags=["QoE"])


@router.get("/qoe/current", response_model=QoECurrentResponse)
def current_qoe() -> QoECurrentResponse:
    try:
        return build_current_qoe()
    except ObservationQueryError as error:
        raise HTTPException(status_code=503, detail=error.code) from error


@router.get("/qoe/history", response_model=QoEHistoryResponse)
def qoe_history(
    client_id: Annotated[ClientId | None, Query()] = None,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> QoEHistoryResponse:
    try:
        return build_qoe_history(
            client_id=client_id,
            start=start,
            end=end,
            limit=limit,
        )
    except UnknownClientError as error:
        raise HTTPException(status_code=404, detail="unknown_client") from error
    except InvalidFilterError as error:
        raise HTTPException(status_code=422, detail=error.code) from error
    except ObservationQueryError as error:
        raise HTTPException(status_code=503, detail=error.code) from error


@router.get("/qoe/formulas")
def qoe_formulas():
    from backend.app.ml.qoe import SCORE_FORMULAS

    return {"formulas": SCORE_FORMULAS, "note": "Operational QoE proxies, not standardized MOS."}
