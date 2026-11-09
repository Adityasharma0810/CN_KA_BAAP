# Running the dashboard with the Linux lab

## One-VM setup

Run the product API, Linux namespace lab, and React dashboard in the Ubuntu
VM. The Windows browser only displays the dashboard; collectors and the
background lab ingester run in Ubuntu. Windows host and hotspot collection
requires a separate Windows-side collector.

From the repository root, run:

```bash
bash scripts/run_dev.sh
```

The script starts the product API on port `8000` and Vite on port `5173`.
It does not run `sudo`. If the namespace lab is missing, it prints the setup
command:

```bash
sudo bash scripts/setup_gateway.sh
```

`EB_LAB_INGEST=1` enables the read-only lab ingester. Its polling interval is
two seconds by default; override it with `EB_LAB_INGEST_INTERVAL` (minimum one
second). At the default interval and three lab clients, expect about 7,200
observation rows per hour: three client rows plus one aggregate row per cycle.
Storage has no automatic deletion or retention cleanup.

## Opening it from the Windows browser

### VirtualBox NAT port forwarding

Configure two NAT port-forwarding rules while the VM is powered off:

| Name | Host port | Guest port |
|---|---:|---:|
| Dashboard | 5173 | 5173 |
| Product API | 8000 | 8000 |

Keep the default `EB_VM_IP` (or `VITE_API_BASE`) as `127.0.0.1`. Open
`http://127.0.0.1:5173` in Windows. The browser reaches both forwarded ports
through Windows localhost, and the backend's default CORS list permits the
dashboard origin.

### Host-only or bridged networking

Find the VM's host-only/bridged IPv4 address. Configure the API origin and
dashboard API base before starting the runner:

```bash
EB_VM_IP=192.168.56.101 \
EB_CORS_ORIGINS=http://192.168.56.101:5173 \
bash scripts/run_dev.sh
```

Replace the example address with the VM's actual address. Open
`http://192.168.56.101:5173` from Windows. You can instead set `VITE_API_BASE`
directly; it takes precedence over `EB_VM_IP`. Restart the backend after
changing `EB_CORS_ORIGINS`.

## Generate lab traffic

Start an iperf3 server in the VM if one is not already listening:

```bash
iperf3 -s -D
```

In another VM terminal, send traffic from a lab client:

```bash
sudo ip netns exec client1 iperf3 -c 10.50.0.1 -t 10
```

The dashboard should show anonymous client and aggregate lab observations
after the accounting collector obtains a usable counter baseline. The first
sample or a counter reset can have null rates; null means unavailable, not
zero.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Runner reports port 8000 or 5173 is already in use | Another API or frontend is listening on a required port | Stop that service, then restart the runner |
| Runner says the lab is missing | Lab namespaces or bridge are not configured | Run `sudo bash scripts/setup_gateway.sh`, then restart the runner |
| Linux lab ingest is disabled | Lab was absent at API startup, ingest was disabled, or the platform is not Linux | Check the capability status, set up the lab, and restart with `EB_LAB_INGEST=1` |
| Lab state is degraded or unavailable | Counter collection failed or the lab went down | Check worker's safe error code; restore the lab and allow automatic retries |
| Client rate says “No data” initially | No counter baseline exists yet, or counters reset | Generate traffic and wait for a later sample; the service will not invent a rate |
| Dashboard says backend unreachable | API is stopped or browser cannot reach port 8000 | Check the runner/API and VirtualBox forwarding or VM address |
| Browser reports a CORS error | Dashboard origin is not allowed | Set `EB_CORS_ORIGINS` to the exact dashboard origin and restart the API |
| Dashboard cannot load from Windows | VM port is not forwarded or reachable | Forward both ports, or use a host-only/bridged IP as described above |
| Windows host/hotspot sources are unavailable | The product API is running in Linux | Use a Windows-side collector; the Ubuntu VM cannot collect Windows counters |
