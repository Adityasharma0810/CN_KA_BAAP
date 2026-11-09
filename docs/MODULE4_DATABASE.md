# Module 4 — Database and Historical Telemetry

**Status:** COMPLETE for the storage layer  
**Date:** 2026-11-09  
**Branch:** `main`

This document describes the privacy-safe SQLite persistence layer added in
Module 4. It does not describe the unified observation API or dashboard history
integration; those remain later-module work.

## Scope and status

Implemented:

- versioned, transactional, non-destructive SQLite migrations;
- canonical aggregate and per-client observation storage;
- anonymous client persistence without identity or address data;
- bounded history queries with explicit scope/source/environment/time filters;
- privacy and data-quality validation;
- migration, storage, integration, privacy, concurrency, and bounded-query
  tests on temporary databases.

Preserved without modification:

- the legacy `network_samples` table and its index;
- all existing legacy columns, timestamps, and metric values.

Not implemented in this module:

- unified observation API routes;
- dashboard history integration;
- gateway health API;
- controlled deletion API;
- retention policy;
- physical-device enrollment or identity continuity.

## Database architecture

There is one SQLite manager, `MetricsStore` in
`network/telemetry/metrics_store.py`. It owns:

- legacy-compatible aggregate writes;
- schema versioning and migrations;
- anonymous client records;
- canonical observation records;
- bounded historical queries.

Each operation opens a short-lived connection, enables foreign keys and a
5-second busy timeout, and closes the connection when done. No global shared
connection is used, so concurrent reads and short writes serialize through
SQLite rather than through shared Python state.

The database path defaults to `data/experience_budget.sqlite3` for the existing
monitoring service. Automated tests always use `tmp_path`; no test writes to the
real project database.

## Tables and relationships

### `network_samples` — legacy, retained unchanged

```sql
CREATE TABLE network_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    interface_label TEXT NOT NULL,
    download_mbps REAL,
    upload_mbps REAL,
    adapter_up INTEGER,
    internet_reachable INTEGER,
    probe_target TEXT,
    probes_sent INTEGER,
    probes_received INTEGER,
    packet_loss_percent REAL,
    rtt_min_ms REAL,
    rtt_avg_ms REAL,
    rtt_max_ms REAL,
    rtt_jitter_avg_ms REAL
);

CREATE INDEX idx_network_samples_recorded_at
    ON network_samples(recorded_at);
```

This table remains the compatibility record. It is never dropped or rewritten by
migration.

### `anonymous_clients`

```sql
CREATE TABLE anonymous_clients (
    client_id TEXT PRIMARY KEY,
    display_label TEXT NOT NULL UNIQUE,
    environment TEXT NOT NULL,
    simulated_lab_slot INTEGER,
    first_seen_at TEXT,
    last_seen_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (environment, simulated_lab_slot)
);
```

Rules:

- `client_id` is an opaque `client-...` token, never an address or device name.
- `display_label` is `Client NN`.
- `simulated_lab_slot` is permitted only for `environment = 'simulated_lab'`.
- There are no IP, MAC, hostname, device-name, adapter, URL, payload, or
  credential columns.
- The simulated-lab slot is explicitly lab configuration, not physical-device
  identity. It is persisted so lab history can be grouped consistently across
  sessions.
- Physical clients must not be inferred from addresses, MACs, hostnames, or
  network behavior.

### `telemetry_observations`

```sql
CREATE TABLE telemetry_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_at TEXT NOT NULL,
    source TEXT NOT NULL,
    scope TEXT NOT NULL,
    environment TEXT NOT NULL,
    quality TEXT NOT NULL,
    stale INTEGER NOT NULL DEFAULT 0,
    collector_error TEXT,
    client_id TEXT REFERENCES anonymous_clients(client_id)
        ON DELETE RESTRICT,
    download_bytes INTEGER,
    upload_bytes INTEGER,
    download_packets INTEGER,
    upload_packets INTEGER,
    download_mbps REAL,
    upload_mbps REAL,
    rtt_ms REAL,
    packet_loss_percent REAL,
    rtt_variation_ms REAL,
    queue_depth_bytes INTEGER,
    queue_delay_ms REAL,
    legacy_sample_id INTEGER UNIQUE,
    legacy_recorded_at TEXT
);
```

Constraints enforce:

- valid enum values for `source`, `scope`, `environment`, and `quality`;
- `stale` is `0` or `1`;
- non-negative counters, rates, RTT, variation, queue depth, and queue delay;
- packet loss between `0` and `100`;
- `collector_error` is short and controlled;
- client-scoped rows require `client_id`;
- aggregate rows require `client_id IS NULL`;
- `legacy_sample_id` is unique, so migration cannot duplicate a legacy row;
- `legacy_recorded_at` preserves the exact original timestamp text.

There is no catch-all JSON or BLOB column.

### Indexes

Indexes follow the actual query patterns:

```sql
CREATE INDEX idx_telemetry_observations_observed_at
    ON telemetry_observations(observed_at, id);

CREATE INDEX idx_telemetry_observations_scope_observed_at
    ON telemetry_observations(scope, observed_at, id);

CREATE INDEX idx_telemetry_observations_client_observed_at
    ON telemetry_observations(client_id, observed_at, id);

CREATE INDEX idx_telemetry_observations_source_observed_at
    ON telemetry_observations(source, observed_at, id);

CREATE INDEX idx_telemetry_observations_environment_observed_at
    ON telemetry_observations(environment, observed_at, id);
```

## Schema versions and migration history

`PRAGMA user_version` is the single migration-version mechanism.

| Version | Change |
| --- | --- |
| `0` | Legacy schema: `network_samples` only. |
| `1` | Adds `anonymous_clients`, `telemetry_observations`, indexes, and copies compatible legacy rows. |

Migration behavior:

1. `MetricsStore.initialize()` creates the legacy table and index if missing.
2. `apply_migrations()` reads `PRAGMA user_version`.
3. If the database is newer than the application, it raises `MigrationError`
   instead of modifying it.
4. Pending migrations run inside `BEGIN IMMEDIATE`.
5. On any failure, the transaction rolls back and `user_version` does not
   advance.
6. On success, `user_version` is set to `SCHEMA_VERSION`.

Migration is repeatable: `legacy_sample_id` plus a `NOT EXISTS` guard prevents
duplicate canonical rows when the migration is replayed. The legacy table and
its index remain available.

Corrupt databases are detected with `CorruptDatabaseError` and are never
overwritten or recreated.

## Legacy data mapping

| Legacy field | Canonical field | Rule |
| --- | --- | --- |
| `id` | `legacy_sample_id` | Preserved, unique. |
| `recorded_at` | `observed_at` | Parsed and normalized to UTC. |
| `recorded_at` | `legacy_recorded_at` | Exact original text preserved. |
| `interface_label = hotspot-aggregate` | `source = windows_hotspot`, `scope = aggregate_hotspot` | Explicit legacy label. |
| `interface_label = Wi-Fi` | `source = windows_host`, `scope = aggregate_gateway` | Current Windows host default. |
| Other `interface_label` | `source = unknown`, `scope = aggregate_gateway` | Provenance uncertainty preserved, not invented. |
| `download_mbps`, `upload_mbps` | Same | Values unchanged. |
| `rtt_avg_ms` | `rtt_ms` | Value unchanged. |
| `rtt_jitter_avg_ms` | `rtt_variation_ms` | Value unchanged. |
| `packet_loss_percent` | Same | Value unchanged. |
| `adapter_up`, `internet_reachable`, `probe_target`, `probes_sent`, `probes_received`, `rtt_min_ms`, `rtt_max_ms` | Remain in `network_samples` | No compatible shared field; not lost. |
| Missing values | `NULL` | Never converted to zero. |
| Migrated quality | `unknown` | Legacy quality cannot be established. |
| Migrated client | `NULL`, aggregate scope | Aggregate rows are never converted into client rows. |
| Malformed legacy timestamp | Left in `network_samples` | Not migrated; no invented instant. |

New Windows aggregate writes through `insert_sample()` now write both the legacy
row and a canonical aggregate observation in one transaction. The canonical row
is linked by `legacy_sample_id`, so replaying the legacy migration does not
duplicate it.

## Observation sources and scopes

Sources use the shared Module 1 vocabulary:

- `windows_host`;
- `windows_hotspot`;
- `linux_gateway`;
- `linux_namespace_lab`;
- `unknown` for legacy rows whose provenance cannot be established.

Scopes:

- `aggregate_gateway` — aggregate host/gateway measurement;
- `aggregate_hotspot` — aggregate Windows Mobile Hotspot measurement;
- `client` — one anonymous client.

Aggregate and per-client records are separate at the schema, write, and query
layers. A client query filters on `scope = 'client'` and `client_id = ?`. An
aggregate query filters on aggregate scopes and never returns client rows.

## Anonymous client storage

`register_client()` validates an opaque client ID, display label, environment,
and optional simulated-lab slot. Registration is idempotent for an identical
record and rejects conflicting labels, IDs, or slots. `get_client()`,
`list_clients()`, and `get_simulated_client_by_slot()` return
`StoredAnonymousClient` objects with only privacy-safe fields.

Client-scoped observations must reference a registered client. Saving an
observation updates that client's `first_seen_at` and `last_seen_at` in the same
transaction.

## Timestamp format

- New observations are stored as timezone-aware ISO 8601 text normalized to UTC.
- Naive timestamps are rejected by the shared schema.
- Legacy timestamps are parsed to UTC for `observed_at`, while the exact
  original text is retained in `legacy_recorded_at`.
- Malformed legacy timestamps are not migrated.
- History range filters compare normalized ISO 8601 UTC strings.

## Data quality semantics

- `None` means the metric was unavailable; it is never stored as zero.
- A valid idle client may store an actual `0.0` rate.
- A first counter sample without a baseline stores unavailable rates with
  `collector_error = rate_unavailable:no_baseline`.
- A counter reset stores unavailable rates with
  `collector_error = rate_unavailable:counter_reset`; negative values are
  rejected by both validation and database constraints.
- Invalid elapsed intervals store `rate_unavailable:invalid_elapsed`.
- Missing interfaces store `interface_unavailable`.
- `quality` preserves `measured`, `derived`, `unavailable`, or `unknown`.
- `stale` preserves staleness.
- `collector_error` accepts only short controlled codes. Addresses, MACs,
  hostnames, paths, credentials, interface names, and free-text diagnostics are
  rejected. Pydantic validation errors hide rejected inputs.
- A failed save rolls back the transaction and does not corrupt earlier rows.

## Privacy protections

The persistence layer rejects or prevents:

- IP addresses;
- MAC addresses;
- real device names and hostnames;
- browsing URLs or histories;
- packet payloads or application contents;
- temporary address-to-anonymous-ID mappings;
- credentials or secrets;
- infrastructure identifiers in persisted error metadata.

Privacy tests inspect actual database rows, the schema, serialized observation
objects, public client records, and error behavior. The runtime registry's
transient address associations are never persisted.

## Query examples

```python
store = MetricsStore("data/experience_budget.sqlite3")

# Aggregate host and hotspot history, newest first, bounded.
aggregate = store.get_aggregate_history(limit=100)

# One anonymous client only.
client = store.get_client_history("client-0123456789abcdef", limit=100)

# One source and environment.
hotspot = store.get_history_by_source(
    "windows_hotspot",
    environment="physical_host",
    limit=50,
)

# Inclusive time range with deterministic oldest-first ordering.
window = store.query_history(
    start="2026-11-09T12:00:00+00:00",
    end="2026-11-09T13:00:00+00:00",
    order="oldest",
    limit=100,
    offset=0,
)

# Counts using the same filters.
count = store.count_observations(aggregate_only=True)
```

Query rules:

- `limit` must be between `1` and `MAX_HISTORY_LIMIT` (`1000`).
- `offset` must be a non-negative integer.
- `start` must not follow `end`.
- Ordering is deterministic: `observed_at` then `id`.
- Invalid scope, source, environment, client ID, or timestamp values are
  rejected.
- `aggregate_only` cannot be combined with client scope or a client ID.
- Empty result sets return an empty list.

## Backup and recovery

Recommended operational procedure before migrating a real database:

1. Stop the application writing to the database.
2. Copy the SQLite file (and any `-wal`/`-shm` files) to a timestamped backup.
3. Verify the backup opens read-only and reports the expected row counts.
4. Run the application's migration path on the copy first.
5. Only then migrate the production file.

Migration is transactional and non-destructive. If it fails, the legacy table
and rows remain, `user_version` does not advance, and the application raises a
safe `MigrationError`. A corrupt file is detected and left untouched.

No real project database file exists in this checkout, so no production-file
migration was performed or claimed. Migration was tested against representative
temporary legacy databases.

## Retention behavior

No retention or automatic deletion policy is enabled. History is preserved by
default. There is no background job that removes old observations and no
implicit size cap. A future retention policy must be explicit, opt-in,
configurable, tested, and documented before it is enabled.

## Testing summary

Module 4 tests use temporary databases only:

- `tests/unit/test_database_migrations.py` — versions, idempotence, rollback,
  corruption, legacy preservation.
- `tests/unit/test_client_persistence.py` — client registration, conflicts,
  simulated-lab slots, schema privacy.
- `tests/unit/test_observation_persistence.py` — canonical writes, null versus
  zero, quality, stale, safe errors, atomic batches.
- `tests/unit/test_history_queries.py` — scope/client/source/environment/time
  filters, pagination, sorting, invalid ranges, separation.
- `tests/unit/test_storage_privacy.py` — rows, schema, serialization, error
  leakage, address-mapping exclusion.
- `tests/unit/test_storage_integration.py` — Windows host/hotspot writes,
  legacy linkage, rollback, Linux collector-to-storage, no-baseline, reset,
  simulated-client grouping.
- `tests/unit/test_storage_reliability.py` — concurrent writers, concurrent
  reads/writes, short lock waiting, large bounded queries.

Full regression at the time of this document: `215 passed`.

## Known limitations

- No real `data/experience_budget.sqlite3` exists in this checkout. The legacy
  schema is defined by code and representative temporary databases; migration
  of an actual production file remains unverified.
- Windows counter-reset handling in the legacy collector still raises instead of
  storing an unavailable aggregate sample. Gateway per-client accounting does
  handle resets safely.
- There is no controlled deletion API and no retention policy.
- The unified observation API and dashboard history integration are later-module
  work.
- Physical-device continuity is not inferred or persisted.
- WAL mode is not enabled; concurrent access relies on short-lived connections
  and SQLite's busy timeout.
