"""Base integration class for future extensions (e.g., Twitch)."""

from __future__ import annotations

from typing import Any


class BaseIntegration:
    """Lifecycle hooks for integrations to react to app events."""

    async def on_app_ready(self, app: Any) -> None:  # pragma: no cover - interface
        pass

    async def on_pipeline_ready(self, task: Any) -> None:  # pragma: no cover - interface
        pass


