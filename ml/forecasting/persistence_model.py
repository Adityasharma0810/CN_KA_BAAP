"""Pickleable persistence forecaster for capacity-model artifacts."""

from __future__ import annotations

from typing import Any


class PersistenceCapacityForecaster:
    """Return the configured capacity present at each forecast origin."""

    feature_names: tuple[str, ...] | None = None

    def predict(self, features: list[dict[str, Any]]) -> list[float]:
        if not features:
            return []
        names = tuple(features[0])
        if any(tuple(row) != names for row in features):
            raise ValueError("all feature rows must have the same ordered columns")
        if self.feature_names is not None and names != self.feature_names:
            raise ValueError("feature names and order do not match the saved model")
        if "configured_capacity_mbps" not in names:
            raise ValueError("features must include configured_capacity_mbps")
        values = [row["configured_capacity_mbps"] for row in features]
        if any(value is None for value in values):
            raise ValueError("configured capacity must be present at every origin")
        return [float(value) for value in values]
