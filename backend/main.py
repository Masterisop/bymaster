"""
Roblox Join Coordinator — FastAPI Backend

Manages connected Roblox instances via HTTP polling and
broadcasts join commands through WebSocket to the web dashboard.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# ── In-memory state ──────────────────────────────────────────────────────────

connected_clients: dict[str, dict[str, Any]] = {}
# { client_id: { username, game_name, status, last_seen, pending_commands: [] } }

dashboard_sockets: list[WebSocket] = []

HEARTBEAT_TIMEOUT = 30  # seconds before a client is considered offline


# ── Models ───────────────────────────────────────────────────────────────────

class RegisterPayload(BaseModel):
    username: str
    game_name: str = "Unknown Game"


class HeartbeatPayload(BaseModel):
    client_id: str
    username: str = ""
    game_name: str = ""


class CommandResult(BaseModel):
    client_id: str
    success: bool
    message: str = ""


# ── Helpers ──────────────────────────────────────────────────────────────────

async def broadcast_state():
    """Push the current client list to all connected dashboard WebSockets."""
    snapshot = _build_snapshot()
    dead: list[WebSocket] = []
    for ws in dashboard_sockets:
        try:
            await ws.send_json({"type": "state", "clients": snapshot})
        except Exception:
            dead.append(ws)
    for ws in dead:
        dashboard_sockets.remove(ws)


def _build_snapshot() -> list[dict]:
    now = time.time()
    out: list[dict] = []
    for cid, info in list(connected_clients.items()):
        age = now - info["last_seen"]
        status = "online" if age < HEARTBEAT_TIMEOUT else "offline"
        out.append(
            {
                "client_id": cid,
                "username": info["username"],
                "game_name": info["game_name"],
                "status": status,
                "last_seen_ago": round(age, 1),
            }
        )
    return out


async def cleanup_loop():
    """Periodically remove stale clients and push updates."""
    while True:
        await asyncio.sleep(10)
        now = time.time()
        stale = [
            cid
            for cid, info in connected_clients.items()
            if now - info["last_seen"] > HEARTBEAT_TIMEOUT * 3
        ]
        for cid in stale:
            del connected_clients[cid]
        if stale:
            await broadcast_state()


# ── App lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(cleanup_loop())
    yield
    task.cancel()


app = FastAPI(title="Roblox Join Coordinator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Roblox client endpoints (HTTP polling) ───────────────────────────────────

@app.post("/api/register")
async def register(payload: RegisterPayload):
    """Called once when the Roblox script starts. Returns a client_id."""
    client_id = str(uuid.uuid4())[:8]
    connected_clients[client_id] = {
        "username": payload.username,
        "game_name": payload.game_name,
        "status": "online",
        "last_seen": time.time(),
        "pending_commands": [],
    }
    await broadcast_state()
    return {"client_id": client_id}


@app.post("/api/heartbeat")
async def heartbeat(payload: HeartbeatPayload):
    """
    Polled every few seconds by each Roblox instance.
    Returns any pending commands (e.g. 'join').
    """
    info = connected_clients.get(payload.client_id)
    if info is None:
        return JSONResponse(status_code=404, content={"error": "not_registered"})

    info["last_seen"] = time.time()
    if payload.username:
        info["username"] = payload.username
    if payload.game_name:
        info["game_name"] = payload.game_name

    cmds = list(info["pending_commands"])
    info["pending_commands"].clear()

    await broadcast_state()
    return {"commands": cmds}


@app.post("/api/result")
async def report_result(payload: CommandResult):
    """Roblox client reports back after executing a command."""
    # Push result to dashboard
    for ws in list(dashboard_sockets):
        try:
            await ws.send_json(
                {
                    "type": "result",
                    "client_id": payload.client_id,
                    "success": payload.success,
                    "message": payload.message,
                }
            )
        except Exception:
            pass
    return {"ok": True}


@app.post("/api/disconnect")
async def disconnect(payload: HeartbeatPayload):
    """Called when the Roblox script stops."""
    connected_clients.pop(payload.client_id, None)
    await broadcast_state()
    return {"ok": True}


# ── Dashboard endpoints ─────────────────────────────────────────────────────

@app.get("/api/clients")
async def list_clients():
    return {"clients": _build_snapshot()}


@app.post("/api/join")
async def trigger_join():
    """
    The big red button — queue a 'join' command for every online client.
    """
    now = time.time()
    count = 0
    for info in connected_clients.values():
        if now - info["last_seen"] < HEARTBEAT_TIMEOUT:
            info["pending_commands"].append({"action": "join"})
            count += 1

    # Notify dashboard
    for ws in list(dashboard_sockets):
        try:
            await ws.send_json({"type": "join_sent", "count": count})
        except Exception:
            pass

    return {"sent_to": count}


# ── Dashboard WebSocket ─────────────────────────────────────────────────────

@app.websocket("/ws/dashboard")
async def dashboard_ws(ws: WebSocket):
    await ws.accept()
    dashboard_sockets.append(ws)
    # Send initial state
    await ws.send_json({"type": "state", "clients": _build_snapshot()})
    try:
        while True:
            data = await ws.receive_json()
            if data.get("action") == "join":
                await trigger_join()
    except WebSocketDisconnect:
        pass
    finally:
        if ws in dashboard_sockets:
            dashboard_sockets.remove(ws)


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "clients": len(connected_clients)}


# ── Serve frontend ──────────────────────────────────────────────────────────

app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
