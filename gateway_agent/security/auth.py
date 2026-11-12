"""Security helpers for the gateway agent.

- Load agent token from environment only (never committed).
- Verify control-plane JWT-like bearer tokens.
- Sign outbound messages for integrity (HMAC).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any

AGENT_TOKEN_ENV = "EB_AGENT_TOKEN"
CONTROL_PLANE_TOKEN_ENV = "EB_CONTROL_PLANE_TOKEN"


def load_agent_token() -> str | None:
    return os.environ.get(AGENT_TOKEN_ENV) or None


def load_control_plane_token() -> str | None:
    return os.environ.get(CONTROL_PLANE_TOKEN_ENV) or None


def sign_message(secret: str, payload: dict[str, Any]) -> str:
    """Return an HMAC-SHA256 signature over a canonical JSON payload."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def verify_signature(secret: str, payload: dict[str, Any], signature: str, tolerance_seconds: int = 300) -> bool:
    expected = sign_message(secret, payload)
    if not hmac.compare_digest(expected, signature):
        return False
    # Replay protection: timestamp must be recent.
    ts = payload.get("timestamp")
    if ts is None:
        return False
    try:
        ts_float = float(ts)
    except (TypeError, ValueError):
        return False
    if abs(time.time() - ts_float) > tolerance_seconds:
        return False
    return True
