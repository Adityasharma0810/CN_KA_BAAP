# Module 5A — Existing API Architecture Audit

**Status:** AUDIT COMPLETE (no application code changed)
**Audit date:** 2026-11-09
**Branch:** `main`
**Baseline HEAD:** `5fb2e6b` (`Test refusal to migrate a newer database schema`)
**Reported baseline regression:** 216 passed

This audit is the mandatory first step of Module 5. It records what exists
today, what the frontend depends on, where the Windows and Linux environments
meet, which fields are unsafe to expose, and the smallest safe next feature.
It deliberately proposes an API but does not implement it.

---

## 1. Current architecture

There are two independent FastAPI applications and no shared API process:

```
Windows host / any dev host                         Ubuntu VM (VirtualBox)
┌──────────────────────────────────────┐           ┌──────────────────────────────┐
│ backend/app/main.py                  │           │ gateway/api.py               │
│  title "Experience Budget"           │           │  title "Experience Budget    │
│  version 0.7.0                       │           │  Gateway"                    │
│  CORS for localhost/127.0.0.1:5173/4 │           │  bound 0.0.0.0:8000 in docs  │
│  includes monitoring router          │           │  /health, /clients           │
│  inline GET / and GET /health        │           │  POST/DELETE limit routes    │
│                                      │           │  POST intent, GET/POST policy│
│ backend/app/api/monitoring.py        │           │  lifespan: sample + policy   │
│  /api/v1/monitoring/*                │           │  loops, clears limits on boot│
│                                      │           └──────────────────────────────┘
│ backend/app/services/*               │
│  monitoring_service.py  ─────────────┼──► Windows psutil / network probes
│  lab_accounting_service.py ──────────┼──► /sys/class/net/veth-cN-br
│  client_registry.py (runtime only)   │      (only exists inside the Linux VM)
│                                      │
│ network/telemetry/metrics_store.py   │
│  data/experience_budget.sqlite3      │
└──────────────────────────────────────┘
                  ▲
                  │ hardcoded http://127.0.0.1:8000
┌─────────────────┴────────────────────┐
│ frontend/src/App.jsx                 │
│ frontend/src/components/             │
│   NetworkTopology.jsx                │
└──────────────────────────────────────┘
```

Key conclusions:

1. **`backend/app/main.py` is the primary product-facing application.** It is
   the only application the React dashboard calls.
2. **`gateway/api.py` is a separate, privileged lab-control application.** It
   must not be mounted wholesale into the product API. It exposes traffic
   shaping through `sudo`, intent changes, and policy toggles.
3. **No dedicated Linux telemetry agent exists.** `gateway/api.py` is a
   control/observation prototype; `gateway/collector.py` is a terminal
   collector; `LabAccountingService` is a Python service that assumes it runs
   on the Linux host and reads `/sys/class/net`. When `backend/app/main.py`
   runs on Windows, those sysfs reads fail and the lab is reported unavailable.
4. **Both apps are documented to use port 8000.** `docs/REPRODUCE.md` says
   explicitly not to run both. The product API must remain the single public
   application; any Linux observation service must be internal and separately
   addressed.
5. **There is no authentication on either app.** The gateway is documented as
   bound to `0.0.0.0:8000`. That is acceptable only for a trusted host-only
   lab network and is not acceptable for a general observation endpoint.

### Windows collection path

`backend/app/api/monitoring.py` → `backend/app/services/monitoring_service.py` →
`network/telemetry/*` (psutil interface counters, ICMP probes) →
`MetricsStore.insert_sample()`.

- Host aggregate: adapter name is accepted by the request and returned in the
  response (`"interface": adapter`).
- Hotspot aggregate: hardcoded adapter `"Local Area Connection* 2"`; only the
  aggregate is stored, labelled `hotspot-aggregate`.
- `insert_sample()` writes the legacy `network_samples` row **and** a canonical
  aggregate `telemetry_observations` row in one transaction.

### Linux per-client collection path

`backend/app/api/monitoring.py::lab_clients()` →
`backend/app/services/lab_accounting_service.py::collect()` →
`gateway/accounting.py::PerClientAccountingCollector.collect()` →
`SysfsCounterReader` → `/sys/class/net/veth-cN-br/statistics/*`.

- `LabAccountingService` is instantiated at import time as
  `lab_accounting_service`.
- It builds a runtime `AnonymousClientRegistry`, registers `Client 01..NN`
  labels, and maps them to `veth-cN-br` gateway interfaces.
- `collect()` returns a raw dictionary, not a typed API model.
- Each HTTP GET to `/api/v1/monitoring/lab/clients` triggers a collection and
  mutates the collector's rate baselines. This is collection on request, not a
  managed background loop.
- The service checks whether any lab interface exists and returns
  `available: false` when none do. On Windows this is the normal outcome.

### VirtualBox connectivity (from existing docs, not re-verified here)

`docs/REPRODUCE.md` documents:

- Adapter 1: NAT, typically `10.0.2.x` (internet access).
- Adapter 2: Host-only, typically `192.168.56.x` (private host↔VM link).
- The author verified reaching `http://<VM host-only IP>:8000/docs` from the
  Windows browser.
- No fixed IP is configured in code. Any integration must use a configurable
  endpoint.
- The VM lab (`br-lab`, namespaces, `veth-cN-br`) is runtime state and is lost
  on reboot.

**Therefore the supported integration path is:** run a restricted read-only
observation service inside the Ubuntu VM, bind it to the host-only interface
(or loopback with an SSH tunnel), and let `backend/app/main.py` call it over
HTTP with a configurable base URL, timeout, and optional shared token. The
Windows backend must never attempt to read Linux sysfs directly.

---

## 2. Route inventory

### 2.1 Primary application — `backend/app/main.py`

| Method | Path | Current behavior | Typed response? | Frontend use |
| --- | --- | --- | --- | --- |
| GET | `/` | Static project/version/mode dictionary | No | No |
| GET | `/health` | Static `{"status": "healthy", "service": ...}` | No | No |
| POST | `/api/v1/monitoring/collect` | Windows host aggregate collection | No (raw dict) | Yes |
| POST | `/api/v1/monitoring/hotspot/collect` | Windows hotspot aggregate collection | No (raw dict) | Yes |
| GET | `/api/v1/monitoring/hotspot/history` | Legacy hotspot rows, `limit` 1–500 | No (raw dict) | Yes |
| GET | `/api/v1/monitoring/lab/clients` | Linux per-client collection (live) | No (raw dict) | Yes |
| GET | `/api/v1/monitoring/history` | Legacy Wi-Fi rows, `limit` 1–500 | No (raw dict) | Yes |

Notes:

- `limit=1000` on the legacy history routes returns **422** by design; the
  existing contract caps at 500.
- Legacy collection routes are POST because they perform measurement and
  persistence. They are not observation-only.
- All legacy errors use `HTTPException(detail=str(error))`. This can leak
  adapter names, paths, or OS diagnostics. It must be replaced or wrapped with
  safe codes in new routes; legacy behavior may need a compatibility decision.
- No OpenAPI tags/descriptions beyond the default; no response models, so
  OpenAPI shows untyped dictionaries.

### 2.2 Gateway application — `gateway/api.py`

| Method | Path | Classification | Risk |
| --- | --- | --- | --- |
| GET | `/health` | Read-only | Safe, but no database/collector detail |
| GET | `/clients` | Read-only observation + control state | Returns internal client numbers, `intent`, `limit`; not privacy-safe for product use |
| POST | `/clients/{n}/limit` | **Privileged control** | Runs `sudo -n /usr/local/sbin/eb-limit-client` |
| DELETE | `/clients/{n}/limit` | **Privileged control** | Runs the same sudo helper |
| POST | `/clients/{n}/intent` | **Policy control** | Changes policy input |
| GET | `/policy` | Control-state disclosure | Exposes limits/intents/budget |
| POST | `/policy` | **Policy control** | Enables/disables shaping; clears limits |

The `lifespan` also:

- clears all limits at startup (privileged side effect);
- starts `sample_loop()` and `policy_loop()`.

**Do not include this router in the product API.** A new read-only adapter is
required. The gateway app can remain available for the lab/control workflows.

### 2.3 Legacy and script consumers

- `gateway/watch.py` polls `http://localhost:8000/clients`.
- `experiments/run_call_vs_download.py` and
  `scripts/call_vs_download.sh` use `localhost:8000` for `/policy`.
- `docs/REPRODUCE.md` documents `uvicorn gateway.api:app --host 0.0.0.0
  --port 8000`.

These are lab/control consumers and must not drive the product API design.
They also confirm that removing `gateway/api.py` outright would break existing
workflows; the safe approach is to leave it alone and add a separate internal
observation surface.

### 2.4 Frontend usage

`frontend/src/App.jsx` hardcodes `API_BASE = "http://127.0.0.1:8000"` and:

- `GET /api/v1/monitoring/history?limit=50`
- `GET /api/v1/monitoring/hotspot/history?limit=50`
- `GET /api/v1/monitoring/lab/clients`
- `POST /api/v1/monitoring/collect`
- `POST /api/v1/monitoring/hotspot/collect`

It expects:

- history responses `{count, samples, scope}`;
- lab response `{available, clients:[{client_id, observation, rate_reason}]}`;
- legacy sample fields `id`, `recorded_at`, `download_mbps`, `upload_mbps`,
  `rtt_avg_ms`, `rtt_jitter_avg_ms`, `packet_loss_percent`,
  `internet_reachable`.

`NetworkTopology.jsx`:

- invents an "Internet Source / Upstream router" node with no measurement;
- uses the last upstream sample for the gateway node;
- renders lab clients from raw `observation` dictionaries;
- falls back to an aggregate hotspot node when no lab clients exist.

Consequence: the new API must either keep these legacy shapes or provide a
tested compatibility layer. The frontend is not being redesigned in Module 5.

---

## 3. Existing database capabilities (Module 4)

`network/telemetry/metrics_store.py` already provides everything the
observation routes need:

| Method | Purpose |
| --- | --- |
| `insert_sample(sample)` | Legacy + canonical aggregate write (Windows) |
| `save_observation(s)` | Validated canonical observation write |
| `get_observation(id)` | Single observation |
| `query_history(...)` | Bounded filtered history, deterministic ordering |
| `get_aggregate_history(...)` | Aggregate scopes only |
| `get_client_history(client_id, ...)` | Exactly one anonymous client |
| `get_history_by_source(...)` | One explicit source |
| `count_observations(...)` | Counts with the same filters |
| `register_client(...)` / `get_client(...)` / `list_clients(...)` | Anonymous client persistence |
| `get_simulated_client_by_slot(...)` | Lab slot lookup |
| `schema_version()` | Migration version |
| `get_recent_samples(...)` / `count_samples()` | Legacy rows |

Important constraints:

- `MAX_HISTORY_LIMIT = 1000`; the storage layer rejects larger limits.
- Ordering is `observed_at` then `id`, ascending or descending.
- `aggregate_only=True` excludes client rows; `client_id` forces client scope.
- Empty results are `[]`, not an error.
- Invalid filters raise `ValueError`; corrupt/newer databases raise
  `CorruptDatabaseError` / `MigrationError` / `StorageError`.
- `MetricsStore.__init__` creates parent directories and runs migrations. A
  health probe must not point at an arbitrary caller-supplied path.
- No real production SQLite file exists in this checkout.

**Rule for Module 5:** route handlers must call these repository methods; they
must not embed SQL. Any missing query capability is added to the storage layer
with tests first.

---

## 4. Privacy and security findings

### 4.1 Fields that could expose private infrastructure

| Location | Field / behavior | Why it is unsafe |
| --- | --- | --- |
| `POST /api/v1/monitoring/collect` response | `interface` / `adapter` | Private Windows adapter name |
| `POST .../collect` request | `adapter` free-form label | Could be used to probe local interfaces; already pattern-limited but still caller-controlled |
| Legacy error responses | `detail=str(error)` | Can contain OS messages, interface names, paths |
| `gateway/api.py` `/clients` | numeric client number, `intent`, `limit` | Internal lab mapping and control state |
| `gateway/api.py` helper | `sudo` invocation | Privileged command execution; must not be reachable from product routes |
| `gateway/api.py` startup | clears limits, starts loops | Side effects on import/startup; unsafe to mount |
| `LabAccountingService.collect()` | `rate_reason`, `collector_error` | Intended safe codes, but the raw dictionary bypasses response-model enforcement |
| `AnonymousClientRegistry.associate_address()` | transient address map | Never serialized today; must stay internal and never be persisted |
| Frontend topology | "Internet Source" node | Not measured; must be represented as unknown/not observed, not as a device |
| Frontend client titles | `Client ${index+1}` | Derived from array index, not the registry label; can disagree with `display_label` |

### 4.2 Security risks

1. **Privileged control routes are mixed with observation routes.** Mounting
   `gateway.api` would expose `sudo`-backed traffic shaping. Must not happen.
2. **No authentication** on either app. The new internal gateway adapter needs
   at least a shared token or host-only binding.
3. **Gateway bound to `0.0.0.0`** in documented commands. A read-only agent
   should bind to the host-only address (or loopback behind an SSH tunnel).
4. **Collection on GET.** `/api/v1/monitoring/lab/clients` mutates state on a
   GET; repeated dashboard calls change baselines and can race.
5. **Unbounded/duplicated collection.** The frontend can trigger host and
   hotspot collection every 15 s; there is no managed scheduler ownership or
   shutdown semantics.
6. **Raw exception leakage.** Legacy `detail=str(error)` may expose internal
   detail.
7. **CORS is explicit but broad in methods/headers.** Origins are correctly
   restricted to `localhost`/`127.0.0.1` ports 5173 and 5174. `allow_methods`
   and `allow_headers` are `"*"`, and `allow_credentials=True`. Keep explicit
   origins; consider narrowing methods/headers when the new API is added.
8. **No response models** on legacy routes, so privacy cannot be enforced at
   serialization time.
9. **Lab inventory is import-time global state.** `EB_LAB_CLIENTS` is read at
   import; invalid values fail application import. Configuration should be
   validated explicitly and reported safely.

### 4.3 Privacy rules the new API must enforce

- Never return IP, MAC, hostname, real device name, adapter/interface/namespace
  name, URL, payload, temporary mapping, credential, or raw exception.
- Client-facing IDs are opaque `client-...` tokens and `Client NN` labels.
- Missing measurements stay `null`/`unavailable`; never fabricated zero.
- Aggregate and per-client observations never mix in one list.
- Pydantic models use `extra="forbid"` where practical.
- Tests must inspect actual serialized HTTP JSON, not only Python objects.

---

## 5. Integration gaps

| Gap | Current state | Required outcome |
| --- | --- | --- |
| Single product API | `main.py` has only legacy monitoring + static health | Add versioned observation routes while preserving legacy |
| Typed contracts | Legacy routes return raw dicts | Typed request/response models with consistent envelopes |
| Health | Static `"healthy"` regardless of DB/collectors/gateway | Component health with `healthy`/`degraded`/`unavailable` |
| Collector status | None | Per-collector status, last success, safe error code |
| Linux gateway access | Backend assumes local sysfs | Read-only HTTP adapter with timeout, unavailable handling, optional token |
| Anonymous clients | Registry exists only inside lab service / gateway collector | Expose registry + persisted clients through `MetricsStore` |
| Current observations | Only live legacy calls | Typed current view for host/hotspot/client |
| History | Legacy Wi-Fi/hotspot rows only | Bounded filtered canonical history + per-client history |
| Topology | Frontend invents it | Server-side topology built only from real measurements/configured lab |
| Managed collection | Request-driven; no scheduler | Owned collection lifecycle or explicit request-only semantics |
| Safe errors | `detail=str(error)` | Stable error codes and safe messages |
| Config | `.env.example` empty | Safe non-secret configuration template |
| Docs | No Module 5 API doc | Architecture, routes, examples, startup, disconnection tests |

### What is blocked today

- **Real Ubuntu gateway integration is BLOCKED** in this checkout: the backend
  runs on the Windows/host side, no Linux observation agent exists yet, and no
  reachable VM endpoint/credentials are configured. Mocked adapter tests can be
  written now; real cross-environment tests must be reported as BLOCKED.
- **Production database migration remains unverified**: no real
  `data/experience_budget.sqlite3` exists here.

---

## 6. Proposed product-facing API

All new routes live under `/api/v1/` on `backend/app/main.py`. Legacy
`/api/v1/monitoring/*` routes remain unchanged until a compatibility layer and
frontend migration are explicitly tested.

| Group | Method | Path | Purpose |
| --- | --- | --- | --- |
| 5A | GET | `/api/v1/health` | Overall app/database/collectors/gateway/registry health |
| 5A | GET | `/api/v1/health/collectors` | Per-collector status, last success, safe error code |
| 5B | GET | `/api/v1/gateway/status` | Read-only Linux gateway availability |
| 5B | GET | `/api/v1/network/topology` | Nodes/edges from actual observations/config only |
| 5C | GET | `/api/v1/clients` | Anonymous client listing |
| 5C | GET | `/api/v1/clients/{client_id}` | One anonymous client + latest summary |
| 5D | GET | `/api/v1/observations/current` | Current observations with validated filters |
| 5E | GET | `/api/v1/observations/history` | Bounded aggregate/history query |
| 5E | GET | `/api/v1/clients/{client_id}/history` | Bounded history for exactly one client |

### Proposed response envelopes

Use one envelope per group, with UTC timestamps and `extra="forbid"`:

```json
// GET /api/v1/health
{
  "status": "degraded",
  "observed_at": "2026-11-09T12:00:00Z",
  "components": {
    "application": {"status": "healthy"},
    "database": {"status": "healthy", "schema_version": 1},
    "windows_collector": {"status": "unavailable", "error_code": "not_configured"},
    "gateway": {"status": "unavailable", "error_code": "gateway_unreachable"},
    "client_registry": {"status": "healthy", "client_count": 3}
  }
}
```

```json
// GET /api/v1/observations/current
{
  "observed_at": "2026-11-09T12:00:00Z",
  "count": 2,
  "observations": [
    {
      "id": 42,
      "metadata": {
        "observed_at": "2026-11-09T11:59:58Z",
        "source": "windows_host",
        "scope": "aggregate_gateway",
        "quality": "measured",
        "environment": "physical_host",
        "stale": false,
        "collector_error": null,
        "client_id": null
      },
      "download_mbps": 12.5,
      "upload_mbps": 1.2,
      "rtt_ms": 18.0,
      "packet_loss_percent": 0.0,
      "rtt_variation_ms": 2.1,
      "download_bytes": null,
      "upload_bytes": null,
      "download_packets": null,
      "upload_packets": null,
      "queue_depth_bytes": null,
      "queue_delay_ms": null
    }
  ],
  "filters": {"source": null, "scope": null, "environment": null, "client_id": null}
}
```

```json
// GET /api/v1/observations/history
{
  "count": 50,
  "limit": 50,
  "offset": 0,
  "order": "newest",
  "observations": [],
  "has_more": false
}
```

Rules:

- `limit` 1–500 for API routes (stricter than the storage maximum of 1000).
- `offset` ≥ 0.
- `start`/`end` are timezone-aware ISO 8601; `start <= end`.
- `order` is `newest` or `oldest`.
- Unknown source/scope/environment/client ID → `422` for malformed values,
  `404` for a well-formed but unknown client.
- Database failure → `503` with a safe code, never a stack trace.
- Gateway failure → `200` with `status: "unavailable"` for status/topology
  reads where possible; collection failures use `503`/`504` with safe codes.
- No route accepts filesystem paths, adapter names, shell arguments, limits,
  intents, or policy toggles.
- No aggregate/per-client mixing: `aggregate_only` is enforced server-side.

### Source and scope vocabulary

Reuse Module 1 exactly:

- sources: `windows_host`, `windows_hotspot`, `linux_gateway`,
  `linux_namespace_lab`, `unknown`;
- scopes: `aggregate_gateway`, `aggregate_hotspot`, `client`;
- quality: `measured`, `derived`, `unavailable`, `unknown`;
- environments: `physical_host`, `simulated_lab`.

### Proposed internal gateway adapter

Add a small read-only client (for example
`backend/app/services/gateway_observation_client.py`) that:

- takes a configurable base URL, timeout, and optional token from environment;
- calls only a read-only endpoint such as `/observations`;
- validates the response into typed models;
- rejects any identity-like field or malformed payload;
- maps timeout/refused/malformed/auth failures to safe codes
  (`gateway_timeout`, `gateway_unreachable`, `gateway_invalid_response`,
  `gateway_auth_failed`);
- never retries indefinitely;
- never exposes the endpoint or token in API responses.

On the Ubuntu side, add a separate read-only observation service (or a
read-only router in a new internal app) that reuses `PerClientAccountingCollector`
and the anonymous registry. It must not import `gateway.api`, `controller`,
`policy`, or any sudo helper. It should bind to the host-only address, not
`0.0.0.0`, and should require a token for non-loopback access.

---

## 7. Testing strategy

New tests will be added before or with each feature:

| Area | Test file (proposed) | Coverage |
| --- | --- | --- |
| Response models/envelopes | `tests/unit/test_api_models.py` | extra fields rejected, UTC, null vs zero, enum values |
| Health | `tests/unit/test_api_health.py` | healthy/degraded/unavailable DB, collectors, gateway, mixed states |
| Gateway adapter | `tests/unit/test_gateway_observation_client.py` | valid, timeout, refused, malformed, missing fields, identity fields, auth failure |
| Gateway status/topology | `tests/unit/test_api_gateway_topology.py` | available/unavailable, no invented nodes, source/environment labels |
| Clients | `tests/unit/test_api_clients.py` | list/detail/unknown/malformed/offline/reconnected, privacy fields |
| Current observations | `tests/unit/test_api_current_observations.py` | host/hotspot/client filters, missing/stale, one collector failing |
| History | `tests/unit/test_api_history.py` | aggregate/client 01/02, filters, range, pagination, order, empty, invalid, max limit, no mixing |
| Security/privacy | `tests/unit/test_api_security.py` | no control routes, no shell, CORS, no traceback, no IP/MAC/device names, bounds |
| Legacy regression | existing `test_monitoring_api.py`, `test_hotspot_api.py` | unchanged legacy contracts |
| Real VM integration | `tests/integration/` or script | **BLOCKED** until VM endpoint exists; report as blocked, not passed |

Mocked transport tests are not evidence of real network integration and must
not be reported as such.

---

## 8. Smallest atomic implementation task

**Task M5-1 — Versioned observation router skeleton and typed health.**

Scope:

1. Create `backend/app/api/v1/__init__.py` and
   `backend/app/api/v1/health.py` (or an equivalent small module).
2. Define typed, privacy-safe response models for health and collector status.
3. Add `GET /api/v1/health` reporting:
   - application: healthy;
   - database: healthy/unavailable via `MetricsStore.schema_version()` on the
     configured path, with a safe error code;
   - collectors/gateway/registry: explicit `unknown`/`unavailable` until wired
     in later atomic tasks (never fabricated healthy).
4. Add `GET /api/v1/health/collectors` returning the same component data in a
   list envelope.
5. Keep `/`, `/health`, and all `/api/v1/monitoring/*` routes unchanged.
6. Add tests for healthy database, missing/unavailable database, and mixed
   states; verify no paths/exceptions leak.
7. Run targeted tests, the monitoring API regression tests, the full suite,
   and `git diff --check`.
8. Commit separately.

Why this is first: it establishes the versioned router, envelope conventions,
safe-error pattern, and database probe that every later observation route will
reuse, without touching the legacy contracts or the unavailable gateway.

Subsequent atomic tasks follow the required order:

1. M5-2 — gateway read-only adapter with mocked transport tests.
2. M5-3 — gateway status and topology routes.
3. M5-4 — anonymous client list/detail routes.
4. M5-5 — current observation routes.
5. M5-6 — historical observation routes.
6. M5-7 — security/privacy hardening and CORS review.
7. M5-8 — real cross-environment integration (BLOCKED until available).
8. M5-9 — `docs/MODULE5_API.md`, `.env.example`, OpenAPI metadata.
9. M5-10 — final regression and status update.

---

## 9. Audit checklist result

- [x] Primary FastAPI application identified.
- [x] Existing frontend routes identified.
- [x] Read-only gateway routes identified.
- [x] Privileged gateway routes identified and excluded from the product API.
- [x] Windows data-entry path identified.
- [x] Linux per-client retrieval path identified.
- [x] VM connectivity mechanism identified from existing documentation.
- [x] Separate-process status of the Ubuntu agent determined (none exists).
- [x] Database query methods inventoried.
- [x] Private response fields identified.
- [x] Integration gaps and blocked items recorded.
- [x] Proposed API structure and test strategy recorded.
- [x] Smallest atomic next task defined.
- [x] No application code modified.
