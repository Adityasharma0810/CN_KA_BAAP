# Experience Budget Architecture

**As-of:** 2026-11-10  
**Repository commit:** `3d466fd`  
**Architecture status:** partially integrated reference implementation; Linux namespace lab is simulated and must not be confused with a physical-router deployment.

## 1. System boundary

Experience Budget has a product-facing Windows-compatible application and a Linux-only namespace lab.

```text
React dashboard
      |
      | HTTP / JSON
      v
FastAPI product backend (backend/app)
      |
      +--> Windows aggregate monitoring --> SQLite
      |
      +--> Linux namespace-lab ingest --> SQLite
      |         +--> per-client counters
      |         +--> restricted ICMP probe helper
      |         +--> derived aggregate observation
      |
      +--> observation/query APIs
      +--> QoE proxy APIs
      +--> Scenario Lab service

Linux VM only:
  namespaces/veth/bridge --> gateway collector --> restricted helper/tc
  gateway API/controller/policy and experiment harnesses
```

The remote gateway observation transport is implemented and unit-tested:

```text
Windows product backend --authenticated read-only transport--> Linux observation agent
    (GatewayTransport + GatewayIngestService)
```

- `GatewayTransport`: fixed read-only path `GET /api/v1/observations/current`, bearer auth, bounded timeout/retry, 1 MB response limit, strict versioned schema validation, injectable HTTP client.
- `GatewayIngestService`: persistent worker with backoff, client registration, canonical SQLite persistence, `connected`/`disconnected` state, safe error codes.
- Lifespan integration in `backend/app/main.py` when `EB_GATEWAY_URL` is configured.

Real Ubuntu VM integration evidence is the next validation step.

## 2. Product backend

`backend/app/main.py` creates the canonical FastAPI app and registers:

- `backend/app/api/monitoring.py` — host and hotspot collection/history;
- `backend/app/api/clients.py` — anonymous client inventory and client history;
- `backend/app/api/topology.py` — evidence-based topology;
- `backend/app/api/v1/*` — health, collector health, observations, QoE, scenarios, gateway status, and capabilities.

The application lifespan starts and stops:

- `latency_probe_service` on Linux when the restricted helper is available;
- `lab_ingest_service` when Linux namespace lab ingestion is enabled/available;
- `scenario_service` cleanup on shutdown.

CORS origins are local-development defaults plus `EB_CORS_ORIGINS`.

## 3. Canonical telemetry flow

`network/telemetry/metrics_store.py` is the persistence boundary. Observations are typed by models under `backend/app/models/` and carry:

- UTC `observed_at`;
- `source` and `scope`;
- `environment`;
- measured/derived/simulated/unavailable quality;
- optional opaque `client_id`;
- safe collector error codes;
- byte/packet counters and rate/latency fields where available.

The lab path is:

1. `lab_accounting_service` reads configured namespace/veth counters.
2. `latency_probe_service` probes configured slots concurrently through `/usr/bin/sudo -n /usr/local/libexec/eb/eb-priv probe <slot>`.
3. `lab_ingest_service` merges probe metrics, validates the complete anonymous inventory, derives an aggregate gateway observation, and saves client plus aggregate rows transactionally through `MetricsStore`.

The remote gateway path (when `EB_GATEWAY_URL` is configured):

1. `GatewayTransport` fetches `GET /api/v1/observations/current` from the configured Linux agent with bearer authentication, bounded timeout, retry budget, and 1 MB response size limit.
2. `GatewayObservationResponse` schema validates version, UTC timestamp, observation count (1–100), and allowed Linux sources.
3. `GatewayIngestService` persists validated observations through `MetricsStore`, registers anonymous clients, and exposes `connected`/`disconnected` state with `last_success_at`.
4. Observation query services apply source/scope/client/time/pagination filters.
5. API response models expose typed, privacy-safe data to the dashboard.

Missing data remains unavailable; it is not converted to zero.

## 4. Anonymous identity model

The lab uses stable opaque IDs for configured simulated slots while the local registry is active. Display labels such as `Client 01` are separate from identifiers. Physical IPs, MACs, hostnames, payloads, and browsing data are not part of the product observation contract.

The identity model is intentionally not a physical-device identity system. A namespace slot is a simulated lab endpoint, not a household phone or laptop.

## 5. Linux lab and enforcement

The Linux VM scripts create a bridge and isolated client namespaces with veth pairs. `gateway/collector.py` reads interface counters. `gateway/policy.py` computes an intent-weighted allocation and `gateway/controller.py` turns measurements into bounded limit targets. The restricted helper and shell scripts apply lab-only `tc` limits and restore them during cleanup.

This is a separate implementation track from the product backend. It demonstrates kernel traffic control inside a testbed; it does not control the physical Wi-Fi adapter, household router, or WAN.

The current enforcement evidence is TBF-based. CAKE, HTB+fq_codel, capability detection, and a product-level enforcement abstraction are still open.

## 6. Decision and QoE path

`ml/qoe/scorer.py` provides deterministic observation-only proxy scoring for call, game, stream, and bulk classes. `backend/app/services/qoe_service.py` maps active Scenario Lab profiles to anonymous clients and returns current/history scores through typed APIs.

The current score is not a validated subjective QoE model and does not infer intent. Scenario declarations supply classes. Forecasting and model artifacts are not yet connected to confidence-gated policy decisions.

## 7. Scenario Lab

`backend/app/services/scenario_service.py` owns one bounded run at a time:

1. validates catalog entry, duration, and available slots;
2. writes a run manifest with timeline and tool versions;
3. invokes only the installed restricted helper through non-interactive sudo;
4. executes bounded phases;
5. cancels/stops traffic and restores the bottleneck in cleanup;
6. exports observations to `observations.csv` and finalizes the manifest.

The API and frontend expose catalog/status/start/stop behavior. Runs are simulated-lab evidence and have explicit manifests; they are not physical network experiments.

## 8. Experiment path

`experiments/run_call_vs_download.py` and `experiments/run_streaming_vs_download.py` run reproducible Linux namespace scenarios and write CSV reports. The existing reports demonstrate the rule-based baseline under a deliberately simulated bottleneck. They do not yet constitute a product-facing A/B experiment service or ML classifier evaluation.

## 9. Planned next integration

The next boundary is an authenticated, read-only gateway observation client:

- configurable URL and token from environment;
- strict versioned response schema;
- bounded timeout and limited retry/backoff;
- safe disconnected and stale states;
- injectable HTTP transport for deterministic tests;
- no arbitrary command execution or enforcement endpoints;
- no public exposure requirement for the Linux agent.

After that boundary is verified, the dependency order is: complete observation freshness/storage contract tests, classifier feature logging and run-held-out evaluation, capacity estimator/forecast confidence gating, intent/decision ledger, policy verification, experiment product integration, and advanced learning capability.

## 10. Deployment truth

| Component | Supported environment | Reality |
|---|---|---|
| Product backend, SQLite, API tests | Windows and Linux | Platform-independent Python path, subject to configured collectors |
| React dashboard | Windows/Linux development browser | Consumes product API; frontend lint has known failures |
| Host/hotspot monitoring | Windows | Aggregate measurements only for hotspot |
| Namespace lab, tc, nftables, ICMP helper | Ubuntu VM/Linux | Simulated clients and lab-only enforcement |
| Physical router/Wi-Fi remediation | None | Not implemented and not claimed |
