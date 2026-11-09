"""Health and application-status routes for the product-facing API."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.models.api_responses import (
    CollectorsResponse,
    HealthResponse,
)
from backend.app.services.health_service import (
    build_collectors_health,
    build_health as build_observation_health,
)


router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Overall observation API health",
    description=(
        "Report application, database, collector, gateway, and anonymous "
        "client registry health using safe status codes. Missing or "
        "unreachable components are reported explicitly and never as zero."
    ),
)
def health() -> HealthResponse:
    return build_observation_health()


@router.get(
    "/health/collectors",
    response_model=CollectorsResponse,
    summary="Collector health",
    description=(
        "Report each measurement collector's status, last successful "
        "measurement time, staleness, and safe error code."
    ),
)
def collectors() -> CollectorsResponse:
    return build_collectors_health()
