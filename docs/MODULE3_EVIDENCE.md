# Module 3 evidence — Linux per-client accounting

Date: 2026-11-09  
Environment: Ubuntu 26.04.1 LTS, kernel 7.0.0-42-generic, Python 3.14.4  
Topology: project-owned bridge `br-lab` (`10.50.0.1/24`), namespaces
`clientN`, host-side veth `veth-cN-br`, and a project-owned nft table
`eb_nat`. No physical adapter is bridged or changed.

## Commands

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
bash scripts/setup_gateway.sh --check 3
bash scripts/setup_gateway.sh --check 5
sudo .venv/bin/python scripts/run_lab_accounting_integration.py \
  --evidence /tmp/opencode/module3_lab_evidence.txt
```

The integration runner uses real sysfs counters from `/sys/class/net/veth-cN-br/statistics`
and Python socket bulk transfers. It does not use mocked counter readings,
inspect packet payloads, or print MAC addresses.

## Real Linux results

Both three-client and five-client inventories passed:

| Check | 3 clients | 5 clients |
| --- | --- | --- |
| Repeated setup (idempotent) | PASS | PASS |
| Namespaces, veths, DNS present | PASS | PASS |
| Gateway and inter-client connectivity | PASS | PASS |
| Baseline sysfs counters | PASS | PASS |
| Client 01 download only | 8,010,490 B down; 5,648 B up; non-target max 304 B | 8,011,292 B down; 5,636 B up; non-target max 504 B |
| Client 02 upload only | 8,010,700 B up; 5,688 B down; non-target max 70 B | 8,009,908 B up; 5,882 B down; non-target max 0 B |
| Simultaneous multi-client traffic | PASS | PASS |
| Idle clients | max 790 B, max 0.004305 Mbit/s | max 340 B, max 0.002232 Mbit/s |
| Interface disappearance isolated | PASS (`client3`) | PASS (`client5`) |
| Counter reset detected after recreate | PASS (`client3`) | PASS (`client5`) |
| Repeated cleanup (idempotent) | PASS | PASS |
| Project resources removed | PASS | PASS |
| Unrelated namespace/interface/bridge/nft/DNS untouched | PASS | PASS |

The first real run failed because the test demanded exactly zero bytes on
non-target clients. A non-target port received 140 bytes of bridge
broadcast/control traffic while the target received about 8 MB. The assertion
was corrected to a documented materiality tolerance (16,384 B, 0.2% of the
target transfer) and still requires the target direction to increase by at
least 4 MB. The rerun passed without changing accounting code.

## Host cleanliness and privacy

After cleanup:

- `ip netns list` is empty.
- No `br-lab`, `veth-cN`, or `veth-cN-br` remains in `/sys/class/net`.
- The default route still uses the original host uplink.
- `net.ipv4.ip_forward` was restored from `0` to `0`.
- No `/etc/netns/clientN` directory remains.
- No payload, browsing history, IP address, MAC address, or real device name
  is stored in observations or the repository by this work.

## Regression results

- Targeted accounting, registry, and schema tests: 33 passed.
- Full Python suite: 153 passed, 1 third-party deprecation warning.
- `git diff --check`: clean.

## Limitations

- Traffic was generated with Python sockets instead of iperf3 because iperf3
  and curl are not installed in this VM; this does not affect counter
  accounting.
- The lab is runtime state and is removed by `scripts/cleanup_gateway.sh`.
- Five-client runtime testing is supported and was executed successfully.
