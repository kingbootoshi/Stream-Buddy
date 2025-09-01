"""Overlay event bus for server → overlay WebSocket broadcast.

Ported from the previous `overlay_server.py` with small adjustments for
modularity.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket
from loguru import logger


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
        """Send an event to all clients. Stale sockets are removed."""
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

    async def on_tts_started(self, mood: str) -> None:
        """Helper to signal start talking with mood."""
        self.snapshot["talking"] = True
        await self.broadcast("start_talking", {"mood": mood})

    async def on_tts_stopped(self) -> None:
        """Helper to signal stop talking."""
        self.snapshot["talking"] = False
        await self.broadcast("stop_talking")


