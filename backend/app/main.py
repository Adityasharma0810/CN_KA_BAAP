from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Network Baseline Monitor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": "Network Baseline Monitor API is running",
        "scope": "local_aggregate_only",
    }


@app.get("/api/health")
def health():
    return {"status": "healthy"}