"""Parallel pipeline builder: voice + twitch branches merged before context.user().

Fan-out into two branches that run in parallel and then merge into a common
tail via ConsumerProcessors. The merge point is just before context_aggregator.user()
so that both mic and chat append to the same OpenAI-style conversation history.
"""

from __future__ import annotations

from typing import Tuple

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.pipeline.parallel_pipeline import ParallelPipeline
from pipecat.processors.consumer_processor import ConsumerProcessor
from pipecat.processors.frame_processor import FrameDirection

from ..config.settings import Settings
from ..core.state import SharedState
from ..processors.mic_gate import MicGate
from ..processors.stt_mute import create_stt_mute_filter
from ..processors.twitch_source import TwitchChatSource
from ..processors.guards import DropRawTextBeforeLLM
from ..processors.user_text_normalizers import (
    make_voice_usertext_producer,
    make_twitch_usertext_producer,
)
from ..processors.turn_arbiter import TurnArbiter
from ..services.audio import create_audio_transport
from ..services.stt import create_stt_service
from ..services.llm import create_llm_service, create_llm_context_and_aggregator
from ..services.tts import create_tts_service


def build_parallel_pipeline(settings: Settings, state: SharedState):
    """Create a ParallelPipeline with voice and twitch branches.

    Returns tuple `(pipeline, task, io, task_params, context_aggregator, twitch_source)`.
    """
    io, audio_params = create_audio_transport(settings)
    stt = create_stt_service(settings)
    llm = create_llm_service(settings)
    tts = create_tts_service(settings)

    # Context aggregator for OpenAI-format messages
    _context, context_aggregator = create_llm_context_and_aggregator(settings, llm)

    # Hard mic gate based on state flags
    def _should_allow_mic() -> bool:
        return bool(state.listening) and not bool(state.tts_speaking)

    mic_gate = MicGate(_should_allow_mic)
    stt_mute = create_stt_mute_filter()

    # Branch-local sources and producers
    # Backpressure: emit Twitch messages only when TTS is not speaking
    def _twitch_should_emit() -> bool:
        return not bool(state.tts_speaking)

    twitch_source = TwitchChatSource(cooldown_secs=0.0, should_emit=_twitch_should_emit)
    voice_producer = make_voice_usertext_producer()
    twitch_producer = make_twitch_usertext_producer()

    parallel = ParallelPipeline(
        [
            io.input(),
            mic_gate,
            stt,
            stt_mute,
            voice_producer,
        ],
        [
            twitch_source,
            twitch_producer,
        ],
    )

    # Merge via consumers just before context.user()
    cons_voice = ConsumerProcessor(producer=voice_producer, direction=FrameDirection.DOWNSTREAM)
    cons_twitch = ConsumerProcessor(producer=twitch_producer, direction=FrameDirection.DOWNSTREAM)

    # Prevent raw TextFrames from flowing past the user context merge
    drop_raw_text = DropRawTextBeforeLLM()

    # Central turn arbiter (serialize voice/twitch turns)
    turn_arbiter = TurnArbiter(state, fairness_after_voice=1, turn_timeout_secs=60.0)

    pipeline = Pipeline(
        [
            parallel,
            cons_voice,
            cons_twitch,
            turn_arbiter,
            context_aggregator.user(),
            drop_raw_text,
            llm,
            tts,
            io.output(),
            context_aggregator.assistant(),
        ]
    )

    task_params = PipelineParams(
        audio_in_sample_rate=audio_params.audio_in_sample_rate,
        audio_out_sample_rate=audio_params.audio_out_sample_rate,
    )

    # Attach LLM log observer for detailed model activity logging
    observers = []
    try:
        from pipecat.observers.loggers.llm_log_observer import LLMLogObserver
        observers.append(LLMLogObserver())
    except Exception:
        pass
    try:
        # DebugLogObserver provides per-frame logs across processors
        from pipecat.observers.loggers.debug_log_observer import DebugLogObserver
        observers.append(DebugLogObserver())
    except Exception:
        pass

    task = PipelineTask(
        pipeline,
        params=task_params,
        observers=observers,
        idle_timeout_secs=None,
        cancel_on_idle_timeout=False,
    )
    # Note: returning task_params for backwards compat callers if needed
    return pipeline, task, io, task_params, context_aggregator, twitch_source
