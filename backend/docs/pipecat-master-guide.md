# Pipecat Development Master Guide (Duck Buddy Backend)

This guide explains how Pipecat is used in this codebase so future devs and coding agents can navigate, debug, and extend it confidently. It covers the frame model, our processors, the merged voice + Twitch pipeline, turn arbitration, Twitch echoing, and operational tips.

## 1) Big Picture

- We run a single Pipecat pipeline that ingests two concurrent user-text sources:
  - Voice: microphone → STT
  - Twitch: chat messages (keyword-triggered) via EventSub
- Both sources normalize into `LLMMessagesAppendFrame` (OpenAI-style message objects) which feed the conversation context and produce an assistant reply via LLM → TTS → audio.
- A central TurnArbiter enforces “one turn at a time”, prioritizing voice while ensuring chat is never starved. It eliminates interleaving issues with the LLM context and prevents overlapping TTS.
- If the turn originated from Twitch, we also echo the assistant’s reply back into chat (while still speaking the reply via TTS). Voice-only turns do not echo to chat.

## 2) Code Map

- Pipeline assembly: `src/pipeline/builder.py`
- Pipeline runner + API server startup: `src/pipeline/runner.py`, `main.py`
- Frame handlers + overlay sync: `src/pipeline/handlers.py`
- Shared state + eventing: `src/core/state.py`
- Services: `src/services/{stt,tts,llm,audio}.py`
- Processors:
  - `src/processors/mic_gate.py` — mutes mic based on state
  - `src/processors/stt_mute.py` — pauses STT while TTS is speaking
  - `src/processors/twitch_source.py` — branch-local Twitch ingress
  - `src/processors/user_text_normalizers.py` — convert STT/Twitch text into `LLMMessagesAppendFrame`
  - `src/processors/guards.py` — drops stray raw `TextFrame` before LLM
  - `src/processors/turn_arbiter.py` — serializes turns, publishes turn metadata
- Twitch integration (network + pipeline glue): `src/integrations/twitch_chat.py`
- Settings loader + system prompt: `src/config/settings.py`, `src/config/personality.yaml`
- API: `src/api/{server,routes,websocket,events}.py`

## 3) Pipecat Mental Model

### 3.1 Frames we use

- Lifecycle: `StartFrame`, `EndFrame`, `CancelFrame`, `StopFrame`
- Audio: `InputAudioRawFrame` (mic), `OutputAudioRawFrame` (TTS output)
- Voice activity/interruption: `UserStartedSpeakingFrame`, `UserStoppedSpeakingFrame`, `StartInterruptionFrame`, `StopInterruptionFrame`
- STT: `InterimTranscriptionFrame` (partial), `TranscriptionFrame` (final)
- LLM: `LLMMessagesAppendFrame` (append user/assistant messages), `LLMMessagesFrame` (full request), `LLMTextFrame` (token chunks), `LLMFullResponseStartFrame`, `LLMFullResponseEndFrame`
- TTS: `TTSStartedFrame`, `TTSStoppedFrame`

Frames travel downstream through the processor list; some processors (like the context aggregator) emit upstream frames toward services.

### 3.2 Context and aggregator

- We use `OpenAILLMContext` plus a context aggregator created by the LLM service (`src/services/llm.py`).
- Producers generate `LLMMessagesAppendFrame` items with `messages=[...]` entries resembling OpenAI chat format; setting `run_llm=True` instructs the aggregator to run a turn. Our TurnArbiter centrally controls when that’s allowed.

## 4) The Pipeline

Defined in `src/pipeline/builder.py` as two branches merged into a common tail. See also the mermaid diagram in `docs/pipeline.md`.

Voice branch:
- `io.input()` → `MicGate` → `STT` → `STTMuteFilter` → `voice_producer`
  - `voice_producer` converts final STT to `LLMMessagesAppendFrame` with `name="voice:bootoshi"` and a normalized content prefix.

Twitch branch:
- `TwitchChatSource` → `twitch_producer`
  - `twitch_producer` converts canonical chat `TextFrame` to `LLMMessagesAppendFrame` with `name="twitch:<username>"`.

Merge + tail:
- `Consumer(voice_producer)` + `Consumer(twitch_producer)` → `TurnArbiter` → `context_aggregator.user()` → `DropRawTextBeforeLLM` → `llm` → `tts` → `io.output()` → `context_aggregator.assistant()`

## 5) TurnArbiter (Concurrency Control)

File: `src/processors/turn_arbiter.py`

Problem: With both branches able to set `run_llm=True`, two turns could interleave and fight over the context aggregator, producing warnings like “Ignoring message from unavailable context …” and occasionally overlapping TTS.

Solution:
- Intercept every `LLMMessagesAppendFrame`, force `run_llm=False`, and place it in a queue.
- When idle, release exactly one queued append with `run_llm=True`:
  - Voice has priority over chat, but there’s a fairness rule that lets at least one chat turn through after voice activity.
- The “busy window” is from release until `TTSStoppedFrame` (observed via `SharedState.set_tts_speaking` change fired by handlers).
- Publishes per-turn metadata into `SharedState`: `current_turn_origin` and `current_turn_user`.
- Includes a watchdog timer to auto-release the lock if providers hang.

Effects:
- Eliminates context races and overlapping TTS.
- Provides deterministic attribution so Twitch echoing tags the correct user.

## 6) State and Overlay

File: `src/core/state.py`, handlers: `src/pipeline/handlers.py`

- `SharedState` contains `listening`, `tts_speaking`, and per-turn metadata `current_turn_origin/current_turn_user` used by integrations.
- Handlers flip `tts_speaking` on `TTSStartedFrame/TTSStoppedFrame` and notify the overlay via `OverlayEventBus`.

## 7) Twitch Echo (Chat-only)

File: `src/integrations/twitch_chat.py`

- Echo is always on for chat turns (no env flag). When an assistant turn ends (`LLMFullResponseEndFrame`), if `SharedState.current_turn_origin == "twitch"`, send the final text back to chat, prefixed with `@<user>`.
- Voice turns never echo into chat.
- The integration resolves broadcaster ID, listens via EventSub, and can send chat messages using the stored user token.

## 8) Turn Lifecycles

Voice turn:
1. Mic audio passes `MicGate` (only when `listening` is True and not `tts_speaking`).
2. STT emits `TranscriptionFrame`.
3. `voice_producer` → `LLMMessagesAppendFrame(name="voice:bootoshi")` → TurnArbiter queues and eventually releases it.
4. Aggregator runs LLM, tokens stream, TTS speaks, then `TTSStoppedFrame` ends the turn.

Twitch turn:
1. EventSub → `TwitchChatSource.ingest(user, text)` → canonical `TextFrame`.
2. `twitch_producer` → `LLMMessagesAppendFrame(name="twitch:<user>")` → TurnArbiter queues/releases.
3. After assistant response ends, Twitch integration echoes the final text back to chat mentioning the username.

## 9) Running and Operating

- Setup: `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
- Run: `python main.py` (FastAPI at `127.0.0.1:8710` + pipeline)
- Health: `curl http://127.0.0.1:8710/healthz`
- Toggle listen: `curl -X POST http://127.0.0.1:8710/api/listen/toggle -H 'X-Overlay-Key: devlocal'`
- Twitch token: `python backend/generate_user_token.py` (writes `backend/.twitch_user_token.json`)

Expected logs:
- `[QUEUE] add origin=<voice|twitch> …`
- `[TURN] release origin=<...> user=<...> raw='…'`
- `TTS synthesis started/finished`
- `<green>[SEND]</green> -> #channel: '@username …'` (chat turns only)

## 10) Troubleshooting

- “Ignoring message from unavailable context …”: ensure `TurnArbiter` is inserted before `context_aggregator.user()` and that no `LLMMessagesAppendFrame` bypasses it.
- No Twitch echo: verify broadcaster ID resolution and that the current turn origin is `twitch` with a non-empty `current_turn_user`. Confirm token file presence.
- Chat feels delayed: tweak TurnArbiter fairness (`fairness_after_voice`) if you need more frequent chat turns during heavy voice activity.

## 11) Extension Points and Tips

- Reduce chat spam: coalesce or rate-limit in `TwitchChatSource` (same-user duplicate lines within a short window).
- Per-user fairness: extend TurnArbiter to demote repetitive users to the back of the chat queue.
- Observability: add a small status dump of `current_turn_origin/user` to your health snapshot for quick diag.
- Testing: write unit tests for processors (MicGate, guards, TurnArbiter) with synthetic frames; mock external services (STT/TTS/LLM/Twitch) to keep tests offline.

