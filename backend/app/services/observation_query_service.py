"""Current-observation queries for the product-facing API.

The service uses the Module 4 repository methods only. It never embeds SQL and
never converts a missing value into zero. Aggregate and per-client queries are
kept separate so one client's data cannot leak into another response.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from backend.app.config import (
    STALE_OBSERVATION_AFTER_SECONDS,
    database_path,
)
from backend.app.models.api_responses import (
    CurrentObservationsResponse,
    ObservationFilters,
    ObservationItem,
)
from backend.app.models.schemas import (
    ObservationScope,
    ObservationSource,
)
from network.telemetry.metrics_store import (
    MetricsStore,
    StorageError,
)


_DEFAULT_AGGREGATE_SOURCES = (
    ObservationSource.WINDOWS_HOST,
    ObservationSource.WINDOWS_HOTSPOT,
    ObservationSource.LINUX_GATEWAY,
)

_QUERY_ERRORS = (StorageError, sqlite3.Error, OSError, ValueError)


def utc_now() -> datetime:
    """Return the injectable UTC clock used for freshness decisions."""

    return datetime.now(timezone.utc)


class ObservationQueryError(RuntimeError):
    """Base class for safe current-observation failures."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class UnknownClientError(ObservationQueryError):
    """Raised when a well-formed anonymous client ID is not registered."""


class InvalidFilterError(ObservationQueryError):
    """Raised when filters cannot be combined or parsed safely."""


def _value(value):
    return value.value if hasattr(value, "value") else value


def _mark_stale(observation, now: datetime):
    """Return a view with computed staleness, without rewriting storage."""

    if observation.metadata.stale:
        return observation

    age = now - observation.metadata.observed_at
    if age <= timedelta(seconds=STALE_OBSERVATION_AFTER_SECONDS):
        return observation

    metadata = observation.metadata.model_copy(update={"stale": True})
    return observation.model_copy(update={"metadata": metadata})


def _item(row, now: datetime) -> ObservationItem:
    return ObservationItem(
        id=row.id,
        legacy_sample_id=row.legacy_sample_id,
        observation=_mark_stale(row.observation, now),
    )


def _empty_response(now: datetime, filters: ObservationFilters):
    return CurrentObservationsResponse(
        observed_at=now,
        count=0,
        filters=filters,
        observations=[],
    )


def _query_rows(
    store: MetricsStore,
    *,
    source: str | None,
    scope: str | None,
    environment: str | None,
    client_id: str | None,
):
    if client_id is not None:
        try:
            store.get_client(client_id)
        except KeyError as error:
            raise UnknownClientError("unknown_client") from error
        except ValueError as error:
            raise InvalidFilterError("invalid_client_id") from error

        return store.get_client_history(
            client_id,
            source=source,
            environment=environment,
            order="newest",
            limit=1,
        )

    if scope == ObservationScope.CLIENT.value or (
        source == ObservationSource.LINUX_NAMESPACE_LAB.value
        and scope is None
    ):
        rows = []
        for client in store.list_clients():
            rows.extend(
                store.get_client_history(
                    client.client_id,
                    source=source,
                    environment=environment,
                    order="newest",
                    limit=1,
                )
            )
        return rows

    sources = (source,) if source is not None else tuple(
        item.value for item in _DEFAULT_AGGREGATE_SOURCES
    )
    rows = []
    for aggregate_source in sources:
        rows.extend(
            store.get_aggregate_history(
                source=aggregate_source,
                scope=scope,
                environment=environment,
                order="newest",
                limit=1,
            )
        )
    return rows


def build_current_observations(
    db_path: Path | None = None,
    *,
    source: str | None = None,
    scope: str | None = None,
    environment: str | None = None,
    client_id: str | None = None,
) -> CurrentObservationsResponse:
    """Return the newest observation per source or per anonymous client."""

    now = utc_now()
    source_value = _value(source)
    scope_value = _value(scope)
    environment_value = _value(environment)
    client_id_value = _value(client_id)

    if client_id_value is not None and scope_value not in (
        None,
        ObservationScope.CLIENT.value,
    ):
        raise InvalidFilterError("invalid_filter_combination")

    try:
        filters = ObservationFilters(
            source=source_value,
            scope=scope_value,
            environment=environment_value,
            client_id=client_id_value,
        )
    except ValidationError as error:
        raise InvalidFilterError("invalid_filter") from error

    path = db_path or database_path()
    if not path.exists():
        return _empty_response(now, filters)

    try:
        store = MetricsStore(path)
        rows = _query_rows(
            store,
            source=source_value,
            scope=scope_value,
            environment=environment_value,
            client_id=client_id_value,
        )
    except UnknownClientError:
        raise
    except InvalidFilterError:
        raise
    except _QUERY_ERRORS as error:
        raise ObservationQueryError("database_unavailable") from error

    rows.sort(
        key=lambda row: (row.observation.metadata.observed_at, row.id),
        reverse=True,
    )

    observations = [_item(row, now) for row in rows]
    return CurrentObservationsResponse(
        observed_at=now,
        count=len(observations),
        filters=filters,
        observations=observations,
    )
