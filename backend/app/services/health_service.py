"""Safe component-health aggregation for the product API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from backend.app.models.api_schemas import (
    CollectorHealthResponse,
    ComponentHealth,
    HealthResponse,
    HealthState,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_component(
    name: str,
    check: Callable[[], bool],
    *,
    checked_at: datetime | None = None,
) -> ComponentHealth:
    """Execute a health check without exposing its exception details."""

    checked = checked_at or utc_now()
    try:
        healthy = bool(check())
    except TimeoutError:
        return ComponentHealth(name=name, status=HealthState.UNAVAILABLE, checked_at=checked, error_code="timeout")
    except Exception:
        return ComponentHealth(name=name, status=HealthState.DEGRADED, checked_at=checked, error_code="check_failed")
    return ComponentHealth(
        name=name,
        status=HealthState.HEALTHY if healthy else HealthState.UNAVAILABLE,
        checked_at=checked,
        error_code=None if healthy else "unavailable",
    )


def aggregate_status(components: list[ComponentHealth]) -> HealthState:
    if any(component.status == HealthState.UNAVAILABLE for component in components):
        return HealthState.DEGRADED if any(component.status == HealthState.HEALTHY for component in components) else HealthState.UNAVAILABLE
    if any(component.status == HealthState.DEGRADED for component in components):
        return HealthState.DEGRADED
    return HealthState.HEALTHY


def build_health(
    *,
    database_check: Callable[[], bool],
    windows_collector_check: Callable[[], bool],
    gateway_check: Callable[[], bool],
    registry_check: Callable[[], bool],
    checked_at: datetime | None = None,
) -> HealthResponse:
    checked = checked_at or utc_now()
    components = [
        safe_component("database", database_check, checked_at=checked),
        safe_component("windows_collector", windows_collector_check, checked_at=checked),
        safe_component("linux_gateway", gateway_check, checked_at=checked),
        safe_component("anonymous_registry", registry_check, checked_at=checked),
    ]
    return HealthResponse(status=aggregate_status(components), checked_at=checked, components=components)


def build_collector_health(
    *,
    windows_collector_check: Callable[[], bool],
    gateway_check: Callable[[], bool],
    checked_at: datetime | None = None,
) -> CollectorHealthResponse:
    checked = checked_at or utc_now()
    collectors = [
        safe_component("windows_collector", windows_collector_check, checked_at=checked),
        safe_component("linux_gateway", gateway_check, checked_at=checked),
    ]
    return CollectorHealthResponse(checked_at=checked, collectors=collectors)
