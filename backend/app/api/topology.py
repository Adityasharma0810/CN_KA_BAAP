"""Product-facing gateway status and topology routes."""

from datetime import datetime, timezone

from fastapi import APIRouter

from backend.app.models.api_schemas import HealthState
from backend.app.models.topology_schemas import (
    GatewayStatusResponse,
    TopologyLink,
    TopologyNode,
    TopologyResponse,
)
from backend.app.services.lab_accounting_service import lab_accounting_service

router = APIRouter(prefix="/api/v1", tags=["Topology"])


def _lab_result() -> dict:
    return lab_accounting_service.collect()


@router.get("/gateway/status", response_model=GatewayStatusResponse)
def gateway_status() -> GatewayStatusResponse:
    now = datetime.now(timezone.utc)
    result = _lab_result()
    clients = result.get("clients", [])
    available = bool(result.get("available"))
    return GatewayStatusResponse(
        status=HealthState.HEALTHY if available else HealthState.UNAVAILABLE,
        source="linux_namespace_lab",
        environment="simulated_lab",
        observed_at=now,
        client_count=len(clients),
        message=None if available else "Linux namespace lab is unavailable.",
    )


@router.get("/network/topology", response_model=TopologyResponse)
def network_topology() -> TopologyResponse:
    now = datetime.now(timezone.utc)
    result = _lab_result()
    available = bool(result.get("available"))
    client_items = result.get("clients", [])
    nodes = [
        TopologyNode(
            node_id="host",
            kind="host",
            label="Experience Budget host",
            status="online",
            source="windows_host",
            environment="physical_host",
            observed_at=now,
        )
    ]
    links: list[TopologyLink] = []

    if available:
        nodes.append(
            TopologyNode(
                node_id="linux-gateway",
                kind="gateway",
                label="Simulated Linux gateway",
                status="measured",
                source="linux_gateway",
                environment="simulated_lab",
                observed_at=now,
            )
        )
        links.append(TopologyLink(source="host", target="linux-gateway", relation="observes"))
        for index, item in enumerate(client_items, start=1):
            observation = item.get("observation", {})
            metadata = observation.get("metadata", {})
            client_id = item.get("client_id")
            node_id = f"client-{index:02d}"
            nodes.append(
                TopologyNode(
                    node_id=node_id,
                    kind="client",
                    label=f"Client {index:02d}",
                    status="measured" if metadata.get("quality") != "unavailable" else "unavailable",
                    source="linux_namespace_lab",
                    environment="simulated_lab",
                    client_id=client_id,
                    observed_at=metadata.get("observed_at"),
                )
            )
            links.append(TopologyLink(source="linux-gateway", target=node_id, relation="per_client_observation"))
    else:
        nodes.append(
            TopologyNode(
                node_id="hotspot-aggregate",
                kind="aggregate",
                label="Physical hotspot aggregate",
                status="unavailable",
                source="windows_hotspot",
                environment="physical_host",
                observed_at=None,
            )
        )
        links.append(TopologyLink(source="host", target="hotspot-aggregate", relation="aggregate_only"))

    return TopologyResponse(
        observed_at=now,
        nodes=nodes,
        links=links,
        physical_hotspot_aggregate=not available,
    )
