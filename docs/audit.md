# Experience Budget Repository Audit

**Audit date:** 2026-11-06  
**Scope:** Current repository contents and available automated checks. No application code was changed as part of this audit.

## Executive summary

The repository currently contains a local, aggregate network-monitoring prototype: a FastAPI backend collects adapter bandwidth, connectivity, and public-endpoint quality measurements; stores samples in SQLite; and serves them to a React dashboard. It also includes aggregate Windows Mobile Hotspot traffic monitoring.

The repository does not yet implement individual device monitoring, machine-learning features, or quality-of-service controls. Several named module areas and project documentation/configuration files are empty. Python tests pass, but frontend lint reports two errors.

## Implemented functionality

### Backend API

Implemented in [`backend/app/main.py`](./backend/app/main.py) and [`backend/app/api/monitoring.py`](./backend/app/api/monitoring.py):

- FastAPI application titled **Experience Budget**, version `0.7.0`.
- Root (`/`) and health (`/health`) endpoints.
- Monitoring API under `/api/v1/monitoring`:
  - `POST /collect` measures the selected local adapter, connectivity, and network quality.
  - `GET /history` returns recent aggregate measurements.
  - `POST /hotspot/collect` measures aggregate hotspot traffic.
  - `GET /hotspot/history` returns hotspot history.
- Request limits and input validation for adapter labels, sample intervals, quality targets, probe counts, and history limits.
- Collection failures from the service are translated to HTTP 503 responses.

### Network telemetry

Implemented modules are under [`network/telemetry`](./network/telemetry):

- [`interface_stats.py`](./network/telemetry/interface_stats.py) reads per-interface aggregate byte/error counters through `psutil`.
- [`bandwidth_monitor.py`](./network/telemetry/bandwidth_monitor.py) calculates upload/download rates and provides a standalone sampling loop.
- [`connectivity_monitor.py`](./network/telemetry/connectivity_monitor.py) checks adapter status and reachability through TCP connection attempts to public endpoints. It includes a standalone monitor and outage-duration tracker.
- [`network_quality.py`](./network/telemetry/network_quality.py) measures ICMP round-trip time to numeric IP targets and summarizes packet loss, RTT min/average/max, and average absolute RTT variation.
- [`hotspot_bandwidth_monitor.py`](./network/telemetry/hotspot_bandwidth_monitor.py) maps Windows virtual-adapter counters to downstream client-perspective upload/download rates.
- [`metrics_store.py`](./network/telemetry/metrics_store.py) validates and persists aggregate measurements in SQLite.
- [`monitoring_service.py`](./backend/app/services/monitoring_service.py) coordinates measurements, persistence, and history retrieval.

### Frontend

Implemented in [`frontend/src/App.jsx`](./frontend/src/App.jsx) and [`frontend/src/components/NetworkTopology.jsx`](./frontend/src/components/NetworkTopology.jsx):

- React dashboard with manual collection and start/stop automatic monitoring.
- Automatic collection every 15 seconds while enabled.
- History display for bandwidth and network quality, plus current download/upload, average RTT, and packet-loss metrics.
- Network topology visualization for an Internet source, laptop gateway, and anonymous aggregate hotspot clients.
- Dashboard loads recent upstream and hotspot samples from the backend.

The topology view explicitly indicates that router metrics are not measured and that hotspot readings are aggregate rather than per-device.

### Tests

The test files cover bandwidth calculations, hotspot direction mapping, connectivity status/outage tracking, network-quality summaries, SQLite storage validation, and monitoring API behavior. The API tests use mocked measurement services where applicable.

## Findings and gaps

### 1. Root README is empty

[`README.md`](./README.md) is empty. There is no root-level explanation of the project, implemented features, setup, run commands, API, privacy scope, or limitations. The [`frontend/README.md`](./frontend/README.md) remains the default Vite template rather than project-specific frontend documentation.

### 2. Root dependency manifest names the wrong package

[`requirements.txt`](./requirements.txt) lists `pustil==7.1.3`, while the application imports `psutil`. The current virtual environment has `psutil` installed, but a fresh install from the root manifest is not assured to install the dependency actually used by the monitoring code.

### 3. Backend CORS origin does not match Vite's default

[`backend/app/main.py`](./backend/app/main.py) permits `http://localhost:5174`. [`frontend/vite.config.js`](./frontend/vite.config.js) does not configure a development port, so Vite normally serves on `5173`. If Vite uses its default port, browser requests to the API will not match the backend's allowed origin.

### 4. Frontend API URL is hardcoded

[`frontend/src/App.jsx`](./frontend/src/App.jsx) sets the API base to `http://127.0.0.1:8000`. This assumes the backend runs locally on that host and port; there is no frontend environment-based API URL configuration in the inspected code.

### 5. Collection and history are inconsistent for non-default adapters

The collect endpoint accepts an adapter name, but [`get_history`](./backend/app/services/monitoring_service.py) always queries samples labeled `"Wi-Fi"`. Therefore, collection for another adapter can succeed while the regular history endpoint and dashboard continue to show only Wi-Fi samples. The dashboard collection request itself also hardcodes `"Wi-Fi"`.

### 6. Hotspot collection relies on a machine-specific interface name

The hotspot service and standalone monitor default to `"Local Area Connection* 2"`. The endpoint does not accept an adapter override, so collection depends on the target Windows machine exposing that exact interface name and having it active.

### 7. ML, QoS, discovery, router, and simulation modules are empty

The following source files exist but contain no implementation:

- `ml/classifier/classifier.py`
- `ml/estimator/kalman.py`
- `ml/forecasting/forecaster.py`
- `ml/qoe/scorer.py`
- `qos/fairness.py`
- `qos/policy.py`
- `qos/rollback.py`
- `qos/shaper.py`
- `qos/verifier.py`
- `network/devices/device_discovery.py`
- `network/discovery/interface_discovery.py`
- `network/gateway/router.py`
- `network/interfaces/manager.py`
- `network/simulation/scenarios.py`

These are placeholders, not available application features.

### 8. Additional telemetry placeholders are empty

`network/telemetry/collector.py`, `network/telemetry/network_monitor.py`, and `network/telemetry/ping_monitor.py` are empty. The functional telemetry described above resides in other files.

### 9. Project configuration and supporting materials are missing or empty

- [`pyproject.toml`](./pyproject.toml) is empty.
- `backend/requirements.txt` and `backend/requirements-dev.txt` are empty.
- `backend/app/config.py`, `backend/app/models/schemas.py`, and `backend/app/services/system_info.py` are empty.
- `docs/`, `experiments/reports/`, `experiments/scenarios/`, and `scripts/` contain no files in the audited workspace.

### 10. Frontend lint fails

`npm run lint` from `frontend/` reports two errors in [`frontend/src/App.jsx`](./frontend/src/App.jsx):

- Line 143: `fetchHistory()` is called synchronously from an effect.
- Line 151: `collectMeasurement()` is called synchronously from an effect.

These are reported by the `react-hooks/set-state-in-effect` ESLint rule. The frontend build succeeds, but Vite emits a warning that the minified JavaScript chunk exceeds 500 kB.

### 11. Test coverage does not demonstrate live end-to-end operation

The available Python suite tests the repository's implemented calculations, storage, and API routes, but API collection tests mock service functions. Passing tests do not verify operation against a real Wi-Fi adapter, a real Windows hotspot interface, ICMP/TCP reachability, or a browser-connected frontend/backend deployment.

## Validation performed

- Python: `.venv\Scripts\python.exe -m pytest -q` — **35 passed**.
- Frontend production build: `npm run build` in `frontend/` — **succeeded**, with a large-chunk warning.
- Frontend lint: `npm run lint` in `frontend/` — **failed with the two effect-related errors above**.

## Overall status

The working product today is a **local aggregate network telemetry prototype with a FastAPI/SQLite backend and a React dashboard**. It does not yet provide per-device usage, router telemetry, predictive/ML analysis, QoS shaping, or the other placeholder module capabilities.
