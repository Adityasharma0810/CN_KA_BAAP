#!/usr/bin/env python3
"""Print the household network tree from live Experience Budget API data.

The tree starts at the Wi-Fi router, continues into the device running the
Experience Budget backend, and lists every device connected to it. Every
node's state comes from the running backend's real endpoints -- nothing is
fabricated; nodes the backend cannot see are marked as such.

Usage:  python3 scripts/network_tree.py [API_BASE]
        (API_BASE defaults to http://127.0.0.1:8000)
"""

from __future__ import annotations

import json
import sys
import urllib.request

API_BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
API_BASE = API_BASE.rstrip("/")

STATE_MARKS = {
    "online": "[online]",
    "degraded": "[degraded]",
    "missing": "[not visible]",
    "unknown": "[unknown]",
}


def fetch(path: str):
    """GET one API path, raising a clear error when the backend is down."""

    try:
        with urllib.request.urlopen(f"{API_BASE}{path}", timeout=5) as response:
            return json.load(response)
    except Exception as error:
        raise SystemExit(
            f"Experience Budget API is not reachable at {API_BASE} ({error}).\n"
            "Start it with: PYTHONPATH=. .venv/bin/python -m uvicorn "
            "backend.app.main:app --host 127.0.0.1 --port 8000"
        ) from error


def mark(state: str | None) -> str:
    return STATE_MARKS.get((state or "").lower(), f"[{state or 'unknown'}]")


def quality(data_quality: str | None) -> str:
    return f" quality={data_quality}" if data_quality else ""


def render(title: str, state: str | None, detail: str) -> str:
    line = f"{title} {mark(state)}"
    if detail:
        line += f" -- {detail}"
    return line


def render_tree(node: tuple[str, list]) -> list[str]:
    """Render a (label, children) node as ASCII tree lines."""

    label, children = node
    lines = [label]
    for index, child in enumerate(children):
        last = index == len(children) - 1
        prefix = "└── " if last else "├── "
        child_label, child_children = child
        lines.append(prefix + child_label)
        deeper = render_tree(child)[1:]
        indent = "    " if last else "│   "
        lines.extend(indent + line for line in deeper)
    return lines


def client_nodes(items: list[dict]) -> list[tuple[str, list]]:
    return [
        (
            f"{item['display_label']} ({item['client_id'][:17]}…)"
            f" {mark(item.get('status'))} -- seen {item.get('last_seen_at') or 'never'}",
            [],
        )
        for item in items
    ]


def main() -> None:
    capabilities = fetch("/api/v1/system/capabilities")
    gateway = fetch("/api/v1/gateway/status")
    clients = fetch("/api/v1/clients")

    app_state = gateway["application"]["state"]
    hotspot_state = gateway["hotspot"]["state"]
    windows_state = gateway["windows_host"]["state"]
    lab_state = gateway["linux_lab"]["state"]

    lab_clients = [
        item for item in clients.get("clients", [])
        if item.get("environment") == "simulated_lab"
    ]
    hotspot_clients = [
        item for item in clients.get("clients", [])
        if item.get("environment") == "physical_host"
    ]

    probe_state = capabilities.get("latency_probe_state", "unknown")
    lab_ingest_state = capabilities.get("lab_ingest_state", "unknown")

    # --- build the tree ---------------------------------------------------

    eb_children: list = []

    # Hotspot hosted by the EB device: where phones and other devices attach.
    hotspot_children = client_nodes(hotspot_clients)
    if hotspot_state != "missing":
        eb_children.append((
            render(
                "Hotspot (devices connected here)",
                hotspot_state,
                f"hotspot source state {hotspot_state}"
                f"{quality(gateway['hotspot']['data_quality'])}",
            ),
            hotspot_children,
        ))
    else:
        note = (
            "hosted on the Windows host NIC; not visible from this backend VM"
            if not capabilities.get("windows_collectors_supported")
            else f"Windows hotspot collector state {windows_state}"
        )
        eb_children.append((
            render("Hotspot (devices connected here)", hotspot_state, note),
            hotspot_children,
        ))

    # Windows host aggregate collector (when the platform supports it).
    if capabilities.get("windows_collectors_supported"):
        eb_children.append((
            render(
                "Windows host collector",
                windows_state,
                quality(gateway["windows_host"]["data_quality"]),
            ),
            [],
        ))

    # Linux namespace lab (simulated clients) when present.
    eb_children.append((
        render(
            "Linux namespace lab",
            lab_state,
            f"ingest {lab_ingest_state}"
            f"{quality(gateway['linux_lab']['data_quality'])}",
        ),
        client_nodes(lab_clients),
    ))

    # Root: the Wi-Fi router. The backend infers the uplink from the
    # application node's derived evidence; it is never claimed as measured.
    uplink = (
        "uplink reachable via the host connection"
        if app_state == "online"
        else "uplink state unknown"
    )
    tree = (
        f"Wi-Fi Router (Internet uplink) [inferred] -- {uplink}",
        [
            (
                render(
                    "Experience Budget device (backend + API)",
                    app_state,
                    f"API online at {API_BASE}, application node {app_state}"
                    f"{quality(gateway['application']['data_quality'])}"
                    f" (probe {probe_state}, lab ingest {lab_ingest_state})",
                ),
                eb_children,
            )
        ],
    )

    print()
    for line in render_tree(tree):
        print(line)
    print()

    message = clients.get("message")
    if message and not clients.get("count"):
        print(f"Note: {message}")
    if not clients.get("count"):
        print(
            "Note: no devices are connected to this backend's visible sources.\n"
            "      The hotspot your phone joins is hosted by the Windows host\n"
            "      NIC; run the backend there or attach a USB Wi-Fi adapter in\n"
            "      AP mode to this machine."
        )
    print()


if __name__ == "__main__":
    main()
