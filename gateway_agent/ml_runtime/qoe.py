"""QoE scoring proxies (F4) for the gateway agent.

Published formulas; missing required inputs yield ``unknown``. These are
operational QoE proxies, not standardized MOS measurements.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class QoEResult:
    score: Optional[float]
    band: str
    inputs: dict[str, float]
    missing_inputs: list[str]
    formula: str


def _clamp(value: float) -> float:
    return round(min(100.0, max(0.0, value)), 2)


def _band(score: Optional[float]) -> str:
    if score is None:
        return "unknown"
    if score >= 75:
        return "green"
    if score >= 50:
        return "amber"
    return "red"


def score_call(rtt_ms, rtt_variation_ms, loss_percent) -> QoEResult:
    """clamp(100 - 0.25*RTT - 1.5*RTT_var - 2.5*loss). All three required."""
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
    return QoEResult(score, _band(score), inputs, missing, "call: clamp(100 - 0.25*RTT - 1.5*RTT_var - 2.5*loss)")


def score_game(rtt_ms, rtt_variation_ms) -> QoEResult:
    """clamp(100 - 0.8*RTT - 2.0*RTT_variation). Both required."""
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
    return QoEResult(score, _band(score), inputs, missing, "game: clamp(100 - 0.8*RTT - 2.0*RTT_var)")


def score_stream(download_mbps, rates, target_bitrate_mbps=8.0) -> QoEResult:
    """clamp(100 * min(1, rate/target) * (1 - min(1, CV_over_5_samples)))."""
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
        return QoEResult(None, "unknown", inputs, missing, "stream: requires 5 rate samples")
    mean_rate = math.fsum(valid) / len(valid)
    cv = (math.sqrt(sum((r - mean_rate) ** 2 for r in valid) / len(valid)) / mean_rate) if mean_rate > 0 else 0.0
    inputs["stability_cv"] = round(cv, 4)
    score = _clamp(min(1.0, float(download_mbps) / target_bitrate_mbps) * 100 * (1 - min(1.0, cv)))
    return QoEResult(score, _band(score), inputs, [], "stream: clamp(100*min(1,rate/target)*(1-min(1,CV)))")


def score_bulk(download_mbps, measured_capacity_mbps, active_flows) -> QoEResult:
    """clamp(100 * min(1, client_rate / fair_share)), fair_share = capacity / flows."""
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
        return QoEResult(None, "unknown", inputs, missing, "bulk: requires capacity + flow count")
    fair_share = float(measured_capacity_mbps) / float(active_flows)
    inputs["fair_share_mbps"] = round(fair_share, 4)
    score = _clamp(min(1.0, float(download_mbps) / fair_share) * 100)
    return QoEResult(score, _band(score), inputs, [], "bulk: clamp(100*min(1,rate/fair_share))")
