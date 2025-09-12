Parallel pipeline integration for Twitch chat

Overview
- The previous single-lane pipeline injected Twitch `TextFrame`s ahead of STT, and the Twitch worker waited until mic listening/tts flags allowed injection. This coupled chat to mic state and caused turns to stall until listening toggled off.
- We now fan out into two parallel branches (voice and Twitch) and merge just before `context_aggregator.user()`. Both sources append to the same conversation history, and the LLM/TTS/output remain shared.

What changed
- Added `backend/src/processors/twitch_source.py`
  - `TwitchChatSource` is a custom FrameProcessor that ingests chat via `ingest(user, text)` and emits canonical `TextFrame`s: `"Twitch Chat User [<user>] says [<text>]"`.
  - Applies soft backpressure (pauses when LLM/TTS are busy) and optional cooldown. Non-blocking.

- Added `backend/src/processors/user_text_normalizers.py`
  - Producer helpers to normalize branch outputs into consistent `TextFrame`s.
  - Voice: transform final STT to `Bootoshi says [<text>]`.
  - Twitch: pass through `TextFrame`s from the Twitch source.

- Added `backend/src/pipeline/builder_parallel.py`
  - Builds `ParallelPipeline` with two branches:
    - Voice: `io.input → MicGate → STT → STTMute → voice_producer`.
    - Twitch: `TwitchChatSource → twitch_producer`.
  - Merges via two `ConsumerProcessor`s and feeds the shared tail:
    - `cons_voice → cons_twitch → context.user → LLM → TTS → io.output → context.assistant`.

- Updated `backend/src/pipeline/runner.py`
  - Uses `build_parallel_pipeline` and passes the constructed `TwitchChatSource` into the Twitch integration.

- Refactored `backend/src/integrations/twitch_chat.py`
  - Removed the internal queue/worker and the gating on `state.listening`/`state.tts_speaking`.
  - On keyword hit, calls `twitch_source.ingest(user, text)` directly.
  - Event handler now detects canonical Twitch user `TextFrame`s in the downstream stream and attributes the next LLM turn to that user for optional echo-back to chat.

Why this fixes the issue
- Chat input is no longer blocked by mic listening state; it flows through its own branch and is serialized by the pipeline/LLM busy detection.
- Both voice and Twitch append to the same conversation right before `context_aggregator.user()`, so history grows with both sources.
- `ParallelPipeline` keeps system frames synchronized and avoids the fragile ordering of mixing audio/STT with programmatic text upstream.

Key files
- `backend/src/processors/twitch_source.py`: custom Twitch ingress.
- `backend/src/processors/user_text_normalizers.py`: branch output normalization via Producer processors.
- `backend/src/pipeline/builder_parallel.py`: parallel pipeline wiring and merge point.
- `backend/src/integrations/twitch_chat.py`: integration refactor to use source.ingest and attribution for chat echo.
- `backend/src/pipeline/runner.py`: switches to the parallel builder and injects the Twitch source into the integration.

Operational notes
- Mic gating behavior is unchanged: `MicGate` still blocks mic/VAD frames while muted or during TTS. STT is muted during TTS via `STTMuteFilter`.
- `TwitchChatSource`’s soft backpressure prevents overlapping Twitch turns with ongoing LLM/TTS activity. If you prefer fully concurrent turns, remove the busy checks.
- Echo-to-chat remains optional; attribution is based on detecting the canonical Twitch user `TextFrame` entering the common tail.

