"""HTTP routes for control plane."""

from __future__ import annotations

from typing import Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse

from ..core.state import SharedState
from ..config.settings import Settings
from .events import OverlayEventBus


def auth_dependency(settings: Settings):
    def _auth(x_overlay_key: str = Header(default="")) -> None:
        if x_overlay_key != settings.overlay_key:
            raise HTTPException(status_code=401, detail="Unauthorized")
    return _auth


def build_router(settings: Settings, state: SharedState, bus: OverlayEventBus) -> APIRouter:
    router = APIRouter()
    _auth = auth_dependency(settings)

    @router.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"ok": True, "clients": len(bus.clients), "snapshot": bus.snapshot})

    @router.post("/api/listen/start")
    async def listen_start(_: None = Depends(_auth)) -> JSONResponse:
        state.set_listening(True)
        bus.snapshot["listening"] = True
        await bus.broadcast("listen_on")
        await bus.broadcast("force_state", {"state": "handsCrossed"})
        return JSONResponse({"ok": True})

    @router.post("/api/listen/stop")
    async def listen_stop(_: None = Depends(_auth)) -> JSONResponse:
        state.set_listening(False)
        bus.snapshot["listening"] = False
        await bus.broadcast("listen_off")
        await bus.broadcast("force_state", {"state": None})
        return JSONResponse({"ok": True})

    @router.post("/api/listen/toggle")
    async def listen_toggle(_: None = Depends(_auth)) -> JSONResponse:
        state.set_listening(not state.listening)
        bus.snapshot["listening"] = state.listening
        if state.listening:
            await bus.broadcast("listen_on")
            await bus.broadcast("force_state", {"state": "handsCrossed"})
        else:
            await bus.broadcast("listen_off")
            await bus.broadcast("force_state", {"state": None})
        return JSONResponse({"ok": True, "listening": state.listening})

    @router.post("/api/talk/mood")
    async def set_talk_mood(body: Dict[str, str], _: None = Depends(_auth)) -> JSONResponse:
        mood = body.get("mood", "neutral")
        if mood not in {"neutral", "happy", "angry"}:
            raise HTTPException(status_code=400, detail="invalid mood")
        state.set_mood(mood)
        bus.snapshot["mood"] = mood
        return JSONResponse({"ok": True, "mood": mood})

    @router.post("/api/hat")
    async def set_hat(body: Dict[str, Optional[str]], _: None = Depends(_auth)) -> JSONResponse:
        hat = body.get("hat", None)
        if hat not in {"hat1", "hat2", "hat3", None}:
            raise HTTPException(status_code=400, detail="invalid hat")
        state.set_hat(hat)
        bus.snapshot["hat"] = hat
        await bus.broadcast("set_hat", {"hat": hat})
        return JSONResponse({"ok": True, "hat": hat})

    @router.post("/api/force-state")
    async def force_state(body: Dict[str, Optional[str]], _: None = Depends(_auth)) -> JSONResponse:
        forced = body.get("state", None)
        if forced not in {"idle", "walk", "handsCrossed", None}:
            raise HTTPException(status_code=400, detail="invalid state")
        state.set_forced_state(forced)
        bus.snapshot["forcedState"] = forced
        await bus.broadcast("force_state", {"state": forced})
        return JSONResponse({"ok": True, "state": forced})

    return router


