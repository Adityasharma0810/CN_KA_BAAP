# QoE Degradation Warner — Runtime Guide

This guide covers **only the QoE predictor** from Experience Budget Runtime 1.0. It explains the files required, the input record schema, the output schema, and how to call the predictor from Python.

## 1. What the QoE model predicts

The QoE component is a **LightGBM binary classifier**. It estimates whether a device that is currently not in the red state is likely to enter a poor-QoE (`red`) state within a selected future horizon.

Two trained horizons are included:

| `horizon_s` | Meaning | Runtime alert threshold (`p_red`) |
|---:|---|---:|
| `5` | Predict the red event about 5 seconds ahead | `0.34882934` |
| `10` | Predict the red event about 10 seconds ahead | `0.42959960` |

The default is **10 seconds**. These thresholds are stored inside `qoe_predictor.joblib`; do not hard-code them into your application. `p_red` is a model probability in the range 0–1, and `alert` becomes `true` when it reaches the selected model threshold.

The current-state red cutoff is also stored in the model bundle: `qoe < 0.5` is treated as already red. A current red device is returned with `state="red"`, `alert=false`, and `p_red=null`; handle that as an **already-degraded condition**, not as a successful early warning.

## 2. Files required to run QoE only

Keep these four files in the same directory:

| File | Required? | Purpose |
|---|---|---|
| `eb_runtime.py` | Yes | Runtime class, feature construction, history tracking, and `push()` API |
| `config.json` | Yes | Enables the QoE predictor and records runtime configuration/verdicts |
| `qoe_predictor.joblib` | Yes | Trained LightGBM models for 5-second and 10-second horizons, model thresholds, feature list, and fallback settings |
| `requirements.txt` | Yes | Python package versions used by this bundle |

Not needed for QoE-only inference:

- `flow_classifier.joblib` — only for flow classification.
- `capacity_forecaster.joblib` — only for capacity forecasting.
- `smoke_test.py` — the supplied smoke test exercises all three models, not just QoE.
- The `eb_results` CSV/CSV.GZ files, charts, and report — evaluation/training artifacts; the runtime does not read them.

The QoE-only package in this ZIP omits the two unrelated model files and marks their flags disabled in its copy of `config.json`. The QoE predictor remains enabled.

## 3. Installation

Use a Python environment compatible with the pinned versions in `requirements.txt`. From PowerShell on Windows:

```powershell
cd qoe_only_bundle
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

On Linux/macOS, activate the environment with:

```bash
source .venv/bin/activate
```

## 4. How to create and call the QoE warner

```python
from eb_runtime import ExperienceBudgetModels

# Load config.json and qoe_predictor.joblib from the current directory.
eb = ExperienceBudgetModels.load(".")

# Supported values are 5 and 10. Default is 10 seconds.
warner = eb.qoe_warner(horizon_s=10)

# Call once per second for each device, in chronological order.
result = warner.push("device-1", 0, record)
print(result)
```

Create **one `warner` instance for the running process** and reuse it for all devices. The runtime keeps separate rolling history for each `device` ID. Do not create a new warner on every request, or it will lose the history used to derive lag and rolling features.

## 5. Input schema

The API is:

```python
warner.push(device, t_sec, record)
```

| Argument / key | Python type | Unit / expected values | Required? | Meaning |
|---|---|---|---|---|
| `device` | `str` (or another hashable ID) | Stable ID, e.g. `"device-1"` | Yes | Selects the per-device history buffer |
| `t_sec` | `int` or `float` | Timestamp/elapsed time in seconds | Yes by API | Sample time supplied by caller. **Current runtime does not read or validate this value**; keep calls one second apart and in order yourself. |
| `qdelay_ms` | `int` or `float` | milliseconds | Yes for meaningful inference | Current network queue delay |
| `rho` | `int` or `float` | Dimensionless load/utilisation indicator | Yes | Current network load indicator. Do not automatically clamp it to 0–1; the training data includes values above 1. |
| `cap` | `int` or `float` | Mbps | Yes | Current estimated network capacity |
| `mode_fq` | `int` or `bool` | `0` or `1` | Recommended | Scheduler/mode flag, encoded the same way as the training pipeline. Defaults to `0` if omitted. |
| `n_call_net` | `int` | count, 0 or greater | Recommended | Number of active call flows on the network. Defaults to `0`. |
| `n_game_net` | `int` | count, 0 or greater | Recommended | Number of active game flows on the network. Defaults to `0`. |
| `n_stream_net` | `int` | count, 0 or greater | Recommended | Number of active streaming flows on the network. Defaults to `0`. |
| `n_bulk_net` | `int` | count, 0 or greater | Recommended | Number of active bulk-transfer flows on the network. Defaults to `0`. |
| `delay` | `int` or `float` | milliseconds | Required when `qoe` is active | Current device-level delay/RTT measurement, using the same definition as the upstream telemetry pipeline |
| `jitter` | `int` or `float` | milliseconds | Required when `qoe` is active | Current device-level jitter |
| `loss` | `int` or `float` | fraction from `0` to `1` | Required when `qoe` is active | Current device-level packet-loss ratio. Example: 0.01 means 1%; do not pass `1` to mean 1%. |
| `thr` | `int` or `float` | Mbps | Required when `qoe` is active | Current device-level measured throughput |
| `n_flows` | `int` | count, 0 or greater | Required when `qoe` is active | Number of active flows for this device |
| `has_call` | `int` or `bool` | `0` or `1` | Required when `qoe` is active | Whether this device currently has a call flow |
| `has_game` | `int` or `bool` | `0` or `1` | Required when `qoe` is active | Whether this device currently has a game flow |
| `has_stream` | `int` or `bool` | `0` or `1` | Required when `qoe` is active | Whether this device currently has a stream flow |
| `has_bulk` | `int` or `bool` | `0` or `1` | Required when `qoe` is active | Whether this device currently has a bulk-transfer flow |
| `qoe` | `int` or `float`, or `None` | Score from `0` to `1` | Required for prediction | **Current device QoE score.** The runtime expects you to calculate/supply this score; it does not calculate QoE from raw metrics. `None` or omission means the device is inactive and no prediction is made. |
| `buf_min` | `int` or `float`, or `None` | seconds | Optional | Minimum current stream playback-buffer level for the device. Use `None` when unavailable/not applicable. The runtime substitutes `40.0` for the current buffer feature when this value is missing. |

The runtime is permissive: most missing numeric fields become `NaN` rather than raising a validation error. LightGBM can process missing values, but missing telemetry can reduce prediction quality. Supply the full record whenever the device is active.

### Example input record

```python
record = {
    # Network-wide measurements (repeat the current network snapshot
    # in each device's record for that second).
    "qdelay_ms": 8.0,
    "rho": 0.82,
    "cap": 100.0,
    "mode_fq": 0,
    "n_call_net": 1,
    "n_game_net": 0,
    "n_stream_net": 1,
    "n_bulk_net": 1,

    # Measurements for this particular device.
    "delay": 35.0,
    "jitter": 4.0,
    "loss": 0.001,
    "thr": 8.0,
    "n_flows": 1,
    "has_call": 1,
    "has_game": 0,
    "has_stream": 0,
    "has_bulk": 0,
    "qoe": 0.92,
    "buf_min": 18.0,
}
```

`qoe` is especially important. The model card describes the training QoE values as proxy scores (call, game, stream, and bulk use different proxy calculations). The bundle does not expose a standalone production QoE-scoring API. Your data-collection/application layer must provide a score on the same 0–1 scale and with a comparable definition.

## 6. Output schema

`push()` returns a Python `dict`. Depending on the device state, some keys are intentionally absent.

| Output key | Python type | Meaning |
|---|---|---|
| `state` | `str` | One of `"inactive"`, `"red"`, or `"ok"` |
| `alert` | `bool` | `True` when the selected predictor's probability crosses its stored threshold. In the current-red and inactive branches it is `False`. |
| `p_red` | `float` or `None` | Estimated probability of a future red/degraded event. `None` when inactive, already red, or using the non-ML fallback. |
| `qoe` | `float` | Current input QoE score; returned in the active `red` and `ok` branches |
| `source` | `str` | `"ml"` when LightGBM is used; `"qoe_level_rule"` when the model is disabled and the rule fallback is used. Omitted for inactive/current-red branches. |
| `features` | `dict[str, float]` | The 31 features built internally for an active `ok` record. Omitted for inactive/current-red branches. |

### Output examples

Model active, device currently OK:

```python
{
    "state": "ok",
    "alert": True,          # or False
    "p_red": 0.72,          # illustrative probability, range 0..1
    "qoe": 0.92,
    "source": "ml",
    "features": { ... }     # 31 numeric model features
}
```

Device already below the current red cutoff (`qoe < 0.5`):

```python
{
    "state": "red",
    "alert": False,
    "p_red": None,
    "qoe": 0.42
}
```

No active device QoE score (`qoe` omitted or `None`):

```python
{
    "state": "inactive",
    "alert": False,
    "p_red": None
}
```

When the model is disabled in `config.json`, the runtime returns `source="qoe_level_rule"` and uses its stored QoE-level fallback (`qoe < 0.75` for 5 seconds; `qoe < 0.85` for 10 seconds) instead of producing a model probability.

## 7. Features created internally

You do **not** need to calculate these 31 fields yourself. The runtime derives them from the input record and its per-device history. The `features` output contains them as numeric Python floats; early history may produce `NaN` values.

| Feature(s) | How runtime derives/uses it |
|---|---|
| `qdelay_ms`, `qd_d3`, `qd_d10`, `qd_max10` | Current queue delay; change versus 3 and 10 samples earlier; maximum queue delay in the recent 10-sample window |
| `rho`, `rho_d5` | Current network load indicator and change versus 5 samples earlier |
| `cap`, `cap_ratio5`, `cap_ratio15` | Current capacity and current capacity divided by capacity 5/15 samples earlier |
| `mode_fq` | Current mode flag |
| `n_call_net`, `n_game_net`, `n_stream_net`, `n_bulk_net` | Network-wide flow counts by traffic class |
| `delay`, `jitter`, `loss`, `loss_ema`, `rtt_d3` | Current device delay, jitter and loss; loss exponential moving average; delay change versus 3 samples earlier |
| `thr_over_cap` | Device throughput divided by network capacity (`thr / cap`) |
| `n_flows` | Current device flow count |
| `has_call`, `has_game`, `has_stream`, `has_bulk` | Device traffic-presence flags |
| `qoe_now`, `qoe_d3`, `qoe_d10`, `qoe_min10` | Current QoE, QoE changes versus 3/10 samples earlier, and minimum available QoE in the recent 10-sample window |
| `buf_min`, `buf_d3` | Current minimum stream buffer and its change versus 3 samples earlier |

The runtime keeps at most 16 records per device. Its history-based features assume one record per second. **The `t_sec` argument is currently not used to detect gaps or reorder samples**, so the caller must maintain a one-second cadence and chronological order.

## 8. Runnable example

Run the included example:

```powershell
python example_qoe.py
```

It loads only the QoE model, sends a sample for one device over consecutive seconds, and prints the final result. Replace the sample metrics with measurements from your router/telemetry pipeline before using it operationally.

For multiple devices, call `warner.push(device_id, timestamp_seconds, record_for_that_device)` once for each active device in each one-second interval. Use the same network-wide values in each device record, but supply the correct device-specific values for each device.

To clear one device's history:

```python
warner.reset("device-1")
```

To clear all device histories:

```python
warner.reset()
```

## 9. Integration and limitations

- The QoE predictor produces a **warning result only**. It does not itself change router queues, bandwidth limits, Wi-Fi settings, or Linux `tc`/CAKE rules. Your controller must decide what action to take when `alert` is true.
- Treat `state="red"` as a current degradation signal even though `alert` is false in that branch.
- Feed the runtime current QoE and current measurements for every active device, once per second. Keep a persistent warner instance so its history is retained.
- Warm up each device with at least 16 consecutive one-second samples before relying on the full history features. The code will emit predictions earlier, but some lag features will be `NaN` until enough history exists.
- The supplied model card says the models were trained on simulated/emulated network data and proxy QoE scores, not real router/ISP measurements. Validate calibration, false alarms, and detection rates on your own network before automating network changes.
- Load `.joblib` files only from a trusted source because joblib uses Python object deserialization.
