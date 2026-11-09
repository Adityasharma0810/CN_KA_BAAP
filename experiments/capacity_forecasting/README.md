# Gateway telemetry dataset collector

This collector records observations from the existing Linux namespace lab. It
does not launch traffic, change `tc` settings, or call the gateway policy. Run
it in a separate terminal alongside an existing experiment to observe the
same traffic and any configured-capacity changes.

## Requirements and permissions

- Python 3.10+ (standard library only; no package installation required).
- The lab from `scripts/setup_gateway.sh` must exist, including `br-lab` and
  `veth-c1-br` through `veth-c3-br`.
- `tc` from iproute2 must be installed. The process needs permission to read
  the veth sysfs counters and inspect `br-lab` qdiscs. If `tc` reports a
  permission error, run the collector with appropriate privileges in the
  isolated lab VM; it never invokes privileged commands to change network
  state.

## Example

From the repository root, with the lab and an experiment already running:

```bash
python3 -m experiments.capacity_forecasting.collect_gateway_telemetry \
  --scenario-id call-vs-download-100mbit \
  --scenario-type constant \
  --random-seed 1234 \
  --traffic-profile udp-call-plus-multi-stream-download \
  --sampling-interval 1 \
  --sampling-tolerance 0.25 \
  --duration 120
```

By default, the collector writes a new, uniquely named CSV under
`data/capacity_forecasting/raw/`. Use `--output-dir PATH` to select another
directory, or `--output-file PATH.csv` to choose an exact new file path.
Existing output files are never overwritten. The CLI prints the generated
`run_id` and output path. `Ctrl+C` flushes the partial CSV, leaves
`run_complete=False`, and returns exit status 130.

Sampling uses monotonic deadlines anchored to run start instead of sleeping
for one interval after each sample's work. Actual sample timestamps and
intervals are recorded. Missed deadlines are skipped; samples are never
duplicated or interpolated. The `sample_cadence_valid` field is true only
when the actual interval is within `--sampling-tolerance` (default 0.25 s)
of `--sampling-interval`. The baseline row has no preceding interval and is
cadence-invalid. Raw counter, capacity, and rate observations are retained
when a sample misses cadence tolerance.

The required scenario ID/type and traffic profile are descriptive metadata;
the collector does not verify the scenario runner's claims or seed traffic
generators. The optional seed is recorded as provided.

## CSV fields and missing values

The versioned CSV contains run/scenario metadata, sample sequence, UTC and
monotonic-relative timestamps, actual sample intervals, verified configured
capacity, per-client raw counters, per-client rates and their counter
intervals, aggregate rates, reset/read status, and run completeness. Clients
use stable lab slot names `client1`, `client2`, and `client3`. Bridge-side
`tx_bytes` is download and `rx_bytes` is upload.

Rates and configured capacity that cannot be established are empty CSV cells,
not zeros. The first sample is a counter baseline and has no rates. A counter
reset marks that direction's rate missing for that sample, then establishes a
new baseline. Missing/failed client reads are recorded in that client's
`*_read_error`; aggregates remain missing unless all three client rates exist.
Capacity is recorded only when `tc -j -d qdisc show dev br-lab` reports exactly
one root TBF qdisc with a valid numeric `options.rate`; iproute2's numeric JSON
rate is bytes per second and is converted to decimal Mbps. `noqueue`, other
qdisc types, malformed output, or command failures produce a missing capacity
and an explicit error. The collector does not fall back to experiment settings
or observed throughput.

Schema 1.1 stores the target interval, tolerance, and cadence-validity flag.
The ML loader still accepts legacy schema 1.0 files, but marks their cadence
unverified because they lack nominal interval/tolerance metadata.

Only the selected capacity and byte-counter fields are collected. This
collector does not fabricate RTT, jitter, packet loss, queue statistics,
active-flow counts, or offered-load measurements.

## API-independent experiment runner

The runner starts no gateway API and does not change controller or policy
state. It uses the existing `scripts/set_bottleneck.sh` workflow, the three
client namespaces, and the collector above. It needs the lab from
`scripts/setup_gateway.sh`, `tc`, `ip`, `iperf3`, reachable iperf3 servers on
`10.50.0.1:5201` and `:5202`, and sudo authorization for the existing
network-control scripts and namespace commands. A third temporary iperf3
server is started on a free port by the runner to provide a distinct endpoint
for client3, then stopped at the end.

From the repository root:

```bash
python3 -m experiments.capacity_forecasting.run_capacity_experiment \
  --scenario constant \
  --scenario-id constant-100mbit \
  --seed 1234 \
  --duration 60 \
  --sampling-interval 1 \
  --sampling-tolerance 0.25
```

Supported `--scenario` values are `constant` (100 Mbps), `step` (100 -> 40 ->
100 Mbps at 0/20/40 seconds), and `periodic` (80/120 Mbps alternating every
10 seconds). Each invocation generates its own run ID and distinct CSV,
metadata JSON, and command logs under `data/capacity_forecasting/raw/` unless
`--output-dir` is supplied. Existing output paths are never overwritten.
Scenario metadata includes the selected capacity schedule, seed, traffic
profile, client/server ports, and seeded client launch offsets.
The runner creates one run ID and passes it explicitly to the collector; the
same ID appears in the CSV filename, every CSV row, collector output, and
manifest.

Before changing the shared qdisc, the runner accepts only the lab's initial
root `noqueue` state. It verifies each TBF rate after using the existing
script and only removes a qdisc at cleanup when it still verifies as the
runner's expected TBF. If state changes unexpectedly, it refuses to replace
or remove that qdisc and records/reports the cleanup failure. On interruption
it stops its traffic, interrupts the collector (leaving an incomplete partial
CSV), stops its temporary server, and attempts the same ownership-checked
qdisc cleanup. The qdisc commands use `sudo -n`; authorize sudo before running
if needed. The runner does not use or require `gateway/api.py`.

## Preliminary offline evaluation

The offline workflow loads only complete CSV/manifest pairs that pass
`ml.forecasting.schema.load_collector_csv`, requires the verified chronological
6/2/2 run-level split, selects model configuration on validation runs, and
evaluates the test runs afterward:

```bash
.venv/bin/python -m experiments.capacity_forecasting.train_offline \
  --output-dir experiments/capacity_forecasting/results/preliminary-<unique-id>
```

The output directory must not already exist. It contains split IDs,
configuration and selection scores, prediction/metric CSVs, training-only
Holt-Winters states, SVG plots, and a report. LightGBM is optional; the
workflow reports it as untrained when its dependency is unavailable and does
not install packages.

## Exporting validation-selected model artifacts

Export one model per horizon using validation predictions only. The exporter
requires at least 30 validation pairs and 80% target coverage for a candidate;
otherwise it records `no_validated_best_model` in metadata and omits that
horizon's pickle file. It reads only the training and validation run CSVs and
does not load test CSVs or test metrics. The destination must not already
exist.

```bash
.venv/bin/python -m experiments.capacity_forecasting.export_best_models \
  --source-dir experiments/capacity_forecasting/results/preliminary_20261108T173000Z \
  --output-dir experiments/capacity_forecasting/models/best
```

The directory contains `best_model_5s.pkl`, `best_model_10s.pkl`,
`best_model_30s.pkl` for horizons with a validated winner, and `metadata.json`.
The metadata records the selected type, validation-only scores and coverage,
training run IDs and configuration, dependencies, and the complete ordered
feature/preprocessing configuration. The exporter reloads each pickle in a
separate Python process and checks that validation predictions are unchanged.

Load a horizon-specific artifact and forecast from features at the current
origin (never from future samples):

```python
import pickle
from pathlib import Path

from ml.forecasting.features import generate_features
from ml.forecasting.schema import load_collector_csv

with Path("experiments/capacity_forecasting/models/best/best_model_10s.pkl").open("rb") as f:
    model = pickle.load(f)

history = load_collector_csv(Path("data/capacity_forecasting/raw/<run-csv>.csv"))
origin_features = generate_features(history)[-1].values
capacity_forecast_mbps = model.predict([origin_features])[0]
```

Use the corresponding pickle for each forecast horizon. For streaming input,
pass the cadence-aware `TelemetrySample` history ending at the forecast origin
to `generate_features`, and supply the latest feature dictionary. Preserve the
feature names and order listed in `metadata.json`; the saved model rejects
incompatible order. Predictions are configured-capacity estimates in Mbps,
not observed-throughput estimates.
