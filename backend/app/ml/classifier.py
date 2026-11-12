"""Privacy-safe traffic flow classifier.

Operates only on permitted metadata features (packet size, inter-arrival time,
direction, rates, flow duration, protocol/port metadata, burst characteristics).
Never inspects encrypted payloads, URLs, or application content.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sklearn.ensemble import RandomForestClassifier

TRAFFIC_CLASSES = ("call", "gaming", "streaming", "bulk", "unknown")
UNKNOWN_THRESHOLD = 0.60
FEATURE_SCHEMA_VERSION = "f1-v1"

# Feature names in canonical order.
FEATURE_NAMES = (
    "avg_packet_size_bytes",
    "packet_rate_pps",
    "byte_rate_mbps",
    "down_up_ratio",
    "inter_arrival_mean_ms",
    "inter_arrival_std_ms",
    "flow_duration_s",
    "burstiness_cv",
    "direction_down_share",
    "port_metadata_present",
    "tcp_share",
    "udp_share",
)


@dataclass
class FlowFeatures:
    values: dict[str, float | None]


class FlowClassifier:
    """Random Forest classifier over live flow metadata.

    ``model`` is None until trained on a labelled dataset. When untrained or
    when confidence is below threshold, the deterministic rule-based fallback
    is used and the result is labelled ``unknown``.
    """

    def __init__(self, version: str = "f1-v1") -> None:
        self.version = version
        self.model: RandomForestClassifier | None = None
        self.trained = False
        self.trained_at: datetime | None = None
        self.feature_provenance: str | None = None
        self.validation_results: dict[str, Any] | None = None
        self.inference_latency_ms: float | None = None
        self.last_inference_at: datetime | None = None

    def extract_features(self, packets: list[dict[str, Any]]) -> FlowFeatures:
        """Build feature vector from packet metadata observations.

        Each packet dict may carry: size_bytes, direction ("down"|"up"),
        timestamp_ms, protocol ("tcp"|"udp"|"other"), port (optional).
        """
        sizes = [int(p.get("size_bytes", 0)) for p in packets if p.get("size_bytes") is not None]
        downs = [p for p in packets if p.get("direction") == "down"]
        total = max(len(packets), 1)
        if len(packets) >= 2:
            timestamps = sorted(float(p.get("timestamp_ms", 0)) for p in packets if p.get("timestamp_ms") is not None)
            inter = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
            inter_mean = statistics.fmean(inter) if inter else 0.0
            inter_std = statistics.pstdev(inter) if len(inter) > 1 else 0.0
        else:
            inter_mean = 0.0
            inter_std = 0.0
        duration_ms = (max(timestamps) - min(timestamps)) if (timestamps := [float(p.get("timestamp_ms", 0)) for p in packets if p.get("timestamp_ms") is not None]) and len(timestamps) > 1 else 0.0
        byte_rate = (sum(sizes) * 8 / 1e6) / (duration_ms / 1000) if duration_ms > 0 else 0.0
        packet_rate = total / (duration_ms / 1000) if duration_ms > 0 else float(total)
        down_share = len(downs) / total
        burstiness = (statistics.pstdev(sizes) / statistics.fmean(sizes)) if (sizes and statistics.fmean(sizes) > 0) else 0.0
        tcp_share = sum(1 for p in packets if p.get("protocol") == "tcp") / total
        udp_share = sum(1 for p in packets if p.get("protocol") == "udp") / total
        port_present = 1.0 if any(p.get("port") is not None for p in packets) else 0.0
        avg_size = statistics.fmean(sizes) if sizes else 0.0

        values = {
            "avg_packet_size_bytes": float(avg_size),
            "packet_rate_pps": float(packet_rate),
            "byte_rate_mbps": float(byte_rate),
            "down_up_ratio": float(len(downs) / max(total - len(downs), 1)),
            "inter_arrival_mean_ms": float(inter_mean),
            "inter_arrival_std_ms": float(inter_std),
            "flow_duration_s": float(duration_ms / 1000),
            "burstiness_cv": float(burstiness),
            "direction_down_share": float(down_share),
            "port_metadata_present": port_present,
            "tcp_share": float(tcp_share),
            "udp_share": float(udp_share),
        }
        return FlowFeatures(values=values)

    def to_vector(self, features: FlowFeatures) -> list[float]:
        return [features.values.get(name, 0.0) or 0.0 for name in FEATURE_NAMES]

    def predict(self, packets: list[dict[str, Any]]) -> dict[str, Any]:
        """Classify a flow. Returns class, confidence, and method."""
        import time

        start = time.perf_counter()
        self.last_inference_at = datetime.now(timezone.utc)
        features = self.extract_features(packets)
        vector = [self.to_vector(features)]

        prediction = "unknown"
        confidence: float | None = None
        method = "rule_based_fallback"
        reason = "model_not_trained"

        if self.model is not None and self.trained:
            try:
                probs = self.model.predict_proba(vector)[0]
                classes = list(self.model.classes_)
                best_index = int(probs.argmax())
                best_class = classes[best_index]
                best_prob = float(probs[best_index])
                method = "ml_inference"
                if best_prob >= UNKNOWN_THRESHOLD:
                    prediction = str(best_class)
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
            "features": features.values,
            "version": self.version,
        }

    def _rule_based(self, features: FlowFeatures) -> tuple[str, float | None, str]:
        v = features.values
        # Deterministic privacy-safe heuristics.
        if v["byte_rate_mbps"] < 0.05 and v["packet_rate_pps"] > 20 and v["udp_share"] > 0.6:
            return "gaming", 0.55, "rule_gaming"
        if v["down_up_ratio"] > 10 and v["byte_rate_mbps"] > 2:
            return "streaming", 0.6, "rule_streaming"
        if v["udp_share"] > 0.5 and 0.1 < v["byte_rate_mbps"] < 5:
            return "call", 0.5, "rule_call"
        if v["byte_rate_mbps"] > 5:
            return "bulk", 0.55, "rule_bulk"
        return "unknown", None, "rule_unknown"

    def train(self, X: list[list[float]], y: list[str], provenance: str | None = None) -> dict[str, Any]:
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import classification_report

        if len(X) < 10:
            raise ValueError("insufficient labelled samples for training")
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.25, random_state=42, stratify=y if len(set(y)) > 1 else None
        )
        model = RandomForestClassifier(n_estimators=100, random_state=42, class_weight="balanced")
        model.fit(X_train, y_train)
        predictions = model.predict(X_test)
        report = classification_report(y_test, predictions, output_dict=True, zero_division=0)
        macro_f1 = report.get("macro avg", {}).get("f1-score")
        self.model = model
        self.trained = True
        self.trained_at = datetime.now(timezone.utc)
        self.feature_provenance = provenance
        self.validation_results = {
            "macro_f1": macro_f1,
            "report": report,
            "train_samples": len(X_train),
            "test_samples": len(X_test),
        }
        return {
            "trained": True,
            "version": self.version,
            "macro_f1": macro_f1,
            "train_samples": len(X_train),
            "test_samples": len(X_test),
        }
