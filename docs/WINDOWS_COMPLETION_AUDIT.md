# Windows Completion Audit

**Date:** 2026-11-10  
**Repository:** `main` at `cf5c19e` (`Windows completion pass: real API integration, honest model page, audit docs`)
**Scope:** Windows-compatible completion pass; native Ubuntu and hardware work remain explicitly separated.

This report supersedes stale Windows-side status claims in `docs/PROJECT_COMPLETION_TRACKER.md` for this audit. Native Ubuntu work is not marked complete without native evidence.

## Current state

The repository contains a Windows-capable FastAPI/SQLite product and a separate Ubuntu namespace gateway lab. The product observation, storage, API, Scenario Lab, gateway transport, and gateway ingest foundations are implemented. The Linux lab has namespace accounting, restricted helper enforcement, TBF shaping, and a rule-based controller.

The three-page React shell uses the shared API client. Live Control reads health, gateway, platform capability, client-scoped observations, and QoE data. Compare uses the bounded Scenario Lab catalog/start/stop lifecycle only; the backend has no paired A/B results endpoint. The repair in this audit removes misleading status fallbacks, overlapping polling, and decorative baseline/optimized comparison labels. Model Intelligence remains a disclosure of offline artifacts and the current product path, not live inference.

## Status key

- `COMPLETE`: implementation and relevant evidence exist.
- `PARTIAL`: implementation exists but acceptance or integration is incomplete.
- `BLOCKED_UBUNTU`: native Linux verification is required.
- `BLOCKED_HARDWARE`: physical router/device capability is required.
- `BLOCKED_ENVIRONMENT`: required runtime or dependency was unavailable.
- `NOT_STARTED`: no verified product-path implementation.

## Core matrix F1-F12

| Feature | Status | Windows work | Ubuntu work | Evidence |
|---|---|---|---|---|
| F1 Observe/normalize | PARTIAL | Complete remaining freshness, retention, and frontend contract coverage | Verify live Linux provenance | Backend APIs, schemas, storage tests |
| F2 Privacy-safe classification | NOT_STARTED | Implement versioned features, held-out evaluation, runtime interface | Capture real Linux counters for live validation | Classifier path is not live |
| F3 Capacity estimation | NOT_STARTED | Implement estimator and uncertainty tests | Validate against live traces | Kalman product path absent |
| F4 Forecasting | PARTIAL | Connect forecasts, persistence fallback, confidence gating | Validate on Linux traces | Offline forecasting modules/artifacts |
| F5 QoE scoring | PARTIAL | Expand fixtures and explanations | Compare with lab experiments | `ml/qoe/scorer.py`, QoE APIs |
| F6 Fairness optimization | PARTIAL | Upgrade weighted allocation to constrained QoE optimizer | Validate enforcement outcomes | `gateway/policy.py` is weighted allocation |
| F7 Intent lifecycle | PARTIAL | Add expiration, cancellation, conflict contracts | Verify policy application | Scenario profiles only |
| F8 Decision ledger | NOT_STARTED | Implement privacy-safe decision records/API | Verify enforcement references | No complete ledger found |
| F9 Verification/rollback | PARTIAL | Implement platform-independent orchestration | Verify qdisc rollback | Scenario cleanup exists; general verifier absent |
| F10 Confidence gating | NOT_STARTED | Connect forecasts/models to safe decisions | Validate degraded operation | No live gate |
| F11 Linux enforcement | PARTIAL | Keep capability abstraction/test adapter | Verify TBF and add CAKE/HTB/fq_codel where supported | Linux lab evidence; native verification required |
| F12 Closed-loop controller | PARTIAL | Integrate controller components and ledger | Run real closed-loop evidence | Rule-based gateway controller |

## Advanced matrix F13-F17

| Feature | Status | Assessment |
|---|---|---|
| F13 Experiment harness | PARTIAL | Existing scripts/reports; registry and statistical service remain | Native repeated runs required |
| F14 Scenario Lab | PARTIAL | APIs exist; frontend lifecycle integration remains | Real helper/namespace execution required |
| F15 ML live integration | NOT_STARTED | Runtime serving, logging, smoothing, policy connection | Live Linux telemetry validation |
| F16 Windows/Ubuntu operations | PARTIAL | Transport and ingest exist; live reconnect evidence remains | VM must be reachable |
| F17 Federated learning | NOT_STARTED | No implementation | Not Ubuntu-only; advanced roadmap |

## Windows-completable work

- Centralize frontend API access and use real backend data.
- Correct route composition and direct navigation verification.
- Complete storage retention, migration, pagination, and concurrency tests.
- Implement classifier feature contracts and offline held-out evaluation.
- Implement estimator and forecast confidence interfaces.
- Expand QoE tests and explanations.
- Implement fairness, intent, verifier, rollback orchestration, and decision ledger as platform-independent modules.
- Add enforcement abstraction and deterministic Windows test adapter.
- Build experiment registry and report processing.
- Add frontend tests and E2E infrastructure.
- Reconcile documentation and completion matrix.

## Ubuntu-only work

- Namespace, bridge, veth, nftables, tc, qdisc, helper, and native Linux integration testing.
- CAKE/HTB/fq_codel capability and enforcement verification.
- Real upload/download shaping and read-back.
- Real gateway-agent execution and restart/recovery.
- Real Linux experiment evidence.

See `docs/UBUNTU_REMAINING_TASKS.md` for the actionable handoff.

## Hardware limitations

Physical per-device attribution, Wi-Fi diagnostics, physical-router QoS, and multi-WAN failover require hardware/router APIs. Namespace evidence must remain labelled `simulated_lab` and cannot establish those capabilities.

## Validation run on 2026-11-10

- Frontend ESLint: PASS (`node frontend/node_modules/eslint/bin/eslint.js frontend`).
- Frontend production build: PASS (`vite v8.3.6`; 291.53 kB JS bundle, 90.44 kB gzip).
- Targeted backend contract/regression tests: 58 PASS on the current Linux development environment; one Starlette/httpx deprecation warning.
- Full Python suite: not rerun in this repair pass; the older Windows-host result (349 PASS, 37 shell-dependent failures) is historical and not current validation.
- Frontend unit tests: not configured; no frontend test script or test files exist.
- Browser route checks: pending runtime availability.

The current checkout is on Linux. These results do not establish native Windows execution or Ubuntu VM/network integration.
