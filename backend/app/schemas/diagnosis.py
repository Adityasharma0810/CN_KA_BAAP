"""Network diagnosis schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DiagnosisHypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cause: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] | None = None
    recommended_fix: str | None = None
    requires_approval: bool = False


class DiagnosisOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gateway_id: str
    diagnosed_at: datetime
    hypotheses: list[DiagnosisHypothesis]
    summary: str
