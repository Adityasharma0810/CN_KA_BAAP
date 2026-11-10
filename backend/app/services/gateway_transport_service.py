"""Authenticated, read-only transport for a Linux observation agent."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.app.models.schemas import ObservationSource, TelemetryObservation


_MAX_OBSERVATIONS = 100
_MAX_RESPONSE_BYTES = 1024 * 1024


class GatewayTransportError(RuntimeError):
    """Safe transport failure with a stable machine-readable code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class GatewayAuthenticationError(GatewayTransportError):
    def __init__(self):
        super().__init__("gateway_authentication_failed")


class GatewaySchemaError(GatewayTransportError):
    def __init__(self):
        super().__init__("gateway_schema_invalid")


class GatewayObservationResponse(BaseModel):
    """Versioned read-only response returned by the observation agent."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    version: int = Field(ge=1, le=1)
    observed_at: datetime
    observations: list[TelemetryObservation] = Field(
        min_length=1, max_length=_MAX_OBSERVATIONS
    )

    @field_validator("observed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        return value.astimezone(timezone.utc)

    @field_validator("observations")
    @classmethod
    def require_linux_observations(
        cls, value: list[TelemetryObservation]
    ) -> list[TelemetryObservation]:
        allowed = {
            ObservationSource.LINUX_GATEWAY,
            ObservationSource.LINUX_NAMESPACE_LAB,
        }
        if any(item.metadata.source not in allowed for item in value):
            raise ValueError("gateway response contains an invalid observation source")
        return value


ClientFactory = Callable[..., Any]


class GatewayTransport:
    """Fetch only the fixed read-only observation route from a configured agent."""

    path = "/api/v1/observations/current"

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout_seconds: float = 2.0,
        max_attempts: int = 3,
        backoff_seconds: float = 0.05,
        client_factory: ClientFactory = httpx.Client,
    ):
        normalized = base_url.strip().rstrip("/")
        if not normalized or any(character.isspace() for character in normalized):
            raise ValueError("gateway URL must be non-empty and contain no whitespace")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("gateway URL must use HTTP or HTTPS")
        if not 0.1 <= timeout_seconds <= 10.0:
            raise ValueError("gateway timeout must be between 0.1 and 10 seconds")
        if not 1 <= max_attempts <= 3:
            raise ValueError("gateway attempts must be between 1 and 3")
        self.base_url = normalized
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.backoff_seconds = max(0.0, min(backoff_seconds, 1.0))
        self.client_factory = client_factory

    def fetch_current(self) -> GatewayObservationResponse:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        for attempt in range(self.max_attempts):
            client = self.client_factory(timeout=self.timeout_seconds)
            try:
                response = client.get(
                    f"{self.base_url}{self.path}",
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                status = int(response.status_code)
                if status in (401, 403):
                    raise GatewayAuthenticationError()
                if status == 404:
                    raise GatewayTransportError("gateway_route_unavailable")
                if 400 <= status < 500:
                    raise GatewayTransportError("gateway_request_rejected")
                if status >= 500:
                    if attempt + 1 < self.max_attempts:
                        self._backoff(attempt)
                        continue
                    raise GatewayTransportError("gateway_service_unavailable")
                content = getattr(response, "content", None)
                if isinstance(content, bytes) and len(content) > _MAX_RESPONSE_BYTES:
                    raise GatewaySchemaError()
                try:
                    payload = response.json()
                    return GatewayObservationResponse.model_validate(payload)
                except (ValueError, TypeError, ValidationError) as error:
                    raise GatewaySchemaError() from error
            except GatewayTransportError:
                raise
            except (httpx.TimeoutException, TimeoutError) as error:
                if attempt + 1 < self.max_attempts:
                    self._backoff(attempt)
                    continue
                raise GatewayTransportError("gateway_timeout") from error
            except (httpx.RequestError, OSError) as error:
                if attempt + 1 < self.max_attempts:
                    self._backoff(attempt)
                    continue
                raise GatewayTransportError("gateway_unreachable") from error
            finally:
                close = getattr(client, "close", None)
                if close is not None:
                    close()
        raise GatewayTransportError("gateway_unreachable")

    def _backoff(self, attempt: int) -> None:
        if self.backoff_seconds:
            time.sleep(self.backoff_seconds * (2**attempt))
