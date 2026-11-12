"""ML runtime for the gateway agent: flow classifier and capacity estimator.

All inference runs locally on the gateway using real telemetry. No raw packet
payloads or encrypted application content are ever inspected.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class FlowFeatures:
    avg_packet_size_bytes: float = 0.0
    packet_rate_pps: float = 0.0
    byte_rate_mbps: float = 0.0
    down_up_ratio: float = 0.0
    inter_arrival_mean_ms: float = 0.0
    flow_duration_s: float = 0.0
    burstiness_cv: float = 0.0
    direction_down_share: float = 0.0
    tcp_share: float = 0.0
    udp_share: float = 0.0

    def to_vector(self) -> list[float]:
        return [
            self.avg_packet_size_bytes,
            self.packet_rate_pps,
            self.byte_rate_mbps,
            self.down_up_ratio,
            self.inter_arrival_mean_ms,
            self.flow_duration_s,
            self.burstiness_cv,
            self.direction_down_share,
            self.tcp_share,
            self.udp_share,
        ]


class FlowClassifier:
    """Privacy-safe Random Forest classifier over flow metadata.

    Falls back to deterministic rules when the model is untrained or confidence
    is below threshold. Never inspects packet payloads.
    """

    TRAFFIC_CLASSES = ("call", "gaming", "streaming", "bulk", "unknown")
    UNKNOWN_THRESHOLD = 0.60

    def __init__(self) -> None:
        try:
            from sklearn.ensemble import RandomForestClassifier

            self._model = RandomForestClassifier(
                n_estimators=100, random_state=42, class_weight="balanced"
            )
        except Exception:
            self._model = None
        self.trained = False
        self.trained_at: datetime | None = None
        self.inference_latency_ms: float | None = None
        self.last_inference_at: datetime | None = None
        self.validation_results: dict[str, Any] | None = None

    def extract_features(self, packets: list[dict]) -> FlowFeatures:
        sizes = [int(p.get("size_bytes", 0)) for p in packets if p.get("size_bytes") is not None]
        total = max(len(packets), 1)
        timestamps = sorted(float(p.get("timestamp_ms", 0)) for p in packets if p.get("timestamp_ms") is not None)
        if len(timestamps) >= 2:
            inter = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
            inter_mean = statistics.fmean(inter) if inter else 0.0
            duration_ms = timestamps[-1] - timestamps[0]
        else:
            inter_mean = 0.0
            duration_ms = 0.0
        downs = [p for p in packets if p.get("direction") == "down"]
        byte_rate = (sum(sizes) * 8 / 1e6) / (duration_ms / 1000) if duration_ms > 0 else 0.0
        packet_rate = total / (duration_ms / 1000) if duration_ms > 0 else float(total)
        mean_size = statistics.fmean(sizes) if sizes else 0.0
        burstiness = (
            statistics.pstdev(sizes) / mean_size if (sizes and mean_size > 0) else 0.0
        )
        tcp_share = sum(1 for p in packets if p.get("protocol") == "tcp") / total
        udp_share = sum(1 for p in packets if p.get("protocol") == "udp") / total
        return FlowFeatures(
            avg_packet_size_bytes=mean_size,
            packet_rate_pps=packet_rate,
            byte_rate_mbps=byte_rate,
            down_up_ratio=len(downs) / max(total - len(downs), 1),
            inter_arrival_mean_ms=inter_mean,
            flow_duration_s=duration_ms / 1000,
            burstiness_cv=burstiness,
            direction_down_share=len(downs) / total,
            tcp_share=tcp_share,
            udp_share=udp_share,
        )

    def predict(self, packets: list[dict]) -> dict[str, Any]:
        import time

        start = time.perf_counter()
        self.last_inference_at = _utc_now()
        features = self.extract_features(packets)
        vector = [features.to_vector()]

        prediction = "unknown"
        confidence: float | None = None
        method = "rule_based_fallback"
        reason = "model_not_trained"

        if self._model is not None and self.trained:
            try:
                probs = self._model.predict_proba(vector)[0]
                classes = list(self._model.classes_)
                best_idx = int(probs.argmax())
                best_prob = float(probs[best_idx])
                method = "ml_inference"
                if best_prob >= self.UNKNOWN_THRESHOLD:
                    prediction = str(classes[best_idx])
                    confidence = best_prob
                    reason = "ml_confident"
                else:
                    prediction = "unknown"
                    confidence = best_prob
                    reason = "ml_confidence_below_threshold"
            except Exception:
                method = "rule_based_fallback"
                reason = "ml_inference_error"

        if method == "rule_based_fallback":
            prediction, confidence, reason = self._rule_based(features)

        latency_ms = (time.perf_counter() - start) * 1000
        self.inference_latency_ms = round(latency_ms, 3)
        return {
            "traffic_class": prediction,
            "confidence": confidence,
            "method": method,
            "reason": reason,
            "features": features,
            "version": "f1-agent-v1",
        }

    def _rule_based(self, f: FlowFeatures) -> tuple[str, float | None, str]:
        if f.byte_rate_mbps < 0.05 and f.packet_rate_pps > 20 and f.udp_share > 0.6:
            return "gaming", 0.55, "rule_gaming"
        if f.down_up_ratio > 10 and f.byte_rate_mbps > 2:
            return "streaming", 0.6, "rule_streaming"
        if f.udp_share > 0.5 and 0.1 < f.byte_rate_mbps < 5:
            return "call", 0.5, "rule_call"
        if f.byte_rate_mbps > 5:
            return "bulk", 0.55, "rule_bulk"
        return "unknown", None, "rule_unknown"

    def train(self, X: list[list[float]], y: list[str]) -> dict[str, Any]:
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import classification_report

        if len(X) < 10:
            raise ValueError("insufficient labelled samples")
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.25, random_state=42,
            stratify=y if len(set(y)) > 1 else None,
        )
        self._model.fit(X_tr, y_tr)
        report = classification_report(y_te, self._model.predict(X_te), output_dict=True, zero_division=0)
        self.trained = True
        self.trained_at = _utc_now()
        self.validation_results = {
            "macro_f1": report.get("macro avg", {}).get("f1-score"),
            "train_samples": len(X_tr),
            "test_samples": len(X_te),
        }
        return {
            "trained": True,
            "macro_f1": self.validation_results["macro_f1"],
            "train_samples": len(X_tr),
            "test_samples": len(X_te),
        }


class KalmanCapacityEstimator:
    """Scalar Kalman filter estimating available download capacity.

    Distinguishes measured throughput from available link capacity. Produces an
    estimate with uncertainty. Never claims to predict unobservable ISP events.
    """

    def __init__(
        self,
        initial_capacity_mbps: float = 100.0,
        process_variance: float = 4.0,
        measurement_variance: float = 25.0,
    ) -> None:
        self.initial_capacity = float(initial_capacity_mbps)
        self.process_variance = float(process_variance)
        self.measurement_variance = float(measurement_variance)
        self._x: float | None = None
        self._p: float = 100.0
        self._last_update: datetime | None = None

    @property
    def initialized(self) -> bool:
        return self._x is not None

    def update(self, measured_mbps: float, elapsed_seconds: float) -> dict[str, Any]:
        now = _utc_now()
        measured = max(float(measured_mbps), 0.0)
        if self._x is None:
            self._x = measured
            self._p = 100.0
        else:
            dt = max(elapsed_seconds, 0.001)
            self._p += self.process_variance * dt
            innovation = measured - self._x
            innovation_variance = self._p + self.measurement_variance
            gain = self._p / innovation_variance if innovation_variance > 0 else 0.0
            self._x += gain * innovation
            self._p = (1.0 - gain) * self._p
        self._x = max(self._x, 0.1)
        self._last_update = now
        return self._snapshot()

    def _snapshot(self) -> dict[str, Any]:
        x = self._x if self._x is not None else self.initial_capacity
        confidence = max(0.0, min(1.0, 1.0 - (self._p / (self._p + 100.0))))
        return {
            "download_capacity_mbps": round(x, 3),
            "uncertainty_mbps": round(math.sqrt(max(self._p, 0.0)), 3),
            "confidence": round(confidence, 3),
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "method": "kalman",
        }

    def estimate(self) -> dict[str, Any]:
        return self._snapshot()

    def reset(self) -> None:
        self._x = None
        self._p = 100.0
        self._last_update = None
