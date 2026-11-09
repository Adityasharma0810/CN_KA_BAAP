"""Stored-evidence-only gateway status and network topology."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Sequence

from backend.app.config import (
    STALE_OBSERVATION_AFTER_SECONDS,
    database_path,
)
from backend.app.models.api_responses import ObservationItem
from backend.app.models.schemas import (
    ObservationScope,
    ObservationSource,
    TelemetryObservation,
    ValueQuality,
)
from backend.app.models.topology_schemas import (
    GatewayStatusResponse,
    SourceStatus,
    TopologyEdgeType,
    TopologyLink,
    TopologyNode,
    TopologyNodeKind,
    TopologyResponse,
    TopologySource,
    TopologySourceStatus,
    TopologyState,
)
from backend.app.services.client_registry import (
    AnonymousClient,
    AnonymousClientRegistry,
    ClientStatus,
)
from backend.app.services.lab_accounting_service import lab_accounting_service
from backend.app.services.observation_query_service import (
    build_current_observations,
)


_LOGGER = logging.getLogger(__name__)
_ObservationResult = list[ObservationItem] | None


class TopologyValidationError(ValueError):
    """Raised when an edge set is internally inconsistent."""


class TopologyServiceError(RuntimeError):
    """Safe error raised when the topology cannot be constructed."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_edges(
    nodes: Sequence[TopologyNode],
    edges: Sequence[TopologyLink],
) -> None:
    """Reject dangling, duplicate, or self-referential topology edges."""

    node_ids = [node.node_id for node in nodes]
    if len(node_ids) != len(set(node_ids)):
        raise TopologyValidationError("duplicate topology node")

    known_nodes = set(node_ids)
    seen_pairs: set[frozenset[str]] = set()
    for edge in edges:
        if edge.source not in known_nodes or edge.target not in known_nodes:
            raise TopologyValidationError("topology edge references unknown node")
        if edge.source == edge.target:
            raise TopologyValidationError("topology edge is a self-loop")
        pair = frozenset((edge.source, edge.target))
        if pair in seen_pairs:
            raise TopologyValidationError("duplicate topology edge")
        seen_pairs.add(pair)


class TopologyService:
    """Build topology from current canonical observations and public registry data."""

    def __init__(
        self,
        *,
        db_path: Path | None = None,
        clock: Callable[[], datetime] = utc_now,
        registry: AnonymousClientRegistry | None = None,
    ):
        self._db_path = db_path
        self.clock = clock
        self.registry = registry or lab_accounting_service.registry

    def gateway_status(self) -> GatewayStatusResponse:
        now = self._now()
        host, host_failed = self._load_source(
            ObservationSource.WINDOWS_HOST,
            ObservationScope.AGGREGATE_GATEWAY,
            now,
        )
        hotspot, hotspot_failed = self._load_source(
            ObservationSource.WINDOWS_HOTSPOT,
            ObservationScope.AGGREGATE_HOTSPOT,
            now,
        )
        gateway, gateway_failed = self._load_source(
            ObservationSource.LINUX_GATEWAY,
            ObservationScope.AGGREGATE_GATEWAY,
            now,
        )
        lab, lab_failed = self._load_source(
            ObservationSource.LINUX_NAMESPACE_LAB,
            ObservationScope.CLIENT,
            now,
        )

        return GatewayStatusResponse(
            observed_at=now,
            application=self._missing_status(),
            windows_host=self._source_status(host, failed=host_failed, now=now),
            hotspot=self._source_status(hotspot, failed=hotspot_failed, now=now),
            linux_lab=self._combined_status(
                (gateway, lab),
                failed=(gateway_failed, lab_failed),
                now=now,
            ),
        )

    def network_topology(self) -> TopologyResponse:
        now = self._now()
        host, host_failed = self._load_source(
            ObservationSource.WINDOWS_HOST,
            ObservationScope.AGGREGATE_GATEWAY,
            now,
        )
        hotspot, hotspot_failed = self._load_source(
            ObservationSource.WINDOWS_HOTSPOT,
            ObservationScope.AGGREGATE_HOTSPOT,
            now,
        )
        gateway, gateway_failed = self._load_source(
            ObservationSource.LINUX_GATEWAY,
            ObservationScope.AGGREGATE_GATEWAY,
            now,
        )
        lab, lab_failed = self._load_source(
            ObservationSource.LINUX_NAMESPACE_LAB,
            ObservationScope.CLIENT,
            now,
        )
        clients, registry_failed = self._load_registry(now)

        host_status = self._source_status(host, failed=host_failed, now=now)
        hotspot_status = self._source_status(
            hotspot, failed=hotspot_failed, now=now
        )
        gateway_status = self._source_status(
            gateway, failed=gateway_failed, now=now
        )
        lab_source_status = self._source_status(
            lab, failed=lab_failed, now=now
        )
        registry_status = self._registry_status(
            clients,
            failed=registry_failed,
            now=now,
        )
        lab_status = self._combined_status(
            (gateway, lab),
            failed=(gateway_failed, lab_failed),
            now=now,
        )

        nodes = [
            self._node(
                node_id="application",
                kind=TopologyNodeKind.APPLICATION,
                label="Experience Budget application",
                source=TopologySource.APPLICATION,
                status=self._missing_status(),
            ),
            self._node(
                node_id="windows-host",
                kind=TopologyNodeKind.WINDOWS_HOST,
                label="Windows host aggregate",
                source=TopologySource.WINDOWS_HOST,
                status=host_status,
            ),
            self._node(
                node_id="hotspot-aggregate",
                kind=TopologyNodeKind.HOTSPOT,
                label="Hotspot aggregate",
                source=TopologySource.WINDOWS_HOTSPOT,
                status=hotspot_status,
            ),
            self._node(
                node_id="linux-lab",
                kind=TopologyNodeKind.LINUX_LAB,
                label="Linux lab",
                source=self._combined_source((gateway, lab)),
                status=lab_status,
            ),
        ]

        client_observations = {
            item.observation.metadata.client_id: item
            for item in (lab or [])
            if item.observation.metadata.client_id is not None
        }
        registry_by_id = {
            client.client_id: client for client in (clients or [])
        }
        all_client_ids = sorted(
            set(client_observations) | set(registry_by_id),
            key=lambda client_id: (
                registry_by_id[client_id].display_label
                if client_id in registry_by_id
                else client_id
            ),
        )
        links: list[TopologyLink] = []
        for index, client_id in enumerate(all_client_ids, start=1):
            item = client_observations.get(client_id)
            client = registry_by_id.get(client_id)
            status = self._client_status(
                item,
                client,
                failed=lab_failed,
                now=now,
            )
            nodes.append(
                self._node(
                    node_id=f"client-{index:02d}",
                    kind=TopologyNodeKind.CLIENT,
                    label=(
                        client.display_label
                        if client is not None
                        else f"Client {index:02d}"
                    ),
                    source=TopologySource.LINUX_LAB,
                    status=status,
                    client_id=client_id,
                )
            )
            links.append(
                TopologyLink(
                    source="linux-lab",
                    target=f"client-{index:02d}",
                    relation=(
                        TopologyEdgeType.OBSERVED
                        if item is not None
                        else TopologyEdgeType.DERIVED
                    ),
                )
            )

        try:
            validate_edges(nodes, links)
        except TopologyValidationError as error:
            _LOGGER.exception("topology edge validation failed")
            raise TopologyServiceError("topology_unavailable") from error

        sources = [
            self._topology_source_status(
                TopologySource.APPLICATION,
                self._missing_status(),
            ),
            self._topology_source_status(
                TopologySource.WINDOWS_HOST, host_status
            ),
            self._topology_source_status(
                TopologySource.WINDOWS_HOTSPOT, hotspot_status
            ),
            self._topology_source_status(
                TopologySource.LINUX_GATEWAY, gateway_status
            ),
            self._topology_source_status(
                TopologySource.LINUX_LAB, lab_source_status
            ),
            self._topology_source_status(
                TopologySource.ANONYMOUS_REGISTRY, registry_status
            ),
        ]
        return TopologyResponse(
            observed_at=now,
            nodes=nodes,
            links=links,
            sources=sources,
        )

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("topology clock must return an aware datetime")
        return now.astimezone(timezone.utc)

    def _load_source(
        self,
        source: ObservationSource,
        scope: ObservationScope,
        now: datetime,
    ) -> tuple[_ObservationResult, bool]:
        try:
            response = build_current_observations(
                self._db_path,
                source=source.value,
                scope=scope.value,
                now=now,
            )
        except Exception:
            _LOGGER.exception(
                "topology observation source unavailable: %s", source.value
            )
            return None, True
        return response.observations, False

    def _load_registry(
        self, now: datetime
    ) -> tuple[list[AnonymousClient] | None, bool]:
        try:
            return self.registry.list_clients(now=now), False
        except Exception:
            _LOGGER.exception("topology anonymous registry unavailable")
            return None, True

    @staticmethod
    def _missing_status() -> SourceStatus:
        return SourceStatus(
            state=TopologyState.MISSING,
            last_observed_at=None,
            data_quality=ValueQuality.UNKNOWN,
        )

    @staticmethod
    def _source_status(
        observations: _ObservationResult,
        *,
        failed: bool,
        now: datetime,
    ) -> SourceStatus:
        if failed:
            return SourceStatus(
                state=TopologyState.UNAVAILABLE,
                last_observed_at=None,
                data_quality=ValueQuality.UNAVAILABLE,
            )
        if not observations:
            return TopologyService._missing_status()
        latest = max(
            observations,
            key=lambda item: item.observation.metadata.observed_at,
        ).observation
        return TopologyService._observation_status(latest, now)

    @staticmethod
    def _combined_status(
        observation_sets: Sequence[_ObservationResult],
        *,
        failed: Sequence[bool],
        now: datetime,
    ) -> SourceStatus:
        observations = [
            item
            for observation_set in observation_sets
            if observation_set
            for item in observation_set
        ]
        if observations:
            latest = max(
                observations,
                key=lambda item: item.observation.metadata.observed_at,
            ).observation
            return TopologyService._observation_status(latest, now)
        if any(failed):
            return SourceStatus(
                state=TopologyState.UNAVAILABLE,
                last_observed_at=None,
                data_quality=ValueQuality.UNAVAILABLE,
            )
        return TopologyService._missing_status()

    @staticmethod
    def _observation_status(
        observation: TelemetryObservation,
        now: datetime,
    ) -> SourceStatus:
        metadata = observation.metadata
        quality = ValueQuality(metadata.quality)
        if quality == ValueQuality.UNAVAILABLE:
            state = TopologyState.UNAVAILABLE
        elif now - metadata.observed_at > timedelta(
            seconds=STALE_OBSERVATION_AFTER_SECONDS
        ):
            state = TopologyState.STALE
        else:
            state = TopologyState.UNKNOWN
        return SourceStatus(
            state=state,
            last_observed_at=metadata.observed_at,
            data_quality=quality,
        )

    @staticmethod
    def _registry_status(
        clients: list[AnonymousClient] | None,
        *,
        failed: bool,
        now: datetime,
    ) -> SourceStatus:
        if failed:
            return SourceStatus(
                state=TopologyState.UNAVAILABLE,
                last_observed_at=None,
                data_quality=ValueQuality.UNAVAILABLE,
            )
        if not clients:
            return TopologyService._missing_status()
        last_observed_at = max(
            (client.last_seen_at for client in clients if client.last_seen_at),
            default=None,
        )
        if last_observed_at is None:
            return TopologyService._missing_status()
        state = (
            TopologyState.STALE
            if now - last_observed_at
            > timedelta(seconds=STALE_OBSERVATION_AFTER_SECONDS)
            else TopologyState.UNKNOWN
        )
        return SourceStatus(
            state=state,
            last_observed_at=last_observed_at,
            data_quality=ValueQuality.UNKNOWN,
        )

    @staticmethod
    def _client_status(
        item: ObservationItem | None,
        client: AnonymousClient | None,
        *,
        failed: bool,
        now: datetime,
    ) -> SourceStatus:
        if client is not None and client.status == ClientStatus.OFFLINE.value:
            return SourceStatus(
                state=TopologyState.OFFLINE,
                last_observed_at=(
                    item.observation.metadata.observed_at
                    if item is not None
                    else client.last_seen_at
                ),
                data_quality=(
                    ValueQuality(item.observation.metadata.quality)
                    if item is not None
                    else ValueQuality.UNKNOWN
                ),
            )
        if failed:
            return SourceStatus(
                state=TopologyState.UNAVAILABLE,
                last_observed_at=None,
                data_quality=ValueQuality.UNAVAILABLE,
            )
        if item is not None:
            return TopologyService._observation_status(
                item.observation, now
            )
        if client is None or client.last_seen_at is None:
            return TopologyService._missing_status()
        age = now - client.last_seen_at
        return SourceStatus(
            state=(
                TopologyState.STALE
                if age > timedelta(seconds=STALE_OBSERVATION_AFTER_SECONDS)
                else TopologyState.UNKNOWN
            ),
            last_observed_at=client.last_seen_at,
            data_quality=ValueQuality.UNKNOWN,
        )

    @staticmethod
    def _node(
        *,
        node_id: str,
        kind: TopologyNodeKind,
        label: str,
        source: TopologySource,
        status: SourceStatus,
        client_id: str | None = None,
    ) -> TopologyNode:
        return TopologyNode(
            node_id=node_id,
            kind=kind,
            label=label,
            source=source,
            state=status.state,
            data_quality=status.data_quality,
            last_observed_at=status.last_observed_at,
            client_id=client_id,
        )

    @staticmethod
    def _combined_source(
        observation_sets: Sequence[_ObservationResult],
    ) -> TopologySource:
        observations = [
            item
            for observation_set in observation_sets
            if observation_set
            for item in observation_set
        ]
        if not observations:
            return TopologySource.LINUX_LAB
        latest = max(
            observations,
            key=lambda item: item.observation.metadata.observed_at,
        )
        source = latest.observation.metadata.source
        return (
            TopologySource.LINUX_GATEWAY
            if source == ObservationSource.LINUX_GATEWAY.value
            else TopologySource.LINUX_LAB
        )

    @staticmethod
    def _topology_source_status(
        source: TopologySource,
        status: SourceStatus,
    ) -> TopologySourceStatus:
        return TopologySourceStatus(
            source=source,
            state=status.state,
            last_observed_at=status.last_observed_at,
            data_quality=status.data_quality,
        )


topology_service = TopologyService()
