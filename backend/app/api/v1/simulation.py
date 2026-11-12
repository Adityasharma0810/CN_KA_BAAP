"""Simulation namespace endpoints. All simulation data carries
``environment=simulated_lab`` and is never merged into production telemetry."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/simulation/capabilities")
async def simulation_capabilities():
    return {
        "available": True,
        "environment": "simulated_lab",
        "supported_traffic_classes": ["call", "gaming", "streaming", "bulk"],
        "supported_impairments": ["bandwidth", "latency", "jitter", "packet_loss"],
        "note": "Isolated virtual lab; synthetic data only.",
    }
