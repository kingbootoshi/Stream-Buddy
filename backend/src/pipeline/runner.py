"""Application runner: starts API server and pipeline concurrently."""

from __future__ import annotations

import asyncio
import contextlib
from loguru import logger

from pipecat.pipeline.runner import PipelineRunner as _PipelineRunner

from ..core.logging import setup_logging
from ..core.state import SharedState
from ..config.settings import Settings
from ..api.events import OverlayEventBus
from ..api.server import create_api
from .builder import build_parallel_pipeline
from .handlers import register_handlers


class AppRunner:
    """Coordinates settings, API, and the Pipecat pipeline lifecycle."""

    def __init__(self) -> None:
        self.settings = Settings.load()
        self.state = SharedState()
        self.bus = OverlayEventBus()

        # Create API app
        self.api = create_api(self.settings, self.state, self.bus)

        # Build pipeline and register handlers
        _pipeline, self.task, _io, _params, _agg, twitch_source = build_parallel_pipeline(
            self.settings, self.state
        )
        register_handlers(self.task, self.state, self.bus)
        # Integrations (Twitch chat → pipeline)
        from ..integrations.twitch_chat import TwitchChatIntegration
        self.integrations = [TwitchChatIntegration(self.settings, self.state, twitch_source)]

    async def run(self) -> None:
        """Run FastAPI (Uvicorn) and pipeline concurrently until cancelled."""
        setup_logging()

        runner = _PipelineRunner()

        import uvicorn  # local import to avoid hard dependency at import time

        server = uvicorn.Server(
            uvicorn.Config(self.api, host="127.0.0.1", port=8710, log_level="info")
        )

        server_task = asyncio.create_task(server.serve())
        pipeline_task = asyncio.create_task(runner.run(self.task))

        # Start integrations once the PipelineTask exists
        for integ in getattr(self, "integrations", []):
            try:
                await integ.on_pipeline_ready(self.task)
            except Exception as exc:  # pragma: no cover - resiliency
                logger.warning(f"Integration startup failed: {exc}")

        async def _heartbeat():
            while True:
                try:
                    current_muted = (not self.state.listening) or bool(self.state.tts_speaking)
                    logger.debug(
                        f"Heartbeat listening={self.state.listening} tts_speaking={self.state.tts_speaking} muted={current_muted}"
                    )
                    await asyncio.sleep(5.0)
                except asyncio.CancelledError:
                    break
                except Exception as exc:  # pragma: no cover
                    logger.warning(f"Heartbeat error: {exc}")
                    await asyncio.sleep(5.0)

        heartbeat_task = asyncio.create_task(_heartbeat())

        try:
            await asyncio.gather(server_task, pipeline_task)
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(Exception):
                await heartbeat_task
