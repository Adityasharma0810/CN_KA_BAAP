"""Additive Holt-Winters seasonal forecaster for configured capacity."""

from __future__ import annotations

import math

from .schema import TelemetrySample


class HoltWintersForecaster:
    """Additive triple-exponential smoothing with a fixed seasonal period."""

    def __init__(
        self,
        *,
        season_length: int,
        alpha: float = 0.3,
        beta: float = 0.1,
        gamma: float = 0.1,
        sample_interval_s: float = 1.0,
    ) -> None:
        if season_length < 2:
            raise ValueError("season_length must be at least 2")
        if not 0 < sample_interval_s or not math.isfinite(sample_interval_s):
            raise ValueError("sample_interval_s must be positive and finite")
        if any(not 0 <= value <= 1 for value in (alpha, beta, gamma)):
            raise ValueError("alpha, beta, and gamma must be in [0, 1]")
        self.season_length = season_length
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.sample_interval_s = sample_interval_s
        self._level: float | None = None
        self._trend: float | None = None
        self._seasonals: list[float] = []
        self._observation_count = 0
        self._fitted = False

    def fit(self, values: list[float]) -> "HoltWintersForecaster":
        """Fit using only supplied historical capacity values."""
        minimum = 2 * self.season_length
        if len(values) < minimum:
            raise ValueError(
                f"Holt-Winters needs at least {minimum} observations "
                f"for season_length={self.season_length}; got {len(values)}"
            )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("Holt-Winters history must contain finite values only")

        first_season = values[: self.season_length]
        second_season = values[self.season_length : 2 * self.season_length]
        first_average = sum(first_season) / self.season_length
        second_average = sum(second_season) / self.season_length
        level = first_average
        trend = (second_average - first_average) / self.season_length
        seasonals = [value - first_average for value in first_season]

        for index in range(self.season_length, len(values)):
            value = values[index]
            season_index = index % self.season_length
            previous_level = level
            seasonal = seasonals[season_index]
            level = self.alpha * (value - seasonal) + (1 - self.alpha) * (
                level + trend
            )
            trend = self.beta * (level - previous_level) + (1 - self.beta) * trend
            seasonals[season_index] = self.gamma * (value - level) + (
                1 - self.gamma
            ) * seasonal

        self._level = level
        self._trend = trend
        self._seasonals = seasonals
        self._observation_count = len(values)
        self._fitted = True
        return self

    def predict(self, steps: int) -> list[float]:
        """Forecast the next ``steps`` observations."""
        if not self._fitted or self._level is None or self._trend is None:
            raise RuntimeError("Holt-Winters forecaster is not fitted")
        if steps <= 0:
            raise ValueError("steps must be positive")
        output = []
        for step in range(1, steps + 1):
            seasonal = self._seasonals[
                (self._observation_count + step - 1) % self.season_length
            ]
            output.append(self._level + step * self._trend + seasonal)
        return output

    def predict_horizon(self, horizon_seconds: float) -> float:
        """Forecast one horizon that is an integer number of sample intervals."""
        steps = horizon_seconds / self.sample_interval_s
        rounded_steps = round(steps)
        if rounded_steps <= 0 or not math.isclose(steps, rounded_steps, abs_tol=1e-9):
            raise ValueError(
                "horizon_seconds must be a positive multiple of sample_interval_s"
            )
        return self.predict(rounded_steps)[-1]

    def fit_samples(
        self, samples: list[TelemetrySample], origin: TelemetrySample
    ) -> "HoltWintersForecaster":
        """Fit on contiguous, valid capacity samples through ``origin`` only."""
        history = sorted(
            (
                sample
                for sample in samples
                if sample.run_id == origin.run_id
                and sample.sample_seq <= origin.sample_seq
            ),
            key=lambda sample: sample.sample_seq,
        )
        if not history or history[-1].sample_seq != origin.sample_seq:
            raise ValueError("origin is not present in the supplied run history")
        values: list[float] = []
        previous: TelemetrySample | None = None
        for sample in history:
            capacity = sample.configured_capacity_mbps
            if capacity is None:
                raise ValueError("Holt-Winters history contains missing capacity")
            if previous is not None:
                interval = sample.elapsed_s - previous.elapsed_s
                if (
                    sample.sample_seq != previous.sample_seq + 1
                    or not sample.sample_cadence_valid
                    or not math.isclose(
                        interval,
                        self.sample_interval_s,
                        rel_tol=0.0,
                        abs_tol=sample.sample_cadence_tolerance_s or 0.0,
                    )
                ):
                    raise ValueError("Holt-Winters history is not regularly sampled")
            values.append(capacity)
            previous = sample
        return self.fit(values)
