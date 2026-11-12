"""Agent WebSocket endpoint.

The local gateway agent initiates an outbound authenticated WebSocket connection
to the cloud control plane. The frontend never connects directly to the agent.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status

from backend.app.api.v1.deps import get_current_user
from backend.app.core.security import decode_token

_LOGGER = logging.getLogger(__name__)

router = APIRouter()

# Active agent sessions keyed by gateway_id.
_agent_sessions: dict[str, WebSocket] = {}


@router.websocket("/agent/connect")
async def agent_connect(
    websocket: WebSocket,
    token: str = Query(...),
    gateway_id: str = Query(...),
):
    try:
        payload = decode_token(token)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if payload.get("type") != "access":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    _agent_sessions[gateway_id] = websocket
    _LOGGER.info("gateway agent connected: %s", gateway_id)
    try:
        while True:
            message = await websocket.receive_text()
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"error": "invalid_json"}))
                continue
            msg_type = data.get("type")
            if msg_type == "heartbeat":
                await websocket.send_text(
                    json.dumps({"type": "heartbeat_ack", "gateway_id": gateway_id})
                )
            elif msg_type == "telemetry":
                # Persisted elsewhere; acknowledge receipt.
                await websocket.send_text(
                    json.dumps({"type": "telemetry_ack", "gateway_id": gateway_id})
                )
            elif msg_type == "command_ack":
                _LOGGER.info("command acknowledgement from %s: %s", gateway_id, data.get("command_id"))
            else:
                await websocket.send_text(json.dumps({"type": "unknown_message", "received": msg_type}))
    except WebSocketDisconnect:
        pass
    finally:
        _agent_sessions.pop(gateway_id, None)
        _LOGGER.info("gateway agent disconnected: %s", gateway_id)


@router.get("/agent/sessions")
async def agent_sessions(user = Depends(get_current_user)):
    return {"connected_gateways": list(_agent_sessions.keys())}


def get_agent_session(gateway_id: str) -> Optional[WebSocket]:
    return _agent_sessions.get(gateway_id)


async def send_agent_command(gateway_id: str, command: dict) -> bool:
    """Send a structured, allow-listed command to a connected agent."""
    session = _agent_sessions.get(gateway_id)
    if session is None:
        return False
    try:
        await session.send_text(json.dumps(command))
        return True
    except Exception:
        _agent_sessions.pop(gateway_id, None)
        return False
