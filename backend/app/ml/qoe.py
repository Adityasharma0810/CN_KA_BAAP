"""Per-device QoE scoring proxies.

Published formulas; missing required inputs yield ``unknown``. These are
operational QoE proxies, not standardized MOS measurements.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

CLAMP_MIN = 0.0
CLAMP_MAX = 100.0


@dataclass
class QoEResult:
    score: Optional[float]
    band: str
    inputs: dict[str, float]
    missing_inputs: list[str]
    formula: str


def _clamp(value: float) -> float:
    return round(min(CLAMP_MAX, max(CLAMP_MIN, value)), 2)


def _band(score: Optional[float]) -> str:
    if score is None:
        return "unknown"
    if score >= 75:
        return "green"
    if score >= 50:
        return "amber"
    return "red"


def score_call(
    rtt_ms: Optional[float],
    rtt_variation_ms: Optional[float],
    loss_percent: Optional[float],
) -> QoEResult:
    """score = clamp(100 - 0.25*RTT - 1.5*RTT_var - 2.5*loss)

    One-way delay approximated as RTT/2. All three inputs required.
    """
    formula = "clamp(100 - 0.25*RTT_ms - 1.5*RTT_variation_ms - 2.5*packet_loss_percent)"
    missing = []
    inputs: dict[str, float] = {}
    if rtt_ms is None:
        missing.append("rtt_ms")
    else:
        inputs["rtt_ms"] = float(rtt_ms)
    if rtt_variation_ms is None:
        missing.append("rtt_variation_ms")
    else:
        inputs["rtt_variation_ms"] = float(rtt_variation_ms)
    if loss_percent is None:
        missing.append("packet_loss_percent")
    else:
        inputs["packet_loss_percent"] = float(loss_percent)
    score = None if missing else _clamp(
        100 - 0.25 * inputs["rtt_ms"] - 1.5 * inputs["rtt_variation_ms"] - 2.5 * inputs["packet_loss_percent"]
    )
    return QoEResult(score, _band(score), inputs, missing, formula)


def score_game(
    rtt_ms: Optional[float], rtt_variation_ms: Optional[float]
) -> QoEResult:
    """score = clamp(100 - 0.8*RTT - 2.0*RTT_variation). Both required."""
    formula = "clamp(100 - 0.8*RTT_ms - 2.0*RTT_variation_ms)"
    missing = []
    inputs = {}
    if rtt_ms is None:
        missing.append("rtt_ms")
    else:
        inputs["rtt_ms"] = float(rtt_ms)
    if rtt_variation_ms is None:
        missing.append("rtt_variation_ms")
    else:
        inputs["rtt_variation_ms"] = float(rtt_variation_ms)
    score = None if missing else _clamp(100 - 0.8 * inputs["rtt_ms"] - 2.0 * inputs["rtt_variation_ms"])
    return QoEResult(score, _band(score), inputs, missing, formula)


def score_stream(
    download_mbps: Optional[float],
    rates: list[float],
    target_bitrate_mbps: float = 8.0,
) -> QoEResult:
    """score = clamp(100 * min(1, rate/target) * (1 - min(1, CV))).

    Requires current rate and 5 stability samples. CV over last five rates.
    """
    formula = "clamp(100 * min(1, download_Mbps/target) * (1 - min(1, CV_over_5_samples)))"
    missing = []
    inputs = {"target_bitrate_mbps": float(target_bitrate_mbps)}
    if download_mbps is None:
        missing.append("download_mbps")
    else:
        inputs["download_mbps"] = float(download_mbps)
    valid = [float(r) for r in rates if r is not None and math.isfinite(float(r))]
    if len(valid) < 5:
        missing.append("rate_stability_samples_5")
    if missing:
        return QoEResult(None, "unknown", inputs, missing, formula)
    mean_rate = math.fsum(valid) / len(valid)
    cv = (math.sqrt(sum((r - mean_rate) ** 2 for r in valid) / len(valid)) / mean_rate) if mean_rate > 0 else 0.0
    inputs["stability_cv"] = round(cv, 4)
    score = _clamp(min(1.0, download_mbps / target_bitrate_mbps) * 100 * (1 - min(1.0, cv)))
    return QoEResult(score, _band(score), inputs, [], formula)


def score_bulk(
    download_mbps: Optional[float],
    measured_capacity_mbps: Optional[float],
    active_flows: Optional[int],
) -> QoEResult:
    """score = clamp(100 * min(1, client_rate / fair_share)), fair_share = capacity / flows.

    Requires client rate, positive capacity, and flow count >= 1.
    """
    formula = "clamp(100 * min(1, download_Mbps / (capacity_Mbps / active_flows)))"
    missing = []
    inputs = {}
    if download_mbps is None:
        missing.append("download_mbps")
    else:
        inputs["download_mbps"] = float(download_mbps)
    if measured_capacity_mbps is None or measured_capacity_mbps <= 0:
        missing.append("measured_capacity_mbps")
    else:
        inputs["measured_capacity_mbps"] = float(measured_capacity_mbps)
    if active_flows is None or active_flows < 1:
        missing.append("active_flows")
    else:
        inputs["active_flows"] = float(active_flows)
    if missing:
        return QoEResult(None, "unknown", inputs, missing, formula)
    fair_share = float(measured_capacity_mbps) / float(active_flows)
    inputs["fair_share_mbps"] = round(fair_share, 4)
    score = _clamp(min(1.0, float(download_mbps) / fair_share) * 100)
    return QoEResult(score, _band(score), inputs, [], formula)


SCORE_FORMULAS = {
    "call": score_call.__doc__ or "see score_call",
    "gaming": score_game.__doc__ or "see score_game",
    "streaming": score_stream.__doc__ or "see score_stream",
    "bulk": score_bulk.__doc__ or "see score_bulk",
}
