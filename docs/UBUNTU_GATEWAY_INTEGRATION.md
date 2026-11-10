# Ubuntu gateway observation integration

## Read-only agent

`gateway.observation_api:app` is a dedicated FastAPI app exposing only
`GET /api/v1/observations/current`. API docs and schema routes are disabled.
The endpoint reads the Linux namespace-lab accounting service, returns
validated anonymous client observations, and rejects unavailable or malformed
inventory rather than manufacturing zero traffic.

Configure the same secret independently on the Ubuntu agent and product
backend. Do not put it in source, shell history, manifests, or logs:

```bash
export EB_GATEWAY_TOKEN='<shared-random-secret>'
uvicorn gateway.observation_api:app --host 127.0.0.1 --port 8100
```

Bind to loopback unless a private VM/host network is explicitly configured.
Never bind this agent to a public interface. The backend reads:

- `EB_GATEWAY_URL` — base URL for the private agent.
- `EB_GATEWAY_TOKEN` — bearer token.
- `EB_GATEWAY_TIMEOUT_SECONDS` — bounded to 0.1–10 seconds.
- `EB_GATEWAY_INGEST_INTERVAL` — polling interval, bounded to 1–3600 seconds.

The backend transport requests one fixed path, uses bearer authentication when
configured, applies a timeout/retry budget and response-size bound, validates
the versioned schema and provenance, and never accepts a remote command path.
Ingestion registers only anonymous IDs, derives display labels locally,
preserves validated observation environment, ignores exact retries, and marks
rejects conflicting duplicates and out-of-order submissions instead of
overwriting newer records.

Namespace observations must be `linux_namespace_lab` and `simulated_lab`.
Client-scoped and aggregate observations remain separate. No IP, MAC, hostname,
or payload field is part of the public observation schema.

## Evidence and Windows boundary

Local FastAPI contract tests pass. No live agent process, Linux lab counter
source, or Windows-to-Ubuntu connection was available. Therefore cross-host
connectivity is **not verified**.

When a private Windows↔Ubuntu route exists, use a PowerShell session without
printing the token:

```powershell
$env:EB_GATEWAY_URL = "http://<private-ubuntu-address>:8100"
$env:EB_GATEWAY_TOKEN = "<shared-random-secret>"
Invoke-RestMethod -Uri "$env:EB_GATEWAY_URL/api/v1/observations/current" `
  -Headers @{ Authorization = "Bearer $env:EB_GATEWAY_TOKEN" }
python -m pytest tests/unit/test_gateway_transport.py tests/unit/test_gateway_ingest_service.py -v
```

Verify missing/invalid-token responses, disconnect/reconnect, stale and
out-of-order samples, and persistence on the real host pair. Do not substitute
mock tests for that boundary evidence.
