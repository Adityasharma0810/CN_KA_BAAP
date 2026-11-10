# Experience Budget Known Limitations

**As-of:** 2026-11-10  
**Purpose:** Honest boundary of what the checked-out implementation does and does not prove.

## Product and deployment limitations

1. The Linux gateway is a namespace-based Ubuntu VM lab. It is not a physical household router, Wi-Fi controller, or production WAN appliance.
2. The product does not discover or persist real household-device identity. Client IDs are opaque and simulated lab slots are not physical devices.
3. Windows Mobile Hotspot telemetry is aggregate-only. It cannot attribute bytes or QoE to individual hotspot clients.
4. The Windows-to-Ubuntu authenticated, bounded observation transport and ingest worker are implemented and contract-tested. Real VM connectivity, persistence, restart recovery, and end-to-end freshness are not yet evidenced; configuration alone is not proof of remote integration.
5. No automated Windows↔Ubuntu VM integration suite currently proves timeout, invalid authentication, malformed response, restart, stale response, and recovery behavior.
6. Linux namespace state, bridge state, NAT state, and traffic-control state are runtime lab state and must be recreated after a VM reboot.
7. The root-owned helper is a lab deployment artifact. Its sudoers allowance and copied installation must not be reused on a shared or production machine without a security review.

## Telemetry and storage limitations

8. Windows adapter and hotspot collection still has known configuration inconsistencies: adapter selection/history behavior and hotspot interface selection need completion.
9. The data model preserves unavailable values, but the full stale/freshness contract is not yet covered by an exhaustive automated test matrix.
10. SQLite is the canonical store for this reference implementation; retention/archival policy and high-concurrency operational behavior are not production-proven.
11. Aggregate observations derived from client observations are not independent measurements of a physical gateway.
12. Counter rates require a baseline. The first sample, counter resets, missing interfaces, and partial inventories can produce unavailable or degraded observations.

## Classification, ML, and decision limitations

13. Intent is currently declared by Scenario Lab profiles or gateway API configuration. It is not inferred by the live product from traffic.
14. No privacy-safe classifier is integrated into the product decision path. Saved model artifacts alone do not establish live classification.
15. No classifier evaluation against real household application traffic exists. Generator-based accuracy would represent simulated traffic only.
16. Forecasting modules and saved artifacts are not connected to a validated live capacity estimator, confidence gate, or rollback controller.
17. QoE scores are deterministic observation-only proxies. They are not subjective user studies, application instrumentation, MOS scores, or proof that a household user perceived the stated band.
18. Stream QoE requires a five-sample stability history. Sparse history correctly produces `unknown`, but this can make early Scenario Lab scores unavailable.
19. Bulk scoring uses measured capacity and a configured number of active profiles. It is not a mathematically complete true max-min QoE optimizer.
20. Conflict negotiation, household priority policy, explanation ledger, and consent/audit workflow are incomplete.

## Enforcement and control limitations

21. Current verified Linux shaping is TBF-based. CAKE and HTB+fq_codel enforcement, capability negotiation, and a unified product abstraction remain open.
22. The gateway controller is a rule-based baseline separate from the product backend. It shapes download in the current policy loop; upload shaping is not integrated into closed-loop policy.
23. Policy limits are primarily in memory. Rules applied manually outside the API are not visible to the controller, although startup cleanup is designed to avoid forgotten active limits.
24. The controller intentionally shapes below the simulated bottleneck and has known throughput inefficiency. Existing experiments show an experience benefit in selected scenarios at a throughput cost; packet-loss improvement must not be claimed.
25. Policy behavior depends on declared intent being correct. Misclassification cost and wrong-intent recovery are not yet measured in the integrated product.
26. General pre/post policy verification and automatic harmful-change rollback are not complete. Scenario cleanup is bounded rollback for a lab run, not the full adaptive controller requirement.

## Experiment and UI limitations

27. Existing experiment harnesses are Linux scripts with CSV output and manual/automated test support. They are not yet a product-facing experiment registry with signed manifests, statistical analysis service, or full A/B UI.
28. Existing reports cover two scenarios and five runs per mode under a deliberately simulated bottleneck. They are evidence for that testbed only, not a household generalization.
29. The frontend has no configured unit-test runner or E2E suite. Lint and a production bundle do not establish direct-route or browser integration behavior; those checks remain incomplete.
30. Dashboard labels and topology views describe measurement provenance, but a visual label is not independent evidence that a physical router or device was observed.
31. About/limitations and settings/safety views must continue to distinguish measured, derived, simulated, configured, stale, and unavailable data.

## Advanced capability limitations

32. No federated learning, secure aggregation, differential privacy training, or cross-household model lifecycle exists.
33. No production-grade model registry, drift monitor, rollback deployment, or online/offline feature parity contract exists.
34. No claim should be made about seamless WAN switching, physical Wi-Fi remediation, production router integration, or persistent physical identity continuity.

## Required wording for demonstrations

Use **simulated Linux namespace lab** for the VM testbed, **aggregate Windows hotspot measurement** for hotspot data, and **proxy QoE score** for the deterministic scoring output. Do not call these physical-device telemetry, per-device hotspot telemetry, user-perceived QoE, or production router control.
