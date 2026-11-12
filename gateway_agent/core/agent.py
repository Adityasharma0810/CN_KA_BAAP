"""Main gateway agent orchestrator.

Ties together: platform adapter, telemetry collection, ML inference, policy
engine, enforcement, offline buffering, and the control-plane connection.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from gateway_agent.communication.agent_connection import AgentConnection
from gateway_agent.core.config import AgentConfig
from gateway_agent.core.interfaces import Observation
from gateway_agent.ml_runtime.models import FlowClassifier, KalmanCapacityEstimator
from gateway_agent.ml_runtime.qoe import score_call, score_game, score_stream, score_bulk
from gateway_agent.security.auth import load_agent_token
from gateway_agent.services.offline_buffer import OfflineBuffer
from gateway_agent.traffic_control.policy_engine import DeviceDemand, optimize

_LOGGER = logging.getLogger("experience-budget-agent")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GatewayAgent:
    def __init__(self, config: AgentConfig, adapter) -> None:
        self.config = config
        self.adapter = adapter
        self.classifier = FlowClassifier()
        self.estimator = KalmanCapacityEstimator()
        self.buffer = OfflineBuffer(config.offline_buffer_path)
        self._last_sample_time: float | None = None
        self._client_rate_history: dict[str, list[float]] = {}
        self._connection: AgentConnection | None = None
        self._running = False
        self._capabilities: dict[str, Any] = {}

    async def start(self) -> None:
        self._running = True
        _LOGGER.info("Experience Budget gateway agent v0.8.0 starting on %s", self.adapter.platform)
        # Detect capabilities honestly.
        self._capabilities = self.adapter.detect_capabilities() if hasattr(self.adapter, "detect_capabilities") else {}
        _LOGGER.info("Capabilities: %s", json.dumps(self._capabilities.to_dict() if hasattr(self._capabilities, 'to_dict') else self._capabilities))

        # Enable IP forwarding / NAT if configured and supported.
        if self.config.enable_ip_forwarding:
            ok = await self.adapter.enable_ip_forwarding()
            _LOGGER.info("IP forwarding: %s", ok)
        if self.config.enable_nat:
            ok = await self.adapter.enable_nat()
            _LOGGER.info("NAT: %s", ok)

        # Connect to control plane.
        token = load_agent_token()
        if self.config.is_configured() and token:
            self._connection = AgentConnection(
                control_plane_url=self.config.control_plane_url,
                gateway_id=self.config.gateway_id,
                agent_token=token,
                on_command=self._handle_command,
            )
            await self._connection.start()
        else:
            _LOGGER.warning("Control plane not configured; running in local-only mode")

        await self._run_loop()

    async def stop(self) -> None:
        self._running = False
        if self._connection:
            await self._connection.stop()
        self.buffer.close()
        _LOGGER.info("Gateway agent stopped")

    async def _run_loop(self) -> None:
        sample_interval = max(self.config.sampling_interval_seconds, 1)
        ml_cycle = max(self.config.ml_cycle_seconds, 5)
        next_ml = time.monotonic() + ml_cycle

        while self._running:
            loop_start = time.monotonic()
            await self._collect_and_infer()
            # ML cycle (30s) runs independently of high-frequency sampling.
            if time.monotonic() >= next_ml:
                await self._ml_cycle()
                next_ml = time.monotonic() + ml_cycle
            # Sleep until next sample, but never block shutdown.
            elapsed = time.monotonic() - loop_start
            await asyncio.sleep(max(0, sample_interval - elapsed))

    async def _collect_and_infer(self) -> None:
        observations = await self.adapter.collect_observations()
        now = time.monotonic()
        elapsed = now - (self._last_sample_time or now)
        self._last_sample_time = now

        # Enrich with per-client data and QoE.
        clients = await self.adapter.discover_clients()
        enriched: list[dict[str, Any]] = []
        for obs in observations:
            d = obs.to_dict()
            d["gateway_id"] = self.config.gateway_id
            enriched.append(d)

        # Per-client QoE from observations.
        for client in clients:
            cid = client.client_id
            rates = self._client_rate_history.setdefault(cid, [])
            if client.download_rate_mbps is not None:
                rates.append(client.download_rate_mbps)
                if len(rates) > 5:
                    rates.pop(0)
            # Pick a QoE scorer based on traffic class (unknown -> bulk-safe).
            tc = (client_traffic_class := "bulk")
            qoe = score_bulk(client.download_rate_mbps, None, 1)
            enriched.append({
                "timestamp": _utc_now().isoformat(),
                "source": "linux_gateway",
                "scope": "client",
                "environment": "physical_host",
                "quality": "measured",
                "client_id": cid,
                "gateway_id": self.config.gateway_id,
                "download_mbps": client.download_rate_mbps,
                "upload_mbps": client.upload_rate_mbps,
                "download_bytes": client.download_bytes,
                "upload_bytes": client.upload_bytes,
                "qoe": qoe.score,
                "qoe_band": qoe.band,
                "traffic_class": tc,
            })

        # Capacity estimator from aggregate download.
        for obs in observations:
            if obs.download_mbps is not None:
                self.estimator.update(obs.download_mbps, elapsed)
                break

        # Send telemetry.
        if self._connection and self._connection.connected:
            ok = await self._connection.send_telemetry(enriched)
            if not ok:
                self.buffer.add(self.config.gateway_id, enriched)
        else:
            self.buffer.add(self.config.gateway_id, enriched)
            self._replay_buffer()

    def _replay_buffer(self) -> None:
        # Best-effort replay of buffered observations once connected.
        if not self._connection or not self._connection.connected:
            return
        count = self.buffer.count_unsent(self.config.gateway_id)
        if count == 0:
            return
        entries = self.buffer.unsent(self.config.gateway_id, limit=200)
        ids = [eid for eid, _ in entries]
        payloads = [json.loads(p) for _, p in entries]
        all_obs = [o for p in payloads for o in p.get("observations", [])]
        # Fire-and-forget; mark sent regardless to avoid unbounded growth.
        asyncio.create_task(self._send_and_mark(ids, all_obs))

    async def _send_and_mark(self, ids: list[int], observations: list[dict]) -> None:
        ok = await self._connection.send_telemetry(observations) if self._connection else False
        if ok:
            self.buffer.mark_sent(ids)

    async def _ml_cycle(self) -> None:
        """30-second ML evaluation cycle. Does not retrain."""
        est = self.estimator.estimate()
        _LOGGER.info("ML cycle: capacity=%.3f Mbps uncertainty=%.3f confidence=%.2f",
                     est.get("download_capacity_mbps"), est.get("uncertainty_mbps"), est.get("confidence"))

    async def _handle_command(self, command: dict) -> dict:
        """Allow-listed command handler invoked by the control plane."""
        cmd = command.get("command")
        if cmd == "get_status":
            return {
                "gateway_id": self.config.gateway_id,
                "capabilities": self._capabilities,
                "estimator": self.estimator.estimate(),
                "classifier_trained": self.classifier.trained,
            }
        if cmd == "rollback":
            ok = await self.adapter.rollback()
            return {"rollback": ok}
        if cmd == "apply_policy":
            allocations = command.get("allocations", {})
            return await self.adapter.apply_policy(allocations)
        return {"error": "unknown_command"}


def load_config() -> AgentConfig:
    return AgentConfig()


def pick_adapter(platform: str | None, config: AgentConfig):
    from gateway_agent.adapters.linux.adapter import LinuxAdapter
    from gateway_agent.adapters.windows.adapter import WindowsAdapter
    from gateway_agent.adapters.macos.adapter import MacOSAdapter
    from gateway_agent.adapters.openwrt.adapter import OpenWrtAdapter

    platform = platform or ("linux" if hasattr(__import__("sys").platform, "startwith") else "linux")
    import sys as _sys
    p = _sys.platform
    if p.startswith("linux"):
        return LinuxAdapter(config)
    if p in ("win32", "cygwin"):
        return WindowsAdapter(config)
    if p == "darwin":
        return MacOSAdapter(config)
    # Default: Linux adapter.
    return LinuxAdapter(config)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()
    adapter = pick_adapter(None, config)
    agent = GatewayAgent(config, adapter)
    try:
        await agent.start()
    except asyncio.CancelledError:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
