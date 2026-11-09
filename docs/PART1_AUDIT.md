# Part 1 — Observe: Current Audit and Dependency Checklist

**Audit date:** 2026-11-09
**Branch:** `main`
**Baseline test command:** `.venv\Scripts\python.exe -m pytest -q`
**Baseline result:** 106 passed

## Scope

This audit inventories the existing repository before Part 1 implementation. It distinguishes working prototype behavior from the capabilities required by the Part 1 — Observe specification. Existing Part 2 model and experiment files are intentionally not being redesigned here.

## Current architecture

The repository currently contains two independent application paths:

1. **Windows/local aggregate monitoring**
   - FastAPI application: `backend/app/main.py`
   - Routes: `backend/app/api/monitoring.py`
   - Coordinator: `backend/app/services/monitoring_service.py`
   - Collectors: `network/telemetry/*`
   - SQLite store: `network/telemetry/metrics_store.py`
   - React dashboard: `frontend/src/App.jsx`

2. **Linux namespace gateway lab**
   - Separate FastAPI application: `gateway/api.py`
   - Per-client collector: `gateway/collector.py`
   - Namespace/veth setup: `scripts/setup_gateway.sh`
   - Cleanup: `scripts/cleanup_gateway.sh`
   - Scenario scripts: `scripts/call_vs_download.sh`, `experiments/run_call_vs_download.py`, and related files

The two application paths do not share schemas, persistence, health reporting, or API routes. Both use port 8000 in their documented/default usage, so they cannot be run together without an explicit integration decision.

## Feature inventory

| Feature | Status | Relevant files | Missing or weak behavior | Acceptance evidence needed |
|---|---|---|---|---|
| Windows adapter aggregate counters | PARTIAL | `network/telemetry/interface_stats.py`, `bandwidth_monitor.py` | Functional, but no shared provenance schema; counter reset raises instead of producing an unavailable/reset sample | Unit tests for normal, reset, missing-interface, and stale samples |
| Windows connectivity and ICMP quality | PARTIAL | `connectivity_monitor.py`, `network_quality.py` | Quality output is not represented by a common telemetry model; ICMP loss must remain clearly distinct from application loss | Schema and serialization tests; documented formula |
| Windows Mobile Hotspot | PARTIAL | `hotspot_bandwidth_monitor.py`, `monitoring_service.py` | Correctly aggregate-only, but hardcoded adapter default and separate storage/query convention | Tests proving aggregate scope and no client identity |
| Existing Windows FastAPI app | PARTIAL | `backend/app/main.py`, `backend/app/api/monitoring.py` | Functional endpoints, but no collector/database/lab health model and no Linux integration | API contract tests and health failure tests |
| Linux per-client counters | PARTIAL | `gateway/collector.py` | Reads bridge-side counters for three hardcoded clients; no reset/disappearance handling; no reusable collector abstraction | Unit tests with fake sysfs; Ubuntu integration tests when available |
| Linux anonymous IDs | PARTIAL | `gateway/collector.py` | Random in-memory IDs exist, but no lifecycle registry, stable session semantics, validation, or privacy tests | Registry lifecycle and forbidden-field tests |
| Linux gateway API | PARTIAL / INTEGRATION BROKEN | `gateway/api.py` | Separate FastAPI app, same default port, policy/control routes mixed into observation path, dashboard does not consume it | Unified API integration tests; Part 1 must not expose arbitrary commands |
| Shared telemetry schema | MISSING | `backend/app/models/schemas.py` is empty | Windows and Linux dictionaries have unrelated field names and provenance semantics | Pydantic model tests and cross-source fixtures |
| SQLite aggregate history | PARTIAL | `network/telemetry/metrics_store.py` | Aggregate-only schema; no observation source/type/client separation or migration versioning | Migration, bounded query, and separation tests |
| Unified observation API | MISSING | `backend/app/main.py`, `backend/app/api/*` | No gateway status, topology, client list, per-client current/history, or lab routes | API unit/integration/privacy tests |
| Lab setup/reset | PARTIAL | `scripts/setup_gateway.sh`, `cleanup_gateway.sh` | Fixed to three clients; cleanup and NAT ownership need stronger validation and state handling | Repeated reset test in Ubuntu VM; blocked status if VM unavailable |
| Scenario A | PARTIAL | `experiments/run_call_vs_download.py`, shell scripts | Existing experiment is not yet the required single reproducible baseline workflow with standard CSV, plots, settings, and versions | Ubuntu scenario run and artifact validation |
| React dashboard | PARTIAL | `frontend/src/App.jsx`, `NetworkTopology.jsx` | Aggregate-only UI; no live anonymous client list or per-client measurements; frontend lint issues must be checked | `npm run lint`, `npm run build`, API fixture/component checks |
| Documentation | PARTIAL | `README.md`, `docs/*`, `frontend/README.md` | Prior audit exists; current Part 1 architecture, API examples, privacy limits, and Windows/Ubuntu workflow need consolidation | Documentation review and command verification |
| ML/QoE/forecasting | DEFERRED | `ml/*`, `machine_learning/*`, `experiments/capacity_forecasting/*` | Outside Part 1 except for future-compatible telemetry fields | No Part 1 implementation claims |

## Privacy and security findings

Existing code generally avoids packet payload inspection and does not persist IP/MAC addresses in the aggregate SQLite table. However, the repository does not yet have a centralized privacy boundary or tests that reject forbidden identity fields across all new storage/API paths. The gateway API also contains privileged helper execution for policy controls; Part 1 observation endpoints must not generalize this into arbitrary command execution.

Tracked generated data exists under `data/capacity_forecasting/` and experiment outputs under `experiments/`. These are existing project artifacts and require a separate decision before changing `.gitignore` or removing anything. Runtime SQLite files are already ignored by `.gitignore`.

## Dependency-ordered Part 1 checklist

- [x] Repository audit and feature inventory.
- [ ] Define common telemetry schema, provenance vocabulary, and UTC serialization.
- [ ] Add anonymous client registry with memory-only address associations and privacy tests.
- [ ] Extract robust Linux per-client counter collector with reset/disconnect handling.
- [ ] Add rate calculation and telemetry-quality/staleness semantics.
- [ ] Migrate SQLite storage with aggregate/per-client separation and bounded queries.
- [ ] Integrate observation routes and health checks into one FastAPI application.
- [ ] Harden namespace/veth lab setup, reset, ownership, and dependency checks.
- [ ] Build reproducible Scenario A CSV/plot/tool-version workflow.
- [ ] Upgrade the existing dashboard using API-provided topology and measurements.
- [ ] Consolidate documentation and run final cross-layer regression tests.

## First atomic implementation task

Implement the shared observation schema only. It must provide typed, privacy-safe representations for:

- UTC measurement timestamps.
- Source/provenance (`windows_host`, `windows_hotspot`, `linux_gateway`, `linux_namespace_lab`).
- Scope (`aggregate_gateway`, `aggregate_hotspot`, `client`).
- Value quality (`measured`, `derived`, `unavailable`).
- Environment (`physical_host`, `simulated_lab`).
- Optional anonymous client ID, with no IP/MAC/device-name fields.
- Freshness/error metadata without inventing unavailable values.

The task is complete only after schema validation/serialization tests pass and the existing 106-test regression suite still passes. No collector, database, API, Linux script, or frontend behavior should be changed in this atomic task.
