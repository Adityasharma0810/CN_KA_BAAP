# Part 1 — Observe: Current Audit and Dependency Checklist

**Audit date:** 2026-11-09
**Updated:** 2026-11-09 (Modules 1–4 status; Module 4 storage layer complete)
**Branch:** `main`
**Original baseline test command:** `.venv\Scripts\python.exe -m pytest -q`
**Original baseline result:** 106 passed
**Current regression command:** `.venv/bin/python -m pytest -q`
**Current regression result:** 215 passed

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
| Linux per-client counters | COMPLETE | `gateway/accounting.py`, `gateway/collector.py` | Reusable sysfs reader, configurable inventory, rate/reset/disappearance handling, and per-client isolation; legacy `read_bytes()` delegates to the shared reader | Unit tests plus real three- and five-client Ubuntu runs in `docs/MODULE3_EVIDENCE.md` |
| Linux anonymous IDs | COMPLETE | `backend/app/services/client_registry.py`, `gateway/collector.py` | Module 2 completed the runtime-only registry with lifecycle, stable labels, memory-only address associations, validation, and privacy tests | Registry lifecycle, forbidden-field, and persistence-boundary tests |
| Linux gateway API | PARTIAL / INTEGRATION BROKEN | `gateway/api.py` | Separate FastAPI app, same default port, policy/control routes mixed into observation path, dashboard does not consume it | Unified API integration tests; Part 1 must not expose arbitrary commands |
| Shared telemetry schema | COMPLETE | `backend/app/models/schemas.py` | Module 1 added typed observation metadata, source/scope/quality/environment vocabulary, UTC validation, client-scope rules, and forbidden-field rejection | `tests/unit/test_observation_schemas.py` |
| SQLite aggregate history | COMPLETE | `network/telemetry/metrics_store.py` | Module 4 added versioned non-destructive migrations, canonical aggregate/per-client observation storage, anonymous client persistence, bounded filtered history queries, privacy validation, and concurrency/large-query tests; legacy `network_samples` remains intact | `tests/unit/test_database_migrations.py`, `test_client_persistence.py`, `test_observation_persistence.py`, `test_history_queries.py`, `test_storage_privacy.py`, `test_storage_integration.py`, `test_storage_reliability.py` |
| Unified observation API | MISSING | `backend/app/main.py`, `backend/app/api/*` | No gateway status, topology, client list, per-client current/history, or lab routes | API unit/integration/privacy tests |
| Lab setup/reset | COMPLETE | `scripts/setup_gateway.sh`, `scripts/cleanup_gateway.sh`, `scripts/lab_common.sh` | Default three clients, configurable to five or more, validated names/counts, ownership markers/state, idempotent setup/cleanup, and only project-owned nft/interface changes | Real three- and five-client reset/cleanup runs in `docs/MODULE3_EVIDENCE.md` |
| Scenario A | PARTIAL | `experiments/run_call_vs_download.py`, shell scripts | Existing experiment is not yet the required single reproducible baseline workflow with standard CSV, plots, settings, and versions | Ubuntu scenario run and artifact validation |
| React dashboard | PARTIAL | `frontend/src/App.jsx`, `NetworkTopology.jsx` | Aggregate-only UI; no live anonymous client list or per-client measurements; frontend lint issues must be checked | `npm run lint`, `npm run build`, API fixture/component checks |
| Documentation | PARTIAL | `README.md`, `docs/*`, `frontend/README.md` | Prior audit exists; current Part 1 architecture, API examples, privacy limits, and Windows/Ubuntu workflow need consolidation | Documentation review and command verification |
| ML/QoE/forecasting | DEFERRED | `ml/*`, `machine_learning/*`, `experiments/capacity_forecasting/*` | Outside Part 1 except for future-compatible telemetry fields | No Part 1 implementation claims |

## Privacy and security findings

Existing code generally avoids packet payload inspection and does not persist IP/MAC addresses in the aggregate SQLite table. However, the repository does not yet have a centralized privacy boundary or tests that reject forbidden identity fields across all new storage/API paths. The gateway API also contains privileged helper execution for policy controls; Part 1 observation endpoints must not generalize this into arbitrary command execution.

**Module 4 update:** the storage layer now has a centralized privacy boundary and automated tests for schema, rows, serialization, error metadata, and address-mapping exclusion. API-layer privacy tests remain future work because the unified observation API is not implemented yet.

Tracked generated data exists under `data/capacity_forecasting/` and experiment outputs under `experiments/`. These are existing project artifacts and require a separate decision before changing `.gitignore` or removing anything. Runtime SQLite files are already ignored by `.gitignore`.

## Module status update (2026-11-09)

This section supersedes the earlier `MISSING`/`PARTIAL` statuses for the rows
noted below. The original audit text above is retained for history.

- **Module 1 — Shared Observation Schema: COMPLETE.** `backend/app/models/schemas.py`
  defines the shared source/scope/quality/environment vocabulary, UTC timestamp
  validation, client-scope rules, and forbidden-identity rejection.
- **Module 2 — Anonymous Client Registry: COMPLETE.** `backend/app/services/client_registry.py`
  is runtime-only, assigns opaque IDs and `Client NN` labels, keeps address
  associations transient, and never serializes them.
- **Module 3 — Genuine Per-Client Linux Accounting: COMPLETE.** `gateway/accounting.py`
  reads one gateway-side veth per client, handles no-baseline/reset/missing
  interfaces without fabricating rates, and passes real three- and five-client
  Ubuntu runs in `docs/MODULE3_EVIDENCE.md`.
- **Module 4 — Database and Historical Telemetry: COMPLETE for the storage
  layer.** `network/telemetry/metrics_store.py` now provides versioned,
  transactional, non-destructive migrations; canonical aggregate and per-client
  observation storage; anonymous client persistence; bounded filtered history
  queries; privacy validation; and concurrency/large-query tests. The legacy
  `network_samples` table and all existing rows remain untouched. See
  `docs/MODULE4_DATABASE.md`.

Module 4 limitation: no real `data/experience_budget.sqlite3` file exists in this
checkout. Migration was tested against representative temporary legacy databases,
not against an actual production file. The unified observation API and dashboard
history integration remain later-module work.

## Dependency-ordered Part 1 checklist

- [x] Repository audit and feature inventory.
- [x] Define common telemetry schema, provenance vocabulary, and UTC serialization.
- [x] Add anonymous client registry with memory-only address associations and privacy tests.
- [x] Extract robust Linux per-client counter collector with reset/disconnect handling.
- [x] Add rate calculation and telemetry-quality/staleness semantics.
- [x] Migrate SQLite storage with aggregate/per-client separation and bounded queries.
- [ ] Integrate observation routes and health checks into one FastAPI application.
- [x] Harden namespace/veth lab setup, reset, ownership, and dependency checks.
- [ ] Build reproducible Scenario A CSV/plot/tool-version workflow.
- [ ] Upgrade the existing dashboard using API-provided topology and measurements.
- [ ] Consolidate documentation and run final cross-layer regression tests.

## First atomic implementation task (completed)

This task was completed in Module 1. It provided typed, privacy-safe
representations for:

- UTC measurement timestamps.
- Source/provenance (`windows_host`, `windows_hotspot`, `linux_gateway`, `linux_namespace_lab`).
- Scope (`aggregate_gateway`, `aggregate_hotspot`, `client`).
- Value quality (`measured`, `derived`, `unavailable`).
- Environment (`physical_host`, `simulated_lab`).
- Optional anonymous client ID, with no IP/MAC/device-name fields.
- Freshness/error metadata without inventing unavailable values.

The task is complete only after schema validation/serialization tests pass and the existing 106-test regression suite still passes. No collector, database, API, Linux script, or frontend behavior should be changed in this atomic task.
