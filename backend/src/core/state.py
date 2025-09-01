"""Shared application state and notifications.

Encapsulates flags used across pipeline and API layers (listening, TTS
speaking, current mood, hat, forced state). Provides a simple event listener
mechanism so other modules can react to state changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


StateListener = Callable[[str, Any], None]


@dataclass
class SharedState:
    """Container for mutable shared state with change notifications."""

    listening: bool = False
    tts_speaking: bool = False
    current_mood: str = "neutral"
    hat: Optional[str] = None
    forced_state: Optional[str] = None

    _listeners: List[StateListener] = field(default_factory=list)

    def add_listener(self, listener: StateListener) -> None:
        """Register a listener for state change notifications."""
        self._listeners.append(listener)

    def _notify(self, event: str, value: Any) -> None:
        """Notify all listeners of a state change event."""
        for listener in list(self._listeners):
            try:
                listener(event, value)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(f"State listener error: {exc}")

    def set_listening(self, value: bool) -> None:
        prev = self.listening
        self.listening = bool(value)
        if prev != self.listening:
            logger.info(f"listening set to {self.listening}")
            self._notify("listening_changed", self.listening)

    def set_tts_speaking(self, value: bool) -> None:
        prev = self.tts_speaking
        self.tts_speaking = bool(value)
        if prev != self.tts_speaking:
            logger.info(f"tts_speaking set to {self.tts_speaking}")
            self._notify("tts_speaking_changed", self.tts_speaking)

    def set_mood(self, mood: str) -> None:
        prev = self.current_mood
        self.current_mood = mood
        if prev != self.current_mood:
            logger.debug(f"mood set to {self.current_mood}")
            self._notify("mood_changed", self.current_mood)

    def set_hat(self, hat: Optional[str]) -> None:
        prev = self.hat
        self.hat = hat
        if prev != self.hat:
            logger.debug(f"hat set to {self.hat}")
            self._notify("hat_changed", self.hat)

    def set_forced_state(self, state: Optional[str]) -> None:
        prev = self.forced_state
        self.forced_state = state
        if prev != self.forced_state:
            logger.debug(f"forced_state set to {self.forced_state}")
            self._notify("forced_state_changed", self.forced_state)


