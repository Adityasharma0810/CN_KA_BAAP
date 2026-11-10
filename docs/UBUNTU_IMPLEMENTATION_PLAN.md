# Ubuntu/Linux implementation and completion matrix

**Checked:** 2026-11-10
**Starting revision:** `781342300ff1c2a7e5a9874a3e97548f4df28f28`
**Environment:** Ubuntu 26.04.1 LTS, Linux 7.0.0-42-generic, Python 3.14.4
**Evidence standard:** code-level/unit-test success is not a native namespace or kernel-enforcement pass.

The checkout already contained a partial Linux lab, authenticated transport,
topology API, and uncommitted `qos/` work. The initial full Python suite passed
386 tests. This execution did not create a namespace, bridge, veth, qdisc, or
firewall rule: the current user has no effective capabilities
(`CapEff: 0000000000000000`), and a read-only-permission probe for
`ip netns add` failed with `Operation not permitted`. The host default route
and link state were inspected and left unchanged.

## Linux task matrix

| Task | Status | Implementation | Test evidence | Remaining blocker |
|---|---|---|---|---|
| P1-05 / P3-05: configurable 3/5-client namespace lab | PARTIAL | Existing lab scripts support configurable counts; setup no longer enables forwarding or NAT through the host uplink. | Shell syntax and `setup_gateway.sh --check 3/5`, cleanup checks pass. | No `CAP_NET_ADMIN`; native setup, traffic, rollback, and teardown not run. Static names are not collision-resistant. |
| P1-06 / P1-07: authenticated gateway transport and ingestion | PARTIAL | Added a read-only agent API, bearer authentication, real bearer header on transport, response-context validation, per-client labels/environment, and idempotent persistence with conflicting/out-of-order replay rejection. | Gateway transport, agent API, and ingest tests pass. | No live gateway process/VM boundary test; the lab source itself is unavailable here. |
| P1-09: Linux topology discovery | PARTIAL | Existing API builds a privacy-safe logical topology from observations and anonymous registry records. | Existing topology unit/API tests pass. | It does not discover live namespaces, bridges, veths, link state, or enforcement points from the Linux kernel. |
| P3-01 / P3-02: CAKE and HTB + fq_codel | PARTIAL | Added typed plans, capability detection, command construction, readback parsing, and refusal of unsupported explicit modes. Upload checks include IFB, matchall, and mirred. | New QoS unit tests pass; capability detection is read-only. | No kernel apply/readback test; CAKE and HTB were not loaded or applied. |
| P3-03: upload/download shaping | PARTIAL | Download egress and upload ingress-to-IFB command paths exist; direct legacy scripts now check lab ownership and reserved qdisc handles. | Command-construction and shell checks pass. | No IFB support or root capability evidence; direction/rate behavior not measured on a live lab. |
| P3-04 / P3-05 / F12: controller-to-enforcement integration | PARTIAL | Existing gateway controller remains separate from the new enforcer; no policy hand-off to `LinuxTrafficEnforcer` is claimed. | Existing controller/policy tests pass. | Privileged lifecycle and verified kernel-state feedback are not wired into the controller. |
| P3-06 / F13: repeatable Linux A/B experiments | PARTIAL | Existing scenario/experiment tools remain; no synthetic results were added. | Existing Python suite passes. | No real lab run, comparable baseline/controlled run, or machine-readable new report in this execution. |
| P3-13: complete lab-to-controller end-to-end pipeline | BLOCKED | The authenticated/read-only and accounting boundaries have code and unit coverage. | Final unit/regression suite: 407 passed; native end-to-end pipeline is not claimed. | Cannot create lab resources without `CAP_NET_ADMIN`; no live service or kernel readback. |
| F1: Linux observation provenance and storage | PARTIAL | Existing typed observation contract; gateway ingest preserves environment, de-duplicates identical retries, and rejects conflicting or out-of-order replays. | Gateway and storage tests pass. | No real network-to-storage pipeline execution. |
| F5: Linux observations into QoE proxy | PARTIAL | Existing backend QoE service consumes canonical observations. | Existing QoE and observation tests pass. | No live Linux feedback cycle in this environment. |
| F9: Linux rollback/readback | PARTIAL | Added bounded ownership-aware cleanup and strict readback failure handling; only the unshaped default is considered restorable. | QoS unit tests pass. | Fault injection against real `tc` and kernel rollback verification unavailable. |
| F11: Linux QoS enforcement | PARTIAL | CAKE/HTB+fq_codel architecture and a safer lab-only TBF path are present. | Command/capability/readback unit tests pass. | No mode was applied or verified on a namespace interface. |
| F2/F3/F4/F6/F7/F8/F10/F15/F17: classifier, forecasting, optimizer, intent, ledger, confidence, ML, federated learning | NOT APPLICABLE | These are broader product/research gaps, not Ubuntu-only implementation work; no unrelated redesign was attempted. | Not tested by this Linux task. | Remain separate project work. |
| F14: Scenario Lab Linux execution | PARTIAL | Existing API/service/test implementation is retained. | Existing scenario tests pass. | Native namespace execution is blocked by missing capability. |
| F16: Windows/Ubuntu operational boundary | PARTIAL | Added a narrow, authenticated read-only observation endpoint and client-side transport. | Local unit/API tests pass. | Windows-to-Ubuntu connectivity was not tested; this session is Ubuntu-only. |

`COMPLETE` requires a relevant test to pass in the target environment. Across
the 11 named task IDs (P1-05, P1-06, P1-07, P1-09, P3-01, P3-02, P3-03, P3-04,
P3-05, P3-06, and P3-13), **0 of 11 are COMPLETE (0%)**. Ten are PARTIAL and
P3-13 is BLOCKED. This is not a percentage of the whole project.

## F1–F12 cross-check

F1, F5, F9, F11, and F12 have Linux-facing code paths and remain partial pending
live integration. F2–F4, F6–F8, and F10 are not Linux-only and were not
implemented in this scope. The additional master tracker items F13, F14, F16,
and F17 are recorded above so the Linux boundary is not mistaken for completion
of the broader project.

## Reproducible checks

- Baseline: `PYTHONPATH=. .venv/bin/pytest -q`
- Focused Linux tests: see `UBUNTU_TEST_RESULTS.md`
- Script validation: `bash -n scripts/lab_common.sh scripts/setup_gateway.sh scripts/cleanup_gateway.sh scripts/set_bottleneck.sh scripts/limit_client.sh`
- Non-mutating inventory: `bash scripts/setup_gateway.sh --check 3` and `bash scripts/setup_gateway.sh --check 5`
- Native setup is intentionally not listed as completed evidence because the
  current VM cannot perform namespace administration.

Historical results in `MODULE3_EVIDENCE.md` and prior tracker entries are
reference material only; they were not reproduced by this execution.
