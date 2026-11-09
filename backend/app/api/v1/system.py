"""System capabilities endpoint."""

from backend.app.config import STALE_OBSERVATION_AFTER_SECONDS
from backend.app.models.system_schemas import SystemCapabilitiesResponse
from backend.app.services.lab_ingest_service import lab_ingest_service
from backend.app.services.latency_probe_service import latency_probe_service
from fastapi import APIRouter


router = APIRouter(tags=["System"])


@router.get(
    "/system/capabilities",
    response_model=SystemCapabilitiesResponse,
    summary="Runtime platform and collector capabilities",
)
def system_capabilities() -> SystemCapabilitiesResponse:
    """Report safe runtime capabilities without infrastructure identifiers."""

    return SystemCapabilitiesResponse(
        platform=lab_ingest_service.platform,
        windows_collectors_supported=lab_ingest_service.platform == "windows",
        lab_ingest_enabled=lab_ingest_service.enabled,
        lab_ingest_state=lab_ingest_service.state,
        lab_ingest_interval_seconds=lab_ingest_service.interval_seconds,
        lab_ingest_last_success=lab_ingest_service.last_success_at,
        lab_ingest_last_error_code=lab_ingest_service.last_error_code,
        observation_freshness_threshold_seconds=STALE_OBSERVATION_AFTER_SECONDS,
        latency_probe_enabled=latency_probe_service.enabled,
        latency_probe_state=latency_probe_service.state,
        latency_probe_last_success=latency_probe_service.last_success_at,
        latency_probe_last_error_code=latency_probe_service.last_error_code,
    )
