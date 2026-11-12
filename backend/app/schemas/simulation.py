"""Simulation namespace schemas. Simulation data is isolated and never merged
into production telemetry."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScenarioRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    duration_seconds: int = Field(default=60, ge=5, le=3600)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class ScenarioRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    scenario_id: str
    state: str
    environment: str = "simulated_lab"
    started_at: datetime | None = None
    remaining_seconds: int | None = None

    model_config = ConfigDict(from_attributes=True)
