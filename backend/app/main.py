"""Experience Budget API entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.monitoring import router as monitoring_router
from backend.app.api.v1 import router as observation_router


app = FastAPI(
    title="Experience Budget",
    description="Privacy-preserving household network monitoring",
    version="0.7.0",
)

# Allow the local React development server to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(monitoring_router)
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