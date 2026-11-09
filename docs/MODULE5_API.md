# Module 5 Product API

## Feature 4 — Historical observations

Historical endpoints query canonical `MetricsStore` observations only. They never start a collector, rewrite timestamps, or infer physical hotspot clients.

- `GET /api/v1/observations/history` returns bounded historical aggregate observations by default. Use `scope=client` or `client_id` to request client observations; aggregate and client rows are never mixed.
- `GET /api/v1/clients/{client_id}/history` returns only the requested registered anonymous client's observations. Unknown valid IDs return `404 unknown_client`; malformed IDs return `422`.

Both endpoints support `source`, `scope` where applicable, `environment`, inclusive timezone-aware `start` and `end`, `order=oldest|newest`, `limit` from 1 through 1000, and non-negative `offset`. Results are deterministically ordered by observation timestamp and storage ID. Responses report `total_count`, returned `count`, `has_more`, pagination values, echoed filters, and strict `ObservationItem` records.

Invalid timestamps, reversed ranges, incompatible client/aggregate filters, invalid enum values, and out-of-range pagination are rejected with safe `422` responses. Missing databases return an empty history without creating storage; corrupt or unavailable databases return `503 database_unavailable`. Stored values, quality, provenance, stale flags, and original UTC timestamps are preserved. No raw SQL, exception text, paths, addresses, or infrastructure identifiers cross the API boundary.

## Feature 3 — Current observations

`GET /api/v1/observations/current` returns the newest canonical observation for each requested source, without changing the stored observation timestamp.

### Filters

Optional query parameters are validated against the shared observation schema:

- `source`: `windows_host`, `windows_hotspot`, `linux_gateway`, `linux_namespace_lab`, or `unknown`.
- `scope`: `aggregate_gateway`, `aggregate_hotspot`, or `client`.
- `environment`: `physical_host` or `simulated_lab`.
- `client_id`: an opaque `client-...` ID registered in the canonical client store.

`client_id` is restricted to client-scoped observations. `linux_namespace_lab` is client-scoped by definition in this implementation; omitting `scope` for that source returns the newest observation for each registered simulated client. Aggregate sources never return client rows.

A well-formed but unknown client ID returns `404 unknown_client`; malformed enum or client values return `422 invalid_filter` or FastAPI validation errors. A valid filter with no data returns `200` with `count: 0` and an empty `observations` list.

### Response and semantics

The response is a strict `CurrentObservationsResponse` envelope. Each item contains a storage ID and a validated `TelemetryObservation` with:

- original UTC `observed_at`;
- source, scope, environment, quality and optional anonymous client ID;
- stale flag and safe collector error code;
- counters, rates, RTT, packet loss, variation and queue values when present.

Missing values remain `null`. A measured zero remains `0`; it is not converted to missing. No request-time timestamp is substituted for the observation timestamp.

### Freshness

The default freshness threshold is `STALE_OBSERVATION_AFTER_SECONDS = 300` seconds. Current observations are stale when their age is strictly greater than five minutes. At exactly five minutes they remain fresh. Staleness is computed in memory and does not modify the database.

### Sources and availability

- `windows_host`: aggregate host telemetry persisted by the Windows monitoring service.
- `windows_hotspot`: aggregate Mobile Hotspot telemetry only; it cannot identify physical hotspot devices.
- `linux_gateway`: aggregate Linux gateway data only when a genuine canonical observation exists.
- `linux_namespace_lab`: simulated per-client observations with opaque IDs, only when the lab collector has produced them.

The current endpoint queries canonical storage. It does not start a new Windows probe, read Linux sysfs from Windows, or invent a remote Ubuntu connection. Missing or unavailable collectors therefore produce an empty result for that source rather than fabricated measurements. Remote gateway transport is a later feature.

### Privacy boundary

The response models use `extra="forbid"` and shared schema validation. Responses contain no IP addresses, MAC addresses, hostnames, device names, URLs, payloads, credentials, temporary address associations, namespace names or private interface names. Aggregate hotspot counters are never assigned to individual clients.

Storage/query failures are converted to a safe `503 database_unavailable` response. Raw exceptions and filesystem details are not returned.

## Feature 5 — Gateway status and network topology

Feature 5 adds two read-only, typed endpoints:

- `GET /api/v1/gateway/status` reports the application health-service component, Windows host, Windows hotspot, and Linux lab separately. Each has a strict state, `last_observed_at`, and `data_quality`; the overall `status` is `healthy` only when all four are online, `unavailable` if any is unavailable, and `degraded` otherwise.
- `GET /api/v1/network/topology` returns the application, Windows host aggregate, hotspot aggregate, and Linux lab nodes plus only anonymous lab-client membership supported by the registry and canonical client observations. The hotspot and Linux lab are independent and may coexist.

Both endpoints use stored observation data and the shared anonymous registry; they do not call collectors or probe the network. The shared `STALE_OBSERVATION_AFTER_SECONDS` threshold is 300 seconds, with exactly 300 seconds fresh. `online` means recently measured with `measured` or `derived` quality; it does not assert connectivity. A lab client is online only with both a fresh measured/derived client observation and an `online` registry status. Application state comes from the `application` component in `build_observation_health()`.

Topology links use the strict `observed`, `derived`, `configured`, or `unknown` enum. Current data supports only lab-to-anonymous-client measurement or registry-membership edges. It does not support router nodes, physical links, or per-client attribution for Windows aggregates. Edge validation rejects duplicate nodes/edges, dangling endpoints, and self-loops; failures return a generic `503 topology_unavailable`.

Response schemas forbid extra fields and exclude addresses, hostnames, namespaces, private interface names, paths, and raw errors. See [MODULE5_TOPOLOGY.md](./MODULE5_TOPOLOGY.md) for field examples, full state and edge rules, privacy guarantees, and evidence limitations.
