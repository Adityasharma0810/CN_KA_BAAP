"""Experience Budget Gateway Agent - standalone local agent.

This agent runs on the computer/router that manages household traffic. It is
independently executable and does not require the full development repository.

Responsibilities:
- Interface discovery
- Access point management (where supported)
- IP forwarding & NAT
- Per-client accounting & device discovery
- ML inference (classifier, capacity estimator)
- Local policy engine (max-min QoE)
- Traffic enforcement via platform adapters
- Verification & rollback
- Secure outbound WebSocket link to the cloud control plane
- Offline buffering of observations
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

AGENT_VERSION = "0.8.0"


@dataclass
class AgentConfig:
    """Configuration for the local gateway agent.

    Values come from environment variables or a config file. Secrets are never
    hardcoded.
    """

    # Control plane
    control_plane_url: str = field(
        default_factory=lambda: os.environ.get("EB_CONTROL_PLANE_URL", "https://experience-budget.example.com")
    )
    agent_token: str = field(default_factory=lambda: os.environ.get("EB_AGENT_TOKEN", ""))
    gateway_id: str = field(default_factory=lambda: os.environ.get("EB_GATEWAY_ID", ""))
    household_id: str = field(default_factory=lambda: os.environ.get("EB_HOUSEHOLD_ID", ""))

    # Networking
    wan_interface: str = field(default_factory=lambda: os.environ.get("EB_WAN_INTERFACE", ""))
    lan_interface: str = field(default_factory=lambda: os.environ.get("EB_LAN_INTERFACE", ""))
    enable_ip_forwarding: bool = field(
        default_factory=lambda: os.environ.get("EB_ENABLE_IP_FORWARDING", "true").lower() == "true"
    )
    enable_nat: bool = field(default_factory=lambda: os.environ.get("EB_ENABLE_NAT", "true").lower() == "true")

    # AP / hotspot
    ap_ssid: str = field(default_factory=lambda: os.environ.get("EB_AP_SSID", "Experience-Budget"))
    ap_password: str = field(default_factory=lambda: os.environ.get("EB_AP_PASSWORD", ""))
    ap_channel: int = field(default_factory=lambda: int(os.environ.get("EB_AP_CHANNEL", "6") or "6"))

    # Telemetry
    sampling_interval_seconds: int = field(
        default_factory=lambda: int(os.environ.get("EB_SAMPLING_INTERVAL_SECONDS", "5") or "5")
    )
    ml_cycle_seconds: int = field(
        default_factory=lambda: int(os.environ.get("EB_ML_CYCLE_SECONDS", "30") or "30")
    )
    offline_buffer_path: str = field(default_factory=lambda: os.environ.get("EB_OFFLINE_BUFFER_PATH", "data/offline_buffer.db"))

    # Safety
    safe_state_path: str = field(default_factory=lambda: os.environ.get("EB_SAFE_STATE_PATH", "data/safe_state.json"))
    enforcement_mode: str = field(default_factory=lambda: os.environ.get("EB_ENFORCEMENT_MODE", "auto"))

    def is_configured(self) -> bool:
        return bool(self.gateway_id and self.control_plane_url)
