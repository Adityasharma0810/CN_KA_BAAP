# Reproducing the V0.9 Linux Gateway Lab

> **Revision note:** Historical performance figures below were recorded before
> the current safety changes and were not reproduced in this execution. The
> current test evidence and capability limitations are in
> `UBUNTU_TEST_RESULTS.md`. The lab is isolated and does not provide external
> connectivity through the VM host uplink.

This guide describes the existing lab and its earlier manual checks. Numbers
marked "observed" are historical results from the author's VM, not current
acceptance evidence.

The lab exists only inside an Ubuntu VM. Nothing here touches your home router or Windows network settings.

## 0. What you need

- A Windows (or any) host with VirtualBox.
- An Ubuntu VM (observed on Ubuntu 26.04 LTS, Python 3.14.4, git 2.53.0) with a normal user account (the author's is `vboxuser`) that can use `sudo`.
- Two network adapters on the VM, set while it is **fully powered off**:
  - Adapter 1: **NAT** (internet access).
  - Adapter 2: **Host-only Adapter** (private link to the host). If the Name list is empty, create one first under File → Tools → Network Manager → Host-only Networks.
- Optional: VS Code on the host with the **Remote - SSH** extension (section 10).

Check the adapters from inside the VM:

```
ip -br addr
```

Expected: `enp0s3` with a `10.0.2.x` address (NAT) and `enp0s8` with a `192.168.56.x` address (host-only). Interface names can differ.

## 1. Install packages

```
sudo apt update
sudo apt install -y git python3-venv python3-pip iperf3 iproute2 nftables openssh-server
```

If the iperf3 installer asks about starting as a daemon, either answer works; the steps below start servers explicitly when needed.

## 2. Get the code and Python environment

```
mkdir -p ~/Projects && cd ~/Projects
git clone https://github.com/Adityasharma0810/CN_KA_BAAP.git
cd CN_KA_BAAP
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run every later command from the repository root with the venv active (the prompt starts with `(.venv)`).

## 3. Build the isolated lab

```
sudo bash scripts/setup_gateway.sh 3
# Or use five clients:
sudo bash scripts/setup_gateway.sh 5
```

The lab creates only project-owned bridge/namespace/veth resources. It does
not enable forwarding or NAT through the Ubuntu host uplink; client namespaces
are intentionally isolated from the internet. Run on a dedicated VM after
checking for name collisions.

Verify:

```
ip netns list
sudo ip netns exec client1 ping -c 2 10.50.0.1
sudo ip netns exec client1 ping -c 2 10.50.0.12
```

These are local lab checks only. Do not test internet connectivity through the
host default route as part of this lab.

The lab is lost on every VM reboot. Re-run `setup_gateway.sh` after a restart.

## 4. Baseline throughput

An iperf3 server must be listening on port 5201:

```
ss -ltn | grep 5201
```

If there is no output, start one in the background: `iperf3 -s -D`.

Single client (observed about 51-54 Gbit/s):

```
sudo ip netns exec client1 iperf3 -c 10.50.0.1 -t 5
```

Three clients at once need one server port each, because an iperf3 server runs one test at a time:

```
iperf3 -s -p 5202 -D
iperf3 -s -p 5203 -D
sudo -v
for i in 1 2 3; do sudo ip netns exec client$i iperf3 -c 10.50.0.1 -p $((5200+i)) -t 5 > /tmp/client$i.txt & done; wait; tail -n 3 /tmp/client*.txt
```

Observed historically: about 3.8-4.0 Gbit/s each, an even split. These
background servers can be left running for later steps. If stopping one, inspect
its PID and terminate only that exact process.

## 5. Per-client monitoring (collector)

Terminal 1:

```
python3 gateway/collector.py
```

Terminal 2:

```
sudo ip netns exec client1 iperf3 -c 10.50.0.1 -t 5
sudo ip netns exec client2 iperf3 -c 10.50.0.1 -t 5 -R
```

Expected: client1's **Up** column jumps to tens of thousands of Mbit/s while its Down stays tiny; client2's **Down** column jumps during the `-R` (reverse) test. IDs look like `dev-a3f19c`, stay fixed while the collector runs, and change on restart. Stop with `Ctrl + C`.

## 6. Manual bandwidth limits

```
sudo bash scripts/limit_client.sh 1 10 5
sudo ip netns exec client1 iperf3 -c 10.50.0.1 -t 5 -R
sudo ip netns exec client1 iperf3 -c 10.50.0.1 -t 5
sudo bash scripts/limit_client.sh 1 off
```

Observed: download about 9.4-9.6 Mbit/s (limit 10), upload about 4.9 Mbit/s (limit 5). The first second overshoots slightly because of the token-bucket burst. Other clients are unaffected while client1 is limited. After `off`, client1 returns to tens of Gbit/s.

`limit_client.sh 1 50` (no upload value) should also clear any earlier upload limit. If it does not, your copy of the script is missing the `else` branch that deletes the upload qdisc.

## 7. Install the privileged helper

The API needs to run `tc` as root without running the whole API as root. This installs a root-owned copy of the limit script and a sudoers rule for that one file:

```
sudo bash scripts/install_helper.sh
```

Expected last line: `Installed /usr/local/sbin/eb-limit-client for user <your user>`. **Re-run this command every time `scripts/limit_client.sh` changes**, because the installed file is a copy.

## 8. Run the authenticated read-only observation agent

```
python3 -m py_compile gateway/observation_api.py && echo "syntax ok"
export EB_GATEWAY_TOKEN='<shared-random-secret>'
uvicorn gateway.observation_api:app --host 127.0.0.1 --port 8100
```

The observation agent is a separate, read-only API. It fails closed unless a
token is configured, and exposes only the documented current-observations
route. Keep it on loopback or a private VM network; never bind it publicly.

```
curl -H "Authorization: Bearer ${EB_GATEWAY_TOKEN}" \
  http://127.0.0.1:8100/api/v1/observations/current
```

The older interactive control API in `gateway/api.py` is not the remote
observation agent and must not be exposed on a public interface. The backend
uses only the authenticated read-only endpoint.

## 9. Local-only legacy controller demonstration

This section exercises the legacy control API and is separate from the
authenticated, read-only observation agent in section 8. Start it bound only
to loopback; do not expose it on a VM, LAN, or public interface:

```
uvicorn gateway.api:app --host 127.0.0.1 --port 8001
```

The policy commands below use that local API on port 8001. They are not a
Windows-to-Ubuntu gateway connectivity test. and live policy run

Unit tests:

```
python -m pytest tests/ -v
```

Observed before the controller tests were added: 40 passed (35 existing + 5 policy). With `tests/test_controller.py` added the suite should show 46 passed after the controller revision (35 existing, 5 policy, 6 controller); this count has not been confirmed yet. Use `python -m pytest`, not plain `pytest`, so the `gateway` package imports.

Live run, with the API running:

```
iperf3 -s -p 5202 -D            # skip if 5202 is already listening
python3 gateway/watch.py        # in its own terminal: live view
```

In another terminal:

```
curl -X POST localhost:8001/policy -H "Content-Type: application/json" -d '{"enabled": true, "budget_mbps": 100}'
curl -X POST localhost:8001/clients/1/intent -H "Content-Type: application/json" -d '{"intent": "streaming"}'
curl -X POST localhost:8001/clients/2/intent -H "Content-Type: application/json" -d '{"intent": "download"}'
sudo -v
sudo ip netns exec client1 iperf3 -c 10.50.0.1 -p 5202 -R -t 30 > /tmp/c1.txt &
sudo ip netns exec client2 iperf3 -c 10.50.0.1 -p 5201 -R -t 30 > /tmp/c2.txt &
wait
curl -s localhost:8001/policy
```

What to expect:

- For the first few seconds both clients run unlimited; the policy reacts every 3 seconds.
- Then the limits settle at about **68 / 17** Mbit/s for client1 (streaming) and client2 (download), and client3 (idle) stays unlimited. The controller shapes at 90% of the 100 Mbit/s budget, reserves a 5 Mbit/s minimum for the idle client, and splits the remaining 85 Mbit/s 4:1 by weight.
- Observed with the first controller version (which capped every client): client2 capped at 19 and client3 at 5. The expected limits above are for the revised controller, which caps only over-share clients; section 9A exercises it.
- A download client running at 90% or more of its cap keeps its limit (anti-oscillation rule).
- After the flows stop, limits should clear within a few seconds. Check with `curl -s localhost:8001/policy`.

Swap the intents (client1 `download`, client2 `streaming`) and repeat; the split should flip to about 19 / 76.

To disable the policy and clear every limit:

```
curl -X POST localhost:8001/policy -H "Content-Type: application/json" -d '{"enabled": false}'
```

## 9A. Shared-bottleneck experiments

These repeat the comparisons that produced the experiment tables in `REPO_AUDIT.md`. Both harnesses set the shared 100 Mbit/s bottleneck themselves and remove it at the end, even if a run fails.

Prerequisites: the lab is up, the helper is installed (section 7), the API is running (section 8) with the revised controller, and iperf3 servers are listening on ports 5201 and 5202 (`ss -ltn | grep -E ':520[12]'`; start missing ones with `iperf3 -s -D` and `iperf3 -s -p 5202 -D`). Run from the repo root with the venv active.

**Call vs download** (about 6 minutes). A 5 Mbit/s UDP call plus a ping probe against a 4-stream download, no policy vs intent policy:

```
sudo -v
python3 experiments/run_call_vs_download.py --runs 5
```

Observed on the author's VM (mean +/- standard deviation over 5 runs): call RTT average 29.95 +/- 14.19 ms without the policy and 1.83 +/- 1.76 ms with it; download 88.0 Mbit/s without and 74.6 Mbit/s with; call loss about 0.25% in both.

**Streaming vs download** (about 9 minutes). One TCP stream paced to 60 Mbit/s against a 4-stream download, in three modes (no policy, equal weights, intent weights):

```
sudo -v
python3 experiments/run_streaming_vs_download.py --runs 5
```

Observed: streaming throughput 16.2 / 40.4 / 63.2 Mbit/s for no policy / equal / intent, with the download at 77.5 / 42.2 / 20.5 Mbit/s. If the script prints a warning that the streaming client exceeded its target rate, `iperf3 -b` is being ignored for TCP in reverse mode on your iperf3 version.

**Outputs:** one CSV per run under `experiments/reports/`, and the raw iperf3 and ping output under `/tmp/eb_runs_<timestamp>` (or `eb_stream_runs_<timestamp>`). Modes are interleaved across repeats, and the first 8 seconds of every run are ignored so the policy has time to engage.

**If a run is interrupted,** reset by hand:

```
curl -X POST localhost:8001/policy -H "Content-Type: application/json" -d '{"enabled": false}'
sudo bash scripts/set_bottleneck.sh off
```

**Quick single run for debugging:** `bash scripts/call_vs_download.sh <label>` runs one call-vs-download test and prints the call result, the RTT summary, the download result, the policy state and the `tc` counters halfway through. Use `STREAMS=1` for a single download stream.

## 10. Optional: edit from Windows VS Code (Remote - SSH)

1. In the VM: `sudo systemctl enable --now ssh`, and note the host-only IP from `ip -br addr`.
2. On Windows, install the Microsoft **Remote - SSH** extension (search `ms-vscode-remote.remote-ssh`; plain search can hide it).
3. Test in PowerShell: `ssh <user>@<host-only IP>`.
4. In VS Code: Ctrl+Shift+P → **Remote-SSH: Connect to Host** → enter the IP, choose Linux, then File → Open Folder → `~/Projects/CN_KA_BAAP` in the VM.
5. Use the VS Code integrated terminal for everything above; it runs inside the VM.

Known snag: if the connection fails with `Bad owner or permissions on ...\.ssh\config`, Windows OpenSSH rejects the file because extra accounts have access. In PowerShell run:

```
icacls "$env:USERPROFILE\.ssh\config" /inheritance:r
icacls "$env:USERPROFILE\.ssh\config" /grant:r "${env:USERNAME}:F"
```

## 11. Clean up

```
sudo bash scripts/cleanup_gateway.sh
```

This removes project-marked namespaces, bridge, veths, and per-client DNS
files; it is intended to be safe to repeat. It does not remove the installed
helper or sudoers rule. New lab setup does not create NAT or change host
forwarding. Inspect legacy project state before cleanup if the lab was created
by an older revision. To remove the helper too:

```
sudo rm /usr/local/sbin/eb-limit-client /etc/sudoers.d/experience-budget
```

## 12. Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `iperf3: error - unable to connect to server: Connection refused` | No server on that port. `iperf3 -s -D` (or `-p 5202`). |
| `iperf3: error - the server is busy running a test` | One server handles one test at a time. Use one port per client. |
| `ip netns list` is empty | The VM rebooted. Re-run `setup_gateway.sh`. |
| API 500 error mentioning `sudo` | Helper not installed or sudoers rule missing. Run `sudo bash scripts/install_helper.sh`. |
| Limit script change has no effect through the API | Installed copy is stale. Re-run `install_helper.sh`. |
| `uvicorn` shows a `SyntaxError` | Fix the line it names; check with `python3 -m py_compile gateway/observation_api.py`. |
| `sudo poweroff` says the operation is inhibited | The desktop session blocks it. Use `systemctl poweroff -i` or the Ubuntu power menu. |
| Settings greyed out in VirtualBox | The VM is running or saved. Power it off fully first. |
| Client pings work but external sites do not | Expected: the isolated lab intentionally has no host-uplink NAT. |

## 13. Known limits of these results

- The 100 Mbit/s budget is simulated; the virtual links have no natural bottleneck. Section 9A adds a shared `tc` limit with a 50 ms queue so clients really compete; absolute latencies depend on that queue depth.
- Intents are set by hand through the API. No classifier exists yet.
- The clients are iperf3 flows in network namespaces, not real devices or realistic traffic.
- The checks in `REPO_AUDIT.md`, finding 18, were confirmed by the author on 2026-11-07. They are manual runs, not automated tests.