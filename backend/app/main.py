"""Experience Budget API entry point."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.clients import router as clients_router
from backend.app.api.monitoring import router as monitoring_router
from backend.app.api.topology import router as topology_router
from backend.app.api.v1 import router as observation_router
from backend.app.config import (
    gateway_url,
    gateway_token,
    gateway_timeout_seconds,
)
from backend.app.services.gateway_ingest_service import GatewayIngestService
from backend.app.services.gateway_transport_service import GatewayTransport
from backend.app.services.lab_ingest_service import lab_ingest_service
from backend.app.services.latency_probe_service import latency_probe_service
from backend.app.services.scenario_service import scenario_service


gateway_ingest_service: GatewayIngestService | None = None


def _allowed_origins() -> list[str]:
    defaults = {
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    }
    configured = os.environ.get("EB_CORS_ORIGINS", "")
    return sorted(
        defaults
        | {
            origin.strip().rstrip("/")
            for origin in configured.split(",")
            if origin.strip()
        }
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Run the optional Linux lab ingester and gateway ingester for the life of the API."""

    latency_probe_service.start()
    lab_ingest_service.start()

    global gateway_ingest_service
    gateway_ingest_service = None
    if os.environ.get("EB_GATEWAY_URL"):
        transport = GatewayTransport(
            base_url=gateway_url(),
            token=gateway_token(),
            timeout_seconds=gateway_timeout_seconds(),
        )
        gateway_ingest_service = GatewayIngestService(transport=transport)
        gateway_ingest_service.start()

    try:
        yield
    finally:
        await scenario_service.shutdown()
        await lab_ingest_service.stop()
        await latency_probe_service.stop()
        if gateway_ingest_service is not None:
            await gateway_ingest_service.stop()


app = FastAPI(
    title="Experience Budget",
    description="Privacy-preserving household network monitoring",
    version="0.7.0",
    lifespan=lifespan,
)

# Allow the local React development server to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(clients_router)
app.include_router(monitoring_router)
app.include_router(topology_router)
app.include_router(observation_router)


@app.get("/")
def root():
    return {
        "project": "Experience Budget",
        "version": "0.7.0",
        "mode": "baseline_monitoring",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "experience-budget",
    }