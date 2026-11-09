"""Versioned, product-facing observation API.

Legacy ``/api/v1/monitoring/*`` routes remain in
``backend/app/api/monitoring.py`` for compatibility. New product routes are
added here and share typed response models.
"""

from fastapi import APIRouter

from backend.app.api.v1.health import router as health_router


router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
