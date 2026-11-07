# Experience Budget Repository Audit

**Original audit date:** 2026-11-06
**Updated:** 2026-11-07 (adds the V0.9 Linux Gateway Lab work done in the Ubuntu VM)
**Scope:** Repository contents and the checks that were actually run. Items in finding 18 were checked by the author and recorded as passing without quoted measurements.

## Executive summary

The repository started as a local, aggregate network-monitoring prototype: a FastAPI backend collects adapter bandwidth, connectivity and public-endpoint quality measurements, stores them in SQLite, and serves them to a React dashboard, plus aggregate Windows Mobile Hotspot monitoring.

Since the first audit, a second track was added: a **Linux gateway lab** that runs inside an Ubuntu VirtualBox VM. It simulates three clients, measures their traffic per client, limits their bandwidth individually, and runs a **rule-based, intent-weighted policy** that splits a simulated bandwidth budget between them. This gives the project its first per-client monitoring and its first traffic control.

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

**Python (`gateway/`)**

| File | Purpose |
| --- | --- |
| `collector.py` | Reads each client's byte counters from `/sys/class/net/veth-cN-br/statistics` (no root needed) and prints per-client down/up Mbit/s. Each client gets a random in-memory anonymous ID (`dev-xxxxxx`) that changes on every restart. |
| `policy.py` | `allocate()`: weighted max-min fair split of a bandwidth budget. Intent weights: call 8, gaming 6, streaming 4, browsing 2, download 1. |
| `controller.py` | `decide()`: turns measurements into limit targets. Treats a client at 90% or more of its cap as still wanting more, ignores changes under 15%, keeps a 5 Mbit/s minimum for idle clients, and applies no limits when total demand is under the budget. |
| `api.py` | FastAPI service: `GET /health`, `GET /clients`, `POST/DELETE /clients/{n}/limit`, `POST /clients/{n}/intent`, `GET/POST /policy`. Runs a 1 s sampling loop and a 3 s policy loop, and clears all limits at startup. |
| `watch.py` | Terminal live view of `/clients`. |

**Tests (`tests/`)**: `test_policy.py` (5 tests) and `test_controller.py` (5 tests).

## Validation performed

**Original audit (Windows):** `pytest -q` 35 passed; `npm run build` succeeded with a large-chunk warning; `npm run lint` failed with two effect-related errors.

**Gateway lab (Ubuntu VM), observed results:**

- **Connectivity:** from a client namespace, ping to the bridge, to another client, to `1.1.1.1` and to `google.com` all succeeded, including after a full cleanup and rebuild of the lab.
- **Baseline throughput (iperf3, no limits):** about 51-54 Gbit/s for a single client. Three clients in parallel (one server port each) got about 3.8-4.0 Gbit/s each, an even split.
- **Collector:** during a client1 upload test, client1's Up column showed about 60 Gbit/s while Down stayed near 30 Mbit/s. During a client2 reverse test, client2's Down column showed about 50 Gbit/s. The direction mapping is correct.
- **Manual limits:** a 10 Mbit/s download limit measured 9.4-9.6 Mbit/s; a 5 Mbit/s upload limit measured about 4.9 Mbit/s; unlimited clients were unaffected; removing the limit restored about 42-46 Gbit/s.
- **API limits:** `POST /clients/1/limit` applied a 10 Mbit/s limit without a password prompt (measured 9.64 Mbit/s), `/clients` showed the limit, and `DELETE` cleared it.
- **pytest:** 40 passed on the VM (the 35 original tests plus 5 policy tests). The 5 controller tests were later run and confirmed passing by the author (2026-11-07).
- **Policy live test:** with intents streaming / download / browsing and a simulated 100 Mbit/s budget, the download client was capped at 19 Mbit/s (measured 17.6) and the idle browsing client was held at 5 Mbit/s, matching the expected 76 / 19 / 5 split. The streaming client's limit and the remaining policy checks were then confirmed by the author (see finding 18).

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

    **Still open:** none from this list. The policy results are manual runs; no automated end-to-end test covers them (finding 11).

## Overall status

The repository now contains two working pieces: the **local aggregate telemetry prototype** (FastAPI, SQLite, React) and the **Linux gateway lab** with per-client monitoring, per-client bandwidth limiting and a rule-based intent policy, verified by the manual runs above. It does not yet provide ML, intent classification, real per-device discovery, router telemetry, or control of the physical network.

The rule-based policy is the baseline for the planned comparison. Next steps in order: build an experiment harness that replays the same scenario with no policy, equal-share limits and the intent policy while logging results to CSV, then build intent-shaped traffic generators and use the labeled logs to train the first classifier.