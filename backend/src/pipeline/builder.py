"""Pipeline construction logic.

Builds a Pipecat Pipeline with MicGate, STT, LLM, TTS, and context aggregator.
"""

from __future__ import annotations

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask, PipelineParams

from ..config.settings import Settings
from ..core.state import SharedState
from ..processors.mic_gate import MicGate
from ..processors.stt_mute import create_stt_mute_filter
from ..services.audio import create_audio_transport
from ..services.stt import create_stt_service
from ..services.llm import create_llm_service, create_llm_context_and_aggregator
from ..services.tts import create_tts_service


def build_pipeline(settings: Settings, state: SharedState):
    """Create transport, services, and assemble the pipeline and task.

    Returns tuple `(pipeline, task, io, task_params, context_aggregator)`.
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

    # Mute STT during TTS
    stt_mute = create_stt_mute_filter()

    pipeline = Pipeline(
        [
            io.input(),
            mic_gate,
            stt,
            stt_mute,
            ## CREATE A PARALLEL BRANCH RIGHT HERE TO HANDLE THE TWITCH CHAT INTEGRATION
            context_aggregator.user(),
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
    
    task = PipelineTask(
        pipeline,
        params=task_params,
        idle_timeout_secs=None,
        cancel_on_idle_timeout=False,
    )

    return pipeline, task, io, task_params, context_aggregator


