# Dashboard Data Map (Stage 1)

Data-source switch: `VITE_DATA_MODE` = `live` (default) | `demo`, plus
`VITE_API_BASE` (default `http://127.0.0.1:8000`), documented in
`frontend/.env.example`. The single adapter lives in `frontend/src/api/client.js`
(`DEMO_MODE` flag, 10 s fetch timeout, `ApiError` normalised errors; consumers
poll with `Promise.allSettled` + `AbortController` cancel on unmount). A
`● LIVE` / `DEMO DATA` badge and a `Backend unreachable` banner are in the
`AppShell` header.

Legend: LIVE = wired to a real endpoint in live mode. NONE = no live endpoint
yet (shows placeholder / "not connected yet" in live mode, demo data in demo
mode).

## Pages

| Page / panel | Shows | Source now | Live endpoint |
|---|---|---|---|
| **ComparePage** > Scenario Lab | scenario pick + start/stop | `getScenarioCatalog` / `startScenario` / `stopScenario` | `/api/v1/scenarios*` (LIVE) |
| ComparePage > Metric comparison | baseline-vs-optimized cards | `getComparison()` | NONE (Stage 4 A/B) |
| ComparePage > Time-series chart | 60-sample comparison lines | `getComparison()` | NONE (Stage 4) |
| ComparePage > Household usage tree | per-client class + policy | `getComparison()` | NONE (live client list is on LiveControlPage) |
| ComparePage > Conclusion | automated findings | `getComparison()` | NONE (Stage 4) |
| **ModelIntelligencePage** (all panels) | ML pipeline, models, feature importance, predictions, health | `getModelIntelligence()` | NONE (ML offline, Stage 2) |
| **LiveControlPage** > System Status | backend + gateway health | `getHealth` / `getGatewayStatus` | `/api/v1/health`, `/api/v1/gateway/status` (LIVE) |
| LiveControlPage > Observed Metrics | aggregate down/up/RTT/jitter/loss | `getCurrentObservations?scope=client` (summed) | `/api/v1/observations/current` (LIVE; `aggregate_gateway` available, currently summed from client scope) |
| LiveControlPage > Connected Clients | per-client down/up/RTT/jitter/loss + QoE | `getCurrentObservations?scope=client` + `getCurrentQoe` | `/api/v1/observations/current?scope=client`, `/api/v1/qoe/current` (LIVE) |
| LiveControlPage > Safety and scope | environment + scope badges | static / derived from observations | static |

## Components

| Component | Role | Source | Notes |
|---|---|---|---|
| AppShell | header + sidebar + status | `getHealth` / `getGatewayStatus` / `getSystemCapabilities` | LIVE in live mode (5 s poll), static in demo. Badge + unreachable banner. |
| ComparisonChart | time-series chart | `getComparison()` via ComparePage | NONE |
| MetricCard | baseline-vs-optimized card | `getComparison()` via ComparePage | NONE |
| StatusBadge | presentational badge | n/a | pure UI |
| NetworkTopology.jsx | topology graph | not imported | DEAD CODE (earlier live-API component) |
| hooks/useProductData.js | multi-endpoint data hook | not imported | DEAD CODE (wires `/observations/history`, `/clients/{id}/history`, `/qoe/history`, `/network/topology`; available for reuse in later stages) |

## Live wiring status (Stage 1 spec map)

- clients and usage tree <- `/network/topology` + `/observations/current?scope=client`: LIVE client cards on LiveControlPage. ComparePage usage tree = not connected yet (component needs null-safe numeric rendering before live wiring).
- household/aggregate metrics <- `/observations/current?scope=aggregate_gateway`: shown on LiveControlPage, computed from live client observations (equivalent to the aggregate endpoint).
- live metrics charts <- `/observations/history` and `/clients/{id}/history`: wired in unused `useProductData.js`; no page renders history charts live yet.
- per-device QoE scorecard <- `/qoe/current` and `/qoe/history`: LIVE QoE on LiveControlPage client cards; `/qoe/history` wired in unused hook.
- Scenario Lab <- `/scenarios*`: LIVE on ComparePage.
- system/health/status <- `/gateway/status`, `/health`, `/system/capabilities`: LIVE on AppShell + LiveControlPage.

## Not connected yet (later stages)

- A/B comparison metrics, series, conclusion (Stage 4).
- ML pipeline, serving models, feature importance, predictions, model health (Stage 2).
- Intent control, decision log, enforcement, forecast, classifier (Stages 2-3).
