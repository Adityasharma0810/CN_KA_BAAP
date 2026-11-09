"""User-triggered, bounded Scenario Lab API."""

from fastapi import APIRouter, HTTPException, Path

from backend.app.models.scenario_schemas import (
    ScenarioCatalogResponse,
    ScenarioId,
    ScenarioStartRequest,
    ScenarioStartResponse,
    ScenarioStatusResponse,
)
from backend.app.services.scenario_service import (
    ScenarioServiceError,
    scenario_service,
)


router = APIRouter(tags=["Scenario Lab"])


def _raise(error: ScenarioServiceError) -> None:
    detail = {"code": error.code}
    if error.code == "helper_missing":
        detail["install_command"] = "sudo bash scripts/privileged/install_eb_priv.sh"
    raise HTTPException(status_code=error.status_code, detail=detail) from error


@router.get("/scenarios", response_model=ScenarioCatalogResponse)
def scenario_catalog() -> ScenarioCatalogResponse:
    return ScenarioCatalogResponse(
        scenarios=scenario_service.catalogue(),
        status=scenario_service.status(),
    )


@router.post(
    "/scenarios/{scenario_id}/start",
    response_model=ScenarioStartResponse,
    status_code=202,
)
async def start_scenario(
    scenario_id: ScenarioId = Path(),
    body: ScenarioStartRequest = ScenarioStartRequest(),
) -> ScenarioStartResponse:
    try:
        status = await scenario_service.start(
            scenario_id,
            duration_seconds=body.duration_seconds,
            seed=body.seed,
        )
    except ScenarioServiceError as error:
        _raise(error)
    return ScenarioStartResponse(status=status)


@router.post("/scenarios/stop", response_model=ScenarioStatusResponse)
async def stop_scenario() -> ScenarioStatusResponse:
    return await scenario_service.stop()


@router.get("/scenarios/status", response_model=ScenarioStatusResponse)
def scenario_status() -> ScenarioStatusResponse:
    return scenario_service.status()
