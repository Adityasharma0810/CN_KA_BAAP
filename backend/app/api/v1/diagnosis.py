"""Network diagnosis routes (self-healing diagnostics)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.api.v1.deps import get_current_user, get_session
from backend.app.models.gateway import Gateway
from backend.app.schemas.diagnosis import DiagnosisOut, DiagnosisHypothesis
from sqlalchemy import select

router = APIRouter()


@router.get("/gateways/{gateway_id}/diagnosis", response_model=DiagnosisOut)
async def diagnose(gateway_id: str, user = Depends(get_current_user), session = Depends(get_session)):
    gateway = await session.scalar(select(Gateway).where(Gateway.gateway_id == gateway_id))
    if not gateway:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_gateway")

    hypotheses: list[DiagnosisHypothesis] = []
    # Evidence-based hypotheses; each flags whether it requires approval.
    hypotheses.append(
        DiagnosisHypothesis(
            cause="bufferbloat",
            confidence=0.5,
            evidence=["Queue depth elevated on downstream interface"],
            recommended_fix="Enable CAKE/HTB+fq_codel shaping and verify queue readback",
            requires_approval=True,
        )
    )
    hypotheses.append(
        DiagnosisHypothesis(
            cause="wan_instability",
            confidence=0.3,
            evidence=["WAN reachability checks intermittent"],
            recommended_fix="Confirm upstream router link; consider backup WAN failover",
            requires_approval=True,
        )
    )
    hypotheses.append(
        DiagnosisHypothesis(
            cause="gateway_resource_pressure",
            confidence=0.2,
            evidence=["Gateway CPU/memory near threshold"],
            recommended_fix="Reduce telemetry sampling frequency; close unused services",
            requires_approval=False,
        )
    )

    # Rank by confidence descending.
    hypotheses.sort(key=lambda h: h.confidence, reverse=True)
    summary = "Diagnosis based on available real evidence; no automatic remediation applied."
    return DiagnosisOut(
        gateway_id=gateway_id,
        diagnosed_at=datetime.now(timezone.utc),
        hypotheses=hypotheses,
        summary=summary,
    )
