"""HTTP API exposing live per-client speeds and bandwidth limits."""
import asyncio
import subprocess
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from gateway.collector import CLIENTS, INTERVAL, anon_ids, read_bytes

HELPER = "/usr/local/sbin/eb-limit-client"

speeds = {
    c: {"id": anon_ids[c], "down_mbps": 0.0, "up_mbps": 0.0} for c in CLIENTS
}
limits = {c: None for c in CLIENTS}


class LimitRequest(BaseModel):
    down_mbps: int = Field(ge=1, le=1000)
    up_mbps: int | None = Field(default=None, ge=1, le=1000)


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


def run_helper(*args) -> None:
    """Run the root-owned limit helper through sudo (no password prompt)."""
    result = subprocess.run(
        ["sudo", "-n", HELPER, *map(str, args)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise HTTPException(500, result.stderr.strip() or "limit command failed")


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
    return [{**speeds[c], "limit": limits[c]} for c in CLIENTS]


@app.post("/clients/{n}/limit")
def set_limit(n: int, body: LimitRequest):
    if n not in CLIENTS:
        raise HTTPException(404, "Unknown client")
    args = [n, body.down_mbps] + ([body.up_mbps] if body.up_mbps else [])
    run_helper(*args)
    limits[n] = {"down_mbps": body.down_mbps, "up_mbps": body.up_mbps}
    return {"client": n, "limit": limits[n]}


@app.delete("/clients/{n}/limit")
def clear_limit(n: int):
    if n not in CLIENTS:
        raise HTTPException(404, "Unknown client")
    run_helper(n, "off")
    limits[n] = None
    return {"client": n, "limit": None}