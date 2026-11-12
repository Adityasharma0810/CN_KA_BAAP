"""Train the lab-derived traffic classifier (run-level split, no leakage).

Reads labelled scenario runs from ``data/scenario_runs/`` (manifest
``slot_to_profile`` is the ground-truth label, keyed by slot) and the matching
``observations.csv``.  One feature vector per (run, client) is produced by
averaging each client's samples within the run, so the split is by RUN (never
by random window) and there is no within-run leakage.

The external ISCX models cannot be used here: they need per-flow packet
inter-arrival and active/idle statistics that the lab does not collect.

Evaluation is against a simple rate-rule baseline (accuracy, macro-F1,
confusion matrix).  The trained model, metrics and metadata are written to
``models/classifier/``.

NOTE: today every existing scenario run failed with ``helper_missing`` (zero
throughput), so this script finds no usable labelled data and exits.  Run
labelled scenarios first (the privileged helper must be installed), then:

    .venv/bin/python -m ml.classifier.train
"""

from __future__ import annotations

import csv
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from backend.app.services.classifier_service import (
    CLASSIFIER_CLASSES,
    CONFIDENCE_THRESHOLD,
    extract_features,
)
from backend.app.models.schemas import TelemetryObservation

REPO = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO / "data" / "scenario_runs"
OUT_DIR = REPO / "models" / "classifier"
DB_PATH = REPO / "data" / "experience_budget.sqlite3"
MIN_RUNS = 4  # need enough runs for a held-out split


def _client_slots_from_db() -> dict[str, int]:
    """client_id -> slot from the persisted anonymous_clients table.

    The in-memory lab inventory generates random client_ids per process and
    does not match the ingest-registered ids stored with observations, so the
    durable DB mapping is the authoritative source for labelling.
    """
    mapping: dict[str, int] = {}
    if not DB_PATH.is_file():
        return mapping
    connection = sqlite3.connect(str(DB_PATH))
    try:
        for row in connection.execute(
            "SELECT client_id, simulated_lab_slot FROM anonymous_clients"
        ):
            mapping[str(row[0])] = int(row[1])
    finally:
        connection.close()
    return mapping


def split_run_ids(run_ids):
    """Split run IDs into (train_run_ids, test_run_ids) by RUN, never random.

    The last ~25% of runs (sorted) are held out for testing; no run appears in
    both splits. Deterministic (no random window) so there is no leakage.
    """
    ordered = sorted(set(run_ids))
    if not ordered:
        return [], []
    if len(ordered) < MIN_RUNS:
        # Too few runs for a meaningful held-out split.
        return list(ordered), []
    split = max(1, len(ordered) // 4)
    test_runs = set(ordered[-split:])
    train_runs = [r for r in ordered if r not in test_runs]
    return train_runs, sorted(test_runs)


def _slot_for_client(client_id: str, slots: dict[str, int]) -> int | None:
    return slots.get(client_id)


def read_labelled_runs() -> list[dict]:
    """Return one feature dict + label per (run, client) with a known class.

    Skips runs whose outcome is an error (e.g. helper_missing) and clients
    whose slot has no declared profile.
    """
    slots = _client_slots_from_db()
    runs: dict[str, list] = defaultdict(list)
    for run_dir in sorted(RUNS_DIR.iterdir() if RUNS_DIR.is_dir() else []):
        manifest_path = run_dir / "manifest.json"
        obs_path = run_dir / "observations.csv"
        if not manifest_path.is_file() or not obs_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("outcome", {}).get("status") == "error":
            continue
        slot_to_profile = manifest.get("slot_to_profile", {})
        if not slot_to_profile:
            continue
        with obs_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("scope") != "client":
                    continue
                client_id = row.get("client_id")
                slot = _slot_for_client(client_id, slots) if client_id else None
                label = slot_to_profile.get(str(slot)) if slot else None
                if label is None:
                    continue
                try:
                    obs = TelemetryObservation(
                        metadata={
                            "observed_at": row["observed_at"],
                            "source": "linux_namespace_lab",
                            "scope": "client",
                            "quality": "measured",
                            "environment": "simulated_lab",
                            "client_id": client_id,
                        },
                        download_mbps=_f(row.get("download_mbps")),
                        upload_mbps=_f(row.get("upload_mbps")),
                    )
                except Exception:  # noqa: BLE001
                    continue
                features = extract_features(obs)
                runs[manifest["run_id"]].append(
                    {"label": label, "features": features, "client_id": client_id}
                )
    # Average features per (run, client) -> one sample per client per run.
    samples = []
    for run_id, items in runs.items():
        by_client: dict[str, list] = defaultdict(list)
        for item in items:
            by_client[item["client_id"]].append(item)
        for client_id, client_items in by_client.items():
            agg = _median_features([i["features"] for i in client_items])
            samples.append({"run_id": run_id, "label": client_items[0]["label"], "features": agg})
    return samples


def _f(value):
    if value is None or value == "":
        return None
    try:
        v = float(value)
        return v if v == v else None  # NaN check
    except (TypeError, ValueError):
        return None


def _median_features(rows):
    """Median of each feature across a client's run samples.

    Median (not mean) is used so a single counter-reset rate spike does not
    corrupt the aggregated feature vector.
    """
    import statistics

    keys = rows[0].keys()
    out = {}
    for k in keys:
        vals = [r[k] for r in rows if r[k] is not None]
        out[k] = statistics.median(vals) if vals else None
    return out


FEATURE_ORDER = [
    "download_mbps",
    "upload_mbps",
    "rate_ratio_down",
    "direction_ratio_up",
    "mean_packet_size_bytes",
]


def rate_rule_baseline(features: dict) -> str:
    """Simple deterministic rate-rule baseline (no ports available in the lab)."""
    down = features.get("download_mbps") or 0.0
    up = features.get("upload_mbps") or 0.0
    ratio = features.get("rate_ratio_down")
    if down > 40:
        return "bulk"
    if ratio is not None and ratio < 0.6 and down < 5:
        return "call"
    if down > 8:
        return "stream"
    return "unknown"


def train_and_evaluate():
    """Train a RandomForest, evaluate vs the rate-rule baseline, save artifacts."""
    samples = read_labelled_runs()
    if len({s["run_id"] for s in samples}) < MIN_RUNS:
        print(
            f"Not enough labelled runs to train (found {len({s['run_id'] for s in samples})}; "
            f"need {MIN_RUNS}). All existing runs failed with helper_missing. "
            "Run labelled scenarios with the privileged helper installed, then retry."
        )
        return

    try:
        import joblib
        import numpy as np
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.impute import SimpleImputer
        from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
        from sklearn.pipeline import Pipeline
    except ImportError:
        print("scikit-learn / joblib not installed; cannot train.")
        return

    run_ids = sorted({s["run_id"] for s in samples})
    train_runs, test_runs = split_run_ids(run_ids)
    train = [s for s in samples if s["run_id"] in set(train_runs)]
    test = [s for s in samples if s["run_id"] in set(test_runs)]

    def matrix(rows):
        return np.asarray([[r["features"].get(k) for k in FEATURE_ORDER] for r in rows], dtype=float)

    y_train = [s["label"] for s in train]
    y_test = [s["label"] for s in test]
    clf = Pipeline(
        [("imputer", SimpleImputer(strategy="median")), ("rf", RandomForestClassifier(n_estimators=80, random_state=2026, class_weight="balanced"))]
    )
    clf.fit(matrix(train), y_train)
    pred = list(clf.predict(matrix(test)))
    baseline = [rate_rule_baseline(s["features"]) for s in test]

    acc = accuracy_score(y_test, pred)
    f1 = f1_score(y_test, pred, average="macro", zero_division=0)
    b_acc = accuracy_score(y_test, baseline)
    b_f1 = f1_score(y_test, baseline, average="macro", zero_division=0)
    labels = sorted(set(y_test) | set(pred))
    cm = confusion_matrix(y_test, pred, labels=labels).tolist()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, OUT_DIR / "classifier.joblib")
    metadata = {
        "version": "1.0",
        "feature_order": FEATURE_ORDER,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "classes": list(CLASSIFIER_CLASSES),
        "held_out_f1": float(f1),
        "held_out_accuracy": float(acc),
        "baseline_f1": float(b_f1),
        "baseline_accuracy": float(b_acc),
        "confusion_matrix": cm,
        "labels": labels,
        "train_runs": [r for r in run_ids if r not in test_runs],
        "test_runs": sorted(test_runs),
        "split": "by run id; last 25% held out",
        "training_note": (
            f"Trained on lab-derived features (rates, direction ratio, mean "
            f"packet size) labelled by scenario run manifests. Held out "
            f"{len(test_runs)} run(s) / {len(test)} samples; held-out classes: "
            f"{sorted(set(y_test))}. With only {len(run_ids)} labelled runs the "
            f"held-out is too small to be a meaningful validation (and does not "
            f"cover all classes), so the F1 is preliminary and likely overfit. "
            f"External ISCX models were not used (per-flow packet features "
            f"unavailable). Lab-scripted/emulated data only; results do not "
            f"prove real-ISP performance."
        ),
    }
    (OUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Trained. held-out F1={f1:.3f} (baseline {b_f1:.3f}), accuracy={acc:.3f} (baseline {b_acc:.3f}).")
    print(f"Saved model + metadata to {OUT_DIR}.")


if __name__ == "__main__":
    train_and_evaluate()
