"""Product-facing stored-evidence gateway status and topology routes."""

from fastapi import APIRouter, HTTPException

from backend.app.models.topology_schemas import (
    GatewayStatusResponse,
    TopologyResponse,
)
from backend.app.services.topology_service import (
    TopologyServiceError,
    topology_service,
)


router = APIRouter(prefix="/api/v1", tags=["Topology"])


@router.get(
    "/gateway/status",
    response_model=GatewayStatusResponse,
    summary="Gateway and collector status",
)
def gateway_status() -> GatewayStatusResponse:
    return topology_service.gateway_status()


@router.get(
    "/network/topology",
    response_model=TopologyResponse,
    summary="Evidence-based network topology",
)
def network_topology() -> TopologyResponse:
    try:
        return topology_service.network_topology()
    except TopologyServiceError as error:
        raise HTTPException(
            status_code=503,
            detail="topology_unavailable",
        ) from error
