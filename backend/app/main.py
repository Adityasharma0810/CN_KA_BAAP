
"""Experience Budget API entry point."""

from fastapi import FastAPI

from backend.app.api.monitoring import router as monitoring_router


app = FastAPI(
    title="Experience Budget",
    description="Privacy-preserving household network monitoring",
    version="0.6.0",
)

app.include_router(monitoring_router)


@app.get("/")
def root():
    return {
        "project": "Experience Budget",
        "version": "0.6.0",
        "mode": "baseline_monitoring",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "experience-budget",
    }
