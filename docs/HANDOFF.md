# Handoff: V0.9 Linux Gateway Lab and the ML stage

Written 2026-11-07. This covers what exists, how to get it running, what the measurements showed, and the task list for the ML stage. Read `REPRODUCE_V0_9.md` for exact commands and `REPO_AUDIT.md` for the full status and open findings.

## 1. What exists

A lab inside an Ubuntu VM that simulates three clients on a virtual bridge, measures each client's traffic, limits each client's bandwidth, and runs a rule-based policy that divides a simulated 100 Mbit/s plan between clients by their declared intent (call, gaming, streaming, browsing, download). Nothing in it touches the physical network.

| Area | Files |
| --- | --- |
| Lab setup and teardown | `scripts/setup_gateway.sh`, `scripts/cleanup_gateway.sh` |
| Per-client limits | `scripts/limit_client.sh`, `scripts/install_helper.sh` (root-owned copy plus a sudoers rule) |
| Shared bottleneck | `scripts/set_bottleneck.sh` |
| Measurement | `gateway/collector.py` (byte counters per client, anonymous in-memory IDs) |
| Policy | `gateway/policy.py` (weighted max-min allocation), `gateway/controller.py` (when and whom to cap) |
| Service | `gateway/api.py` (FastAPI: `/clients`, `/clients/{n}/limit`, `/clients/{n}/intent`, `/policy`), `gateway/watch.py` (live terminal view) |
| Experiments | `experiments/run_call_vs_download.py`, `experiments/run_streaming_vs_download.py`, CSVs in `experiments/reports/` |
| Tests | `tests/test_policy.py`, `tests/test_controller.py` |

## 2. Get it running

Follow `REPRODUCE_V0_9.md` sections 0 to 8 (VM, packages, clone, venv, lab, API). Then:

```
python -m pytest tests/ -v
python3 experiments/run_call_vs_download.py --runs 5
python3 experiments/run_streaming_vs_download.py --runs 5
```

The lab disappears when the VM reboots. Re-run `sudo bash scripts/setup_gateway.sh`. If you change `scripts/limit_client.sh`, re-run `sudo bash scripts/install_helper.sh`, because the API calls an installed copy.

## 3. What the measurements showed (baseline for any ML comparison)

Five runs per mode on a 100 Mbit/s shared bottleneck with a 50 ms queue.

| Scenario | No policy | Equal weights | Intent weights |
| --- | --- | --- | --- |
| Call RTT average (call vs download) | 29.95 ms | n/a | 1.83 ms |
| Streaming throughput, asks for 60 Mbit/s | 16.2 Mbit/s | 40.4 Mbit/s | 63.2 Mbit/s |
| Download in the streaming scenario | 77.5 Mbit/s | 42.2 Mbit/s | 20.5 Mbit/s |

The policy lowers latency under load and lets a high-priority client reach its requested rate. It does **not** reduce packet loss, and it costs roughly 10 to 15% of total throughput. Do not present loss as a benefit.

These numbers use intents that were set by hand. Anything the ML stage does is compared against them: the target is for predicted intents to reproduce the intent-weights column.

## 4. Task list for the ML stage

### A. Traffic generators, one per intent

Each generator runs inside a client namespace (`sudo ip netns exec clientN ...`) and is scripted, so the dataset can be rebuilt by anyone. Starting points, all to be tuned:

| Intent | Shape |
| --- | --- |
| call | steady UDP, a few Mbit/s, small to medium packets, roughly symmetric up and down |
| gaming | low-rate UDP, very small packets at a high packet rate, symmetric |
| streaming | mostly downstream TCP in bursts every few seconds, with idle gaps |
| browsing | short random bursts of varying size separated by idle time |
| download | one long saturating TCP flow (or several) |

Randomize rates, packet sizes and timing per run. A classifier trained on constant parameters will memorize the generator.

### B. Feature logging

`collector.py` reads only byte counters. The same sysfs folder (`/sys/class/net/veth-cN-br/statistics`) also has `rx_packets` and `tx_packets`, which gives mean packet size and packet rate without any packet capture and without root. Suggested per-client features over a window of about 5 seconds: download and upload rate, their ratio, packet rates, mean packet size per direction, and burstiness (coefficient of variation of the 1-second rates inside the window).

Write one CSV row per client per window with the label from the generator that was running. Keep the privacy scope: aggregate counters and anonymous IDs only, no payloads and no addresses in the dataset.

### C. Classifier

Start with a decision tree or random forest in scikit-learn. Check that scikit-learn installs on the VM's Python 3.14 and add it to `requirements.txt`; if no wheel is available, use a virtual environment with an older Python.

- Split train and test **by run**, not by window. Windows from the same run are highly correlated, and a window-level split will inflate accuracy.
- Hold out some generator parameter ranges entirely to see how the model handles unseen settings.
- Report a confusion matrix, not just accuracy.

### D. Integration

Add a loop that predicts each client's intent every few seconds and calls the existing `POST /clients/{n}/intent`. Smooth predictions (for example a majority vote over the last few windows) so limits don't flap when one window is misclassified.

Then add an `ml` mode to `run_streaming_vs_download.py` next to `nopolicy`, `equal` and `intent`. Also run it with deliberately wrong intents, to measure what a misclassification costs.

### E. Validation on real traffic

Accuracy on traffic from your own generators shows that the pipeline works. It does not show that the model recognizes real calls or streams. Test on real captures (for example a phone on the Windows hotspot) before making that claim, and label simulated results as simulated.

## 5. Known issues and improvements

1. **Throughput left unused.** The controller shapes at 90% of the link, assumes 1.2x demand headroom and a 5 Mbit/s minimum for idle clients. In the intent run the streaming client uses about 63 Mbit/s while the controller allocates it about 68, and the download is held to about 20 with part of the plan unused. Reclaim unused allocation.
2. **Download only.** The policy loop shapes download only. Upload limits exist in `limit_client.sh` but the loop doesn't use them.
3. **Limits live in memory.** The API tracks limits in a dictionary and clears all limits at startup. Limits applied by hand with `limit_client.sh` are invisible to the API.
4. **Two separate FastAPI apps.** `backend/app/main.py` (original monitoring) and `gateway/api.py` are independent and both default to port 8000. The dashboard doesn't read the gateway API.
5. **Layout.** The policy code lives in `gateway/`, while the empty `qos/` and `ml/` folders from the original plan are untouched. The new tests sit in `tests/`, the older ones in `tests/unit/`. Pick one layout.
6. **No automated end-to-end test.** The lab results come from manual runs and the experiment scripts.
7. **Unconfirmed at handoff:** the pytest result for the six revised controller tests, and that the revised controller, tests, scripts, harnesses and CSVs are committed (audit finding 24).
8. **Older audit items** (empty README, CORS port mismatch, hardcoded API URL, adapter-name issues, frontend lint errors) are still open; see the audit.

## 6. Ground rules

- Keep everything inside the VM's namespaces. Don't bridge the real Wi-Fi adapter or change real routing or NAT.
- The sudoers rule allows the API user to run one root-owned script with any arguments. That is fine for a lab VM. Don't copy it to a shared machine unchanged.
- If something turns a mystery, check the troubleshooting table in `REPRODUCE_V0_9.md` first.