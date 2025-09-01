"""WebSocket endpoint handlers and helpers."""

from __future__ import annotations

import time
import uuid
from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from .events import OverlayEventBus


async def handle_overlay_ws(ws: WebSocket, bus: OverlayEventBus) -> None:
    """Accept overlay WS, send hello snapshot, and keep the socket alive."""
    await ws.accept()
    bus.clients.add(ws)
    logger.info("Overlay connected")
    try:
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
            _ = await ws.receive_json()
    except WebSocketDisconnect:
        logger.info("Overlay disconnected")
    except Exception as exc:  # pragma: no cover
        logger.exception(f"WS error: {exc}")
    finally:
        bus.clients.discard(ws)


