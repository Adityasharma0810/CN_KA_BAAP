# Module 5 API Audit

**Audit date:** 2026-11-09
**Feature 3 status:** Implemented and targeted-tested; final regression verification pending.

## Current-observation source audit

The product-facing application is `backend/app/main.py`. It mounts the legacy monitoring routes, the anonymous client routes, topology routes, and the versioned observation router. The privileged `gateway/api.py` application is not mounted.

### Windows host aggregate

`backend/app/api/monitoring.py` calls `monitoring_service.collect_and_store()`. That service measures the selected Windows adapter, connectivity and approved network-quality targets, then writes a canonical aggregate observation through `MetricsStore.insert_sample()`. The canonical source is `windows_host`, scope `aggregate_gateway`, environment `physical_host`.

The current-observation endpoint does not invoke this long-running probe on GET. It returns the newest canonical observation and computes freshness from its original timestamp.

### Windows Mobile Hotspot aggregate

`collect_hotspot_and_store()` measures the Windows Mobile Hotspot adapter and persists one aggregate row labelled `hotspot-aggregate`. The canonical source is `windows_hotspot`, scope `aggregate_hotspot`, environment `physical_host`. Windows hotspot counters do not identify individual physical devices; the current API never maps them to anonymous clients.

### Linux simulated lab

`LabAccountingService` uses `PerClientAccountingCollector` and sysfs counters only in the environment where the Linux lab exists. On Windows, missing lab interfaces produce an unavailable result. Canonical client observations use source `linux_namespace_lab`, scope `client`, environment `simulated_lab`, and an opaque `client_id`. There is no remote Ubuntu transport in this feature.

The current endpoint reads canonical observations from `MetricsStore`; it does not claim that a Python import or an old row makes a collector currently available.

## Current endpoint contract

`GET /api/v1/observations/current` supports validated `source`, `scope`, `environment`, and `client_id` filters. Aggregate and client queries are separated through repository methods. `linux_namespace_lab` is treated as client-scoped even when `scope` is omitted, so source filtering cannot silently route client data through aggregate-only queries.

The response uses strict `CurrentObservationsResponse` and `ObservationItem` models containing validated `TelemetryObservation` values. Missing metrics remain `null`, measured zero remains zero, provenance is preserved, and stale is computed without rewriting storage.

Default staleness is strictly greater than 300 seconds. A sample exactly 300 seconds old is fresh; a sample older than that is stale. The request timestamp is separate from each observation's original `observed_at`.

## Failure and privacy behavior

A missing database or no matching source returns an empty collection. Storage corruption/query failures return a safe `503 database_unavailable`. Unknown valid clients return `404`; malformed filters return `422`. Raw exception text, paths, addresses, interface names, namespace names, credentials, payloads and browsing data are not returned.

## Verification status

Feature 3 targeted tests cover aggregate sources, simulated clients, missing/unavailable data, source/scope separation, client isolation, filter validation, staleness boundaries, null versus zero semantics, UTC preservation, and privacy. Full regression verification remains required before committing the feature.
