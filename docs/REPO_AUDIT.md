# Experience Budget Repository Audit

**Original audit date:** 2026-11-06
**Updated:** 2026-11-07 (adds the V0.9 Linux Gateway Lab work done in the Ubuntu VM)
**Scope:** Repository contents and the checks that were actually run. Items in finding 18 were checked by the author and recorded as passing without quoted measurements.

## Executive summary

The repository started as a local, aggregate network-monitoring prototype: a FastAPI backend collects adapter bandwidth, connectivity and public-endpoint quality measurements, stores them in SQLite, and serves them to a React dashboard, plus aggregate Windows Mobile Hotspot monitoring.

Since the first audit, a second track was added: a **Linux gateway lab** that runs inside an Ubuntu VirtualBox VM. It simulates three clients, measures their traffic per client, limits their bandwidth individually, and runs a **rule-based, intent-weighted policy** that splits a simulated bandwidth budget between them. This gives the project its first per-client monitoring and its first traffic control. Two repeated experiments (see Validation performed) show the policy cutting a call's latency under load and giving a streaming client its requested rate.

Still not implemented: machine learning, a classifier for intent (intents are set by hand), real-device discovery, router telemetry, and QoS against the physical network. The lab clients are simulated network namespaces, not real phones or laptops.

## Implemented functionality

### Backend API (original, unchanged)

Implemented in `backend/app/main.py` and `backend/app/api/monitoring.py`:

- FastAPI application titled **Experience Budget**, version `0.7.0`, with `/` and `/health`.
- Monitoring API under `/api/v1/monitoring`: `POST /collect`, `GET /history`, `POST /hotspot/collect`, `GET /hotspot/history`.
- Input validation and request limits; collection failures become HTTP 503.

### Network telemetry (original, unchanged)

Under `network/telemetry`: `interface_stats.py`, `bandwidth_monitor.py`, `connectivity_monitor.py`, `network_quality.py`, `hotspot_bandwidth_monitor.py`, `metrics_store.py`, plus `backend/app/services/monitoring_service.py`. These measure aggregate adapter and hotspot traffic through `psutil` and ICMP/TCP probes and persist aggregate samples to SQLite.

### Frontend (original, unchanged)

React dashboard in `frontend/src/App.jsx` and `frontend/src/components/NetworkTopology.jsx`: manual and automatic (15 s) collection, bandwidth and quality history, and a topology view that states that router metrics are not measured and that hotspot readings are aggregate.

### Linux gateway lab (new, V0.9)

Runs inside the Ubuntu VM (Ubuntu 26.04 LTS, Python 3.14.4). The VM has two VirtualBox adapters: NAT (internet) and Host-only (private link to Windows, `192.168.56.101`).

**Scripts (`scripts/`)**

| File | Purpose |
| --- | --- |
| `setup_gateway.sh` | Creates bridge `br-lab` (10.50.0.1/24) and three client network namespaces (`client1..3`, 10.50.0.11-13) joined by veth pairs. Adds per-client DNS and NAT (nftables table `eb_nat`) out through the VM's default interface. Safe to re-run. |
| `cleanup_gateway.sh` | Removes the namespaces, bridge, per-client DNS files and the NAT table. Safe to re-run. |
| `limit_client.sh` | `limit_client.sh <1\|2\|3> <down_mbit> [up_mbit]` or `... off`. Download is shaped on the bridge-side veth, upload inside the namespace, both with `tc tbf`. |
| `install_helper.sh` | Installs a root-owned copy of `limit_client.sh` at `/usr/local/sbin/eb-limit-client` and adds a sudoers rule so the API user can run only that file without a password. |

**Experiments (`scripts/` and `experiments/`)**

| File | Purpose |
| --- | --- |
| `scripts/set_bottleneck.sh` | `set_bottleneck.sh <mbit\|off>`: puts a shared `tc tbf` limit with a deliberately short 50 ms queue on `br-lab`, simulating a home plan so clients actually compete. |
| `scripts/call_vs_download.sh` | One-off run of the call-vs-download scenario with a mid-run snapshot of the policy state and `tc` counters. Used for diagnosis. |
| `experiments/run_call_vs_download.py` | Repeats the call-vs-download scenario (5 Mbit/s UDP call plus ping probe against a 4-stream download), alternating no policy and intent policy, 8 s warm-up ignored, writes a CSV and prints mean and standard deviation. |
| `experiments/run_streaming_vs_download.py` | Repeats a streaming-vs-download scenario (one paced TCP stream asking for 60 Mbit/s against a 4-stream download) in three modes: no policy, equal weights, intent weights. Imports helpers from the file above. |
| `experiments/reports/*.csv` | One row per run, written by the two harnesses. |

**Python (`gateway/`)**

| File | Purpose |
| --- | --- |
| `collector.py` | Reads each client's byte counters from `/sys/class/net/veth-cN-br/statistics` (no root needed) and prints per-client down/up Mbit/s. Each client gets a random in-memory anonymous ID (`dev-xxxxxx`) that changes on every restart. |
| `policy.py` | `allocate()`: weighted max-min fair split of a bandwidth budget. Intent weights: call 8, gaming 6, streaming 4, browsing 2, download 1. |
| `controller.py` | `decide()`: turns measurements into limit targets. Treats a client at 90% or more of its cap as still wanting more, ignores changes under 15%, keeps a 5 Mbit/s minimum for idle clients, applies no limits when total demand is under 90% of the budget, shapes at 90% of the link rate so the shared queue stays short, and caps only clients that demand more than their allocation. |
| `api.py` | FastAPI service: `GET /health`, `GET /clients`, `POST/DELETE /clients/{n}/limit`, `POST /clients/{n}/intent`, `GET/POST /policy`. Runs a 1 s sampling loop and a 3 s policy loop, and clears all limits at startup. |
| `watch.py` | Terminal live view of `/clients`. |

**Tests (`tests/`)**: `test_policy.py` (5 tests) and `test_controller.py` (6 tests after the controller revision in finding 19).

## Validation performed

**Original audit (Windows):** `pytest -q` 35 passed; `npm run build` succeeded with a large-chunk warning; `npm run lint` failed with two effect-related errors.

**Gateway lab (Ubuntu VM), observed results:**

- **Connectivity:** from a client namespace, ping to the bridge, to another client, to `1.1.1.1` and to `google.com` all succeeded, including after a full cleanup and rebuild of the lab.
- **Baseline throughput (iperf3, no limits):** about 51-54 Gbit/s for a single client. Three clients in parallel (one server port each) got about 3.8-4.0 Gbit/s each, an even split.
- **Collector:** during a client1 upload test, client1's Up column showed about 60 Gbit/s while Down stayed near 30 Mbit/s. During a client2 reverse test, client2's Down column showed about 50 Gbit/s. The direction mapping is correct.
- **Manual limits:** a 10 Mbit/s download limit measured 9.4-9.6 Mbit/s; a 5 Mbit/s upload limit measured about 4.9 Mbit/s; unlimited clients were unaffected; removing the limit restored about 42-46 Gbit/s.
- **API limits:** `POST /clients/1/limit` applied a 10 Mbit/s limit without a password prompt (measured 9.64 Mbit/s), `/clients` showed the limit, and `DELETE` cleared it.
- **pytest:** 40 passed on the VM (the 35 original tests plus 5 policy tests). The 5 controller tests were later run and confirmed passing by the author (2026-11-07).
- **Policy live test (first controller version, before the revision in finding 19):** with intents streaming / download / browsing and a simulated 100 Mbit/s budget, the download client was capped at 19 Mbit/s (measured 17.6) and the idle browsing client was held at 5 Mbit/s, matching the expected 76 / 19 / 5 split. The streaming client's limit and the remaining policy checks were then confirmed by the author (see finding 18).

**Shared-bottleneck experiments (observed by the author, 2026-11-07).** A 100 Mbit/s shared bottleneck with a 50 ms queue; 5 runs per mode, modes interleaved, 8 s warm-up discarded, values are mean +/- standard deviation.

*Call vs download* (client1: 5 Mbit/s UDP call plus ping; client2: 4-stream TCP download; revised controller):

| Metric | No policy | Intent policy |
| --- | --- | --- |
| Call RTT average | 29.95 +/- 14.19 ms | 1.83 +/- 1.76 ms |
| Call RTT 95th percentile | 44.72 +/- 13.83 ms | 10.66 +/- 12.72 ms |
| Call RTT maximum | 77.04 +/- 28.06 ms | 44.20 +/- 41.00 ms |
| Call jitter | 5.91 +/- 8.86 ms | 0.73 +/- 0.76 ms |
| Call loss | 0.24 +/- 0.41 % | 0.27 +/- 0.53 % |
| Download | 88.00 +/- 1.38 Mbit/s | 74.56 +/- 0.79 Mbit/s |

The policy's average RTT was lower in all five paired runs. Loss shows no difference.

*Streaming vs download* (client1: one TCP stream paced to 60 Mbit/s; client2: 4-stream download):

| Metric | No policy | Equal weights | Intent weights |
| --- | --- | --- | --- |
| Streaming throughput | 16.2 +/- 7.1 Mbit/s | 40.4 +/- 1.1 Mbit/s | 63.2 +/- 3.4 Mbit/s |
| Streaming shortfall vs 60 target | 72.9 +/- 11.8 % | 32.6 +/- 1.8 % | 0.5 +/- 1.2 % |
| Download | 77.5 +/- 8.4 Mbit/s | 42.2 +/- 2.6 Mbit/s | 20.5 +/- 2.2 Mbit/s |
| Total | 93.7 +/- 2.2 Mbit/s | 82.6 +/- 3.1 Mbit/s | 83.7 +/- 2.3 Mbit/s |
| Streaming client RTT average | 42.4 +/- 17.5 ms | 19.0 +/- 2.3 ms | 11.7 +/- 2.2 ms |

Without a policy, TCP shares per flow, so the 4-stream download wins. Equal weights split per client. Intent weights give the streaming client its requested rate.

## Findings and gaps

### Carried over from the first audit

1. **Root README is empty.** `README.md` has no project description, setup, run commands, API list, privacy scope or limitations. `frontend/README.md` is still the Vite template. **Open.** `docs/REPRODUCE_V0_9.md` (added with this update) covers the lab but not the whole project.
2. **Root dependency manifest named the wrong package.** The first audit found `pustil==7.1.3`. The root `requirements.txt` now lists `fastapi`, `uvicorn`, `pytest`, `httpx` and `psutil`. **Resolved** (versions are unpinned, which is a smaller issue; see finding 17).
3. **Backend CORS origin does not match Vite's default** (`5174` allowed, Vite serves `5173`). **Open.**
4. **Frontend API URL is hardcoded** to `http://127.0.0.1:8000`. **Open.**
5. **Collection and history are inconsistent for non-default adapters** (history always queries `"Wi-Fi"`). **Open.**
6. **Hotspot collection depends on the interface name** `"Local Area Connection* 2"`. **Open.**
7. **ML, QoS, discovery, router and simulation modules are empty.** **Partly changed.** ML modules (`ml/*`) are still empty. The working allocation policy and limiter live in `gateway/` instead of the empty `qos/policy.py`, `qos/fairness.py` and `qos/shaper.py`, and the lab scripts take the place of `network/simulation/scenarios.py`. See finding 13.
8. **Additional telemetry placeholders are empty** (`collector.py`, `network_monitor.py`, `ping_monitor.py`). **Open.**
9. **Configuration and supporting files.** `scripts/` now contains the four lab scripts. pytest reports `pyproject.toml` as its config file, so it is no longer empty (its contents were not reviewed here). `backend/requirements*.txt`, `config.py`, `schemas.py`, `system_info.py`, `docs/` (apart from the new reproduction guide) and `experiments/` need a fresh check.
10. **Frontend lint fails** with two `react-hooks/set-state-in-effect` errors in `App.jsx`. **Open.**
11. **Tests do not demonstrate live end-to-end operation.** **Partly addressed** for the lab: the manual checks listed above ran against real kernel networking. There is still no automated end-to-end test, and the Windows-side monitoring still has none.

### New findings

12. **Two separate FastAPI apps exist.** The original backend (`backend/app/main.py`) and the gateway API (`gateway/api.py`) are independent and both default to port 8000 in the instructions used so far. They cannot run on the same port at once, and the dashboard does not read the gateway API.
13. **Policy code lives outside the planned module layout.** `gateway/policy.py` and `gateway/controller.py` duplicate the purpose of the empty `qos/policy.py` and `qos/fairness.py`. New tests sit in `tests/` while existing ones are in `tests/unit/`. Decide on one layout before the code grows.
14. **The lab is runtime state.** Namespaces, the bridge, NAT rules and `tc` limits disappear on VM reboot. `setup_gateway.sh` must be re-run after every restart.
15. **The root-owned helper copy goes stale.** `/usr/local/sbin/eb-limit-client` is a copy, so changes to `scripts/limit_client.sh` take effect only after `sudo bash scripts/install_helper.sh` is run again. The sudoers rule allows any arguments to that one file; the script validates its own arguments. This is acceptable for a lab VM, but it should not be copied to a shared or production machine unchanged.
16. **Policy limits are in memory and download-only.** The API tracks limits in a dictionary. Startup now clears all limits, so a restart cannot leave a rule the API has forgotten, but `limit_client.sh` run by hand is invisible to the API. The policy loop shapes download only.
17. **Simulation assumptions.** The 100 Mbit/s budget is simulated (the virtual links run at tens of Gbit/s and nothing contends naturally). Intents are set by hand through the API. Dependencies are unpinned. The lab clients are generated by iperf3, which is one flat saturating flow, so there is no realistic traffic mix yet.
18. **Verified by the author on 2026-11-07.** These were checked by the author and are recorded here as passing; the measured values were not sent to the assistant, so none are quoted.
    - `tests/test_controller.py` passes.
    - `controller.py`, the policy version of `api.py`, `watch.py` and `test_controller.py` are committed and pushed.
    - The streaming client's limit during the policy live test, and the swapped-intent test (split flips as expected).
    - Limits clear on their own within seconds after the traffic stops.
    - The gateway API is reachable from the Windows browser at `http://192.168.56.101:8000/clients`.
    - The "clear upload limit when none is given" fix in `limit_client.sh` is saved, and the helper was reinstalled afterwards.
    - VS Code Remote-SSH from Windows works, after the `.ssh/config` file permission fix described in the reproduction guide.

    **Still open:** none from this list. The policy results are manual runs; no automated end-to-end test covers them (finding 11). The live results in this finding refer to the first controller version.

19. **Controller revision.** The first controller capped every client, including the call: a 5 Mbit/s cap on a call whose traffic slightly exceeds 5 Mbit/s built a queue of about 119 KB on the call's own limiter, and in a single run the call's average RTT rose to about 60 ms against about 12 ms with no policy. The revision caps only clients that demand more than their allocation and shapes at 90% of the link rate (`TARGET_UTILIZATION`). The tests in `tests/test_controller.py` were rewritten for this behavior.
20. **No loss benefit.** Packet loss is statistically the same with and without the policy (about 0.25% in both). Earlier single runs ranged from 0% to 4.6% with no pattern, so they were noise. Loss should not be claimed as a benefit. Out-of-order datagrams (hundreds per run, even without a policy) add noise to iperf3's loss count.
21. **Throughput cost and a known inefficiency.** The call-vs-download policy run gave up about 13 Mbit/s (15%) of the download, and the streaming scenario's total fell from 93.7 to about 83 Mbit/s with either policy. Causes: shaping at 90% of the link, the 1.2x demand headroom, and a 5 Mbit/s minimum demand assumed for idle clients. In the intent run the streaming client uses about 63 Mbit/s while the controller's arithmetic allocates it about 68, and the download is held to about 20 Mbit/s with part of the plan left unused. Reclaiming unused allocation is a follow-up improvement.
22. **Scope of the experiments.** Two scenarios, 5 runs per mode, a simulated bottleneck with a queue depth chosen by us (absolute no-policy latency depends on it). iperf3 `-b` pacing for TCP is approximate: the streaming client reached up to 66.8 Mbit/s against a 60 target, and the shortfall metric clamps overshoot to zero.
23. **Intent is configured, not inferred.** The intent results show what the allocation does when the intent is right. Inferring intent from traffic (the classifier) and the cost of misclassification are untested. The training-dataset work is deliberately out of scope for V0.9 and handed off in `docs/HANDOFF.md`.
24. **Not yet confirmed after the controller revision.** The result of `python -m pytest tests/ -v` with the six revised controller tests, and whether the revised `controller.py`, `tests/test_controller.py`, the new scripts, both harness files and the CSVs are committed and pushed.

## Overall status

The repository now contains two working pieces: the **local aggregate telemetry prototype** (FastAPI, SQLite, React) and the **Linux gateway lab** with per-client monitoring, per-client bandwidth limiting and a rule-based intent policy, verified by the manual runs above. It does not yet provide ML, intent classification, real per-device discovery, router telemetry, or control of the physical network.

The rule-based policy is the baseline for the planned comparison, and both experiments are now measured: it cuts a call's latency under load by roughly 16 times in the average RTT (29.95 ms to 1.83 ms) and gives a streaming client its requested rate where equal sharing and no policy do not, at a cost of about 10-15% of total throughput. It does not reduce packet loss.

Next steps, in order: confirm finding 24; fix the controller inefficiency in finding 21; then the ML stage described in `docs/HANDOFF.md` (intent-shaped traffic generators, a feature logger, a classifier, and a harness mode that uses predicted instead of configured intent).