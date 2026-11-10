# Ubuntu Remaining Tasks

**Handoff date:** 2026-11-10  
**Related audit:** `docs/WINDOWS_COMPLETION_AUDIT.md`

This is an actionable native-Ubuntu handoff. It does not claim that Windows or mocked tests are Linux integration evidence. The 2026-11-10 frontend/API repair pass did not exercise the namespace lab or a separate Ubuntu gateway VM.

## U-01 — Confirm VM network and gateway reachability

**Status:** NOT REVALIDATED; earlier Windows-to-VM checks could not reach the supplied addresses.

Already implemented:
- Gateway transport and ingest configuration via `EB_GATEWAY_URL` and `EB_GATEWAY_TOKEN`.
- Bounded timeout/retry behavior and strict response validation.

Ubuntu work:

```bash
ip -br addr
ip route
ss -ltn
```

Expected evidence:
- Current host-only address recorded.
- Gateway observation endpoint reachable from the Windows host.
- No assumption that the old NAT address remains valid.

## U-02 — Rebuild and validate the namespace lab

**Status:** PARTIAL; scripts and unit checks exist, native execution remains required.

Files:
- `scripts/setup_gateway.sh`
- `scripts/cleanup_gateway.sh`
- `scripts/lab_common.sh`

Commands:

```bash
sudo bash scripts/setup_gateway.sh
ip netns list
sudo ip netns exec client1 ping -c 2 10.50.0.1
sudo ip netns exec client1 ping -c 2 1.1.1.1
```

Expected evidence:
- Supported client counts build successfully.
- Connectivity works after cleanup and rebuild.
- NAT and forwarding are limited to project-owned state.

## U-03 — Validate per-client accounting

**Status:** PARTIAL.

Files:
- `gateway/accounting.py`
- `gateway/collector.py`
- `backend/app/services/lab_ingest_service.py`

Required evidence:
- Correct upload/download direction.
- Missing interface handling.
- Counter reset handling.
- 3-client and 5-client observations.
- No double counting.

## U-04 — Validate restricted helper and TBF shaping

**Status:** PARTIAL; documented manual evidence exists, current native rerun required.

Files:
- `scripts/privileged/eb-priv`
- `scripts/privileged/install_eb_priv.sh`
- `scripts/limit_client.sh`

Commands:

```bash
sudo bash scripts/privileged/install_eb_priv.sh
sudo bash scripts/limit_client.sh 1 10 5
sudo ip netns exec client1 iperf3 -c 10.50.0.1 -t 5 -R
sudo bash scripts/limit_client.sh 1 off
```

Expected evidence:
- Download and upload limits are applied and removable.
- Invalid helper arguments produce fixed safe output.
- Unrelated interfaces and rules are untouched.

## U-05 — Determine qdisc capabilities

**Status:** NOT VERIFIED.

Commands:

```bash
tc qdisc add dev br-lab root cake bandwidth 100mbit
 tc qdisc show dev br-lab
 tc qdisc del dev br-lab root
 tc qdisc add dev br-lab root handle 1: htb default 10
 tc qdisc show dev br-lab
 tc qdisc del dev br-lab root
 tc qdisc add dev br-lab root fq_codel
 tc qdisc show dev br-lab
 tc qdisc del dev br-lab root
```

Run only against the project lab bridge and clean up each test. Record whether CAKE, HTB, and fq_codel are available. Do not treat TBF evidence as CAKE evidence.

## U-06 — Validate upload and download controller behavior

**Status:** PARTIAL.

Files:
- `gateway/controller.py`
- `gateway/api.py`
- `gateway/policy.py`

Required evidence:
- Upload shaping participates in the policy loop if supported.
- Download shaping remains correct.
- Limits clear when demand drops.
- Read-back matches desired policy.
- No client starvation.

## U-07 — Run native Scenario Lab

**Status:** PARTIAL.

Files:
- `backend/app/services/scenario_service.py`
- `scripts/privileged/eb-priv`

Required evidence:
- `call_vs_download`.
- `wan_drop`.
- `tvs_and_gamer` with the required client count.
- Bounded cleanup after completion, failure, and cancellation.
- Manifest and observation export.

## U-08 — Live Windows-to-Ubuntu observation integration

**Status:** BLOCKED_ENVIRONMENT until U-01 is complete.

Required sequence:

1. Start only the restricted read-only observation endpoint.
2. Configure Windows backend environment variables without committing credentials.
3. Run a valid observation fetch.
4. Confirm SQLite persistence.
5. Stop/restart the Ubuntu agent.
6. Confirm disconnected state.
7. Restore the agent.
8. Confirm recovery and freshness.

Expected evidence:
- Valid typed response.
- Correct source/scope/environment.
- Anonymous labels remain distinct.
- No private network identifiers cross the product boundary.

## U-09 — Native experiment reruns

**Status:** PARTIAL.

Files:
- `experiments/run_call_vs_download.py`
- `experiments/run_streaming_vs_download.py`
- `experiments/reports/`

Run only after the lab and helper are validated. Record raw outputs, configuration, seed, environment, and repeated-trial statistics. Do not claim physical-router behavior.

## U-10 — Native Linux regression suite

**Status:** NOT RUN in this audit pass; run on the target Ubuntu environment to record native Linux results.

Run on Ubuntu:

```bash
python -m pytest -q
```

The historical Windows result of 349 passing and 37 shell-test failures is not Linux validation. The API contract tests run in the current Linux development environment are not a substitute for this full native regression run.

## Core versus roadmap impact

- U-01 through U-04 and U-08 are required for credible Windows + Ubuntu core integration.
- U-05 and U-06 are required for expanded Linux enforcement claims.
- U-07 and U-09 support reproducible demonstrations.
- Federated learning and physical-router integration are not Ubuntu-only and remain separate roadmap/hardware work.
