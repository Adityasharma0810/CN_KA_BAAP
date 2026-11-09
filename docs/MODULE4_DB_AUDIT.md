# Module 4 database audit

Audit date: 2026-11-09  
Repository: `CN_KA_BAAP`  
Branch: `main`  
Git state at audit start: clean, two commits ahead of `origin/main`
(`2867cbc`, `128f724`).

## Scope

This audit covers the existing SQLite persistence path before Module 4 changes.
It does not migrate, modify, delete, or recreate any real database. Automated
inspection used a temporary database created in the system temporary directory.

## Actual files found

- The documented runtime database path is `data/experience_budget.sqlite3`.
- No `*.sqlite3`, `*.sqlite`, or `*.db` file exists anywhere in the checkout.
- `data/` currently contains only `data/capacity_forecasting/`.
- `.gitignore` excludes `*.db`, `data/*.sqlite3`, and `data/*.db`.
- All existing automated tests use `tmp_path` databases.
- Because no real database file is present in this checkout, the migration
  tests must use a representative temporary legacy database. No claim can be
  made that a database file from another machine was migrated.

## Existing code-defined schema

`network/telemetry/metrics_store.py` creates the only table used by the
monitoring service:

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

A temporary database created through the current `MetricsStore` reports:

- `PRAGMA user_version = 0` (no schema version mechanism).
- One table: `network_samples`.
- One application index: `idx_network_samples_recorded_at`.
- No migration ledger.
- No client table.
- No canonical observation table.
- Zero rows in a newly created database.

## Existing data sources

| Source | Current label | Persisted today | Notes |
| --- | --- | --- | --- |
| Windows host aggregate | arbitrary adapter name, default `Wi-Fi` | yes, `network_samples` | rates derived from adapter counters |
| Windows Mobile Hotspot aggregate | `hotspot-aggregate` | yes, `network_samples` | downstream client perspective, aggregate only |
| Linux namespace lab per client | not persisted | no | `gateway/accounting.py` produces shared `TelemetryObservation` objects, but no storage call exists |
| Future physical gateway | not persisted | no | no supported enrollment or identity mechanism yet |

`backend/app/services/client_registry.py` is intentionally runtime-only. It
stores anonymous IDs, display labels, and transient address associations in
memory. Address associations are never serialized. The registry resets on
process restart and cannot establish that a new anonymous ID is the same
physical device.

## Existing query behavior

`MetricsStore` supports only:

- `get_samples_by_interface(interface_label, limit)`: exact legacy label match,
  newest first.
- `get_recent_samples(limit)`: all legacy rows, newest first.
- `count_samples()`: total legacy rows.

The public service path additionally hardcodes:

- `get_history()` queries only `interface_label = "Wi-Fi"`.
- `get_hotspot_history()` queries only `interface_label = "hotspot-aggregate"`.

Missing query capabilities:

- no filter by observation source;
- no filter by observation scope;
- no filter by environment;
- no filter by anonymous client ID;
- no time range;
- no offset/pagination;
- no explicit maximum query limit;
- no deterministic tie-breaker beyond `id` ordering;
- no aggregate-only or client-only guarantee at the storage layer.

## Missing aggregate/per-client separation

The legacy table has no `source`, `scope`, `environment`, or `client_id`
columns. It cannot represent a per-client observation at all. A future naive
extension that put client rows into `network_samples` would risk:

- returning aggregate Wi-Fi rows for a Client 01 query;
- combining hotspot aggregate rows with individual client rows;
- treating an interface label as a client identity;
- losing the distinction between measured and derived values;
- inventing provenance for old rows.

The target storage layer must make scope and source explicit and must reject
client IDs on aggregate observations.

## Timestamp format

Current writers use `datetime.now(timezone.utc).isoformat()`, which produces an
offset-aware ISO 8601 string such as `2026-11-09T12:00:00.123456+00:00`.
The legacy reader does not parse or validate the timestamp, so older rows could
contain naive or malformed text. Migration must preserve the original text and
must not silently fabricate a different instant. Representative migration tests
will cover aware and naive ISO timestamps; malformed legacy timestamps remain
in the untouched legacy table rather than being converted into invented data.

## Existing data preservation

No real database file is present in this checkout, so there are no observed
row counts to preserve here. The migration design nevertheless assumes the
legacy table may contain rows and must:

- keep `network_samples` and its index;
- keep every legacy column value;
- link migrated rows back to their legacy ID;
- avoid duplicate migration on repeated runs;
- leave malformed/unrepresentable legacy rows in the legacy table.

## Privacy risks

Current and proposed risks:

1. `network_samples.interface_label` can contain a real adapter name because
   `monitoring_service.collect_and_store()` accepts an arbitrary adapter label.
   This is infrastructure metadata, not a client identity, but it must not be
   copied into a client-facing canonical record.
2. `network_samples.probe_target` stores approved public probe addresses such
   as `1.1.1.1` and `8.8.8.8`. These are not household device addresses, but
   the new canonical table should not add a general IP-address column.
3. `collector_error` is currently free text. A future storage layer must not
   persist raw exception text, interface names, addresses, hostnames, paths, or
   credentials.
4. The runtime registry's transient address mappings must never be persisted.
5. A simulated lab slot must not be described as physical-device continuity.
6. A permissive JSON blob would allow arbitrary identity fields and is
   prohibited.

## Proposed target schema

The smallest safe architecture is one SQLite manager, `MetricsStore`, with:

### `network_samples` (legacy, retained)

Unchanged. Continues to hold legacy-compatible rows and keeps all existing
columns, timestamps, and values.

### `anonymous_clients`

```sql
client_id TEXT PRIMARY KEY,
display_label TEXT NOT NULL UNIQUE,
environment TEXT NOT NULL,
simulated_lab_slot INTEGER,
first_seen_at TEXT,
last_seen_at TEXT,
created_at TEXT NOT NULL,
UNIQUE (environment, simulated_lab_slot)
```

Rules:

- `client_id` is an opaque `client-...` token, never an address or device name.
- `display_label` is `Client NN`.
- `simulated_lab_slot` is allowed only for `environment = 'simulated_lab'`.
- No IP, MAC, hostname, adapter, URL, payload, or credential columns exist.

### `telemetry_observations`

```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
observed_at TEXT NOT NULL,
source TEXT NOT NULL,
scope TEXT NOT NULL,
environment TEXT NOT NULL,
quality TEXT NOT NULL,
stale INTEGER NOT NULL,
collector_error TEXT,
client_id TEXT REFERENCES anonymous_clients(client_id),
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
```

Rules:

- New rows use the shared `TelemetryObservation` model and its enum values.
- `NULL` means unavailable; it is never converted to zero.
- Client scope requires a registered anonymous client ID.
- Aggregate scope requires `client_id IS NULL`.
- No catch-all JSON column exists.
- `legacy_sample_id` makes migration repeatable and preserves the original
  legacy identifier.
- `legacy_recorded_at` preserves the exact original timestamp text.

Indexes will follow actual query patterns:

- `observed_at`
- `scope, observed_at`
- `client_id, observed_at`
- `source, observed_at`
- `environment, observed_at`

### Schema version

Use SQLite `PRAGMA user_version` as the single migration-version mechanism.
Version `0` is the legacy schema. Version `1` adds the canonical tables,
indexes, and legacy-row migration. The legacy table remains available.

## Legacy mapping

| Legacy field | Canonical field | Rule |
| --- | --- | --- |
| `id` | `legacy_sample_id` | preserved, unique |
| `recorded_at` | `observed_at`, `legacy_recorded_at` | parse to UTC; preserve exact original text |
| `interface_label = hotspot-aggregate` | `source = windows_hotspot`, `scope = aggregate_hotspot` | explicit legacy label |
| `interface_label = Wi-Fi` | `source = windows_host`, `scope = aggregate_gateway` | current Windows host default |
| other `interface_label` | `source = unknown`, `scope = aggregate_gateway` | preserve provenance uncertainty |
| `download_mbps`, `upload_mbps` | same | values unchanged |
| `rtt_avg_ms` | `rtt_ms` | value unchanged |
| `rtt_jitter_avg_ms` | `rtt_variation_ms` | value unchanged |
| `packet_loss_percent` | same | value unchanged |
| `adapter_up`, `internet_reachable`, `probe_target`, `probes_sent`, `probes_received`, `rtt_min_ms`, `rtt_max_ms` | remain in `network_samples` | no compatible shared field; not lost |
| missing counters/quality | `NULL`, `quality = unknown` | do not invent values |
| no client | `client_id = NULL`, `scope` aggregate | never convert aggregate to client |

Migration is transactional. On failure the transaction rolls back and the
schema version does not advance. Re-running migration uses
`legacy_sample_id` plus a `NOT EXISTS` guard, so rows are not duplicated.

## Migration and test plan

1. **Schema/version framework**
   - Create the migration entry point and `PRAGMA user_version`.
   - Verify version `0`, apply version `1`, verify idempotence.
   - Verify a failed migration rolls back.
2. **Non-destructive legacy migration**
   - Build temporary databases matching the real legacy schema.
   - Insert representative host and hotspot rows with known values/timestamps.
   - Verify row counts, values, timestamps, source, scope, and IDs.
   - Verify a second migration does not duplicate rows.
   - Verify the original legacy table and rows still exist.
3. **Canonical observation persistence**
   - Save shared `TelemetryObservation` objects.
   - Preserve NULL versus zero, quality, stale, source, scope, environment.
   - Verify invalid models and unsafe error text are rejected.
4. **Anonymous client persistence**
   - Register, retrieve, list, duplicate-handle, and conflict-check clients.
   - Verify simulated lab slot persistence and grouping.
   - Verify no address/identity columns or values exist.
5. **Aggregate/per-client history separation**
   - Query aggregate-only, Client 01-only, Client 02-only, by source, by
     environment, by scope, and by time range.
   - Verify no cross-client or aggregate/client contamination.
6. **Bounded queries**
   - Validate limit, offset, sorting, maximum limit, empty results, invalid
     ranges, and deterministic ordering.
7. **Reliability**
   - Missing file, empty database, corrupt file, failed transaction, concurrent
     reads/writes, and large bounded queries.
8. **Privacy**
   - Inspect actual rows, schema, serialized objects, and client records.
   - Reject IP, MAC, device name, hostname, URL, payload, credential, and
     address-to-ID mapping attempts.
9. **Regression**
   - Run existing metrics, registry, schema, accounting, API, and full Python
     suites.
   - Run `git diff --check`.

## Smallest first atomic task

Implement only the versioned migration framework and non-destructive legacy
schema migration, with tests on temporary databases. Do not yet add canonical
observation writes or history APIs. Acceptance criteria:

- existing `network_samples` rows and values survive;
- `PRAGMA user_version` advances from `0` to `1`;
- migration is idempotent;
- a failed migration rolls back;
- legacy table and index remain;
- targeted tests pass;
- no real database is touched.
