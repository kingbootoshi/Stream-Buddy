### Pipecat main pipeline

The pipeline is now assembled in `backend/src/pipeline/builder_parallel.py` (parallel branches) and run by `backend/src/pipeline/runner.py`. It wires audio I/O, gating, STT → LLM → TTS, and context aggregation. Downstream frame handlers in `backend/src/pipeline/handlers.py` log activity and synchronize the overlay (TTS started/stopped), updating shared state.

```mermaid
flowchart TD
    subgraph Transport
        A["input"]
        J["output"]
    end

    subgraph Processors
        G["MicGate<br/>allow when listening=true and speaking=false"]
        B["STT<br/>audio -> transcription"]
        C["STT Mute<br/>drop STT while TTS speaking"]
        D["Context.user<br/>build messages"]
        E["LLM<br/>messages -> text"]
        F["TTS<br/>text -> audio"]
        H["Context.assistant<br/>append assistant turn"]
    end

    A --> G --> B --> C --> D --> E --> F --> J --> H

    subgraph Handlers_and_State
        K["Downstream handlers<br/>logs Text / LLM / TTS"]
        L["Overlay bus<br/>toggle tts_speaking; clear forced state"]
    end

    E -.-> K
    F -.-> K
    K --> L
```

- The `MicGate` enforces speaking/listening rules at the audio level, preventing hot-mic while the agent is speaking.
- The STT mute filter ensures no transcriptions are processed while TTS is active, avoiding echo/feedback loops.
- Context aggregation maintains a chat-style history for both user and assistant turns.


### Parallel pipeline (voice + Twitch)

We split sources into two branches that run in parallel and merge just before `context_aggregator.user()`. Both sources append to the same conversation history and share LLM, TTS, output, and `context_aggregator.assistant()`.

```mermaid
flowchart TD
    subgraph Transport
        A["input"]
        J["output"]
    end

    subgraph ParallelPipeline
        direction LR
        subgraph Voice_Branch
            G["MicGate<br/>allow when listening=true and speaking=false"]
            B["STT<br/>audio -> transcription"]
            C["STT Mute<br/>drop STT while TTS speaking"]
            VP["Producer: voice_usertext<br/>Transcription → TextFrame<br/>‘Bootoshi says […]’"]
        end
        subgraph Twitch_Branch
            TS["TwitchChatSource<br/>ingest(user,text) → TextFrame"]
            TP["Producer: twitch_usertext<br/>TextFrame passthrough"]
        end
    end

    subgraph Merge_and_Tail
        CV["Consumer(voice_usertext)"]
        CT["Consumer(twitch_usertext)"]
        D["Context.user<br/>build messages (shared)"]
        E["LLM<br/>messages -> text (shared)"]
        F["TTS<br/>text -> audio (shared)"]
        H["Context.assistant<br/>append assistant turn (shared)"]
    end

    %% Voice branch wiring
    A --> G --> B --> C --> VP
    %% Twitch branch wiring
    TS --> TP

    %% Producer → Consumer routing (cross-branch)
    VP -. produces .-> CV
    TP -. produces .-> CT

    %% Merge order and shared tail
    CV --> CT --> D --> E --> F --> J --> H

    subgraph Handlers_and_State
        K["Downstream handlers<br/>logs Text / LLM / TTS"]
        L["Overlay bus<br/>toggle tts_speaking; clear forced state"]
    end

    E -.-> K
    F -.-> K
    K --> L

    subgraph Twitch_Integration
        T0["EventSub WS"]
        T1["event_message"]
        T2{keyword hit}
        T3["on_keyword_hit"]
        I0["source.ingest(user,text)"]
    end

    T0 --> T1 --> T2
    T2 -- yes --> T3 --> I0 -.-> TS
    T2 -- no --> T1
```

- Voice path remains gated by `MicGate` and muted via `STTMuteFilter` during TTS.
- `TwitchChatSource` ingests chat programmatically and emits canonical `TextFrame`s (no dependency on mic state).
- Producers capture just the frames intended for the tail; Consumers inject them right before `Context.user()`.
- Both sources share a single LLM/TTS/output and append to the same context history.

### (Legacy) Twitch chat → pipeline integration

Prior design (kept here for context) used an internal queue/worker that waited on mic listening/speaking state and injected `TextFrame`s directly into the task. It has been replaced by the parallel design above.

```mermaid
flowchart TD
    subgraph Twitch
        T0["EventSub WS"]
        T1["event_message"]
        T2{keyword hit}
        T3["enqueue ChatTrigger"]
    end

    subgraph Worker
        W0["dequeue ChatTrigger"]
        W1{listening=false<br/>and speaking=false}
        W2["queue TextFrame: Twitch Chat User [u] says [t]"]
        W3["wait TTSStopped or timeout"]
        W4["cooldown"]
    end

    subgraph Pipeline
        P1["Context.user"]
        P2["LLM"]
        P3["TTS"]
        P4["output"]
        P5["Context.assistant"]
    end

    T0 --> T1 --> T2
    T2 -- yes --> T3 --> W0 --> W1
    W1 -- ready --> W2 --> P1 --> P2 --> P3 --> P4 --> P5 --> W3 --> W4 --> W0
    T2 -- no --> T1

    subgraph Echo_Optional
        E0["collect LLM text"]
        E1{has final}
        E2["send chat: @user final[0..350]"]
    end

    P2 -.-> E0 --> E1
    E1 -- yes --> E2
```

- Keyword detection is configurable via `TWITCH_TRIGGER_WORDS` (default: `questboo,duck,chicken`).
- Echo-to-chat is controlled by `TWITCH_ECHO_ASSISTANT_TO_CHAT` (enabled by default).
- Broadcaster ID and user token are resolved to enable sending chat messages.
