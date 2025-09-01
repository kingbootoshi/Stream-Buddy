"""FastAPI app setup and dependency wiring."""

from __future__ import annotations

from fastapi import FastAPI, WebSocket
from loguru import logger

from ..config.settings import Settings
from ..core.state import SharedState
from .events import OverlayEventBus
from .routes import build_router
from .websocket import handle_overlay_ws


def create_api(settings: Settings, state: SharedState, bus: OverlayEventBus) -> FastAPI:
    """Create FastAPI app with routes and WebSocket endpoint."""
    api = FastAPI()

    # Add HTTP routes
    api.include_router(build_router(settings, state, bus))

    # Register WS handler
    @api.websocket("/ws/overlay")
    async def ws_overlay(ws: WebSocket):  # noqa: D401
        await handle_overlay_ws(ws, bus)

    logger.info("API created")
    return api


