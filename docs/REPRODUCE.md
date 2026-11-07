# Reproducing the V0.9 Linux Gateway Lab

This guide rebuilds the lab from the GitHub repository and repeats the checks that produced the results in `REPO_AUDIT.md`. Numbers marked "observed" came from the author's VM; yours will differ a little, especially the multi-Gbit/s figures.

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

## 3. Build the lab

```
sudo bash scripts/setup_gateway.sh
```

Expected output:

```
Created bridge br-lab (10.50.0.1)
Created client1 (10.50.0.11)
Created client2 (10.50.0.12)
Created client3 (10.50.0.13)
NAT enabled via enp0s3
Lab ready.
```

Verify:

```
ip netns list
sudo ip netns exec client1 ping -c 2 10.50.0.1
sudo ip netns exec client1 ping -c 2 10.50.0.12
sudo ip netns exec client1 ping -c 2 1.1.1.1
sudo ip netns exec client1 ping -c 2 google.com
```

All pings should succeed with 0% loss. To prove the scripts rebuild everything from nothing, run `sudo bash scripts/cleanup_gateway.sh`, then `setup_gateway.sh` again, then repeat the last two pings.

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
pkill -f "iperf3 -s -p 520[23]"
```

Observed: about 3.8-4.0 Gbit/s each, an even split. Note that `pkill` also stops the 5202 server; start it again later when a step needs it.

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

## 8. Run the API

```
python3 -m py_compile gateway/api.py && echo "syntax ok"
uvicorn gateway.api:app --host 0.0.0.0 --port 8000
```

Leave it running and use a second terminal. This is separate from the original `backend/app` API; do not run both on port 8000.

```
curl localhost:8000/health
curl localhost:8000/clients
```

Expected: `{"status":"ok"}` and a JSON list of three clients with `intent` and `limit` fields. The API clears all limits when it starts.

Apply and remove a limit through the API:

```
curl -X POST localhost:8000/clients/1/limit -H "Content-Type: application/json" -d '{"down_mbps": 10}'
sudo ip netns exec client1 iperf3 -c 10.50.0.1 -t 5 -R
curl localhost:8000/clients
curl -X DELETE localhost:8000/clients/1/limit
```

Observed: download about 9.6 Mbit/s, `/clients` lists the limit for client1, and the DELETE returns `"limit":null`. From the host browser you can also open `http://<VM host-only IP>:8000/docs` (verified from the Windows browser by the author).

## 9. Policy tests and live policy run

Unit tests:

```
python -m pytest tests/ -v
```

Observed before the controller tests were added: 40 passed (35 existing + 5 policy). With `tests/test_controller.py` added the suite should show 45 passed; the author confirmed the controller tests pass. Use `python -m pytest`, not plain `pytest`, so the `gateway` package imports.

Live run, with the API running:

```
iperf3 -s -p 5202 -D            # skip if 5202 is already listening
python3 gateway/watch.py        # in its own terminal: live view
```

In another terminal:

```
curl -X POST localhost:8000/policy -H "Content-Type: application/json" -d '{"enabled": true, "budget_mbps": 100}'
curl -X POST localhost:8000/clients/1/intent -H "Content-Type: application/json" -d '{"intent": "streaming"}'
curl -X POST localhost:8000/clients/2/intent -H "Content-Type: application/json" -d '{"intent": "download"}'
sudo -v
sudo ip netns exec client1 iperf3 -c 10.50.0.1 -p 5202 -R -t 30 > /tmp/c1.txt &
sudo ip netns exec client2 iperf3 -c 10.50.0.1 -p 5201 -R -t 30 > /tmp/c2.txt &
wait
curl -s localhost:8000/policy
```

What to expect:

- For the first few seconds both clients run unlimited; the policy reacts every 3 seconds.
- Then the limits settle at about **76 / 19 / 5** Mbit/s for client1 (streaming), client2 (download) and client3 (browsing). Client3 is idle but the controller reserves it a 5 Mbit/s minimum, so the 100 Mbit/s budget is 5 for client3 and the remaining 95 split 4:1 by weight.
- Observed: client2 capped at 19 (measured 17.6) and client3 at 5. The 76 for client1 follows from the same math and was confirmed by the author.
- A download client running at 90% or more of its cap keeps its limit (anti-oscillation rule).
- After the flows stop, limits should clear within a few seconds. Check with `curl -s localhost:8000/policy`.

Swap the intents (client1 `download`, client2 `streaming`) and repeat; the split should flip to about 19 / 76.

To disable the policy and clear every limit:

```
curl -X POST localhost:8000/policy -H "Content-Type: application/json" -d '{"enabled": false}'
```

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

This removes the namespaces, the bridge, per-client DNS files and the NAT table, and is safe to run repeatedly. It does not remove the installed helper or the sudoers rule. To remove those too:

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
| `uvicorn` shows a `SyntaxError` | Fix the line it names; check with `python3 -m py_compile gateway/api.py`. |
| `sudo poweroff` says the operation is inhibited | The desktop session blocks it. Use `systemctl poweroff -i` or the Ubuntu power menu. |
| Settings greyed out in VirtualBox | The VM is running or saved. Power it off fully first. |
| Client pings work but `google.com` fails | DNS files missing. Re-run `setup_gateway.sh`, which writes `/etc/netns/clientN/resolv.conf`. |

## 13. Known limits of these results

- The 100 Mbit/s budget is simulated; the virtual links have no natural bottleneck.
- Intents are set by hand through the API. No classifier exists yet.
- The clients are iperf3 flows in network namespaces, not real devices or realistic traffic.
- The checks in `REPO_AUDIT.md`, finding 18, were confirmed by the author on 2026-11-07. They are manual runs, not automated tests.