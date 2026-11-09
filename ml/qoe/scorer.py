"""Deterministic, observation-only QoE proxy scoring functions."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Iterable, Mapping


TRAFFIC_CLASSES = {"call", "game", "stream", "bulk"}
STABILITY_SAMPLE_COUNT = 5


@dataclass(frozen=True)
class QoEScore:
    score: float | None
    band: str
    inputs: Mapping[str, float]
    missing_inputs: tuple[str, ...]


def _band(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 75:
        return "green"
    if score >= 50:
        return "amber"
    return "red"


def _clamp(value: float) -> float:
    return round(min(100.0, max(0.0, value)), 2)


def score_qoe(
    traffic_class: str,
    observation: object,
    *,
    history: Iterable[object] = (),
    measured_capacity_mbps: float | None = None,
    fair_share_clients: int | None = None,
) -> QoEScore:
    """Score one observation; unavailable required inputs produce unknown."""

    if traffic_class not in TRAFFIC_CLASSES:
        return QoEScore(None, "unknown", {}, ("traffic_class",))

    values = {
        key: getattr(observation, key, None)
        for key in (
            "rtt_ms",
            "rtt_variation_ms",
            "packet_loss_percent",
            "download_mbps",
        )
    }
    inputs: dict[str, float] = {
        key: float(value)
        for key, value in values.items()
        if value is not None and math.isfinite(float(value))
    }
    missing: list[str] = []
    score: float | None

    if traffic_class == "call":
        required = ("rtt_ms", "rtt_variation_ms", "packet_loss_percent")
        missing.extend(key for key in required if key not in inputs)
        score = None if missing else _clamp(
            100
            - 0.25 * inputs["rtt_ms"]
            - 1.5 * inputs["rtt_variation_ms"]
            - 2.5 * inputs["packet_loss_percent"]
        )
    elif traffic_class == "game":
        required = ("rtt_ms", "rtt_variation_ms")
        missing.extend(key for key in required if key not in inputs)
        score = None if missing else _clamp(
            100 - 0.8 * inputs["rtt_ms"] - 2.0 * inputs["rtt_variation_ms"]
        )
    elif traffic_class == "stream":
        if "download_mbps" not in inputs:
            missing.append("download_mbps")
        samples = list(history)[:STABILITY_SAMPLE_COUNT]
        rates = [
            float(getattr(item, "download_mbps"))
            for item in samples
            if getattr(item, "download_mbps", None) is not None
            and math.isfinite(float(getattr(item, "download_mbps")))
        ]
        if len(samples) < STABILITY_SAMPLE_COUNT or len(rates) != STABILITY_SAMPLE_COUNT:
            missing.append("rate_stability_samples")
        if missing:
            score = None
        else:
            mean_rate = statistics.fmean(rates)
            variation = (
                statistics.pstdev(rates) / mean_rate if mean_rate > 0 else 0.0
            )
            inputs["stability_cv"] = variation
            score = _clamp(min(1.0, inputs["download_mbps"] / 8.0) * 100 * (1 - min(1.0, variation)))
    else:
        if "download_mbps" not in inputs:
            missing.append("download_mbps")
        if measured_capacity_mbps is None or not math.isfinite(
            float(measured_capacity_mbps)
        ) or measured_capacity_mbps <= 0:
            missing.append("measured_capacity_mbps")
        if fair_share_clients is None or fair_share_clients < 1:
            missing.append("fair_share_clients")
        if missing:
            score = None
        else:
            inputs["measured_capacity_mbps"] = float(measured_capacity_mbps)
            inputs["fair_share_clients"] = float(fair_share_clients)
            fair_share = float(measured_capacity_mbps) / fair_share_clients
            score = _clamp(
                min(1.0, inputs["download_mbps"] / fair_share) * 100
            )

    return QoEScore(score, _band(score), inputs, tuple(missing))