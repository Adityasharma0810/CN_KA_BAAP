"""Unit tests for the traffic-classifier service."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest
from pydantic import ValidationError

import backend.app.services.classifier_service as cs
from backend.app.models.classifier_schemas import ClassifierStatus, LabelCorrectionRequest
from backend.app.models.schemas import TelemetryObservation


def _obs(dl=50.0, ul=5.0):
    return TelemetryObservation(
        metadata={
            "observed_at": datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc),
            "source": "linux_namespace_lab",
            "scope": "client",
            "quality": "measured",
            "environment": "simulated_lab",
            "client_id": "client-aaaaaaaaaaa1",
        },
        download_mbps=dl,
        upload_mbps=ul,
        download_bytes=6_000_000,
        upload_bytes=600_000,
        download_packets=9000,
        upload_packets=900,
    )


class _FakeModel:
    def __init__(self, proba, classes):
        self._proba = np.asarray(proba)
        self.classes_ = np.asarray(classes)

    def predict_proba(self, X):
        return self._proba


@pytest.fixture(autouse=True)
def _reset_model():
    cs._model.reset()
    yield
    cs._model.reset()


def test_missing_model_returns_unknown_and_unavailable():
    label, conf, available = cs.classify(_obs())
    assert available is False
    assert label is None
    assert conf is None


def test_low_confidence_thresholds_to_unknown():
    cs._model._model = _FakeModel([[0.4, 0.3, 0.2, 0.1]], ["call", "bulk", "stream", "game"])
    cs._model._loaded = True
    label, conf, available = cs.classify(_obs())
    assert available is True
    assert label == "unknown"
    assert conf is not None and conf < cs.CONFIDENCE_THRESHOLD


def test_high_confidence_returns_class():
    cs._model._model = _FakeModel([[0.8, 0.1, 0.05, 0.05]], ["call", "bulk", "stream", "game"])
    cs._model._loaded = True
    label, conf, available = cs.classify(_obs())
    assert available is True
    assert label == "call"
    assert conf == pytest.approx(0.8)


def test_feature_extraction_uses_lab_counters():
    features = cs.extract_features(_obs())
    assert features["download_mbps"] == 50.0
    assert features["direction_ratio_up"] is not None
    assert 0.0 < features["direction_ratio_up"] < 1.0
    assert features["mean_packet_size_bytes"] is not None
    assert features["mean_packet_size_bytes"] > 0


def test_feature_extraction_handles_missing_counters():
    obs = TelemetryObservation(
        metadata={
            "observed_at": datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc),
            "source": "linux_namespace_lab",
            "scope": "client",
            "quality": "measured",
            "environment": "simulated_lab",
            "client_id": "client-aaaaaaaaaaa1",
        },
        download_mbps=10.0,
        upload_mbps=2.0,
    )
    features = cs.extract_features(obs)
    assert features["direction_ratio_up"] is None
    assert features["mean_packet_size_bytes"] is None
    assert features["rate_ratio_down"] is not None


def test_status_reports_unavailable_with_honest_note():
    cs._model.reset()
    result = cs.status()
    assert isinstance(result, ClassifierStatus)
    assert result.available is False
    assert result.held_out_f1 is None
    assert "no labelled" in result.training_note.lower() or "helper_missing" in result.training_note.lower()


def test_status_has_no_private_identifiers():
    result = cs.status()
    text = result.model_dump_json()
    for token in ("127.0.0.1", "10.50.0.1", "client-", "/usr/", "br-lab"):
        assert token not in text


def test_label_correction_request_rejects_extra_fields():
    with pytest.raises(ValidationError):
        LabelCorrectionRequest(corrected_label="bulk", leak="x")  # type: ignore[arg-type]


def test_label_correction_request_rejects_invalid_label():
    with pytest.raises(ValidationError):
        LabelCorrectionRequest(corrected_label="video_call")  # type: ignore[arg-type]


def test_store_correction_persists_and_never_trains(monkeypatch, tmp_path):
    db = tmp_path / "corrections.sqlite3"
    monkeypatch.setattr(cs, "CORRECTIONS_DB", db)
    response = cs.store_correction("client-aaaaaaaaaaa1", "bulk", note="wrong")
    assert response.accepted is True
    assert response.training_triggered is False
    rows = cs.list_corrections()
    assert len(rows) == 1
    assert rows[0]["corrected_label"] == "bulk"
