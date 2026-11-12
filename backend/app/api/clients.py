"""Product-facing anonymous client observation routes.

Clients come from the real configured sources only:

* the Linux namespace lab (per-client traffic measurements), and
* Linux hotspot presence detection (devices seen on an AP-mode interface).

No demo or placeholder clients are ever returned; an empty registry with no
available source is reported honestly.
"""

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

from backend.app.services.hotspot_client_service import hotspot_client_service
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

_LAB_ENVIRONMENT = ObservationEnvironment.SIMULATED_LAB
_HOST_ENVIRONMENT = ObservationEnvironment.PHYSICAL_HOST


def _observations_by_client(result: dict) -> dict[str, object]:
    if not result.get("available"):
        return {}
    return {
        item["client_id"]: item.get("observation")
        for item in result.get("clients", [])
        if isinstance(item, dict) and item.get("client_id") and item.get("observation")
    }


def _client_response(
    client,
    observation,
    *,
    environment: ObservationEnvironment,
):
    return AnonymousClientResponse(
        client_id=client.client_id,
        display_label=client.display_label,
        status=client.status,
        environment=environment,
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


def _hotspot_safe():
    try:
        return hotspot_client_service.collect()
    except Exception:
        _LOGGER.warning("hotspot client telemetry unavailable", exc_info=True)
        return {
            "available": False,
            "clients": [],
            "message": "Hotspot client detection is unavailable.",
        }


def _combined_sources() -> tuple[dict, dict]:
    """Return the lab and hotspot collection results."""

    return _collect_safe(), _hotspot_safe()


def _envelope(lab: dict, hotspot: dict) -> tuple[ObservationSource, ObservationEnvironment, str | None]:
    """Pick the top-level source, environment, and honest combined message."""

    hotspot_available = bool(hotspot.get("available"))
    lab_available = bool(lab.get("available"))

    if hotspot_available:
        source = ObservationSource.LINUX_HOTSPOT
        environment = _HOST_ENVIRONMENT
    else:
        source = ObservationSource.LINUX_NAMESPACE_LAB
        environment = _LAB_ENVIRONMENT

    if lab_available or hotspot_available:
        return source, environment, None

    lab_message = lab.get("message") or "Linux namespace lab telemetry is unavailable."
    hotspot_message = hotspot.get("message") or "Hotspot client detection is unavailable."
    combined = f"{lab_message} {hotspot_message}".strip()
    if len(combined) > 160:
        combined = "No client telemetry source is available on this system."
    return source, environment, combined


@router.get("", response_model=AnonymousClientsResponse)
def list_clients() -> AnonymousClientsResponse:
    """List registered anonymous clients without private identity metadata."""

    lab, hotspot = _combined_sources()
    observations = _observations_by_client(lab)
    clients = [
        _client_response(
            client,
            observations.get(client.client_id),
            environment=_LAB_ENVIRONMENT,
        )
        for client in lab_accounting_service.registry.list_clients()
    ]
    # Hotspot presence clients have no per-client traffic observation yet;
    # latest_observation stays None instead of being fabricated.
    clients += [
        _client_response(
            client,
            None,
            environment=_HOST_ENVIRONMENT,
        )
        for client in hotspot_client_service.registry.list_clients()
    ]

    source, environment, message = _envelope(lab, hotspot)
    return AnonymousClientsResponse(
        count=len(clients),
        available=bool(lab.get("available")) or bool(hotspot.get("available")),
        clients=clients,
        source=source,
        environment=environment,
        message=message,
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
    except ValueError as error:
        raise HTTPException(status_code=422, detail="invalid_client_id") from error

    try:
        client = lab_accounting_service.registry.get(client_id)
        environment = _LAB_ENVIRONMENT
    except KeyError:
        try:
            client = hotspot_client_service.registry.get(client_id)
            environment = _HOST_ENVIRONMENT
        except KeyError as error:
            raise HTTPException(status_code=404, detail="unknown_client") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail="invalid_client_id") from error

    lab, hotspot = _combined_sources()
    available = bool(lab.get("available")) or bool(hotspot.get("available"))
    if environment == _LAB_ENVIRONMENT:
        observation = _observations_by_client(lab).get(client_id)
        source = lab.get("source") or ObservationSource.LINUX_NAMESPACE_LAB
        message = None if available else lab.get("message")
    else:
        observation = None
        source = hotspot.get("source") or ObservationSource.LINUX_HOTSPOT
        message = None if available else hotspot.get("message")

    response = _client_response(client, observation, environment=environment)
    return AnonymousClientDetailResponse(
        **response.model_dump(),
        available=available,
        source=source,
        message=message,
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
    """Return only this anonymous client's stored history."""

    try:
        _CLIENT_ID.validate_python(client_id)
        lab_accounting_service.registry.get(client_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="invalid_client_id") from error
    except KeyError:
        try:
            hotspot_client_service.registry.get(client_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="unknown_client") from error

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
