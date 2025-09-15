### Duck Buddy AI Pipeline

The pipeline is assembled in `backend/src/pipeline/builder.py` and run by `backend/src/pipeline/runner.py`. It features a parallel architecture to process voice input from the microphone and text input from Twitch chat simultaneously. Both branches merge into a common tail, allowing the AI to use a shared context, LLM, and TTS service.

Downstream frame handlers in `backend/src/pipeline/handlers.py` log activity and synchronize the overlay's animations by updating the shared state.

```mermaid
flowchart TD
    subgraph Transport
        A["Mic Audio Input"]
        J["Audio Output"]
    end

    subgraph ParallelPipeline
        direction LR
        subgraph Voice_Branch
            G["MicGate<br/>allow when listening=true and speaking=false"]
            B["STT<br/>audio -> transcription"]
            C["STT Mute<br/>drop STT while TTS speaking"]
            VP["Producer: voice_usertext<br/>Transcription → LLM Message"]
        end
        subgraph Twitch_Branch
            TS["TwitchChatSource<br/>ingest(user,text) → TextFrame"]
            TP["Producer: twitch_usertext<br/>TextFrame → LLM Message"]
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
        T0["Twitch EventSub WS"]
        T1["event_message"]
        T2{keyword hit}
        T3["on_keyword_hit"]
        I0["source.ingest(user,text)"]
    end

    T0 --> T1 --> T2
    T2 -- yes --> T3 --> I0 -.-> TS
    T2 -- no --> T1
```

- **Voice Branch**: The voice path is gated by `MicGate` to enforce push-to-talk and is muted by `STTMuteFilter` during TTS to prevent feedback loops.
- **Twitch Branch**: The `TwitchChatSource` ingests chat messages programmatically from the Twitch integration and emits them into the pipeline, independent of the microphone's state.
- **Merge & Tail**: Producers in each branch create a normalized frame, which is then picked up by consumers. These consumers feed into the shared `Context.user` processor, ensuring both voice and chat contribute to the same conversational history for the LLM.
- **Twitch Integration**: A TwitchIO client listens for chat messages via EventSub. When a trigger keyword is detected, the message is sent to the `TwitchChatSource` to be injected into the AI pipeline.