"""Secure outbound communication with the cloud control plane.

The gateway agent initiates an authenticated WebSocket connection. The frontend
never connects directly to the agent; all traffic goes through the control plane.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

import websockets

_LOGGER = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentConnection:
    """Authenticated, outbound WebSocket session to the control plane.

    Implements bounded exponential backoff reconnection, heartbeat, command
    allow-listing, telemetry streaming, and offline buffering hooks.
    """

    ALLOWED_COMMANDS = {
        "apply_policy",
        "get_status",
        "set_sampling_interval",
        "set_enforcement_mode",
        "rollback",
        "discover_clients",
    }

    def __init__(
        self,
        *,
        control_plane_url: str,
        gateway_id: str,
        agent_token: str,
        on_command: Callable[[dict], Any] | None = None,
        on_telemetry_ack: Callable[[dict], Any] | None = None,
        max_backoff_seconds: float = 60.0,
        base_backoff_seconds: float = 1.0,
        heartbeat_interval: float = 30.0,
    ) -> None:
        self.control_plane_url = control_plane_url.rstrip("/")
        self.gateway_id = gateway_id
        self.agent_token = agent_token
        self.on_command = on_command
        self.on_telemetry_ack = on_telemetry_ack
        self.max_backoff_seconds = max_backoff_seconds
        self.base_backoff_seconds = base_backoff_seconds
        self.heartbeat_interval = heartbeat_interval

        self._ws = None
        self._connected = False
        self._running = False
        self._backoff = base_backoff_seconds
        self._task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._version = "0.8.0"

    @property
    def connected(self) -> bool:
        return self._connected and self._ws is not None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run(), name="agent-connection")

    async def stop(self) -> None:
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._task:
            self._task.cancel()
        if self._ws:
            await self._ws.close()

    async def _run(self) -> None:
        while self._running:
            try:
                await self._connect_and_run()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # keep retrying
                _LOGGER.exception("connection error: %s", exc)
            if not self._running:
                break
            await self._wait_backoff()

    async def _connect_and_run(self) -> None:
        ws_url = f"{self.control_plane_url.replace('http', 'ws')}/api/v1/agent/connect"
        params = {"gateway_id": self.gateway_id, "token": self.agent_token}
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{ws_url}?{query}"
        async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
            self._ws = ws
            self._connected = True
            self._backoff = self.base_backoff_seconds
            _LOGGER.info("gateway %s connected to control plane", self.gateway_id)
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name="agent-heartbeat")
            try:
                async for message in ws:
                    await self._handle_message(message)
            finally:
                self._heartbeat_task.cancel()
                self._connected = False
                self._ws = None

    async def _wait_backoff(self) -> None:
        delay = min(self._backoff, self.max_backoff_seconds)
        _LOGGER.info("reconnecting in %.1fs", delay)
        self._backoff = min(self._backoff * 2, self.max_backoff_seconds)
        await asyncio.sleep(delay)

    async def _heartbeat_loop(self) -> None:
        while self._running and self._connected:
            await asyncio.sleep(self.heartbeat_interval)
            await self.send({"type": "heartbeat", "gateway_id": self.gateway_id, "version": self._version})

    async def _handle_message(self, message: str) -> None:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            await self.send({"type": "error", "error": "invalid_json"})
            return
        msg_type = data.get("type")
        if msg_type == "heartbeat_ack":
            return
        if msg_type == "command":
            command_id = data.get("command_id")
            command = data.get("command")
            if command not in self.ALLOWED_COMMANDS:
                await self.send({"type": "command_reject", "command_id": command_id, "reason": "command_not_allowed"})
                return
            if self.on_command:
                try:
                    result = await self.on_command(data)
                    await self.send({"type": "command_ack", "command_id": command_id, "result": result})
                except Exception as exc:
                    _LOGGER.exception("command failed")
                    await self.send({"type": "command_ack", "command_id": command_id, "error": str(exc)})
        else:
            await self.send({"type": "unknown_message", "received": msg_type})

    async def send(self, payload: dict) -> bool:
        if not self._connected or self._ws is None:
            return False
        try:
            await self._ws.send(json.dumps(payload))
            return True
        except Exception:
            self._connected = False
            return False

    async def send_telemetry(self, observations: list[dict]) -> bool:
        return await self.send(
            {
                "type": "telemetry",
                "gateway_id": self.gateway_id,
                "timestamp": _utc_now().isoformat(),
                "observations": observations,
            }
        )
