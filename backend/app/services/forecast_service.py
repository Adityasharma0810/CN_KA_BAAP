"""Live capacity-forecast service backed by the exported LightGBM models.

Serves the 10 s and 30 s horizons ONLY (the 5 s model loses to persistence per
the offline evaluation).  A persistence baseline is always computed alongside.
The model is used only when (a) enough history exists, (b) features build
successfully, (c) the model loads, and (d) the model's rolling live error is
not worse than persistence; otherwise the response reports a
``persistence_fallback`` with a deterministic reason.  A missing model or
lightgbm never breaks the API (status ``unavailable``).

Forecast-vs-actual history is held in memory and resets on restart.
"""

from __future__ import annotations

import pickle
import sqlite3
import statistics
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.config import database_path
from backend.app.models.forecast_schemas import (
    ForecastCurrentResponse,
    ForecastHistoryPoint,
    ForecastHistoryResponse,
    ForecastPoint,
)
from backend.app.models.schemas import TelemetryObservation
from backend.app.services.capacity_service import build_capacity_estimate
from backend.app.services.observation_query_service import _shared_store
from ml.forecasting.live_features import MIN_SAMPLES, build_live_feature_row

SERVED_HORIZONS = (10, 30)
MODEL_DIR = Path(__file__).resolve().parents[3] / "experiments" / "capacity_forecasting" / "models" / "best"
MIN_LIVE_COMPARISONS = 5
MAX_HISTORY_POINTS = 200
_AGG_LOOKBACK = 60  # aggregate samples to keep for actual matching


class _ModelCache:
    """Lazy, failure-isolated model holder."""

    def __init__(self) -> None:
        self._models: dict[int, object] | None = None
        self._error: str | None = None

    def load(self) -> dict[int, object] | None:
        if self._models is not None:
            return self._models
        if self._error is not None:
            return None
        try:
            models: dict[int, object] = {}
            for horizon in SERVED_HORIZONS:
                path = MODEL_DIR / f"best_model_{horizon}s.pkl"
                if not path.is_file():
                    self._error = "model_file_missing"
                    return None
                with path.open("rb") as handle:
                    models[horizon] = pickle.load(handle)
            self._models = models
            return self._models
        except Exception:  # noqa: BLE001 - never break the API
            self._error = "model_load_failed"
            return None

    @property
    def available(self) -> bool:
        return self.load() is not None

    def reset(self) -> None:
        self._models = None
        self._error = None


_models = _ModelCache()

# Rolling live-error tracking (in memory).
_pending: deque = deque(maxlen=200)  # (forecast_at, horizon, model_pred, persist_pred)
_live_errors: dict[int, deque] = {h: deque(maxlen=30) for h in SERVED_HORIZONS}
_history: deque = deque(maxlen=MAX_HISTORY_POINTS)


def _client_slots() -> dict[str, int]:
    """client_id -> slot from the persisted DB.

    The in-memory lab inventory generates random client_ids per process that
    do not match the ingest-registered ids stored with observations, so the
    durable DB mapping is the authoritative source for mapping observation
    client_ids to slots.
    """
    mapping: dict[str, int] = {}
    path = database_path()
    if not path.exists():
        return mapping
    connection = sqlite3.connect(str(path))
    try:
        for row in connection.execute(
            "SELECT client_id, simulated_lab_slot FROM anonymous_clients"
        ):
            mapping[str(row[0])] = int(row[1])
    finally:
        connection.close()
    return mapping


def _aggregate_series(store) -> list[TelemetryObservation]:
    rows = store.get_aggregate_history(
        source="linux_gateway",
        scope="aggregate_gateway",
        limit=_AGG_LOOKBACK,
        order="newest",
    )
    return [item.observation for item in rows]


def _client_series(store, *, limit: int) -> list[TelemetryObservation]:
    rows = store.query_history(
        source="linux_namespace_lab",
        scope="client",
        limit=limit,
        order="newest",
    )
    return [item.observation for item in rows]


def _match_pending(actuals_by_ts: dict[datetime, float], now: datetime) -> None:
    """Match elapsed pending forecasts to actuals and record live errors."""
    remaining: deque = deque()
    for forecast_at, horizon, model_pred, persist_pred in _pending:
        target_at = forecast_at + timedelta(seconds=horizon)
        if target_at > now:
            remaining.append((forecast_at, horizon, model_pred, persist_pred))
            continue
        actual = _nearest_actual(actuals_by_ts, target_at)
        if actual is None:
            # No matching observation yet; keep pending a little longer.
            if (now - target_at).total_seconds() < 120:
                remaining.append((forecast_at, horizon, model_pred, persist_pred))
            continue
        if model_pred is not None and persist_pred is not None:
            model_err = abs(model_pred - actual)
            persist_err = abs(persist_pred - actual)
            _live_errors[horizon].append((model_err, persist_err))
            source = _decide_source(horizon, model_pred, persist_pred)
            _history.append(
                ForecastHistoryPoint(
                    forecast_at=forecast_at,
                    horizon_seconds=horizon,
                    target_at=target_at,
                    forecast_mbps=model_pred,
                    persistence_mbps=persist_pred,
                    actual_mbps=actual,
                    source=source,
                )
            )
    _pending.clear()
    _pending.extend(remaining)


def _nearest_actual(actuals_by_ts: dict[datetime, float], target: datetime) -> float | None:
    if not actuals_by_ts:
        return None
    best = None
    best_gap = None
    for ts, value in actuals_by_ts.items():
        gap = abs((ts - target).total_seconds())
        if best_gap is None or gap < best_gap:
            best_gap = gap
            best = value
    if best is None or best_gap is None or best_gap > 15:
        return None
    return best


def _decide_source(horizon: int, model_pred: float, persist_pred: float) -> str:
    errors = _live_errors.get(horizon, deque())
    if len(errors) < MIN_LIVE_COMPARISONS:
        return "model"
    model_maes = [e[0] for e in errors]
    persist_maes = [e[1] for e in errors]
    model_mae = statistics.fmean(model_maes)
    persist_mae = statistics.fmean(persist_maes)
    if model_mae >= persist_mae:
        return "persistence_fallback"
    return "model"


def _confidence(horizon: int) -> float | None:
    errors = _live_errors.get(horizon, deque())
    if len(errors) < MIN_LIVE_COMPARISONS:
        return None
    model_mae = statistics.fmean(e[0] for e in errors)
    persist_mae = statistics.fmean(e[1] for e in errors)
    if persist_mae <= 0:
        return None
    return round(max(0.0, min(1.0, (persist_mae - model_mae) / persist_mae)), 3)


def reset_state() -> None:
    """Clear in-memory tracking (used by tests)."""
    _pending.clear()
    for horizon in SERVED_HORIZONS:
        _live_errors[horizon].clear()
    _history.clear()


def build_current_forecast(*, requested_at: datetime | None = None) -> ForecastCurrentResponse:
    now = requested_at or datetime.now(timezone.utc)
    path = database_path()
    store = _shared_store(path, None) if path.exists() else None
    models = _models.load()
    model_available = models is not None

    horizons: list[ForecastPoint] = []
    if store is None:
        return ForecastCurrentResponse(
            observed_at=now,
            capacity_mbps=None,
            capacity_uncertainty_mbps=None,
            history_samples=0,
            model_available=model_available,
            horizons=[
                ForecastPoint(
                    horizon_seconds=h,
                    source="unavailable",
                    forecast_mbps=None,
                    persistence_mbps=None,
                    confidence=None,
                    reason="database unavailable; no observations yet",
                )
                for h in SERVED_HORIZONS
            ],
        )

    aggregates = _aggregate_series(store)
    actuals_by_ts = {
        obs.metadata.observed_at: obs.download_mbps
        for obs in aggregates
        if obs.download_mbps is not None
    }
    _match_pending(actuals_by_ts, now)

    client_obs = _client_series(store, limit=MIN_SAMPLES * 3 + 10)
    slots = _client_slots()
    capacity_estimate = build_capacity_estimate(reversed(aggregates)) if aggregates else None
    capacity_mbps = capacity_estimate.capacity_mbps if capacity_estimate and capacity_estimate.available else None
    capacity_unc = capacity_estimate.uncertainty_mbps if capacity_estimate and capacity_estimate.available else None

    persistence_mbps = next(
        (obs.download_mbps for obs in aggregates if obs.download_mbps is not None),
        None,
    )

    # configured_capacity_mbps (the declared bottleneck the model was trained
    # on) is not exposed by the scenario service, so it is left unknown (None)
    # and the model relies on rate features. The Kalman capacity estimate is
    # reported separately in the response for context.
    feature_result = build_live_feature_row(
        client_obs,
        aggregates,
        slots,
        None,
    )

    for horizon in SERVED_HORIZONS:
        if feature_result is None:
            horizons.append(
                ForecastPoint(
                    horizon_seconds=horizon,
                    source="persistence_fallback",
                    forecast_mbps=persistence_mbps,
                    persistence_mbps=persistence_mbps,
                    confidence=None,
                    reason="history too short (<31 aligned samples); using persistence",
                )
            )
            continue
        if not model_available or models is None:
            horizons.append(
                ForecastPoint(
                    horizon_seconds=horizon,
                    source="persistence_fallback",
                    forecast_mbps=persistence_mbps,
                    persistence_mbps=persistence_mbps,
                    confidence=None,
                    reason="model unavailable; using persistence",
                )
            )
            continue
        feature_row, sample_count = feature_result
        try:
            prediction = float(models[horizon].predict([feature_row])[0])
            if prediction < 0:
                prediction = 0.0
        except Exception:  # noqa: BLE001 - fall back, never break the API
            horizons.append(
                ForecastPoint(
                    horizon_seconds=horizon,
                    source="persistence_fallback",
                    forecast_mbps=persistence_mbps,
                    persistence_mbps=persistence_mbps,
                    confidence=None,
                    reason="model prediction failed; using persistence",
                )
            )
            continue
        source = _decide_source(horizon, prediction, persistence_mbps or 0.0)
        confidence = _confidence(horizon)
        if source == "model":
            forecast_value = prediction
            _pending.append((now, horizon, prediction, persistence_mbps))
            reason = "LightGBM forecast; live error not worse than persistence"
        else:
            forecast_value = persistence_mbps
            errors = _live_errors.get(horizon, deque())
            if len(errors) >= MIN_LIVE_COMPARISONS:
                reason = (
                    "model live error worse than persistence; using persistence"
                )
            else:
                reason = "model prediction held; awaiting live-error comparisons"
        horizons.append(
            ForecastPoint(
                horizon_seconds=horizon,
                source=source,
                forecast_mbps=forecast_value,
                persistence_mbps=persistence_mbps,
                confidence=confidence,
                reason=reason,
            )
        )

    return ForecastCurrentResponse(
        observed_at=now,
        capacity_mbps=capacity_mbps,
        capacity_uncertainty_mbps=capacity_unc,
        history_samples=(feature_result[1] if feature_result else 0),
        model_available=model_available,
        horizons=horizons,
    )


def build_forecast_history(*, requested_at: datetime | None = None) -> ForecastHistoryResponse:
    now = requested_at or datetime.now(timezone.utc)
    points = list(_history)
    return ForecastHistoryResponse(
        requested_at=now,
        count=len(points),
        points=points,
    )
