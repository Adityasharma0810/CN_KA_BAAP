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
    HistoricalObservationsResponse,
    HistoryFilters,
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


def _history_filters(*, source, scope, environment, client_id, start, end, order):
    try:
        return HistoryFilters(
            source=_value(source),
            scope=_value(scope),
            environment=_value(environment),
            client_id=_value(client_id),
            start=start,
            end=end,
            order=order,
        )
    except ValidationError as error:
        raise InvalidFilterError("invalid_filter") from error


def build_historical_observations(
    db_path: Path | None = None,
    *,
    source: str | None = None,
    scope: str | None = None,
    environment: str | None = None,
    client_id: str | None = None,
    start: datetime | str | None = None,
    end: datetime | str | None = None,
    limit: int = 100,
    offset: int = 0,
    order: str = "newest",
    requested_at: datetime | None = None,
    client_history: bool = False,
) -> HistoricalObservationsResponse:
    now = requested_at or utc_now()
    source_value = _value(source)
    scope_value = _value(scope)
    if (
        source_value == ObservationSource.LINUX_NAMESPACE_LAB.value
        and scope_value is None
        and not client_history
    ):
        scope_value = ObservationScope.CLIENT.value
    environment_value = _value(environment)
    client_id_value = _value(client_id)
    filters = _history_filters(
        source=source,
        scope=ObservationScope.CLIENT.value if client_history else scope,
        environment=environment,
        client_id=client_id,
        start=start,
        end=end,
        order=order,
    )
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise InvalidFilterError("invalid_pagination")
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise InvalidFilterError("invalid_pagination")
    if filters.start is not None and filters.end is not None and filters.start > filters.end:
        raise InvalidFilterError("invalid_time_range")

    if client_history:
        scope_value = ObservationScope.CLIENT.value
        if client_id_value is None:
            raise InvalidFilterError("invalid_client_id")
    elif client_id_value is not None and scope_value not in (None, ObservationScope.CLIENT.value):
        raise InvalidFilterError("invalid_filter_combination")

    path = db_path or database_path()
    if not path.exists():
        if client_history:
            raise UnknownClientError("unknown_client")
        total_count = 0
        rows = []
    else:
        try:
            store = MetricsStore(path)
            if client_history or client_id_value is not None:
                try:
                    store.get_client(client_id_value)
                except KeyError as error:
                    raise UnknownClientError("unknown_client") from error
            if client_history:
                rows = store.get_client_history(
                    client_id_value,
                    source=source_value,
                    environment=environment_value,
                    start=start,
                    end=end,
                    order=order,
                    limit=limit,
                    offset=offset,
                )
                total_count = store.count_observations(
                    scope=ObservationScope.CLIENT,
                    client_id=client_id_value,
                    source=source_value,
                    environment=environment_value,
                    start=start,
                    end=end,
                )
            elif scope_value in (
                None,
                ObservationScope.AGGREGATE_GATEWAY.value,
                ObservationScope.AGGREGATE_HOTSPOT.value,
            ):
                aggregate_only = scope_value is None and client_id_value is None
                rows = store.query_history(
                    scope=scope_value,
                    client_id=client_id_value,
                    source=source_value,
                    environment=environment_value,
                    start=start,
                    end=end,
                    aggregate_only=aggregate_only,
                    order=order,
                    limit=limit,
                    offset=offset,
                )
                total_count = store.count_observations(
                    scope=scope_value,
                    client_id=client_id_value,
                    source=source_value,
                    environment=environment_value,
                    start=start,
                    end=end,
                    aggregate_only=aggregate_only,
                )
            else:
                rows = store.query_history(
                    scope=scope_value,
                    client_id=client_id_value,
                    source=source_value,
                    environment=environment_value,
                    start=start,
                    end=end,
                    order=order,
                    limit=limit,
                    offset=offset,
                )
                total_count = store.count_observations(
                    scope=scope_value,
                    client_id=client_id_value,
                    source=source_value,
                    environment=environment_value,
                    start=start,
                    end=end,
                )
        except _QUERY_ERRORS as error:
            raise ObservationQueryError("database_unavailable") from error

    observations = [_item(row, now) for row in rows]
    return HistoricalObservationsResponse(
        requested_at=now,
        total_count=total_count,
        count=len(observations),
        limit=limit,
        offset=offset,
        has_more=offset + len(observations) < total_count,
        filters=filters,
        observations=observations,
    )


def build_current_observations(
    db_path: Path | None = None,
    *,
    source: str | None = None,
    scope: str | None = None,
    environment: str | None = None,
    client_id: str | None = None,
    _store: "MetricsStore | None" = None,
) -> CurrentObservationsResponse:
    """Return the newest observation per source or per anonymous client.

    Pass ``_store`` to reuse an already-constructed MetricsStore and avoid
    the connection + schema-check overhead for every sub-call within one
    request (e.g. the topology service calls this four times).
    """

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
    if _store is None and not path.exists():
        return _empty_response(now, filters)

    try:
        store = _store if _store is not None else MetricsStore(path)
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
