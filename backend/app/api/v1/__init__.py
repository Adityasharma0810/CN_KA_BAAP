"""Versioned, product-facing observation API.

Legacy ``/api/v1/monitoring/*`` routes remain in
``backend/app/api/monitoring.py`` for compatibility. New product routes are
added here and share typed response models.
"""

from fastapi import APIRouter

from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.observations import router as observations_router
from backend.app.api.v1.qoe import router as qoe_router
from backend.app.api.v1.scenarios import router as scenarios_router
from backend.app.api.v1.system import router as system_router


router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
router.include_router(observations_router)
router.include_router(system_router)
router.include_router(scenarios_router)
router.include_router(qoe_router)
