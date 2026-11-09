"""Optional LightGBM regression wrapper; never substitutes another estimator."""

from __future__ import annotations

import math
from os import PathLike
from typing import Any


class LightGBMDependencyError(ImportError):
    """Raised when the optional LightGBM package is unavailable."""


class LightGBMForecaster:
    """Thin horizon-specific supervised regressor wrapper."""

    def __init__(self, **model_params: Any) -> None:
        self.model_params = model_params
        self._model: Any | None = None
        self.feature_names: tuple[str, ...] | None = None

    @classmethod
    def from_model_file(
        cls, path: str | PathLike[str], **model_params: Any
    ) -> "LightGBMForecaster":
        try:
            import lightgbm
        except ImportError as error:
            raise LightGBMDependencyError(
                "loading a LightGBM model requires the optional 'lightgbm' package"
            ) from error

        model = cls(**model_params)
        model._model = lightgbm.Booster(model_file=str(path))
        model.feature_names = tuple(model._model.feature_name())
        return model

    def fit(
        self,
        features: list[dict[str, float | None]],
        targets: list[float],
    ) -> "LightGBMForecaster":
        if not features or len(features) != len(targets):
            raise ValueError("features and targets must be non-empty and equal length")
        if any(not math.isfinite(value) for value in targets):
            raise ValueError("targets must be finite")
        feature_names = tuple(features[0])
        if any(tuple(row) != feature_names for row in features):
            raise ValueError("all feature rows must have the same ordered columns")

        try:
            import lightgbm
            import numpy
        except ImportError as error:
            raise LightGBMDependencyError(
                "LightGBM forecasting requires the optional 'lightgbm' and "
                "'numpy' packages; install them in the project environment before fitting"
            ) from error

        params = dict(self.model_params)
        num_boost_round = int(params.pop("n_estimators", 100))
        params.setdefault("objective", "regression")
        matrix = numpy.asarray(_matrix(features, feature_names), dtype=float)
        dataset = lightgbm.Dataset(
            matrix, label=targets, feature_name=list(feature_names)
        )
        self._model = lightgbm.train(
            params, dataset, num_boost_round=num_boost_round
        )
        self.feature_names = feature_names
        return self

    def predict(self, features: list[dict[str, float | None]]) -> list[float]:
        if self._model is None:
            raise RuntimeError("LightGBM forecaster is not fitted")
        if not features:
            return []
        feature_names = tuple(features[0])
        if any(tuple(row) != feature_names for row in features):
            raise ValueError("all feature rows must have the same ordered columns")
        if self.feature_names is not None and feature_names != self.feature_names:
            raise ValueError("feature names and order do not match the fitted model")
        return [float(value) for value in self._model.predict(_matrix(features, feature_names))]

    def save_model(self, path: str) -> None:
        if self._model is None:
            raise RuntimeError("LightGBM forecaster is not fitted")
        self._model.save_model(path)


def _matrix(
    features: list[dict[str, float | None]], feature_names: tuple[str, ...]
) -> list[list[float]]:
    return [
        [
            math.nan if row[name] is None else float(row[name])
            for name in feature_names
        ]
        for row in features
    ]
