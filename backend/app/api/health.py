"""Versioned, privacy-safe application health routes."""

from pathlib import Path

import psutil
from fastapi import APIRouter

from backend.app.models.api_schemas import CollectorHealthResponse, HealthResponse
from backend.app.services.health_service import build_collector_health, build_health
from backend.app.services.lab_accounting_service import lab_accounting_service
from network.telemetry.metrics_store import DEFAULT_DB_PATH

router = APIRouter(prefix="/api/v1/health", tags=["Health"])


def database_available() -> bool:
    """Check that the configured database parent is accessible without querying data."""

    path = Path(DEFAULT_DB_PATH)
    return path.parent.exists() and path.parent.is_dir()


def windows_collector_available() -> bool:
    return bool(psutil.net_if_stats())


def linux_gateway_available() -> bool:
    return bool(lab_accounting_service.collect().get("available"))


def registry_available() -> bool:
    return isinstance(lab_accounting_service.registry.public_snapshot(), list)


@router.get("", response_model=HealthResponse)
def application_health() -> HealthResponse:
    return build_health(
        database_check=database_available,
        windows_collector_check=windows_collector_available,
        gateway_check=linux_gateway_available,
        registry_check=registry_available,
    )


@router.get("/collectors", response_model=CollectorHealthResponse)
def collector_health() -> CollectorHealthResponse:
    return build_collector_health(
        windows_collector_check=windows_collector_available,
        gateway_check=linux_gateway_available,
    )
