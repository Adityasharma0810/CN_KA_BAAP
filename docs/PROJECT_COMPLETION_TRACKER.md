# Experience Budget Project Completion Tracker

**Source of truth date:** 2026-11-10  
**Repository:** `main` at `cf5c19e` (`Windows completion pass: real API integration, honest model page, audit docs`)
**Scope:** Master project completion prompt, reconciled against the checked-out code and the repository audit.

## Status vocabulary

- **NOT STARTED** — no implementation exists in the product path.
- **IN PROGRESS** — implementation has begun but acceptance is incomplete.
- **IMPLEMENTED** — code exists, but integration or evidence is incomplete.
- **TESTED** — targeted automated tests pass, but product integration may remain.
- **INTEGRATED** — connected to the product path and verified at its boundary.
- **COMPLETE** — acceptance criteria, tests, evidence, documentation, and limitations all pass.
- **BLOCKED** — cannot be completed in the current environment without the stated dependency.

## Executive status

The checkout contains two substantially working tracks:

1. A Windows-friendly FastAPI/SQLite/React aggregate monitoring product.
2. A Linux namespace lab with per-client counters, ICMP measurements, traffic limits, a rule-based intent policy, Scenario Lab, and manually measured experiments.

The tracks are now connected by an authenticated, read-only gateway observation transport with bounded response size, strict schema validation, safe disconnected/stale state reporting, and a persistent gateway ingest worker that runs alongside the local lab ingest. ML classification, forecasting, intent negotiation, closed-loop policy verification, A/B product APIs, and federated learning are not complete.

**Overall project status: IN PROGRESS.**

## Part 1 — Observe

| Area | Status | Evidence / remaining work |
|---|---|---|
| P1.1 Canonical observation schema | INTEGRATED | Typed `TelemetryObservation` models, UTC metadata, source/scope/environment/quality fields, and SQLite persistence exist. Add a complete contract test matrix for stale and derived values. |
| P1.2 Windows host and hotspot monitoring | IMPLEMENTED | Existing monitoring services collect aggregate adapter/hotspot data. Fix adapter selection/history consistency, configurable hotspot interface, and add Windows failure/staleness tests. |
| P1.3 Anonymous client management | INTEGRATED | Runtime opaque IDs, simulated slot registry, display labels, and persisted simulated-slot continuity exist. Expand lifecycle/reset/privacy coverage. |
| P1.4 Linux gateway accounting | TESTED | Namespace lab collector and ingest service persist per-client and aggregate observations. Real VM evidence is documented; automated multi-client VM E2E remains outstanding. |
| P1.5 Windows–Ubuntu integration | TESTED | Authenticated read-only gateway transport with bounded response size, strict schema validation, retry/backoff, safe error codes, and a persistent gateway ingest worker with connected/disconnected state are implemented and unit-tested. Real Ubuntu VM integration evidence is the next validation step. |
| P1.6 SQLite storage | IMPLEMENTED | Versioned `MetricsStore`, migrations, indexes, privacy validation, and historical queries exist. Complete concurrent access, retention, and migration fixture tests. |
| P1.7 Product observation APIs | INTEGRATED | Health, collector health, gateway status, clients, observations, topology, capabilities, scenarios, and QoE routes are present. Complete invalid-filter and disconnected-agent contract tests. |
| P1.8 Evidence-based topology | INTEGRATED | Product topology API and dashboard representation distinguish measured/configured/simulated topology. Audit physical identity and stale-state cases. |
| P1.9 Observation dashboard | IMPLEMENTED | Product dashboard consumes product APIs. Current repair validation: lint and production build are being rerun; no frontend unit-test runner or E2E suite is configured. |

## Part 2 — Understand and decide

| Feature | Status | Evidence / remaining work |
|---|---|---|
| F1 Observe and normalize telemetry | INTEGRATED | Canonical observations and query services exist. Finish contract and freshness coverage. |
| F2 Privacy-safe traffic classification | NOT STARTED | `ml` classifier path is not live; current Scenario Lab uses declared profiles. Implement packet-counter feature extraction and a run-held-out classifier. |
| F3 Capacity estimation | NOT STARTED | No integrated Kalman capacity estimator in the product decision path. |
| F4 Capacity forecasting | IMPLEMENTED | Forecasting research/modules and saved artifacts exist, but no validated live product integration or confidence gating is evidenced. |
| F5 Workload-aware QoE scoring | IMPLEMENTED | `ml/qoe/scorer.py` and `/api/v1/qoe/*` provide deterministic observation-only proxy scores. Validate against broader workload fixtures and document proxy limits. |
| F6 True max-min QoE optimization | IMPLEMENTED | `gateway/policy.py` provides weighted allocation, not yet a product-integrated QoE optimizer with utility curves, constraints, and proof/evidence. |
| F7 Intent declaration and conflict handling | IMPLEMENTED | Temporary Scenario Lab profile declaration exists. Expiry/rollback exists for scenarios; general intent API, conflict negotiation, and explanations are incomplete. |
| F8 Decision explanations and ledger | NOT STARTED | No complete product decision ledger with inputs, constraints, selected action, confidence, and rollback reason. |
| F9 Policy verification and rollback | IMPLEMENTED | Scenario cleanup and bounded rollback exist. A general pre/post verifier for policy actions is missing. |
| F10 Forecast/confidence gating | NOT STARTED | Forecast artifacts are not connected to a confidence-gated controller. |

## Part 3 — Act and demonstrate

| Feature | Status | Evidence / remaining work |
|---|---|---|
| F11 Linux QoS enforcement | IMPLEMENTED | Lab `tc` shaping and restricted helper work in the VM. Enforcement is TBF-based; CAKE/HTB+fq_codel support and a product abstraction are not complete. |
| F12 Closed-loop adaptive controller | IMPLEMENTED | Rule-based gateway controller is manually validated in the lab. It is separate from the Windows product API and has known throughput inefficiency. |
| F13 Reproducible A/B experiment harness | IMPLEMENTED | Two Python harnesses and CSV reports exist for two scenarios. Add a product-facing experiment registry, manifests, statistical summaries, and ML mode. |
| F14 Scenario Lab | INTEGRATED | Catalog and bounded lifecycle APIs, phase timeline, manifests, observation export, cleanup, and UI lifecycle integration exist. Paired A/B result APIs and native helper/namespace acceptance remain unavailable. |
| F15 ML Lab / live classifier integration | NOT STARTED | Saved model artifacts exist, but live feature logging, model serving, prediction smoothing, and policy integration are absent. |
| F16 Windows/Ubuntu operational integration | IN PROGRESS | Authenticated bounded transport and persistent ingest with safe disconnected/retry state are implemented and unit-tested. Real Windows-to-Ubuntu VM reconnect/staleness evidence remains missing. |
| F17 Advanced learning / federated capability | NOT STARTED | No federated learning or privacy-preserving cross-household training path exists. |

## Highest-priority incomplete atomic task

**Run the real Ubuntu VM integration smoke test** for the already implemented product-facing gateway observation transport. Verify connected/disconnected transitions, persistence, invalid authentication, timeout/backoff, restart recovery, and freshness through the product APIs. Keep VM evidence separate from mocked contract tests.

This is the highest-priority remaining Part 1 integration checkpoint because it establishes the Windows-to-Ubuntu boundary before forecast, classification, or policy decisions can safely consume remote per-client observations. See `docs/NEXT_IMPLEMENTATION_TASK.md`.

## Milestone acceptance policy

A milestone is not marked COMPLETE until:

- targeted tests pass;
- relevant regression tests pass;
- privacy and security checks pass;
- the product boundary is integrated;
- evidence identifies simulated versus real VM behavior;
- known limitations are updated;
- the diff is reviewed and committed.

## Test and evidence ledger

| Check / evidence | Current result | Reference |
|---|---|---|
| Targeted backend contract/regression tests | 58 passed on the current Linux development environment; one Starlette/httpx deprecation warning | `tests/unit/` |
| Linux gateway policy/controller tests | Reported passing on Ubuntu VM | `tests/test_policy.py`, `tests/test_controller.py` |
| Linux lab manual connectivity and shaping | Observed passing on Ubuntu VM | `docs/REPO_AUDIT.md`, `docs/REPRODUCE_V0_9.md` |
| Call-vs-download experiment | 5-run manual report exists | `experiments/reports/` |
| Streaming-vs-download experiment | 5-run manual report exists | `experiments/reports/` |
| Frontend production build | PASS (`vite v8.3.6`; 291.53 kB JS bundle) | `frontend/` |
| Frontend lint | PASS (ESLint) | `frontend/` |
| Gateway transport contract tests | 5 tests passed: valid response, auth failure no retry, malformed payload, oversized response, transport failure bounded | `tests/unit/test_gateway_transport.py` |
| Gateway ingest service tests | 2 tests passed: valid observations persisted, transport failure safe state | `tests/unit/test_gateway_ingest_service.py` |

## Commit references

- `cf5c19e` — audited base checkout (`Windows completion pass: real API integration, honest model page, audit docs`)
- `258b1c9` — `eb-priv` stop-all argument handling
- `285b217` — Scenario Lab
- `bb644d4` — client data consistency
- `d76304c` — Phase 2 dashboard

This tracker must be updated after each completed milestone; it must not be used to imply completion from file presence alone.
