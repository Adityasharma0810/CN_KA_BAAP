
"""Experience Budget monitoring API."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.services.monitoring_service import (
    collect_and_store,
    get_history,
)


router = APIRouter(
    prefix="/api/v1/monitoring",
    tags=["Monitoring"],
)


class CollectionRequest(BaseModel):
    adapter: str = Field(
        default="Wi-Fi",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9 _.-]+$",
    )

    sample_interval_seconds: float = Field(
        default=1.0,
        gt=0,
        le=5,
    )

    quality_target: Literal["1.1.1.1", "8.8.8.8"] = "1.1.1.1"

    quality_count: int = Field(
        default=5,
        ge=1,
        le=10,
    )


@router.post("/collect")
def collect_metrics(request: CollectionRequest):
    """Collect and persist one aggregate monitoring sample."""

    try:
        return collect_and_store(
            adapter=request.adapter,
            sample_interval=request.sample_interval_seconds,
            quality_target=request.quality_target,
            quality_count=request.quality_count,
        )

    except (ValueError, RuntimeError, OSError) as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error


@router.get("/history")
def monitoring_history(
    limit: int = Query(default=100, ge=1, le=500),
):
    """Return recent aggregate measurements."""

    try:
        samples = get_history(limit)

        return {
            "count": len(samples),
            "samples": samples,
            "scope": "aggregate_only",
        }

    except (ValueError, RuntimeError, OSError) as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error
