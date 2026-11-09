"""Product-facing anonymous client observation routes."""

import logging

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import TypeAdapter

from backend.app.models.client_responses import (
    AnonymousClientDetailResponse,
    AnonymousClientResponse,
    AnonymousClientsResponse,
)
from backend.app.models.api_responses import HistoricalObservationsResponse
from backend.app.models.schemas import (
    ClientId,
    ObservationEnvironment,
    ObservationSource,
)

from backend.app.services.lab_accounting_service import lab_accounting_service
from backend.app.services.observation_query_service import (
    InvalidFilterError,
    ObservationQueryError,
    UnknownClientError,
    build_historical_observations,
)

router = APIRouter(prefix="/api/v1/clients", tags=["Clients"])
_CLIENT_ID = TypeAdapter(ClientId)
_LOGGER = logging.getLogger(__name__)


def _observations_by_client(result: dict) -> dict[str, object]:
    if not result.get("available"):
        return {}
    return {
        item["client_id"]: item.get("observation")
        for item in result.get("clients", [])
        if isinstance(item, dict) and item.get("client_id") and item.get("observation")
    }


def _client_response(client, observation, *, available: bool):
    return AnonymousClientResponse(
        client_id=client.client_id,
        display_label=client.display_label,
        status=client.status,
        environment="simulated_lab",
        first_seen_at=client.first_seen_at,
        last_seen_at=client.last_seen_at,
        stale=client.stale,
        latest_observation=observation,
    )


def _collect_safe():
    try:
        return lab_accounting_service.collect()
    except Exception:
        # Keep the HTTP contract safe while retaining a diagnostic in server logs.
        _LOGGER.warning("anonymous client telemetry unavailable", exc_info=True)
        return {
            "available": False,
            "clients": [],
            "message": "Linux namespace lab telemetry is unavailable.",
        }


@router.get("", response_model=AnonymousClientsResponse)
def list_clients() -> AnonymousClientsResponse:
    """List registered anonymous clients without private identity metadata."""

    result = _collect_safe()
    available = bool(result.get("available"))
    observations = _observations_by_client(result)
    clients = [
        _client_response(client, observations.get(client.client_id), available=available)
        for client in lab_accounting_service.registry.list_clients()
    ]
    return AnonymousClientsResponse(
        count=len(clients),
        available=available,
        clients=clients,
        source="linux_namespace_lab",
        environment="simulated_lab",
        message=None if available else "Linux namespace lab telemetry is unavailable.",
    )


@router.get("/{client_id}", response_model=AnonymousClientDetailResponse)
def get_client(
    client_id: str = Path(
        min_length=14,
        max_length=40,
        pattern=r"^client-[a-z0-9]{8,32}$",
    ),
) -> AnonymousClientDetailResponse:
    """Return exactly one anonymous client and its genuine latest observation."""

    try:
        _CLIENT_ID.validate_python(client_id)
        client = lab_accounting_service.registry.get(client_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="invalid_client_id") from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail="unknown_client") from error

    result = _collect_safe()
    available = bool(result.get("available"))
    observation = _observations_by_client(result).get(client_id)
    response = _client_response(client, observation, available=available)
    return AnonymousClientDetailResponse(
        **response.model_dump(),
        available=available,
        source="linux_namespace_lab",
        message=None if available else "Linux namespace lab telemetry is unavailable.",
    )


@router.get("/{client_id}/history", response_model=HistoricalObservationsResponse)
def client_history(
    client_id: str = Path(
        min_length=14,
        max_length=40,
        pattern=r"^client-[a-z0-9]{8,32}$",
    ),
    start: Annotated[str | None, Query()] = None,
    end: Annotated[str | None, Query()] = None,
    source: Annotated[ObservationSource | None, Query()] = None,
    environment: Annotated[ObservationEnvironment | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    order: Annotated[str, Query(pattern=r"^(oldest|newest)$")] = "newest",
) -> HistoricalObservationsResponse:
    try:
        return build_historical_observations(
            source=source,
            environment=environment,
            client_id=client_id,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
            order=order,
            client_history=True,
        )
    except UnknownClientError as error:
        raise HTTPException(status_code=404, detail="unknown_client") from error
    except InvalidFilterError as error:
        raise HTTPException(status_code=422, detail=error.code) from error
    except ObservationQueryError as error:
        raise HTTPException(status_code=503, detail="database_unavailable") from error
