"""Live traffic-classifier service.

The external ISCX-trained models cannot be fed from the lab (they need
per-flow packet inter-arrival and active/idle statistics the lab does not
collect), so this service serves a lab-derived classifier instead: a small
model trained on per-client rates, direction ratio and mean packet size,
labelled by scenario run manifests.

When no trained model is available (the current state: every existing
scenario run failed with helper_missing, so there is no labelled data yet),
:class:`classify` returns ``unknown`` and ``available=False``.  The
infrastructure is ready for a model produced by ``ml/classifier/train.py``.

Label corrections are persisted to a separate SQLite store and are NEVER
used for auto-training.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.config import database_path
from backend.app.models.classifier_schemas import (
    ClassifierStatus,
    LabelCorrectionResponse,
    TrafficClass,
)
from backend.app.models.schemas import TelemetryObservation

CONFIDENCE_THRESHOLD = 0.6
CLASSIFIER_CLASSES: tuple[str, ...] = ("call", "game", "stream", "bulk", "unknown")
MODEL_DIR = Path(__file__).resolve().parents[3] / "models" / "classifier"
MODEL_FILE = MODEL_DIR / "classifier.joblib"
METADATA_FILE = MODEL_DIR / "metadata.json"
CORRECTIONS_DB = Path(__file__).resolve().parents[3] / "data" / "classifier_corrections.sqlite3"

_TRAINING_NOTE_NO_DATA = (
    "No trained model: all existing scenario runs failed with helper_missing, "
    "so there is no labelled lab data yet. The external ISCX models cannot be "
    "fed from lab counters (per-flow packet features). A model can be trained "
    "with ml/classifier/train.py once labelled runs exist."
)


def extract_features(observation: TelemetryObservation) -> dict[str, float | None]:
    """Lab-derived, privacy-safe features for traffic classification."""
    down = observation.download_mbps
    up = observation.upload_mbps
    down_bytes = observation.download_bytes
    up_bytes = observation.upload_bytes
    down_pkts = observation.download_packets
    up_pkts = observation.upload_packets
    total_bytes = None
    if down_bytes is not None and up_bytes is not None:
        total_bytes = down_bytes + up_bytes
    total_pkts = None
    if down_pkts is not None and up_pkts is not None:
        total_pkts = down_pkts + up_pkts
    direction_ratio = None
    if total_bytes is not None and total_bytes > 0:
        direction_ratio = up_bytes / total_bytes
    mean_packet_size = None
    if total_bytes is not None and total_pkts and total_pkts > 0:
        mean_packet_size = total_bytes / total_pkts
    rate_ratio = None
    if down is not None and up is not None and (down + up) > 0:
        rate_ratio = down / (down + up)
    return {
        "download_mbps": down,
        "upload_mbps": up,
        "rate_ratio_down": rate_ratio,
        "direction_ratio_up": direction_ratio,
        "mean_packet_size_bytes": mean_packet_size,
    }


class _ModelHolder:
    def __init__(self) -> None:
        self._model: Any | None = None
        self._loaded = False
        self._error: str | None = None

    def load(self) -> Any | None:
        if self._loaded:
            return self._model
        self._loaded = True
        if not MODEL_FILE.is_file():
            self._error = "model_file_missing"
            return None
        try:
            import joblib  # type: ignore[import-not-found]

            self._model = joblib.load(MODEL_FILE)
            return self._model
        except Exception:  # noqa: BLE001 - never break the API
            self._error = "model_load_failed"
            self._model = None
            return None

    @property
    def available(self) -> bool:
        return self.load() is not None

    def reset(self) -> None:
        self._model = None
        self._loaded = False
        self._error = None


_model = _ModelHolder()


def _load_metadata() -> dict[str, Any] | None:
    if not METADATA_FILE.is_file():
        return None
    try:
        return json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def classify(observation: TelemetryObservation) -> tuple[str | None, float | None, bool]:
    """Return (class, confidence, available).

    When no model is loaded, returns (None, None, False) so the caller keeps
    the scenario-declared class.  Below the confidence threshold the class is
    ``unknown``.
    """
    model = _model.load()
    if model is None:
        return None, None, False
    features = extract_features(observation)
    try:
        import numpy as np  # type: ignore[import-not-found]

        row = np.asarray(
            [
                [
                    features["download_mbps"],
                    features["upload_mbps"],
                    features["rate_ratio_down"],
                    features["direction_ratio_up"],
                    features["mean_packet_size_bytes"],
                ]
            ],
            dtype=float,
        )
        proba = model.predict_proba(row)[0]
        classes = list(getattr(model, "classes_", CLASSIFIER_CLASSES))
        idx = int(proba.argmax())
        confidence = float(proba[idx])
        label = str(classes[idx]) if idx < len(classes) else "unknown"
        if confidence < CONFIDENCE_THRESHOLD:
            return "unknown", confidence, True
        return label, confidence, True
    except Exception:  # noqa: BLE001 - never break the API
        return None, None, False


def status() -> ClassifierStatus:
    metadata = _load_metadata() or {}
    available = _model.available
    return ClassifierStatus(
        available=available,
        version=metadata.get("version"),
        classes=list(CLASSIFIER_CLASSES),
        confidence_threshold=CONFIDENCE_THRESHOLD,
        held_out_f1=metadata.get("held_out_f1"),
        baseline_f1=metadata.get("baseline_f1"),
        last_fallback_reason=("model unavailable" if not available else None),
        training_note=metadata.get("training_note", _TRAINING_NOTE_NO_DATA),
    )


def _ensure_corrections_db() -> sqlite3.Connection:
    CORRECTIONS_DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(CORRECTIONS_DB)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS label_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stored_at TEXT NOT NULL,
            client_id TEXT NOT NULL,
            corrected_label TEXT NOT NULL,
            note TEXT
        )
        """
    )
    connection.commit()
    return connection


def store_correction(
    client_id: str, corrected_label: TrafficClass, note: str | None = None
) -> LabelCorrectionResponse:
    """Persist a user correction; never triggers training."""
    now = datetime.now(timezone.utc)
    connection = _ensure_corrections_db()
    try:
        connection.execute(
            "INSERT INTO label_corrections (stored_at, client_id, corrected_label, note) "
            "VALUES (?, ?, ?, ?)",
            (now.isoformat(), client_id, corrected_label, note),
        )
        connection.commit()
    finally:
        connection.close()
    return LabelCorrectionResponse(
        accepted=True,
        stored_at=now,
        client_id=client_id,
        corrected_label=corrected_label,
        training_triggered=False,
    )


def list_corrections() -> list[dict[str, Any]]:
    """Read stored corrections (used by tests; never auto-trained)."""
    if not CORRECTIONS_DB.is_file():
        return []
    connection = sqlite3.connect(CORRECTIONS_DB)
    try:
        rows = connection.execute(
            "SELECT stored_at, client_id, corrected_label, note FROM label_corrections "
            "ORDER BY id DESC LIMIT 100"
        ).fetchall()
        return [
            {"stored_at": r[0], "client_id": r[1], "corrected_label": r[2], "note": r[3]}
            for r in rows
        ]
    finally:
        connection.close()
