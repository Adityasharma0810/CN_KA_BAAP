"""QoE proxy scores derived only from observations in the query service."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.app.config import database_path
from backend.app.models.qoe_schemas import (
    QoEClientScore,
    QoECurrentResponse,
    QoEHistoryResponse,
    QoEInput,
)
from backend.app.models.schemas import TelemetryObservation
from backend.app.services.lab_accounting_service import lab_accounting_service
from backend.app.services.observation_query_service import (
    _shared_store,
    build_current_observations,
    build_historical_observations,
)
from backend.app.services.scenario_service import scenario_service
from ml.qoe.scorer import score_qoe
from network.telemetry.metrics_store import MetricsStore


_METRIC_UNITS = {
    "rtt_ms": "ms",
    "rtt_variation_ms": "ms",
    "packet_loss_percent": "%",
    "download_mbps": "Mbps",
    "measured_capacity_mbps": "Mbps",
    "stability_cv": "ratio",
    "fair_share_clients": "clients",
}


def _client_slots() -> dict[str, int]:
    return {
        client.client_id: client.client_number
        for client in lab_accounting_service.inventory
    }


def _score(
    observation: TelemetryObservation,
    history: list[TelemetryObservation],
    profiles: dict[int, str],
    slots: dict[str, int],
    capacity: float | None,
    capacity_observed_at: datetime,
    class_started_at: datetime | None,
) -> QoEClientScore:
    client_id = observation.metadata.client_id
    assert client_id is not None
    slot = slots.get(client_id)
    traffic_class = profiles.get(slot or -1)
    if class_started_at is not None and observation.metadata.observed_at < class_started_at:
        traffic_class = None
    class_source = "scenario_declared" if traffic_class is not None else "unclassified"
    traffic_class = traffic_class or "unknown"
    active_flow_count = len(profiles)
    result = score_qoe(
        traffic_class,
        observation,
        history=history,
        measured_capacity_mbps=capacity,
        fair_share_clients=active_flow_count if active_flow_count else None,
    )
    observed_at = observation.metadata.observed_at
    inputs: dict[str, QoEInput] = {}
    for name, value in result.inputs.items():
        timestamp = (
            capacity_observed_at
            if name == "measured_capacity_mbps"
            else observed_at
        )
        inputs[name] = QoEInput(
            value=float(value),
            unit=_METRIC_UNITS[name],
            observed_at=timestamp,
        )
    return QoEClientScore(
        client_id=client_id,
        traffic_class=traffic_class,
        class_source=class_source,
        score=result.score,
        band=result.band,
        observed_at=observed_at,
        inputs=inputs,
        missing_inputs=list(result.missing_inputs),
    )


def build_current_qoe(*, requested_at: datetime | None = None) -> QoECurrentResponse:
    now = requested_at or datetime.now(timezone.utc)
    profiles = scenario_service.active_profiles
    class_started_at = scenario_service.active_started_at
    slots = _client_slots()
    path = database_path()
    store = _shared_store(path, None) if path.exists() else None
    current = build_current_observations(
        source="linux_namespace_lab",
        scope="client",
        _store=store,
    )
    # We use at most 5 history points per client.  Fetch 5 × (number of
    # clients + a small buffer) instead of a flat 1000 to keep Pydantic
    # validation overhead proportional to the actual client count.
    client_count = max(len(slots), len(current.observations), 1)
    history_limit = min(client_count * 5 + 10, 100)
    if store is not None:
        client_rows = store.query_history(
            source="linux_namespace_lab",
            scope="client",
            limit=history_limit,
            order="newest",
        )
        history_by_client: dict[str, list[TelemetryObservation]] = {}
        for row in client_rows:
            identity = row.observation.metadata.client_id
            if identity:
                history_by_client.setdefault(identity, []).append(row.observation)
        aggregate_rows = store.get_aggregate_history(
            source="linux_gateway",
            scope="aggregate_gateway",
            limit=20,
            order="newest",
        )
        aggregates = [item.observation for item in aggregate_rows]
    else:
        history_by_client = {}
        aggregates = []
    scores = []
    for item in current.observations:
        observation = item.observation
        client_id = observation.metadata.client_id
        if client_id is None:
            continue
        history = history_by_client.get(client_id, [])[:5]
        capacity_observation = next(
            (
                item
                for item in aggregates
                if item.metadata.observed_at == observation.metadata.observed_at
            ),
            None,
        )
        scores.append(
            _score(
                observation,
                history,
                profiles,
                slots,
                (
                    capacity_observation.download_mbps
                    if capacity_observation is not None
                    else None
                ),
                (
                    capacity_observation.metadata.observed_at
                    if capacity_observation is not None
                    else now
                ),
                class_started_at,
            )
        )
    return QoECurrentResponse(observed_at=now, clients=scores)


def build_qoe_history(
    *,
    client_id: str | None = None,
    start: datetime | str | None = None,
    end: datetime | str | None = None,
    limit: int = 100,
    requested_at: datetime | None = None,
) -> QoEHistoryResponse:
    now = requested_at or datetime.now(timezone.utc)
    profiles = scenario_service.active_profiles
    class_started_at = scenario_service.active_started_at
    slots = _client_slots()
    history_result = build_historical_observations(
        source="linux_namespace_lab",
        scope="client",
        client_id=client_id,
        start=start,
        end=end,
        limit=limit,
        order="newest",
        client_history=client_id is not None,
    )
    stability_history = build_historical_observations(
        source="linux_namespace_lab",
        scope="client",
        client_id=client_id,
        end=end,
        limit=min(limit * 5 + 10, 500),
        order="newest",
        client_history=client_id is not None,
    )
    aggregate = build_historical_observations(
        source="linux_gateway",
        scope="aggregate_gateway",
        start=start,
        end=end,
        limit=min(limit + 10, 200),
        order="newest",
    )
    aggregates = [item.observation for item in aggregate.observations]
    all_rows = history_result.observations
    by_client: dict[str, list[TelemetryObservation]] = {}
    for item in stability_history.observations:
        identity = item.observation.metadata.client_id
        if identity:
            by_client.setdefault(identity, []).append(item.observation)
    scores = []
    for item in all_rows:
        observation = item.observation
        identity = observation.metadata.client_id
        if identity is None:
            continue
        score_history = [
            candidate
            for candidate in by_client[identity]
            if candidate.metadata.observed_at <= observation.metadata.observed_at
        ][:5]
        capacity_observation = next(
            (
                candidate
                for candidate in aggregates
                if candidate.metadata.observed_at == observation.metadata.observed_at
            ),
            None,
        )
        scores.append(
            _score(
                observation,
                score_history,
                profiles,
                slots,
                (
                    capacity_observation.download_mbps
                    if capacity_observation is not None
                    else None
                ),
                (
                    capacity_observation.metadata.observed_at
                    if capacity_observation is not None
                    else now
                ),
                class_started_at,
            )
        )
    return QoEHistoryResponse(
        requested_at=now,
        client_id=client_id,
        count=len(scores),
        observations=scores,
    )
