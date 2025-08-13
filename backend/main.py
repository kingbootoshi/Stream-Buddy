# Standard library
import os
from pathlib import Path

# Third-party helper to load environment variables from a local .env file
try:
    from dotenv import load_dotenv

    # Load variables from .env (if the file exists).  Using `override=False` so
    # that any variables *already* present in the shell take precedence.
    load_dotenv(Path(".env"))
except ModuleNotFoundError:
    # If python-dotenv is not installed we silently continue; missing vars will
    # raise clear KeyError exceptions further below.
    pass
import yaml  # External dependency to load YAML configuration files
# Pipecat's Pipeline class is defined in `pipecat.pipeline.pipeline` but
# is not re-exported at the package level, so we import it directly from its
# module.
from pipecat.pipeline.pipeline import Pipeline
# NEW IMPORTS: bring in PipelineTask & PipelineRunner utilities
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.pipeline.runner import PipelineRunner
import asyncio  # Needed for running the async runner
from loguru import logger
# Local system audio transport (PyAudio under the hood)
# NOTE: The transport implementation lives under `pipecat.transports.local.audio`.
# We also import the parameter model used to configure sample-rate, channels, etc.
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams
from pipecat.services.assemblyai.stt import AssemblyAISTTService
from pipecat.services.openrouter.llm import OpenRouterLLMService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.filters.function_filter import FunctionFilter
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.filters.stt_mute_filter import (
    STTMuteFilter,
    STTMuteConfig,
    STTMuteStrategy,
)

# 🔑  grab your keys from env or a secrets manager
AAI_KEY   = os.environ["ASSEMBLYAI_API_KEY"]
OR_KEY    = os.environ["OPENROUTER_API_KEY"]        # needs Referer header too
EL_KEY    = os.environ["ELEVENLABS_API_KEY"]
# Optional
MEM0_KEY  = os.getenv("MEM0_API_KEY", "")

# 📄  System prompt configuration (YAML)
# Allow overriding the prompt path with env var, default to `config/personality.yaml`.
PROMPT_PATH = Path(os.getenv("SYSTEM_PROMPT_PATH", "config/personality.yaml"))


def load_app_config(config_path: Path) -> dict:  # noqa: D401
    """Load application config from YAML.

    Expected shape:
    - system_prompt: str (required)
    - elevenlabs.voice_id: str (optional)
    - memory.user_id: str (optional)
    """
    try:
        with config_path.open("r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp)
    except FileNotFoundError:
        logger.error(f"Config YAML not found at: {config_path}")
        raise
    except Exception as exc:
        logger.exception(f"Failed to load config YAML: {exc}")
        raise

    if not isinstance(data, dict) or "system_prompt" not in data:
        raise ValueError("YAML must contain a top-level 'system_prompt' string field")
    if not isinstance(data["system_prompt"], str):
        raise TypeError("'system_prompt' must be a string in the YAML file")

    # Normalize prompt text to end with a single newline for consistency
    data["system_prompt"] = data["system_prompt"].rstrip() + "\n"

    # Create nested sections if missing
    data.setdefault("elevenlabs", {})
    data.setdefault("memory", {})

    # Log what configurable IDs we picked (not the prompt content)
    picked_voice = data["elevenlabs"].get("voice_id", "<default>")
    picked_user = data["memory"].get("user_id", "<default>")
    logger.info(f"Loaded config from {config_path} (voice_id={picked_voice}, memory.user_id={picked_user})")
    return data

# Load configuration early so it is available to service constructors below
CONFIG = load_app_config(PROMPT_PATH)
SYSTEM_PROMPT = CONFIG["system_prompt"]

# 🎤  Microphone / speakers on the local machine (change to WebRTC, Twilio, etc. if needed)
#
# Pipecat expects a `LocalAudioTransportParams` instance to configure the
# transport.  Here we enable both input & output, and lock the audio to
# 16 kHz / mono for input (optimized for STT) and 22.05 kHz / mono for output
# to preserve TTS fidelity. This avoids unnecessary downsampling of TTS audio
# which would audibly reduce quality.

audio_params = LocalAudioTransportParams(
    audio_in_enabled=True,
    audio_out_enabled=True,
    audio_in_sample_rate=16000,   # keep mic capture optimized for STT accuracy/latency
    audio_out_sample_rate=22050,  # raise playback SR to match common TTS output for better fidelity
    audio_in_channels=1,
    audio_out_channels=1,
)

# Create a single transport that provides both input() and output() processors
io = LocalAudioTransport(audio_params)

# 🗣️  realtime STT with end‑of‑speech detection (~120 ms latency)
stt = AssemblyAISTTService(
        api_key=AAI_KEY
        )

# 🧠  Grok-4 (x-ai/grok-4) via OpenRouter
llm = OpenRouterLLMService(
        api_key=OR_KEY,
        model=CONFIG.get("openrouter", {}).get("model", "anthropic/claude-3.7-sonnet"),
        headers={"HTTP-Referer": "https://bitcoinboos.com"})

# ---------------------------
# 📚 Conversation context & aggregator
# ---------------------------
# The LLM expects conversation messages in OpenAI-chat format (LLMMessagesFrame).
# A context aggregator converts raw STT transcription frames into those messages.
context = OpenAILLMContext(
    messages=[
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]
)
# Create paired processors for user → LLM and assistant replies → history
context_aggregator = llm.create_context_aggregator(context)

# 🔊  ElevenLabs streaming TTS (word‑timed WebSocket)
tts = ElevenLabsTTSService(
        api_key=EL_KEY,
        voice_id=CONFIG.get("elevenlabs", {}).get("voice_id", "V33LkP9pVLdcjeB2y5Na"))
        # Removed explicit low-latency mode to favor higher quality. If you need
        # ultra-low round-trip times, re-enable a low-latency mode—but expect a
        # noticeable fidelity tradeoff.

# ---------------------------
# Mic gating (push-to-talk) & echo prevention during bot speech
# ---------------------------
from pipecat.frames.frames import (
    InputAudioRawFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    StartInterruptionFrame,
    StopInterruptionFrame,
)

# Import the overlay control app & shared knobs
from overlay_server import api as overlay_api  # FastAPI app
from overlay_server import bus, listening_flag, current_mood

# Track when TTS is actively speaking to temporarily drop mic frames
tts_speaking = {"on": False}


async def _mic_gate(frame):  # noqa: D401
    """Drop user audio/VAD frames while muted to avoid queue growth.

    Why: Pausing processors may buffer; dropping frames is safer for long-idle.
    """
    # Also drop user audio while TTS is speaking to avoid echo/feedback.
    if listening_flag["on"] and not tts_speaking["on"]:
        return True
    return not isinstance(
        frame,
        (
            InputAudioRawFrame,
            UserStartedSpeakingFrame,
            UserStoppedSpeakingFrame,
            StartInterruptionFrame,
            StopInterruptionFrame,
        ),
    )


mic_gate_filter = FunctionFilter(filter=_mic_gate, direction=FrameDirection.DOWNSTREAM)
stt_mute = STTMuteFilter(config=STTMuteConfig(strategies={STTMuteStrategy.ALWAYS}))


# 🪄  put it all together
# Build the processing pipeline with gating and mute filter.
pipeline = Pipeline([
    io.input(),                      # 🎤 capture mic frames
    mic_gate_filter,                 # 🚦 gate mic by hotkey
    stt,                             # 🗣️  → transcription frames
    stt_mute,                        # 🤐 mute STT during bot speech to avoid echo/interruptions
    context_aggregator.user(),       # 🧩 convert to chat messages
    llm,                             # 🧠  → assistant text reply
    tts,                             # 🔊  → audio frames
    io.output(),                     # 🔈 play through speakers
    context_aggregator.assistant(),  # 🗃️  store assistant response in history
])

# Configure pipeline parameters (match audio sample-rates, etc.)
# NOTE: We set both in/out rates to 16 kHz so the STT & TTS services get the
# expected format. Adjust here if you change `audio_params` above.
task_params = PipelineParams(
    audio_in_sample_rate=audio_params.audio_in_sample_rate,
    audio_out_sample_rate=audio_params.audio_out_sample_rate,
)

# Wrap our pipeline into an executable PipelineTask and run it with the helper
# PipelineRunner (handles proper shutdown, signal handling, etc.).
task = PipelineTask(pipeline, params=task_params)


# ---------------------------
# Add runtime logging hooks
# ---------------------------

from pipecat.frames.frames import (
    TextFrame,
    LLMMessagesFrame,
    LLMFullResponseStartFrame,
    LLMFullResponseEndFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    OutputAudioRawFrame,
    # STT specific frames for deeper visibility
    InterimTranscriptionFrame,
    TranscriptionFrame,
)


@task.event_handler("on_frame_reached_upstream")
async def _log_upstream_frames(_, frame):  # noqa: D401
    """Log frames travelling upstream (towards the source)."""
    if isinstance(frame, LLMMessagesFrame):
        logger.info("LLM request → OpenRouter (LLMMessagesFrame)")


@task.event_handler("on_frame_reached_downstream")
async def _log_downstream_frames(_, frame):  # noqa: D401 – simple callback
    """Log notable downstream frames for visibility while debugging."""
    if isinstance(frame, TextFrame):
        logger.info(f"Text: {getattr(frame, 'text', '')}")
    elif isinstance(frame, LLMFullResponseStartFrame):
        logger.info("LLM response started")
    elif isinstance(frame, LLMFullResponseEndFrame):
        logger.info("LLM response ended")
    elif isinstance(frame, TTSStartedFrame):
        logger.info("TTS synthesis started (→ ElevenLabs)")
    elif isinstance(frame, OutputAudioRawFrame):
        logger.debug("Received TTS audio frame")
    elif isinstance(frame, TTSStoppedFrame):
        logger.info("TTS synthesis finished")
    elif isinstance(frame, InterimTranscriptionFrame):
        logger.info(f"STT interim: {getattr(frame, 'text', '')}")
    elif isinstance(frame, TranscriptionFrame):
        logger.info(f"STT final : {getattr(frame, 'text', '')}")


# Enable the handler only for the frame types we care about
task.set_reached_upstream_filter((LLMMessagesFrame,))
task.set_reached_downstream_filter(
    (
        TextFrame,
        LLMFullResponseStartFrame,
        LLMFullResponseEndFrame,
        TTSStartedFrame,
        OutputAudioRawFrame,
        TTSStoppedFrame,
        InterimTranscriptionFrame,
        TranscriptionFrame,
    )
)


# ---------------------------
# Async entry point
# ---------------------------
async def run_pipeline():
    """Create an event-loop-aware runner and execute the task + control server."""

    runner = PipelineRunner()  # Now created inside an active event loop

    # Tie TTS lifecycle to overlay events for animation sync
    @task.event_handler("on_frame_reached_downstream")
    async def _signal_overlay(_, frame):  # noqa: D401
        if isinstance(frame, TTSStartedFrame):
            # Mark bot speaking to drop user mic frames (prevents echo)
            tts_speaking["on"] = True
            bus.snapshot["talking"] = True
            await bus.broadcast("start_talking", {"mood": current_mood["value"]})
        elif isinstance(frame, TTSStoppedFrame):
            # Re-enable mic ingestion
            tts_speaking["on"] = False
            bus.snapshot["talking"] = False
            await bus.broadcast("stop_talking")

    import uvicorn  # Local import to avoid hard dependency at import time

    server = uvicorn.Server(uvicorn.Config(overlay_api, host="127.0.0.1", port=8710, log_level="info"))

    # Run control server and pipeline concurrently
    server_task = asyncio.create_task(server.serve())
    pipeline_task = asyncio.create_task(runner.run(task))
    await asyncio.gather(server_task, pipeline_task)


if __name__ == "__main__":
    try:
        # asyncio.run() creates the event loop for us.
        asyncio.run(run_pipeline())
    except KeyboardInterrupt:
        # Graceful shutdown – runner handles cleanup internally.
        pass