# Pipeline Architecture (Mermaid)

The pipeline merges concurrent Voice and Twitch branches into a single serialized turn stream, then runs LLM → TTS → Output. Turn arbitration ensures one active turn at a time with voice priority and fairness to chat.

```mermaid
flowchart LR
  %% Subgraphs for clarity
  subgraph Voice Branch
    A1[Mic Input] --> A2[MicGate]
    A2 --> A3[STT]
    A3 --> A4[STTMuteFilter]
    A4 --> A5[Voice Producer]
  end

  subgraph Twitch Branch
    B1[TwitchChatSource] --> B2[Twitch Producer]
  end

  %% Merge via consumers (already implicit in our build)
  A5 --> M1[Turn Arbiter]
  B2 --> M1

  %% Common tail
  M1 --> C1[Context Aggregator User]
  C1 --> G1[DropRawTextBeforeLLM]
  G1 --> L1[LLM Service]
  L1 --> T1[TTS Service]
  T1 --> O1[Audio Output]
  O1 --> C2[Context Aggregator Assistant]

  %% Overlay + State side-channel
  T1 -. emits .-> H1[TTS Events]
  H1 -. handlers .-> S1[Shared State]
  S1 -. notifies .-> E1[Overlay Event Bus]

  %% Twitch integration (out-of-band)
  subgraph Twitch Integration
    TI1[TwitchIO EventSub] -->|chat lines| B1
    C2 -. downstream frames .-> TI2[Twitch Chat Integration]
    TI2 -->|if origin=twitch| TI3[Username Reply to Chat]
  end
```

Notes
- TurnArbiter flips any incoming `run_llm=True` appends to `False`, queues them, and re-emits exactly one at a time with `run_llm=True`.
- The “busy” period is from release until TTS stops (handlers flip `state.tts_speaking` which the arbiter listens to).
- Chat echo triggers at the end of assistant responses only when the active turn’s origin is `twitch`.

