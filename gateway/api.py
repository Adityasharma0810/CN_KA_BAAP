"""HTTP API: live per-client speeds, manual limits, and the policy loop."""
import asyncio
import subprocess
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from gateway.collector import CLIENTS, INTERVAL, anon_ids, read_bytes
from gateway.controller import decide
from gateway.policy import DEFAULT_INTENT, INTENT_WEIGHTS

HELPER = "/usr/local/sbin/eb-limit-client"
POLICY_INTERVAL = 3.0

speeds = {
    c: {"id": anon_ids[c], "down_mbps": 0.0, "up_mbps": 0.0} for c in CLIENTS
}
limits = {c: None for c in CLIENTS}
intents = {c: DEFAULT_INTENT for c in CLIENTS}
policy = {"enabled": False, "budget_mbps": 100}


class LimitRequest(BaseModel):
    down_mbps: int = Field(ge=1, le=1000)
    up_mbps: int | None = Field(default=None, ge=1, le=1000)


class IntentRequest(BaseModel):
    intent: str


class PolicyRequest(BaseModel):
    enabled: bool
    budget_mbps: int = Field(default=100, ge=1, le=10000)


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


def set_down_limit(c: int, target) -> None:
    """Apply (or remove) a download-only limit and record it."""
    if target is None:
        run_helper(c, "off")
        limits[c] = None
    else:
        run_helper(c, target)
        limits[c] = {"down_mbps": target, "up_mbps": None}


def clear_all_limits() -> None:
    for c in CLIENTS:
        try:
            set_down_limit(c, None)
        except HTTPException:
            pass


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


async def policy_loop() -> None:
    while True:
        await asyncio.sleep(POLICY_INTERVAL)
        if not policy["enabled"]:
            continue
        try:
            measured = {c: speeds[c]["down_mbps"] for c in CLIENTS}
            current = {
                c: limits[c]["down_mbps"] if limits[c] else None for c in CLIENTS
            }
            targets = decide(policy["budget_mbps"], measured, current, intents)
            for c, target in targets.items():
                if target != current[c]:
                    await asyncio.to_thread(set_down_limit, c, target)
        except Exception as e:  # keep the loop alive no matter what
            print(f"policy loop error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(clear_all_limits)  # start clean
    tasks = [
        asyncio.create_task(sample_loop()),
        asyncio.create_task(policy_loop()),
    ]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Experience Budget Gateway", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/clients")
def clients():
    return [
        {**speeds[c], "intent": intents[c], "limit": limits[c]} for c in CLIENTS
    ]


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


@app.post("/clients/{n}/intent")
def set_intent(n: int, body: IntentRequest):
    if n not in CLIENTS:
        raise HTTPException(404, "Unknown client")
    if body.intent not in INTENT_WEIGHTS:
        raise HTTPException(422, f"intent must be one of {sorted(INTENT_WEIGHTS)}")
    intents[n] = body.intent
    return {"client": n, "intent": body.intent}


@app.get("/policy")
def get_policy():
    return {**policy, "intents": intents, "limits": limits}


@app.post("/policy")
def set_policy(body: PolicyRequest):
    policy["enabled"] = body.enabled
    policy["budget_mbps"] = body.budget_mbps
    if not body.enabled:
        clear_all_limits()
    return policy