# Next Implementation Task

**Date:** 2026-11-10  
**Priority:** P1 — Part 1 integration foundation  
**Status:** Completed — gateway transport and ingest worker are implemented, unit-tested, and integrated in the FastAPI lifespan. Next validation step is real Ubuntu VM integration.

## Completed atomic task

Implemented the product-facing, read-only Linux gateway observation transport and its contract tests.

- `GatewayTransport` in `backend/app/services/gateway_transport_service.py`: bounded timeout, retry budget, bearer authentication, strict versioned schema validation, 1 MB response size limit, safe error codes, injectable HTTP client.
- `GatewayIngestService` in `backend/app/services/gateway_ingest_service.py`: persistent worker with backoff, client registration, canonical SQLite persistence, connected/disconnected state, safe error reporting.
- Integrated in `backend/app/main.py` lifespan when `EB_GATEWAY_URL` is configured.
- Unit tests in `tests/unit/test_gateway_transport.py` (5 passing) and `tests/unit/test_gateway_ingest_service.py` (2 passing).

## Next highest-priority atomic task

**Run real Ubuntu VM integration smoke test** for the gateway transport.

The transport and ingest are unit-tested with mocked HTTP clients. The next evidence step is to:
1. Configure an Ubuntu VM with the existing lab gateway agent exposing a restricted read-only endpoint (`GET /api/v1/observations/current`) that returns the versioned schema.
2. Set `EB_GATEWAY_URL`, `EB_GATEWAY_TOKEN`, and `EB_GATEWAY_TIMEOUT_SECONDS` on the Windows host.
3. Start the product backend and verify the `gateway_ingest_service` transitions to `connected`, persists observations, and reports `last_success_at` in health/topology APIs.
4. Verify timeout, invalid token, malformed response, agent restart, and stale observation scenarios against the real VM.
5. Record the results as **real VM integration evidence** separate from mocked transport tests.

This validation is not a code change; it is a demonstrated integration checkpoint before moving to forecasting, classification, or policy work.

## Validation commands

On Windows host:
```powershell
python -m pytest tests/unit/test_gateway_transport.py tests/unit/test_gateway_ingest_service.py -v
```

On Ubuntu VM (separate, labelled integration evidence):
- Start the restricted read-only observation agent on port 8100.
- Run the Windows backend with `EB_GATEWAY_URL=http://<vm-ip>:8100 EB_GATEWAY_TOKEN=<shared-token>`.
- Observe `GET /api/v1/health` gateway collector status, `GET /api/v1/observations/current` source `linux_gateway`, and `GET /api/v1/system/capabilities` gateway ingest state.

## Security review checklist

- [x] No arbitrary URL path or command parameters from API input.
- [x] No token in logs, responses, manifests, CSVs, or exception text.
- [x] No public bind requirement for the Linux agent.
- [x] Read-only route only; privileged helper remains outside this transport.
- [x] Strict response size (1 MB) and item-count (100) bounds.
- [x] Safe allowlist of error codes.
- [x] Timeout and retry limits prevent request amplification.

## Acceptance criteria for VM integration

- [ ] Windows backend starts with `EB_GATEWAY_URL` set and gateway ingest reports `connected`.
- [ ] Valid observations appear in `GET /api/v1/observations/current` with source `linux_gateway`/`linux_namespace_lab`.
- [ ] Health API reports `last_success_at` for the gateway collector.
- [ ] Invalid token produces `disconnected` with `gateway_authentication_failed` in health.
- [ ] Agent restart recovers to `connected` without Windows restart.
- [ ] Timeout/backoff behavior observed under VM network degradation.