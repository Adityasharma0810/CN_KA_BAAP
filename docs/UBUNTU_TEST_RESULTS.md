# Ubuntu/Linux test results

**Execution date:** 2026-11-10
**OS/kernel/Python:** Ubuntu 26.04.1 LTS / 7.0.0-42-generic / Python 3.14.4
**Starting revision:** `781342300ff1c2a7e5a9874a3e97548f4df28f28`

## Baseline

```text
PYTHONPATH=. .venv/bin/pytest -q
386 passed, 1 third-party Starlette/httpx deprecation warning
```

Running the test executable without `PYTHONPATH=.` failed collection because
the repository packages were not on the executable's import path; this was a
test invocation issue, not a product failure. The correct invocation above
passed.

## Implementation checks

- Focused gateway API/transport/ingest tests: **18 passed**, 1 existing
  Starlette/httpx deprecation warning; focused QoS tests: **10 passed**.
- Python compile check:
  `.venv/bin/python -m compileall -q backend gateway network qos scripts/run_lab_accounting_integration.py tests/unit/test_qos_enforcement.py tests/unit/test_gateway_observation_api.py`
  — passed.
- Bash syntax check for lab setup, cleanup, bottleneck, and client scripts —
  passed.
- `setup_gateway.sh --check 3`, `setup_gateway.sh --check 5`, and cleanup
  configuration check — passed.
- `git diff --check` — passed at the recorded check.

## Linux integration readiness and result

Read-only baseline:

- `iproute2`/`tc`: 6.19.0; nftables: 1.1.6.
- `iperf3`: unavailable.
- Interfaces: loopback and one UP virtual adapter; default route unchanged.
- Existing namespaces: none; no project lab bridge present.
- Current host-uplink qdisc readback: `fq_codel` root. It was inspected only;
  it was not modified.
- Effective capabilities: `CapEff: 0000000000000000`.
- Namespace permission probe:
  `ip netns add eb-capability-probe` failed with
  `mount --make-shared /run/netns failed: Operation not permitted`; no namespace
  was created.

Consequently, no namespace setup/teardown, three/five-client traffic test,
CAKE/HTB live test, upload/download rate test, rollback fault injection against
the kernel, multi-client A/B experiment, or complete non-mocked pipeline test
was run. This is an environment limitation, not a passing integration result.

## Final regression

```text
PYTHONPATH=. .venv/bin/pytest -q
407 passed, 1 third-party Starlette/httpx deprecation warning, 21.67s
```

The final suite includes the new gateway and QoS unit/API tests. The warning
originates from the installed Starlette test client integration with `httpx`;
it did not fail a test.

## Enforcement capability distinction

The read-only capability detector found CAKE, HTB, fq_codel, IFB, matchall,
and mirred in kernel module indexes and selected CAKE as the preferred mode.
This is module-index evidence only: no qdisc was loaded, configured, or
verified on a lab interface. Neither CAKE nor HTB + fq_codel was tested live.

Download and upload shaping, actual kernel readback, rollback after a kernel
failure, resource cleanup, multi-client contention, and A/B results remain
unverified because namespace administration is blocked. No Windows/Ubuntu
connectivity test was performed.
