"""Current-observation routes for the product-facing API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from backend.app.models.api_responses import (
    CurrentObservationsResponse,
    HistoricalObservationsResponse,
)
from backend.app.models.schemas import (
    ClientId,
    ObservationEnvironment,
    ObservationScope,
    ObservationSource,
)
from backend.app.services.observation_query_service import (
    InvalidFilterError,
    ObservationQueryError,
    UnknownClientError,
    build_current_observations,
    build_historical_observations,
)


router = APIRouter(tags=["Observations"])


@router.get(
    "/observations/current",
    response_model=CurrentObservationsResponse,
    summary="Current observations",
    description=(
        "Return the newest aggregate observation per source, or the newest "
        "observation per anonymous client. Aggregate and per-client results "
        "are never mixed. Missing values remain null and old observations are "
        "marked stale."
    ),
)
def current_observations(
    source: Annotated[ObservationSource | None, Query()] = None,
    scope: Annotated[ObservationScope | None, Query()] = None,
    environment: Annotated[ObservationEnvironment | None, Query()] = None,
    client_id: Annotated[ClientId | None, Query()] = None,
) -> CurrentObservationsResponse:
    try:
        return build_current_observations(
            source=source,
            scope=scope,
            environment=environment,
            client_id=client_id,
        )
    except UnknownClientError as error:
        raise HTTPException(status_code=404, detail="unknown_client") from error
    except InvalidFilterError as error:
        raise HTTPException(status_code=422, detail="invalid_filter") from error
    except ObservationQueryError as error:
        raise HTTPException(
            status_code=503,
            detail="database_unavailable",
        ) from error


@router.get(
    "/observations/history",
    response_model=HistoricalObservationsResponse,
    summary="Historical observations",
)
def historical_observations(
    start: Annotated[str | None, Query()] = None,
    end: Annotated[str | None, Query()] = None,
    source: Annotated[ObservationSource | None, Query()] = None,
    scope: Annotated[ObservationScope | None, Query()] = None,
    environment: Annotated[ObservationEnvironment | None, Query()] = None,
    client_id: Annotated[ClientId | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    order: Annotated[str, Query(pattern=r"^(oldest|newest)$")] = "newest",
) -> HistoricalObservationsResponse:
    try:
        return build_historical_observations(
            start=start,
            end=end,
            source=source,
            scope=scope,
            environment=environment,
            client_id=client_id,
            limit=limit,
            offset=offset,
            order=order,
        )
    except InvalidFilterError as error:
        raise HTTPException(status_code=422, detail=error.code) from error
    except UnknownClientError as error:
        raise HTTPException(status_code=404, detail="unknown_client") from error
    except ObservationQueryError as error:
        raise HTTPException(status_code=503, detail="database_unavailable") from error
