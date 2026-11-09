from datetime import datetime, timezone

from backend.app.models.api_schemas import HealthState
from backend.app.services.health_service import (
    aggregate_status,
    build_collector_health,
    build_health,
    safe_component,
)


CHECKED = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def test_safe_component_hides_failures_and_timeouts():
    failed = safe_component("database", lambda: 1 / 0, checked_at=CHECKED)
    timed_out = safe_component("linux_gateway", lambda: (_ for _ in ()).throw(TimeoutError()), checked_at=CHECKED)

    assert failed.status == HealthState.DEGRADED
    assert failed.error_code == "check_failed"
    assert timed_out.status == HealthState.UNAVAILABLE
    assert timed_out.error_code == "timeout"


def test_aggregate_status_distinguishes_partial_and_total_outage():
    healthy = safe_component("one", lambda: True, checked_at=CHECKED)
    unavailable = safe_component("two", lambda: False, checked_at=CHECKED)

    assert aggregate_status([healthy, unavailable]) == HealthState.DEGRADED
    assert aggregate_status([unavailable]) == HealthState.UNAVAILABLE
    assert aggregate_status([healthy]) == HealthState.HEALTHY


def test_health_response_contains_expected_safe_components():
    response = build_health(
        database_check=lambda: True,
        windows_collector_check=lambda: True,
        gateway_check=lambda: False,
        registry_check=lambda: True,
        checked_at=CHECKED,
    )

    assert response.status == HealthState.DEGRADED
    assert {component.name for component in response.components} == {
        "database", "windows_collector", "linux_gateway", "anonymous_registry"
    }
    assert all(component.checked_at == CHECKED for component in response.components)
    assert all("path" not in component.model_dump() for component in response.components)


def test_collector_health_is_separate_from_overall_health():
    response = build_collector_health(
        windows_collector_check=lambda: True,
        gateway_check=lambda: False,
        checked_at=CHECKED,
    )

    assert [item.name for item in response.collectors] == ["windows_collector", "linux_gateway"]
    assert response.collectors[1].status == HealthState.UNAVAILABLE
