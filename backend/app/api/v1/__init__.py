"""Versioned, product-facing observation API.

Legacy ``/api/v1/monitoring/*`` routes remain in
``backend/app/api/monitoring.py`` for compatibility. New product routes are
added here and share typed response models.
"""

from fastapi import APIRouter

from backend.app.api.v1.observations import router as observations_router


router = APIRouter(prefix="/api/v1")
router.include_router(observations_router)
