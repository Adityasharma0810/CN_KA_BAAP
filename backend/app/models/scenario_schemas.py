"""Strict, privacy-safe Scenario Lab API contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ScenarioId = Literal["call_vs_download", "wan_drop", "tvs_and_gamer"]
ScenarioState = Literal["idle", "starting", "running", "stopping", "completed", "stopped", "error"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ScenarioDefinition(StrictModel):
    id: ScenarioId
    name: str
    description: str
    duration_seconds: int = Field(ge=5, le=120)
    slots_needed: int = Field(ge=1, le=99)


class ScenarioCatalogResponse(StrictModel):
    scenarios: list[ScenarioDefinition]
    status: "ScenarioStatusResponse"


class ScenarioStartRequest(StrictModel):
    duration_seconds: int | None = Field(default=None, ge=5, le=120)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class ScenarioPhase(StrictModel):
    name: str
    at_seconds: int = Field(ge=0, le=120)
    action: str


class ScenarioStatusResponse(StrictModel):
    state: ScenarioState
    run_id: str | None = None
    scenario_id: ScenarioId | None = None
    started_at: datetime | None = None
    ends_at: datetime | None = None
    remaining_seconds: int | None = Field(default=None, ge=0)
    phases: list[ScenarioPhase] = Field(default_factory=list)
    manifest_id: str | None = None
    error_code: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{0,39}$",
    )
    install_command: str | None = None


class ScenarioStartResponse(StrictModel):
    status: ScenarioStatusResponse
