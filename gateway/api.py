"""HTTP API exposing live per-client speeds."""
import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from gateway.collector import CLIENTS, INTERVAL, anon_ids, read_bytes

speeds = {
    c: {"id": anon_ids[c], "down_mbps": 0.0, "up_mbps": 0.0} for c in CLIENTS
}


async def sample_loop() -> None:
    prev = {c: read_bytes(c) for c in CLIENTS}
    prev_t = time.monotonic()
    while True:
        await asyncio.sleep(INTERVAL)
        now = time.monotonic()
        dt = now - prev_t
        for c in CLIENTS:
            down, up = read_bytes(c)
            speeds[c]["down_mbps"] = round((down - prev[c][0]) * 8 / dt / 1e6, 1)
            speeds[c]["up_mbps"] = round((up - prev[c][1]) * 8 / dt / 1e6, 1)
            prev[c] = (down, up)
        prev_t = now


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(sample_loop())
    yield
    task.cancel()


app = FastAPI(title="Experience Budget Gateway", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/clients")
def clients():
    return list(speeds.values())