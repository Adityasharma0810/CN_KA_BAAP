"""Build the exported forecaster's feature vector from live lab observations.

The LightGBM models were trained on offline collector CSVs with a fixed
schema (client1/2/3 + aggregate rates, configured capacity, cadence flags).
This module maps the live per-client (anonymous) and aggregate-gateway
observations onto that same ``TelemetrySample`` schema so the exported models
can score without retraining.

Limitations (documented, honest):
  * The 3 lab clients are mapped to client1/2/3 by their slot number.
  * ``configured_capacity_mbps`` is the current Kalman capacity estimate,
    assumed roughly constant over the recent window.  When no estimate is
    available it is ``None`` and the model relies on rate features (or the
    gate falls back to persistence).
  * ``sample_cadence_valid`` is set ``True`` under the assumption that the 2 s
    ingest cadence is regular; the persistence-vs-model gate catches errors
    from cadence gaps.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import datetime
from typing import Iterable

from ml.forecasting.features import generate_features
from ml.forecasting.schema import CLIENT_NAMES, TelemetrySample

MIN_SAMPLES = 31
# Client and aggregate observations in the same ingest cycle are timestamped a
# fraction of a millisecond apart, so they are aligned by nearest timestamp
# within this tolerance (well under the ~2 s ingest interval).
ALIGN_TOLERANCE_S = 1.0


def build_live_feature_row(
    client_observations: Iterable,
    aggregate_observations: Iterable,
    client_slots: dict[str, int],
    capacity_mbps: float | None,
    *,
    min_samples: int = MIN_SAMPLES,
) -> tuple[dict[str, float | None], int] | None:
    """Return ``(feature_row, sample_count)`` for the most recent sample.

    ``client_observations`` and ``aggregate_observations`` are
    ``TelemetryObservation`` objects (any order).  ``client_slots`` maps
    client_id -> slot number (1/2/3).  Returns ``None`` when fewer than
    ``min_samples`` aligned timestamps are available.
    """
    by_ts_clients: dict[datetime, dict[str, object]] = defaultdict(dict)
    client_ts: list[datetime] = []
    for obs in client_observations:
        cid = obs.metadata.client_id
        if cid is None:
            continue
        ts = obs.metadata.observed_at
        by_ts_clients[ts][cid] = obs
        client_ts.append(ts)
    client_ts = sorted(set(client_ts))

    by_ts_agg: dict[datetime, object] = {}
    for obs in aggregate_observations:
        by_ts_agg[obs.metadata.observed_at] = obs

    # Align each aggregate timestamp to the nearest client timestamp within the
    # tolerance (same ingest cycle).  Key the aligned sample by the client ts.
    aligned: list[tuple[datetime, object]] = []
    for agg_ts, agg in by_ts_agg.items():
        idx = bisect.bisect_left(client_ts, agg_ts)
        nearest: datetime | None = None
        best_gap = None
        if idx > 0:
            candidate = client_ts[idx - 1]
            gap = abs((candidate - agg_ts).total_seconds())
            if best_gap is None or gap < best_gap:
                best_gap, nearest = gap, candidate
        if idx < len(client_ts):
            candidate = client_ts[idx]
            gap = abs((candidate - agg_ts).total_seconds())
            if best_gap is None or gap < best_gap:
                best_gap, nearest = gap, candidate
        if nearest is not None and best_gap is not None and best_gap <= ALIGN_TOLERANCE_S:
            aligned.append((nearest, agg))

    aligned.sort(key=lambda pair: pair[0])
    if len(aligned) < min_samples:
        return None
    aligned = aligned[-min_samples:]
    first_ts = aligned[0][0]

    # Map slot number -> client_id once.
    slot_to_client: dict[int, str | None] = {}
    for name in CLIENT_NAMES:
        slot = int(name.removeprefix("client"))
        slot_to_client[slot] = next(
            (cid for cid, num in client_slots.items() if num == slot), None
        )

    samples: list[TelemetrySample] = []
    for seq, (ts, agg) in enumerate(aligned):
        client_map = by_ts_clients[ts]
        client_rates: dict[str, dict[str, float | None]] = {}
        for name in CLIENT_NAMES:
            slot = int(name.removeprefix("client"))
            cid = slot_to_client.get(slot)
            obs = client_map.get(cid) if cid else None
            client_rates[name] = {
                "down": obs.download_mbps if obs is not None else None,
                "up": obs.upload_mbps if obs is not None else None,
            }
        elapsed = (ts - first_ts).total_seconds()
        samples.append(
            TelemetrySample(
                schema_version="1.1",
                scenario_id="live",
                run_id="live",
                sample_seq=seq,
                timestamp_utc=ts,
                elapsed_s=float(elapsed),
                sample_interval_s=2.0,
                configured_capacity_mbps=capacity_mbps,
                capacity_config_valid=(
                    capacity_mbps is not None and capacity_mbps > 0
                ),
                sample_timing_valid=True,
                client_rates_mbps=client_rates,
                aggregate_rates_mbps={
                    "down": agg.download_mbps,
                    "up": agg.upload_mbps,
                },
                sample_interval_target_s=2.0,
                sample_cadence_tolerance_s=1.0,
                sample_cadence_valid=True,
                scenario_type="live",
            )
        )

    rows = generate_features(samples)
    if not rows:
        return None
    return rows[-1].values, len(aligned)
