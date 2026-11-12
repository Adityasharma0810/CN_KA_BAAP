"""Versioned, product-facing observation API.

Legacy ``/api/v1/monitoring/*`` routes remain in
``backend/app/api/monitoring.py`` for compatibility. New product routes are
added here and share typed response models. All control-plane routes are
mounted once under the single ``/api/v1`` prefix.
"""

from fastapi import APIRouter

from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.capacity import router as capacity_router
from backend.app.api.v1.classification import router as classification_router
from backend.app.api.v1.decisions import router as decisions_router
from backend.app.api.v1.devices import router as devices_router
from backend.app.api.v1.diagnosis import router as diagnosis_router
from backend.app.api.v1.experiments import router as experiments_router
from backend.app.api.v1.forecasts import router as forecasts_router
from backend.app.api.v1.gateways import router as gateways_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.intents import router as intents_router
from backend.app.api.v1.model_registry import router as model_registry_router
from backend.app.api.v1.multiwan import router as multiwan_router
from backend.app.api.v1.observations import router as observations_router
from backend.app.api.v1.policy import router as policy_router
from backend.app.api.v1.qoe import router as qoe_router
from backend.app.api.v1.schedules import router as schedules_router
from backend.app.api.v1.scenarios import router as scenarios_router
from backend.app.api.v1.simulation import router as simulation_router
from backend.app.api.v1.system import router as system_router
from backend.app.api.v1.verification import router as verification_router
from backend.app.api.v1.websocket import router as websocket_router


router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
router.include_router(observations_router)
router.include_router(system_router)
router.include_router(scenarios_router)
router.include_router(qoe_router)
# Control-plane routes (each mounted once).
router.include_router(auth_router)
router.include_router(gateways_router)
router.include_router(devices_router)
router.include_router(intents_router)
router.include_router(policy_router)
router.include_router(verification_router)
router.include_router(decisions_router)
router.include_router(capacity_router)
router.include_router(forecasts_router)
router.include_router(classification_router)
router.include_router(model_registry_router)
router.include_router(schedules_router)
router.include_router(diagnosis_router)
router.include_router(multiwan_router)
router.include_router(experiments_router)
router.include_router(simulation_router)
router.include_router(websocket_router)
