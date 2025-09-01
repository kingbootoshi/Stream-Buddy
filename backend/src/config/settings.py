"""Application settings and configuration loading.

Responsibilities:
- Load environment variables (supports both repo root `.env` and `backend/.env`).
- Load YAML system prompt from a configurable path, with sane defaults.
- Provide typed accessors for required keys.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency at runtime
    load_dotenv = None

import yaml


@dataclass
class Settings:
    """Runtime settings loaded from env and YAML config."""

    assemblyai_api_key: str
    openrouter_api_key: str
    elevenlabs_api_key: str
    openrouter_model: str
    http_referer: str
    overlay_key: str
    system_prompt: str
    voice_id: str
    memory_user_id: str

    audio_in_sample_rate: int = 16000
    audio_out_sample_rate: int = 22050
    audio_in_channels: int = 1
    audio_out_channels: int = 1

    @staticmethod
    def load() -> "Settings":
        """Load settings from env and YAML.

        Order of env loading:
        1) repo root `.env`
        2) `backend/.env`
        Existing env values take precedence over later files.
        """
        if load_dotenv is not None:
            # Load both potential env locations; later calls won't override set vars
            load_dotenv(Path(".env"))
            load_dotenv(Path("backend/.env"))

        # Resolve prompt path robustly relative to this file and common roots
        base_dir = Path(__file__).resolve().parent  # backend/src/config
        env_prompt = os.getenv("SYSTEM_PROMPT_PATH", "").strip()

        candidates: List[Path] = []
        if env_prompt:
            env_path = Path(env_prompt).expanduser()
            if env_path.is_absolute():
                candidates.append(env_path)
            else:
                # Try relative to CWD and relative to this config directory
                candidates.append(Path.cwd() / env_path)
                candidates.append(base_dir / env_path)

        # Defaults: local to this module, legacy backend/config, and repo-level config
        candidates.extend(
            [
                base_dir / "personality.yaml",  # backend/src/config/personality.yaml
                base_dir.parent.parent / "config" / "personality.yaml",  # backend/config/personality.yaml
                Path.cwd() / "config" / "personality.yaml",  # ./config/personality.yaml when running from repo root
                Path.cwd() / "backend" / "config" / "personality.yaml",  # repo root fallback
            ]
        )

        prompt_path = next((p for p in candidates if p.exists()), None)
        if prompt_path is None:
            logger.error(
                "Config YAML not found. Checked: "
                + ", ".join(str(p) for p in candidates)
            )
            raise FileNotFoundError("personality.yaml not found in expected locations")

        try:
            with prompt_path.open("r", encoding="utf-8") as fp:
                data: Dict[str, Any] = yaml.safe_load(fp) or {}
        except FileNotFoundError:
            logger.error(f"Config YAML not found at: {prompt_path}")
            raise
        except Exception as exc:
            logger.exception(f"Failed to load config YAML: {exc}")
            raise

        if "system_prompt" not in data or not isinstance(data["system_prompt"], str):
            raise ValueError("YAML must contain a top-level 'system_prompt' string field")

        system_prompt = data["system_prompt"].rstrip() + "\n"
        eleven = data.get("elevenlabs", {}) or {}
        memory = data.get("memory", {}) or {}
        openrouter = data.get("openrouter", {}) or {}

        settings = Settings(
            assemblyai_api_key=os.environ["ASSEMBLYAI_API_KEY"],
            openrouter_api_key=os.environ["OPENROUTER_API_KEY"],
            elevenlabs_api_key=os.environ["ELEVENLABS_API_KEY"],
            openrouter_model=str(openrouter.get("model", "anthropic/claude-3.7-sonnet")),
            http_referer=os.getenv("HTTP_REFERER", "https://bitcoinboos.com"),
            overlay_key=os.getenv("OVERLAY_KEY", "devlocal"),
            system_prompt=system_prompt,
            voice_id=str(eleven.get("voice_id", "V33LkP9pVLdcjeB2y5Na")),
            memory_user_id=str(memory.get("user_id", "<default>")),
        )

        logger.info(
            f"Loaded settings (voice_id={settings.voice_id}, memory.user_id={settings.memory_user_id}, model={settings.openrouter_model})"
        )
        return settings


