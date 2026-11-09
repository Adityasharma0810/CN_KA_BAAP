# Module 5 — Unified Observation API Audit

**Audit date:** 2026-11-09
**Actual HEAD:** `1234b00 Expose per-client lab telemetry in topology`
**Branch:** `main`
**Working tree at audit start:** clean

## Repository discrepancy

The requested starting context names Module 4 commits such as `bb949a1`, `1818aa8`, `413d71a`, `40b48f4`, `c60a943`, `857fe53`, `e01f672`, and `5fb2e6b`. Those commits are not present in the current repository history. `docs/MODULE4_DATABASE.md` is also absent. The actual repository contains the earlier aggregate-only `network/telemetry/metrics_store.py`, so Module 5 must not assume the claimed Module 4 storage APIs exist. Storage integration will either use the methods that actually exist or be preceded by a separately tested storage upgrade.

## Current application architecture

### Primary product application

`backend/app/main.py` is the primary FastAPI application. It currently:

- Creates the `Experience Budget` FastAPI app.
- Configures CORS for localhost ports 5173 and 5174 using both localhost and 127.0.0.1.
- Includes `backend.app.api.monitoring.router`.
- Exposes unversioned `/` and `/health` endpoints.

This is the application used by the React frontend and must remain the only product-facing FastAPI app.

### Existing product routes

`backend/app/api/monitoring.py` currently mounts `/api/v1/monitoring`:

| Route | Behavior | Data source | Risk/gap |
|---|---|---|---|
| `POST /collect` | Collects and stores local adapter aggregate telemetry | Windows/local collectors | Returns an untyped dictionary; raw exception text becomes HTTP 503 detail |
| `POST /hotspot/collect` | Collects Windows Mobile Hotspot aggregate traffic | Windows hotspot interface counters | Correctly aggregate-only, but no common response model |
| `GET /history` | Reads recent Wi-Fi aggregate history | `MetricsStore` | Fixed to `Wi-Fi`; no source/environment filters or pagination |
| `GET /hotspot/history` | Reads hotspot aggregate history | `MetricsStore` | Fixed interface label; no common envelope |
| `GET /lab/clients` | Reads local Linux namespace lab counters | `LabAccountingService` | Useful lab route, but not a product-wide client/current observation API |

### Linux gateway application

`gateway/api.py` is a separate FastAPI app. It contains:

- Read-only-ish `/health` and `/clients` routes.
- Privileged limit routes under `/clients/{n}/limit`.
- Intent mutation routes under `/clients/{n}/intent`.
- Policy mutation routes under `/policy`.
- A startup lifecycle that clears limits and starts sampling/policy loops.

It must not be included wholesale in `backend/app/main.py`. Its policy and helper routes can execute privileged operations and are outside the Module 5 observation API boundary.

### Linux accounting implementation

`gateway/accounting.py` reads gateway-side veth statistics from Linux sysfs:

- `veth-cN-br/statistics/tx_bytes` and `tx_packets` represent client download.
- `veth-cN-br/statistics/rx_bytes` and `rx_packets` represent client upload.
- Results use the shared `TelemetryObservation` model with source `linux_namespace_lab`, scope `client`, and environment `simulated_lab`.
- `backend/app/services/lab_accounting_service.py` owns a runtime anonymous registry and returns three configured lab clients when interfaces exist.

This is local-process observation. There is no Windows-to-Ubuntu HTTP/SSH/agent adapter in the current checkout, and Windows cannot directly read Ubuntu sysfs or namespaces.

### Windows collectors and storage

- `backend/app/services/monitoring_service.py` coordinates local aggregate and hotspot collection.
- `network/telemetry/interface_stats.py` reads aggregate interface counters via `psutil`.
- `network/telemetry/network_quality.py` probes explicitly allowed numeric public IPs.
- `network/telemetry/metrics_store.py` currently stores only aggregate rows in `network_samples`. It has no source, environment, scope, or client ID columns in this checkout.
- The current history service methods return raw dictionaries and do not support the requested Module 4-style time-range, source, environment, client, offset, or order filters.

### Frontend consumers

`frontend/src/App.jsx` currently calls:

- `/api/v1/monitoring/history?limit=50`
- `/api/v1/monitoring/hotspot/history?limit=50`
- `/api/v1/monitoring/lab/clients`
- `/api/v1/monitoring/collect`
- `/api/v1/monitoring/hotspot/collect`

`NetworkTopology.jsx` renders individual nodes only when genuine Linux lab client results are available. Otherwise it renders one aggregate Windows hotspot node. It must not infer physical client count from aggregate hotspot counters.

## Integration gaps

1. No common product-facing response envelopes.
2. No versioned health or collector-health routes.
3. No gateway status adapter or configurable remote gateway endpoint.
4. No product-facing client listing/detail routes.
5. No current observation aggregation route.
6. No topology response model or topology service.
7. No historical query layer with the requested filters and pagination.
8. Existing storage is aggregate-only despite the claimed Module 4 completion.
9. Existing route handlers expose raw service dictionaries and raw exception strings.
10. `.env.example` is empty, so gateway endpoint and timeout configuration are undocumented.
11. Existing gateway policy/control app must remain separate from observation routes.

## Security and privacy risks

- Mounting `gateway.api.app` would expose policy and privileged helper routes in the product API; this must not happen.
- Existing `HTTPException(detail=str(error))` behavior can expose filesystem/interface details.
- Raw gateway dictionaries could expose internal lab infrastructure if returned without filtering.
- The Windows hotspot collector is aggregate-only and cannot produce physical per-client observations.
- No IP/MAC fields are currently needed for product responses; future models must use `extra="forbid"` and exclude infrastructure names.
- CORS is permissive for four local development origins but does not allow arbitrary origins; this should be retained and documented until a configuration task narrows it further.
- No credentials or gateway address are currently stored in the repository.

## Proposed product-facing structure

Keep `backend/app/main.py` as the sole product app and add separate route modules under `backend/app/api/`:

- `health.py`: application, database, Windows collector, gateway adapter, and registry status.
- `observations.py`: current and bounded historical observation envelopes.
- `clients.py`: anonymous client listing, details, and client history.
- `topology.py`: topology and gateway status.

Keep adapters/services separate:

- Windows aggregate collectors remain in `monitoring_service.py` and `network/telemetry`.
- Linux lab observations remain behind `LabAccountingService`.
- A future remote Ubuntu adapter must be read-only, configurable, timeout-bounded, and schema-validated. It must not expose arbitrary shell execution or reuse the privileged `gateway/api.py` app.
- Storage upgrades must be handled in the repository layer with migrations and tests before API history routes claim those capabilities.

## First atomic implementation

Add typed product-facing response models and a safe health status service without changing collector behavior or storage schema. The first feature will provide:

- Consistent status values: `healthy`, `degraded`, `unavailable`.
- Safe component health records with no raw exceptions, paths, addresses, or credentials.
- Strict response models for health and collector status.
- Tests for healthy, degraded, and unavailable component aggregation.

This creates the contract required by later API routes while keeping the missing Module 4 storage work explicit and isolated.
