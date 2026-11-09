# Network Capacity Forecaster — V1 Technical Specification

**Status:** Approved design; an initial offline pipeline is implemented. No collector datasets or trained models are available, and no controller integration is implemented.

## 1. Forecasting problem definition

### Target

V1 predicts **configured shared bottleneck capacity** in the Linux gateway lab. Let \(C_t\) be the configured rate, in Mbit/s, of the root TBF qdisc on bridge `br-lab` at time \(t\). The desired forecasts are:

- \(\hat C_{t+5}\): capacity at the timestamp five seconds after the forecast origin.
- \(\hat C_{t+10}\): capacity ten seconds after the forecast origin.
- \(\hat C_{t+30}\): capacity thirty seconds after the forecast origin.

Each prediction is a scalar in Mbit/s, issued using information available at \(t\). Labels are the configured rate active at the corresponding future time, not measured traffic rate. The primary target is the shared bridge bottleneck, not per-client throughput, link speed, or residual/available bandwidth.

In the current lab, [scripts/set_bottleneck.sh](../scripts/set_bottleneck.sh) applies `tc qdisc replace dev br-lab root tbf rate "${RATE}mbit"` with a configured 50 ms queue. The experiment harnesses define `BUDGET = 100` Mbit/s and apply it through that script. The setting is controlled by the experiment, not inferred from traffic. V1 should store that applied configuration explicitly and confirm command success. It must not infer \(C_t\) from a throughput measurement.

### Why throughput is not capacity

Observed throughput is traffic that successfully crossed a measurement point during a time interval. It depends on offered traffic, protocol behavior, competing flows, per-client shaping, congestion, queueing, loss, and timing. A client offering 5 Mbit/s cannot demonstrate that a 100 Mbit/s bottleneck has only 5 Mbit/s capacity; a saturated client may receive less than the configured capacity due to competition or overhead. Likewise, summing observed client rates is not a reliable capacity estimate in all conditions.

Store configured capacity and observed throughput in separate fields. A low observed rate is not evidence that the configured capacity dropped. V1 is a controlled laboratory forecast of a scripted `tc` setting, **not** a real-world ISP available-bandwidth estimator.

### Forecast origin and cadence

The dataset cadence is one row per nominal one-second sample per run. Each row needs both a UTC timestamp for cross-run provenance and a monotonic elapsed time/sequence for ordering and elapsed-time calculations. Forecasts are generated at a sample boundary using only that sample and earlier available information. The actual elapsed interval must be recorded because a one-second sleep does not guarantee an exact one-second interval.

## 2. Dataset collection design

### Existing reusable behavior

- [gateway/collector.py](../gateway/collector.py) reads bridge-side veth sysfs byte counters at `/sys/class/net/veth-cN-br/statistics`. It maps bridge `tx_bytes` to client download and `rx_bytes` to client upload, differences successive counters, divides by measured monotonic elapsed time, and prints rates. It samples nominally once per second.
- [gateway/api.py](../gateway/api.py) independently samples the same byte counters, stores rounded per-client download/upload Mbit/s in process memory, and exposes current values through `GET /clients`. It does not persist samples. Its policy loop is separate and runs every three seconds.
- [scripts/setup_gateway.sh](../scripts/setup_gateway.sh) creates `br-lab` and three client namespaces with veth pairs. The shared TBF bottleneck is applied separately using `set_bottleneck.sh`.
- [experiments/run_call_vs_download.py](../experiments/run_call_vs_download.py) and [experiments/run_streaming_vs_download.py](../experiments/run_streaming_vs_download.py) launch controlled traffic and set a 100 Mbit/s bottleneck. They write aggregate run/mode result CSVs and raw command text under `/tmp`; neither records a one-second capacity/telemetry time series.

### Proposed collector behavior — not implemented

Add a dedicated, read-only dataset collector for the lab. Reuse the counter-direction mapping and elapsed-time rate calculation from `gateway/collector.py`, but separate recording from `gateway/api.py` and its controller/policy loop. The collector should not apply limits, change the bottleneck, set intents, or invoke the controller.

1. A scenario runner creates a unique `scenario_id`, a unique `run_id`, and a recorded random seed (including seed-generation method/version). Record the scenario definition, traffic-generator command/configuration, tool versions, host/lab description, and start/end markers as run metadata.
2. The scenario runner applies a specified bottleneck schedule using the existing script or equivalent checked `tc` operations. Log every requested rate change, its monotonic and UTC times, command exit status, and resulting configured qdisc state where independently read back. A successful command requested at a time is not itself proof that the qdisc remained active throughout the run.
3. Start the recorder before traffic and continue through explicitly marked warm-up, measured, transition, and recovery phases. Use a single monotonic clock for relative sample and event time. Record UTC timestamps too.
4. Sample cumulative byte counters for all client veths and any selected gateway qdisc counters. Compute rates using actual elapsed seconds; retain raw counter values and intervals so derived rates can be audited. Do not silently fill failed reads, counter resets, or missed samples.
5. Append records incrementally to a durable run-scoped output (CSV is sufficient for the first dataset) and flush periodically. On interruption, preserve the partial run and mark it incomplete rather than treating it as a valid complete sequence.
6. Store run-local client slot identifiers (`client1`..`client3`) rather than the collector's random display IDs as durable identity. The latter are regenerated on process restart and are not stable. Do not record IP/MAC addresses or packet payloads.

The current `gateway/collector.py` only prints rates and assigns random in-memory IDs; the API keeps current rates in memory. Neither is a timestamped data logger. Recording scenario/run/seed metadata, actual capacity changes, additional metrics, and completeness status are all **proposed and unimplemented**.

## 3. Proposed dataset schema

Use one row per sample timestamp and run, with fixed columns for the three known lab slots. Keep metadata in the same row for a straightforward CSV initially; a normalized run-metadata sidecar can be considered later. Types below are logical types; CSV serialization needs a documented null representation and schema version.

| Column(s) | Type | Unit | Description | Role / current availability |
|---|---|---|---|---|
| `schema_version` | string | — | Dataset schema version. | Metadata; proposed. |
| `scenario_id` | string | — | ID shared by repetitions of a scenario design. | Metadata; proposed, not currently recorded. |
| `run_id` | string | — | Unique ID for one execution, used for grouping/splitting. | Metadata; proposed, not currently recorded. |
| `random_seed` | integer or null | — | Seed passed to scenario/traffic randomization; null only when no RNG is used, with method documented. | Metadata; proposed. Existing harnesses do not define or record a seed. |
| `scenario_type` | string | — | For example `constant`, `periodic`, `step_drop`, `ramp`, or `recovery`. | Metadata; proposed. |
| `phase` | string | — | For example `warmup`, `measured`, `transition`, `recovery`. | Metadata; proposed. |
| `sample_seq` | integer | sample index | Increasing run-local sample sequence. | Metadata/order; proposed. |
| `timestamp_utc` | ISO-8601 string | UTC | Wall-clock timestamp when counters/configuration are sampled. | Metadata; proposed. The current gateway API does not timestamp its in-memory samples. |
| `elapsed_s` | float | s | Monotonic elapsed seconds from run start. | Metadata/time feature; proposed. |
| `sample_interval_s` | float | s | Actual elapsed time since the prior valid counter snapshot. | Metadata/quality control; proposed. Required for correct rate derivation. |
| `configured_capacity_mbps` | float | Mbit/s | Shared `br-lab` root TBF rate active at this sample, from the applied configuration/state. | **Target source and current-capacity input.** The harness configures 100 Mbit/s, and the script applies a whole-number rate; no sample-level capacity history/readback currently exists. |
| `capacity_config_source` | string | — | How current configured capacity was established/read (e.g. scenario event and qdisc readback). | Provenance metadata; proposed. |
| `capacity_config_valid` | boolean | — | Whether the collector can establish a valid current configured capacity for this timestamp. | Label/data quality; proposed. |
| `capacity_change_event` | boolean | — | Marks a sample associated with a configured-rate transition, with transition timing governed by a documented convention. | Metadata/feature candidate; proposed. |
| `client1_down_bytes`, `client1_up_bytes` (and client2/client3 equivalents) | integer | bytes | Cumulative bridge-side veth counters. Download maps to bridge `tx_bytes`; upload maps to bridge `rx_bytes`. | Raw telemetry input; underlying byte counters currently read by `gateway/collector.py`, but the raw values are not persisted. |
| `client1_down_mbps`, `client1_up_mbps` (and client2/client3 equivalents) | float | Mbit/s | Per-client directional counter deltas divided by actual sample interval. | Input features. Derived and printed by the collector/API today; not persisted. |
| `aggregate_down_mbps`, `aggregate_up_mbps` | float | Mbit/s | Sum of the three per-client directional rates for that sample. | Input features; proposed derived values. These are observed throughput, **not** capacity. |
| `clientN_active_flows` | integer or null | flows | Number of active flows attributed to a client at sample time. | Candidate feature; **not currently measured**. Requires flow instrumentation or generator-side lifecycle accounting; null is not zero. |
| `clientN_offered_load_mbps` | float or null | Mbit/s | Generator-configured intended/offered load for a client, if known. | Candidate demand feature; **not currently measured** by the gateway. Generator parameters may be known from scenario metadata, but configured rate is not guaranteed actual offered demand (e.g. iperf3 TCP pacing behavior). |
| `clientN_limit_down_mbps`, `clientN_limit_up_mbps` | float or null | Mbit/s | Per-client configured `tc` limit, where available. | Context feature; API tracks its own limits in memory and manual script changes are invisible to it. Requires direct state/event recording for dependable data. |
| `rtt_probe_target` | string or null | — | Explicit lab target used for an RTT probe. | Metadata; current experiment ping targets bridge `10.50.0.1`; no general gateway time-series target is configured. |
| `rtt_avg_ms`, `rtt_p95_ms` | float or null | ms | RTT summary over a clearly defined sample window. | Candidate input features; not currently stored per second. The experiment scripts summarize ping for a whole run; their ping is client1-to-bridge, not a WAN capacity probe. A one-second probe stream/window would be new instrumentation. |
| `jitter_ms` | float or null | ms | Defined RTT or traffic jitter statistic; definition and window must be fixed in schema documentation. | Candidate feature; not currently sampled continuously. Existing reports include call UDP jitter for a whole experiment and streaming RTT averages, not per-second jitter. |
| `packet_loss_pct` | float or null | percent | Loss with measurement method, population, and sample window fixed. | Candidate feature; not currently a gateway time series. Call experiment parses an iperf3 UDP call's run summary; this is not general link loss. |
| `qdisc_backlog_bytes`, `qdisc_backlog_packets` | integer or null | bytes, packets | Queue backlog for the shared bottleneck, if supported and sampled consistently. | Candidate features; **not currently sampled continuously**. [scripts/call_vs_download.sh](../scripts/call_vs_download.sh) captures a one-time `tc -s` snapshot for selected devices only. |
| `qdisc_drops`, `qdisc_overlimits`, `qdisc_requeues` | integer or null | packets/events | Cumulative qdisc counters since qdisc creation/reset. | Candidate raw telemetry; **not currently collected as a time series**. Requires parsing/reading qdisc statistics and handling counter resets. |
| `traffic_profile` | string | — | Generator profile, e.g. UDP call, paced TCP stream, multi-stream download, or idle. | Metadata; current experiment script command configuration can establish profiles, but the collector does not record them. |
| `controller_policy_enabled`, `policy_budget_mbps`, `clientN_intent` | boolean/float/string or null | — / Mbit/s | Policy state for interpretability of any future-policy runs. | Optional context, **not required for initial capacity forecast**. API holds this in memory. Avoid using as features unless a legitimate, available-at-forecast-time use is established. |
| `run_complete` | boolean | — | Marks a completed run; false for interrupted or invalid runs. | Dataset-quality metadata; proposed. |

`N` in the column names means the run-local slot 1, 2, or 3. Keep raw counters and their derived rates so timestamps, counter reset handling, and rate calculations can be validated. Optional/unavailable measures must be null with missingness preserved; do not convert missing instrumentation to zero. A feature-specific training dataset may select a subset after validation, but raw collection should not discard provenance.

## 4. Dataset-generation scenarios

All schedules below are **proposed**, in the current lab's whole-number Mbit/s range accepted by `set_bottleneck.sh`. No schedule automation currently exists. Each schedule should be repeated with independent run IDs and seeds, and the active rate must be recorded from the configuration/event log separately from observed rates.

| Scenario | Example configured-capacity schedule | Purpose |
|---|---|---|
| Constant | 100 Mbit/s from 0 to 300 s. | Persistence baseline, collection integrity, false-change behavior. |
| Periodic square wave | 80 Mbit/s for 30 s, then 120 Mbit/s for 30 s; repeat for 10 cycles. | Test recurring patterns and seasonal-naive/Holt-Winters behavior. Use multiple periods/phases across scenarios; do not only train and test on the same phase. |
| Sudden drop and hold | 100 Mbit/s until 60 s, 40 Mbit/s from 60–120 s, then 100 Mbit/s. | Measure detection/forecast behavior around an abrupt configured change and recovery. |
| Gradual degradation | 120 Mbit/s initially, lower by 1 Mbit/s every 2 s to 60 Mbit/s, hold, then reverse the ramp. | Test trending capacity changes instead of only steps. |
| Drop, variable hold, recovery | 100 Mbit/s; at a seeded time in a documented range step to 50 Mbit/s for a seeded duration; restore 100 Mbit/s. | Test variation in event timing and duration. The seed and actual event times are required metadata. |
| Traffic-load variation | Repeat selected capacity schedules with idle/light, moderate, and saturating offered traffic; vary concurrent clients, flow count, and direction where the generators support it. | Check whether traffic telemetry helps forecast the configured schedule and expose throughput/capacity confounding. |

These are controlled `tc` schedules, not models of real ISP dynamics. Script changes should be spaced far enough apart for the configured command to apply and the one-second sampler to observe transitions. Record the actual transition time; do not assume an intended schedule boundary aligns perfectly with a sampled timestamp. Generate train/validation/test runs with independent seeds and held-out schedule parameters (such as a different period, amplitude, transition time, or traffic load).

## 5. Feature engineering and leakage controls

Features for a forecast at time \(t\) may only use measurements and known state available at or before \(t\):

- **Capacity history:** current configured capacity and lag values at 1, 2, 5, 10, and 30 seconds; changes in capacity over prior intervals. The current configured value is known in this lab; do not expose future schedule events.
- **Traffic history:** per-client and aggregate upload/download rates, lagged rates, direction ratios (with safe handling of zero denominators), and sum/difference features.
- **Rolling statistics:** trailing-window means, standard deviations, minima/maxima, quantiles, and trend estimates over explicitly trailing 5-, 10-, and 30-second windows. Windows must be entirely at or before \(t\).
- **Rate of change:** first differences and trailing slopes for configured capacity and observed throughput, normalized by actual elapsed time. Do not calculate differences across run boundaries or counter resets.
- **Demand/load:** generator-provided offered load, active flow count, and traffic profile can be useful where known at forecast time. These fields are proposed instrumentation. Actual throughput must not be relabeled as demand; a bottleneck can censor observed offered traffic.
- **Network quality and queues:** trailing latency/jitter/loss and qdisc backlog/drop counters may be candidate inputs after they are measured continuously and their direction, target, definitions, and windows are validated. They are currently incomplete or absent as time series.
- **Time and seasonality:** elapsed time in run, time since a recorded capacity transition, and cyclic encodings of within-day/week time only if data spans meaningful real-world clock cycles. For the controlled lab, periodic schedule phase can support an experimental seasonal model, but must be derived solely from past samples and must not reveal future schedule commands.

Do **not** use `scenario_id`, `run_id`, `random_seed`, future schedule values, future transition timestamps, `phase` if it reveals the future event, or any target-derived future data as model features. Such fields are for grouping, provenance, analysis, or split construction. Scenario family may be used for stratified reporting but should not be a predictor unless that metadata is guaranteed available operationally and the intended use justifies it.

Avoid centered rolling windows, interpolation using future observations, random row splits, fitting transforms on validation/test data, and overlapping target windows across split boundaries. Fit scalers/encoders (if any) and model selection only on training data. A configured-capacity history will make persistence strong in constant and long-hold scenarios; report this rather than disguising it.

## 6. Target construction and data quality

For each valid sample at origin \(t\), construct three independent labels:

- `target_capacity_5s = configured_capacity_mbps(t + 5 s)`
- `target_capacity_10s = configured_capacity_mbps(t + 10 s)`
- `target_capacity_30s = configured_capacity_mbps(t + 30 s)`

Labels come from the verified configured-capacity event/state timeline, not throughput, qdisc rate inferred from achieved traffic, or a model of traffic demand. Capacity schedules are piecewise constant in the proposed lab tests. Define timestamp matching consistently: use the configured state active at the requested future timestamp. Record exact event timestamps and the source of state; if an exact timestamp is missing, do not silently substitute an unrelated nearest sample.

### Missing and irregular samples

- Use `elapsed_s` and `sample_interval_s` to detect jitter and gaps. Define an allowed deviation from the nominal one-second cadence before collection; mark samples outside tolerance invalid for regular-grid feature/target construction.
- Do not forward-fill missing capacity observations without an independent event/state record. For missing telemetry features, retain nulls or exclude affected windows according to a documented model-specific rule.
- Resampling is permitted only with an explicit rule that does not use future information. For configured capacity, reconstruct the timeline from verified change events only when state continuity is known. Do not linearly interpolate a step schedule.
- Handle counter decreases as resets/recreation; invalidate the rate spanning that interval and mark the reset rather than producing a negative rate.
- Exclude a target if the future timestamp is unavailable, the run ends before the horizon, capacity state is invalid, or the target crosses a run boundary. Never join labels across `run_id`s.
- Exclude warm-up or incomplete runs according to a predeclared rule, retaining their raw data and exclusion reason for auditability.

For each horizon, construct features and labels per run independently. At least the final 30 seconds of each run cannot have a 30-second label. Where train/validation/test are chronological within a run, purge at least the maximum 30-second horizon around split boundaries to prevent overlapping windows/targets from leaking.

## 7. Training and evaluation

### Splits

Use independent `run_id` groups, not random sample rows. The preliminary chronological 6/2/2 evaluation requires at least 10 complete, manifest-verified runs. Training must contain at least three scenario types; validation and test must each contain at least one scenario type and two valid configured-capacity values. Keep all derived windows from a run in the same split. Report held-out scenario parameters and traffic loads, and reserve the test set before model selection. Reject unsuitable coverage and collect more runs rather than relying on a random window split.

### Models and baselines

Train separate horizon-specific predictors or one explicitly multi-output design, with a clear and consistent output contract for the three horizons.

- **Persistence baseline:** forecast the currently configured capacity at origin \(t\) for each horizon.
- **Seasonal-naive baseline:** forecast the value at the same phase in the previous observed cycle, using only historical training/forecast-origin data and a season length justified by the schedule. Do not apply a seasonal baseline where no defensible period exists.
- **Holt-Winters:** univariate model of configured capacity history, with additive/multiplicative trend/seasonality chosen based on data properties. Fit without future values; identify the season length from the controlled schedule and test sensitivity. It is a time-series baseline, not a replacement for the supervised model.
- **LightGBM:** supervised model using the lagged/rolling and other eligible features above. Train and tune only on training/validation runs. Consider one model per horizon initially for clarity. An optional wrapper is implemented, but LightGBM is not installed in the current project environment.

The persistence and seasonal-naive baselines, an additive Holt-Winters wrapper, an optional LightGBM wrapper, dataset validation/loading, target and feature generation, and run-level metrics/splitting are implemented in `ml/forecasting/`. No model is currently trained. The raw telemetry directory is absent, so training and held-out evaluation await real collector runs.

The current target builder aligns to monotonic `elapsed_s` within a 0.25-second default tolerance and does not interpolate. For a non-exact match, it requires valid, equal capacity readings bracketing the requested horizon; targets near an observed capacity transition are omitted as ambiguous. Collector schema 1.1 records the requested interval, tolerance, and `sample_cadence_valid`, defined as an actual interval within the configured absolute tolerance of the nominal interval. Samples are scheduled against monotonic deadlines; missed deadlines are skipped, not backfilled. The loader remains able to read schema 1.0 CSVs, but marks their cadence unverified. Feature lags and rolling windows require contiguous cadence-valid intervals; their time basis must not be presumed regular for legacy or invalid-cadence samples.

### Metrics and reporting

Report per-horizon MAE and RMSE in Mbit/s on held-out runs. Also report:

- **Bias / mean error** to detect systematic over- or under-forecasting.
- **Capacity-change direction accuracy** and event timing error for step/ramp scenarios, with an explicit change threshold and event matching rule.
- **Baseline-relative MAE/RMSE improvement** so models are compared to persistence and seasonal-naive, not only to each other.
- Per-scenario, per-capacity-range, per-load, and stable-vs-transition metrics; include sample/run counts and uncertainty across independent runs.

MAPE is not a primary metric because it is unstable or undefined near zero; the proposed positive schedules avoid zero, but MAE/RMSE remain more interpretable. Report prediction clipping policy separately if predictions are constrained to valid configured rates. Do not claim real-network performance from simulated evaluation.

## 8. Proposed implementation structure

The following paths distinguish implemented pipeline modules from remaining recommendations.

```text
experiments/
  capacity_forecasting/
    collect_gateway_telemetry.py   # implemented: time-series collector, no control
    run_scenarios.py               # proposed: schedule/traffic orchestration and IDs/seeds
    validate_dataset.py            # proposed: schema, cadence, labels, completeness checks
    schema.py                      # proposed: raw dataset columns and version
data/
  capacity_forecasting/
    raw/                           # proposed, generated run-scoped CSVs; do not commit by default
    processed/                     # proposed, reproducible feature/target tables
ml/
  forecasting/
    schema.py                      # implemented: collector CSV validation and loading
    features.py                    # implemented: causal lags/rolling features
    targets.py                     # implemented: timestamp-aligned 5/10/30 s labels
    baselines.py                   # implemented: persistence and seasonal-naive
    holt_winters.py                # implemented: additive seasonal Holt-Winters wrapper
    lightgbm_model.py              # implemented: optional LightGBM wrapper
    evaluation.py                  # implemented: chronological run splits and metrics
    train.py                       # proposed: training orchestration and tuning
    evaluate.py                    # proposed: horizon/scenario reporting
    serialization.py               # proposed: versioned model, feature, and metadata save/load
    forecaster.py                  # implemented: public offline pipeline imports
tests/
  unit/
    test_capacity_forecasting_pipeline.py  # implemented
  integration/
    test_capacity_dataset_pipeline.py  # proposed synthetic fixture, no live lab required
```

Keep the collector in `experiments/capacity_forecasting/` or another lab-owned boundary, not inside `gateway/api.py`'s controller loop. The dataset should be versioned and reproducible; generated raw datasets and model artifacts need not be committed. Model serialization should include model/library version, schema version, target definition, horizon, feature names/order, training run IDs/split, configuration, and evaluation summary.

Initially invoke the trained forecaster offline or through a standalone read-only interface. Do not wire it to `gateway/controller.py`, `gateway/policy.py`, `qos/`, or the existing policy loop in this stage. The project has two separate FastAPI apps—`backend/app/main.py` and `gateway/api.py`—documented to use port 8000, so a future online serving design must resolve app/port ownership deliberately rather than adding an unplanned conflicting service. No dependencies should be added until implementation and environment compatibility are addressed.

## 9. Risks and limitations

- **Scripted capacity is predictable by design.** A model may learn the schedule generator or periodic phase rather than general network dynamics. Use held-out runs, seeds, phases, and schedule parameters, and document when future schedule metadata is known. A benchmark with a preannounced schedule is not evidence that the model anticipates an unexpected external event.
- **Unexpected changes are fundamentally difficult.** If the configured `tc` rate changes without a preceding observable signal, a model using only past telemetry cannot know the future change. Evaluate persistence and timing honestly; do not imply advance prediction where there is no predictive information.
- **Configured capacity is not real ISP capacity.** `tc` sets a simulated shared limit over virtual links. It does not characterize an ISP plan, radio conditions, external congestion, or available bandwidth on a household WAN.
- **Demand and throughput are easily confused.** Current gateway counters show bytes that crossed the veth, not unsatisfied demand. Current experiment rates summarize achieved traffic under specific iperf3 configurations. TCP pacing may differ from its requested rate; the streaming harness explicitly warns about this. Treat offered-load configurations as scenario metadata unless their actual semantics are verified.
- **Instrumentation is incomplete.** No continuous queue, qdisc drop, per-second RTT/jitter/loss, active-flow, or offered-demand time series currently exists. The experiment ping and iperf3 summaries have different scopes and aggregation windows. Do not populate schema columns as though they are already measured.
- **Sampling timing matters.** Scheduler delays, process pauses, qdisc replacement, and command latency can shift observations from intended boundaries. Store monotonic timing, actual sample intervals, and capacity transition events; invalidate gaps rather than hiding them.
- **Policy may confound data.** The API's 3-second policy loop and client shaping can affect observed traffic and queue metrics. Initial data-generation runs should keep policy state controlled and recorded; avoid mixing modes without metadata. The collector itself must not alter policy.
- **Small independent sample counts can overstate quality.** The existing reports contain five runs per mode in two scenarios, but their CSVs are run summaries and cannot train a time-series forecaster. Gather many independent runs and assess variability across held-out scenarios.
- **Lab-to-real transfer is untested.** Namespace traffic, a fixed TBF queue, three simulated clients, and scripted schedules differ from live household networks and ISP behavior. V1 claims must remain limited to the controlled laboratory target.

## Next-stage implementation checklist: telemetry dataset collector

- [ ] Implement a dedicated collector that reads the existing per-client byte counters at nominal one-second cadence without changing gateway control behavior.
- [ ] Generate and record `scenario_id`, unique `run_id`, random seed, scenario configuration, traffic profile, and run completeness.
- [ ] Record UTC and monotonic timestamps, sample sequence, actual interval, raw directional counters, and derived per-client/aggregate rates.
- [ ] Record each configured-capacity event and verify/log the active shared `tc` setting separately from observed throughput.
- [ ] Add queue/quality/flow/demand instrumentation only where its measurement method and scope are explicit; otherwise leave proposed columns null/absent in the initial schema.
- [ ] Write append-only, run-scoped raw output; preserve partial runs and mark invalid intervals, resets, missing measurements, and run boundaries.
- [ ] Validate schema, units, cadence, counter resets, event alignment, and separation of capacity labels from throughput before generating any training features.
- [ ] Add focused tests for counter direction/rate calculation, timing jitter/gaps, capacity event logging, and run-boundary integrity.
- [ ] Review the first collected dataset and schema before proceeding to feature engineering or model training.
