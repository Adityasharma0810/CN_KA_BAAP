"""Component health reporting for the product-facing observation API.

The service reuses the Module 4 storage layer and the Module 2 registry. It
never returns filesystem paths, gateway endpoints, exception text, or identity
data. Missing measurements are reported as unavailable, never as zero.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.config import (
    STALE_OBSERVATION_AFTER_SECONDS,
    database_path,
)
from backend.app.models.api_responses import (
    CollectorHealth,
    CollectorName,
    CollectorsResponse,
    ComponentHealth,
    ComponentStatus,
    DatabaseHealth,
    HealthComponents,
    HealthResponse,
    RegistryHealth,
)
from backend.app.services.lab_accounting_service import lab_accounting_service
from network.telemetry.metrics_store import (
    CorruptDatabaseError,
    MetricsStore,
    MigrationError,
    StorageError,
)


from backend.app.models.api_schemas import (
    CollectorHealthResponse,
    ComponentHealth as LegacyComponentHealth,
    HealthResponse as LegacyHealthResponse,
    HealthState,
)

_QUERY_ERRORS = (StorageError, sqlite3.Error, OSError, ValueError)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_component(name, check, *, checked_at=None):
    checked = checked_at or utc_now()
    try:
        healthy = bool(check())
    except TimeoutError:
        return LegacyComponentHealth(name=name, status=HealthState.UNAVAILABLE, checked_at=checked, error_code="timeout")
    except Exception:
        return LegacyComponentHealth(name=name, status=HealthState.DEGRADED, checked_at=checked, error_code="check_failed")
    return LegacyComponentHealth(name=name, status=HealthState.HEALTHY if healthy else HealthState.UNAVAILABLE, checked_at=checked, error_code=None if healthy else "unavailable")


def aggregate_status(components):
    if any(c.status == HealthState.UNAVAILABLE for c in components):
        return HealthState.DEGRADED if any(c.status == HealthState.HEALTHY for c in components) else HealthState.UNAVAILABLE
    if any(c.status == HealthState.DEGRADED for c in components):
        return HealthState.DEGRADED
    return HealthState.HEALTHY


def build_health(*, database_check, windows_collector_check, gateway_check, registry_check, checked_at=None):
    checked = checked_at or utc_now()
    components = [safe_component("database", database_check, checked_at=checked), safe_component("windows_collector", windows_collector_check, checked_at=checked), safe_component("linux_gateway", gateway_check, checked_at=checked), safe_component("anonymous_registry", registry_check, checked_at=checked)]
    return LegacyHealthResponse(status=aggregate_status(components), checked_at=checked, components=components)


def build_collector_health(*, windows_collector_check, gateway_check, checked_at=None):
    checked = checked_at or utc_now()
    return CollectorHealthResponse(checked_at=checked, collectors=[safe_component("windows_collector", windows_collector_check, checked_at=checked), safe_component("linux_gateway", gateway_check, checked_at=checked)])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _probe_database(path: Path) -> tuple[DatabaseHealth, MetricsStore | None]:
    """Return database health and, when usable, an open store handle."""

    if not path.exists():
        return (
            DatabaseHealth(
                status=ComponentStatus.DEGRADED,
                error_code="database_not_initialized",
                schema_version=None,
            ),
            None,
        )

    try:
        store = MetricsStore(path)
        version = store.schema_version()
    except CorruptDatabaseError:
        return (
            DatabaseHealth(
                status=ComponentStatus.UNAVAILABLE,
                error_code="database_corrupt",
                schema_version=None,
            ),
            None,
        )
    except MigrationError:
        return (
            DatabaseHealth(
                status=ComponentStatus.UNAVAILABLE,
                error_code="database_schema_unsupported",
                schema_version=None,
            ),
            None,
        )
    except (StorageError, sqlite3.Error, OSError, ValueError):
        return (
            DatabaseHealth(
                status=ComponentStatus.UNAVAILABLE,
                error_code="database_unavailable",
                schema_version=None,
            ),
            None,
        )

    return (
        DatabaseHealth(
            status=ComponentStatus.HEALTHY,
            error_code=None,
            schema_version=version,
        ),
        store,
    )


def _probe_collector(
    store: MetricsStore | None,
    *,
    collector: CollectorName,
    source: str,
    scope: str,
    now: datetime,
) -> CollectorHealth:
    """Report one collector from its newest canonical observation."""

    if store is None:
        return CollectorHealth(
            collector=collector,
            status=ComponentStatus.UNAVAILABLE,
            error_code="database_unavailable",
            last_success_at=None,
            stale=False,
        )

    try:
        rows = store.get_history_by_source(
            source,
            scope=scope,
            order="newest",
            limit=1,
        )
    except _QUERY_ERRORS:
        return CollectorHealth(
            collector=collector,
            status=ComponentStatus.UNAVAILABLE,
            error_code="collector_query_failed",
            last_success_at=None,
            stale=False,
        )

    if not rows:
        return CollectorHealth(
            collector=collector,
            status=ComponentStatus.UNAVAILABLE,
            error_code="no_observations",
            last_success_at=None,
            stale=False,
        )

    observation = rows[0].observation
    observed_at = observation.metadata.observed_at
    quality = observation.metadata.quality
    stale = (now - observed_at) > timedelta(
        seconds=STALE_OBSERVATION_AFTER_SECONDS
    )

    if quality == "unavailable":
        return CollectorHealth(
            collector=collector,
            status=ComponentStatus.DEGRADED,
            error_code="collector_reported_unavailable",
            last_success_at=None,
            stale=stale,
        )

    if quality == "unknown":
        return CollectorHealth(
            collector=collector,
            status=ComponentStatus.DEGRADED,
            error_code="quality_unknown",
            last_success_at=None,
            stale=stale,
        )

    if stale:
        return CollectorHealth(
            collector=collector,
            status=ComponentStatus.DEGRADED,
            error_code="stale_observation",
            last_success_at=observed_at,
            stale=True,
        )

    return CollectorHealth(
        collector=collector,
        status=ComponentStatus.HEALTHY,
        error_code=None,
        last_success_at=observed_at,
        stale=False,
    )


def _gateway_health() -> ComponentHealth:
    """Report the not-yet-integrated read-only gateway adapter honestly."""

    return ComponentHealth(
        status=ComponentStatus.UNAVAILABLE,
        error_code="gateway_not_configured",
        last_success_at=None,
    )


def _registry_health() -> RegistryHealth:
    try:
        client_count = len(lab_accounting_service.registry.list_clients())
    except (ValueError, RuntimeError, OSError):
        return RegistryHealth(
            status=ComponentStatus.UNAVAILABLE,
            error_code="registry_unavailable",
            client_count=None,
        )

    return RegistryHealth(
        status=ComponentStatus.HEALTHY,
        error_code=None,
        client_count=client_count,
    )


def _overall_status(
    database: DatabaseHealth,
    collectors: list[CollectorHealth],
    gateway: ComponentHealth,
    registry: RegistryHealth,
) -> ComponentStatus:
    if database.status == ComponentStatus.UNAVAILABLE:
        return ComponentStatus.UNAVAILABLE

    statuses = [database.status, gateway.status, registry.status]
    statuses.extend(collector.status for collector in collectors)

    if all(status == ComponentStatus.HEALTHY for status in statuses):
        return ComponentStatus.HEALTHY

    return ComponentStatus.DEGRADED


def _snapshot(
    db_path: Path | None = None,
) -> tuple[HealthResponse, CollectorsResponse]:
    now = _utc_now()
    database, store = _probe_database(db_path or database_path())

    collectors = [
        _probe_collector(
            store,
            collector=CollectorName.WINDOWS_HOST,
            source="windows_host",
            scope="aggregate_gateway",
            now=now,
        ),
        _probe_collector(
            store,
            collector=CollectorName.WINDOWS_HOTSPOT,
            source="windows_hotspot",
            scope="aggregate_hotspot",
            now=now,
        ),
        _probe_collector(
            store,
            collector=CollectorName.LINUX_GATEWAY,
            source="linux_gateway",
            scope="aggregate_gateway",
            now=now,
        ),
    ]

    gateway = _gateway_health()
    registry = _registry_health()

    def component(collector: CollectorHealth) -> ComponentHealth:
        return ComponentHealth(
            status=collector.status,
            error_code=collector.error_code,
            last_success_at=collector.last_success_at,
        )

    health = HealthResponse(
        status=_overall_status(database, collectors, gateway, registry),
        observed_at=now,
        components=HealthComponents(
            application=ComponentHealth(status=ComponentStatus.HEALTHY),
            database=database,
            windows_host_collector=component(collectors[0]),
            windows_hotspot_collector=component(collectors[1]),
            gateway=gateway,
            client_registry=registry,
        ),
    )
    collector_response = CollectorsResponse(
        observed_at=now,
        collectors=collectors,
    )
    return health, collector_response


def build_observation_health(db_path: Path | None = None) -> HealthResponse:
    """Return the versioned observation health envelope."""

    health, _ = _snapshot(db_path)
    return health


def build_collectors_health(db_path: Path | None = None) -> CollectorsResponse:
    """Return per-collector health entries."""

    _, collectors = _snapshot(db_path)
    return collectors
