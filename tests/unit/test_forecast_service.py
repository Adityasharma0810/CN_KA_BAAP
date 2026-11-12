"""Unit tests for the live capacity-forecast service and feature builder."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from pydantic import ValidationError

import backend.app.services.forecast_service as fs
from backend.app.models.forecast_schemas import ForecastCurrentResponse, ForecastPoint
from backend.app.models.schemas import TelemetryObservation
from ml.forecasting.features import feature_names
from ml.forecasting.live_features import build_live_feature_row, MIN_SAMPLES


def _obs(ts, scope, cid, dl, ul):
    return TelemetryObservation(
        metadata={
            "observed_at": ts,
            "source": "linux_namespace_lab" if scope == "client" else "linux_gateway",
            "scope": scope,
            "quality": "measured",
            "environment": "simulated_lab",
            "client_id": cid,
        },
        download_mbps=dl,
        upload_mbps=ul,
    )


def _series(n=35):
    base = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
    slots = {
        "client-aaaaaaaaaaa1": 1,
        "client-bbbbbbbbbbb2": 2,
        "client-ccccccccccc3": 3,
    }
    client_obs, agg_obs = [], []
    for i in range(n):
        ts = base + timedelta(seconds=2 * i)
        client_obs.append(_obs(ts, "client", "client-aaaaaaaaaaa1", 50.0 + 0.5 * i, 5.0))
        client_obs.append(_obs(ts, "client", "client-bbbbbbbbbbb2", 30.0, 3.0))
        client_obs.append(_obs(ts, "client", "client-ccccccccccc3", 20.0, 2.0))
        agg_obs.append(_obs(ts, "aggregate_gateway", None, 100.0 + 0.5 * i, 10.0))
    return client_obs, agg_obs, slots


def test_feature_row_matches_model_feature_names():
    client_obs, agg_obs, slots = _series()
    result = build_live_feature_row(client_obs, agg_obs, slots, 100.0)
    assert result is not None
    row, count = result
    assert count == MIN_SAMPLES
    assert tuple(row.keys()) == tuple(feature_names())


def test_feature_row_none_when_history_too_short():
    client_obs, agg_obs, slots = _series(n=10)
    assert build_live_feature_row(client_obs, agg_obs, slots, 100.0) is None


def test_feature_row_none_when_no_capacity_is_tolerated():
    """Capacity may be None; the row still builds from rate features."""
    client_obs, agg_obs, slots = _series()
    result = build_live_feature_row(client_obs, agg_obs, slots, None)
    assert result is not None
    row, _ = result
    assert row["configured_capacity_mbps"] is None


def test_gate_falls_back_when_model_worse_than_persistence():
    fs.reset_state()
    horizon = 10
    # Model errors consistently larger than persistence errors.
    fs._live_errors[horizon].extend([(30.0, 10.0)] * fs.MIN_LIVE_COMPARISONS)
    assert fs._decide_source(horizon, 50.0, 50.0) == "persistence_fallback"


def test_gate_uses_model_when_better_than_persistence():
    fs.reset_state()
    horizon = 10
    fs._live_errors[horizon].extend([(5.0, 20.0)] * fs.MIN_LIVE_COMPARISONS)
    assert fs._decide_source(horizon, 50.0, 50.0) == "model"


def test_gate_needs_minimum_comparisons():
    fs.reset_state()
    horizon = 10
    fs._live_errors[horizon].extend([(30.0, 10.0)] * (fs.MIN_LIVE_COMPARISONS - 1))
    # Not enough comparisons yet -> model is trusted provisionally.
    assert fs._decide_source(horizon, 50.0, 50.0) == "model"


def test_confidence_is_none_without_comparisons():
    fs.reset_state()
    assert fs._confidence(10) is None


def test_confidence_reflects_relative_improvement():
    fs.reset_state()
    fs._live_errors[10].extend([(5.0, 20.0)] * fs.MIN_LIVE_COMPARISONS)
    confidence = fs._confidence(10)
    assert confidence is not None
    assert 0.0 < confidence <= 1.0


def test_build_current_forecast_no_database_is_unavailable(monkeypatch):
    """With no observation database the API must not raise."""
    from pathlib import Path

    monkeypatch.setattr(fs, "database_path", lambda: Path("/nonexistent/eb.db"))
    response = fs.build_current_forecast(
        requested_at=datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
    )
    assert isinstance(response, ForecastCurrentResponse)
    assert response.model_available in (True, False)
    assert response.history_samples == 0
    for point in response.horizons:
        assert point.source == "unavailable"
        assert point.forecast_mbps is None


def test_missing_model_isolation(monkeypatch):
    """A missing/broken model never raises; availability reports False."""
    from pathlib import Path

    cache = fs._ModelCache()
    monkeypatch.setattr(fs, "MODEL_DIR", Path("/nonexistent/models"))
    assert cache.load() is None
    assert cache.available is False


def test_forecast_point_schema_rejects_extra_fields():
    with pytest.raises(ValidationError):
        ForecastPoint(
            horizon_seconds=10,
            source="model",
            forecast_mbps=50.0,
            persistence_mbps=48.0,
            confidence=0.6,
            reason="ok",
            secret_field="leak",  # type: ignore[arg-type]
        )
