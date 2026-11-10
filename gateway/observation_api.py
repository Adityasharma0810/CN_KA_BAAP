"""Authenticated read-only API for Linux namespace-lab observations."""

from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.schemas import TelemetryObservation
from backend.app.services.lab_accounting_service import lab_accounting_service


class ObservationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    observed_at: datetime
    observations: list[TelemetryObservation] = Field(min_length=1, max_length=100)


def _require_bearer_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("EB_GATEWAY_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="gateway_authentication_not_configured")
    scheme, separator, supplied = (authorization or "").partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not supplied
        or not hmac.compare_digest(supplied, expected)
    ):
        raise HTTPException(
            status_code=401,
            detail="gateway_authentication_failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


app = FastAPI(
    title="Experience Budget Linux Observation Agent",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get(
    "/api/v1/observations/current",
    response_model=ObservationResponse,
    dependencies=[Depends(_require_bearer_token)],
)
def current_observations() -> ObservationResponse:
    try:
        collection = lab_accounting_service.collect()
        if not collection.get("available"):
            raise HTTPException(
                status_code=503,
                detail="gateway_lab_unavailable",
            )
        observations = [
            TelemetryObservation.model_validate(client["observation"])
            for client in collection["clients"]
        ]
        client_ids = [
            observation.metadata.client_id
            for observation in observations
        ]
        if (
            not observations
            or any(client_id is None for client_id in client_ids)
            or len(set(client_ids)) != len(client_ids)
            or any(
                observation.metadata.scope != "client"
                or observation.metadata.source != "linux_namespace_lab"
                or observation.metadata.environment != "simulated_lab"
                for observation in observations
            )
        ):
            raise ValueError("invalid anonymous client inventory")
    except HTTPException:
        raise
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=503,
            detail="gateway_observation_unavailable",
        ) from None

    observed_at = max(
        observation.metadata.observed_at
        for observation in observations
    ).astimezone(timezone.utc)
    return ObservationResponse(
        version=1,
        observed_at=observed_at,
        observations=observations,
    )
