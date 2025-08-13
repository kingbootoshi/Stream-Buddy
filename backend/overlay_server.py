"""
Overlay control server: FastAPI app with WebSocket broadcast and small HTTP API.

Why: Provides a durable, versioned control-plane for the OBS overlay to
receive state changes from the Pipecat backend (listen on/off, start/stop
talking with mood, set hat, force state). This keeps audio processing local
and low-latency while animation control travels over a lightweight WS.

How: Maintains a snapshot and fan-out to connected WebSocket clients. Mutating
HTTP routes require a shared secret header `X-Overlay-Key` from `.env`.

Notes:
- All events are JSON with shape { v: 1, type, data?, ts, id }.
- Bind your server to 127.0.0.1 only for local control.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Any, Dict, Optional, Set

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from loguru import logger


# Shared secret for mutating routes (set in .env / environment)
OVERLAY_KEY = os.getenv("OVERLAY_KEY", "devlocal")


def _auth(x_overlay_key: str = Header(default="")) -> None:
    """Simple header auth for local HTTP control.

    Raises 401 if header doesn't match configured key.
    """
    if x_overlay_key != OVERLAY_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


class OverlayEventBus:
    """In-memory fan-out with state snapshot for reconnect resilience."""

    def __init__(self) -> None:
        self.clients: Set[WebSocket] = set()
        self.snapshot: Dict[str, Any] = {
            "listening": False,
            "talking": False,
            "mood": "neutral",
            "hat": None,
            "forcedState": None,
        }
        self._lock = asyncio.Lock()

    async def broadcast(self, type_: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Send an event to all clients. Stale sockets are removed.

        Args:
            type_: Event name (e.g., 'start_talking').
            data: Optional event payload.
        """
        evt = {
            "v": 1,
            "type": type_,
            "data": data or {},
            "ts": int(time.time() * 1000),
            "id": str(uuid.uuid4()),
        }
        async with self._lock:
            stale: list[WebSocket] = []
            for ws in list(self.clients):
                try:
                    await ws.send_json(evt)
                except Exception as exc:  # pragma: no cover - network failure is best-effort
                    logger.warning(f"Overlay client send failed: {exc}")
                    stale.append(ws)
            for ws in stale:
                self.clients.discard(ws)


# Global bus and shared state knobs for the pipeline to read/update
bus = OverlayEventBus()

# Mic listening hotkey flag and current mood for next speaking turn.
# Dicts allow mutation across modules without 'global' statements.
listening_flag: Dict[str, bool] = {"on": False}
current_mood: Dict[str, str] = {"value": "neutral"}


api = FastAPI()


@api.get("/healthz")
async def healthz() -> JSONResponse:  # noqa: D401
    """Liveness probe for supervisord/systemd or manual checks."""
    return JSONResponse({"ok": True, "clients": len(bus.clients), "snapshot": bus.snapshot})


@api.websocket("/ws/overlay")
async def ws_overlay(ws: WebSocket) -> None:  # noqa: D401
    """WebSocket endpoint for OBS overlay clients.

    On connect: send a 'hello' with the current snapshot.
    Then, keep the socket open and accept basic pings from client.
    """
    await ws.accept()
    bus.clients.add(ws)
    logger.info("Overlay connected")
    try:
        # Send initial snapshot
        await ws.send_json(
            {
                "v": 1,
                "type": "hello",
                "data": bus.snapshot,
                "ts": int(time.time() * 1000),
                "id": str(uuid.uuid4()),
            }
        )
        while True:
            # Optional client messages: ready/pong/error
            _ = await ws.receive_json()
    except WebSocketDisconnect:
        logger.info("Overlay disconnected")
    except Exception as exc:  # pragma: no cover
        logger.exception(f"WS error: {exc}")
    finally:
        bus.clients.discard(ws)


@api.post("/api/listen/start")
async def listen_start(_: None = Depends(_auth)) -> JSONResponse:  # noqa: D401
    """Enable mic listening and place the avatar into a waiting pose."""
    listening_flag["on"] = True
    bus.snapshot["listening"] = True
    await bus.broadcast("listen_on")
    await bus.broadcast("force_state", {"state": "handsCrossed"})
    return JSONResponse({"ok": True})


@api.post("/api/listen/stop")
async def listen_stop(_: None = Depends(_auth)) -> JSONResponse:  # noqa: D401
    """Disable mic listening and clear any forced state."""
    listening_flag["on"] = False
    bus.snapshot["listening"] = False
    await bus.broadcast("listen_off")
    await bus.broadcast("force_state", {"state": None})
    return JSONResponse({"ok": True})


@api.post("/api/talk/mood")
async def set_talk_mood(body: Dict[str, str], _: None = Depends(_auth)) -> JSONResponse:  # noqa: D401
    """Set default talking mood for the next speaking turn."""
    mood = body.get("mood", "neutral")
    if mood not in {"neutral", "happy", "angry"}:
        raise HTTPException(status_code=400, detail="invalid mood")
    current_mood["value"] = mood
    bus.snapshot["mood"] = mood
    return JSONResponse({"ok": True, "mood": mood})


@api.post("/api/hat")
async def set_hat(body: Dict[str, Optional[str]], _: None = Depends(_auth)) -> JSONResponse:  # noqa: D401
    """Set hat alias or hide when null."""
    hat = body.get("hat", None)
    if hat not in {"hat1", "hat2", "hat3", None}:
        raise HTTPException(status_code=400, detail="invalid hat")
    bus.snapshot["hat"] = hat
    await bus.broadcast("set_hat", {"hat": hat})
    return JSONResponse({"ok": True, "hat": hat})


@api.post("/api/force-state")
async def force_state(body: Dict[str, Optional[str]], _: None = Depends(_auth)) -> JSONResponse:  # noqa: D401
    """Force a visual state (idle|walk|handsCrossed) or clear with null."""
    state = body.get("state", None)
    if state not in {"idle", "walk", "handsCrossed", None}:
        raise HTTPException(status_code=400, detail="invalid state")
    bus.snapshot["forcedState"] = state
    await bus.broadcast("force_state", {"state": state})
    return JSONResponse({"ok": True, "state": state})


