### Voice Agent Integration Plan

Goal: When the backend streams audio (or signals speech activity), the overlay should play a selected talking animation (`neutral` | `happy` | `angry`). While not talking, Quest Boo should alternate between idle and autonomous walking. When the stream ends, he returns to the idle/walk cycle.

This document proposes a front-end control API and message schema to drive the overlay from any backend (WebSocket, SSE, or postMessage). Implementers can adapt transport as needed.

#### Front-end control API (to be added)
We will expose a small controller module, conceptually as follows:

```ts
// Pseudo-API shape (to be implemented)
type TalkMood = 'neutral' | 'happy' | 'angry'

interface OverlayController {
  // Start talking animation in the specified mood; remains active until stopTalking.
  startTalking(mood: TalkMood): void

  // Stop talking and resume normal idle/walk cycles.
  stopTalking(): void

  // Optional: force walking/idle for testing
  forceWalk(): void
  forceIdle(): void
  clearForces(): void
}

// The instance would be attached to window for easy integration:
// (window as any).overlay = controller
```

Under the hood:
- `startTalking()` maps mood to `DuckBuddy.setState('talk'|'happyTalk'|'angryTalk')`.
- Movement controller in `main.ts` continues to run but will only translate X while the rig is in `walk` state. When `startTalking()` is active, we set a timer to pause horizontal movement (character stays put) and keep only mouth/eyes animating.
- `stopTalking()` resumes the background cycle: random walk interleaved with idle.

#### Event/message schema
Transport-agnostic JSON messages suggested for a WS/SSE channel named `overlay-control`:

```json
{ "type": "start_talking", "mood": "neutral" }
{ "type": "start_talking", "mood": "happy" }
{ "type": "start_talking", "mood": "angry" }
{ "type": "stop_talking" }
```

Notes:
- Backends that already stream audio can send `start_talking` when speech energy crosses a VAD threshold, and `stop_talking` after trailing silence (e.g., >300ms) or after the stream completes.
- If real audio waveforms are available in the browser, the mouth animation speed can be modulated by RMS/energy for extra liveliness (optional future work).

#### Idle/Walk scheduler
The current code moves horizontally whenever state is `walk`. To have Quest Boo “sometimes idle, sometimes roam”, add a simple scheduler (to be implemented):

```ts
// Conceptual only — integrate into main.ts
let cycleTimerMs = 0
let nextCycleMs = 2500 + Math.random() * 4000
let isRoaming = true

function updateCycle(dtMs: number) {
  if (overlayIsTalking) return // talking overrides cycles
  cycleTimerMs += dtMs
  if (cycleTimerMs >= nextCycleMs) {
    isRoaming = !isRoaming
    buddy.setState(isRoaming ? 'walk' : 'idle')
    cycleTimerMs = 0
    nextCycleMs = 2500 + Math.random() * 4000
  }
}
```

Integrate by calling `updateCycle(dtMs)` in the ticker before motion. Movement logic remains unchanged: it only translates X when the state is `walk`.

#### Minimal backend sequence example
1. Page connects a WebSocket to your backend and subscribes to `overlay-control`.
2. Backend starts streaming TTS/voice; on first audio chunk emit `{ type: 'start_talking', mood: 'happy' }`.
3. Page calls `overlay.startTalking('happy')` which sets `happyTalk` state and pauses horizontal translation.
4. When audio stream completes (or VAD detects silence), backend emits `{ type: 'stop_talking' }`.
5. Page calls `overlay.stopTalking()` which resumes the idle/walk scheduler.

#### Security and resilience
- Validate incoming message types and fields before acting.
- Ignore duplicate `start_talking` if already talking with same mood.
- Time out talking after N seconds as a guardrail in case the backend disconnects.

#### TODOs for implementation (tracked here for future PR)
- Implement `OverlayController` in `main.ts` and attach to `window`.
- Add the idle/walk scheduler stub above.
- Optionally expose `setSpeed`, `setBounds`, and `setFacing` overrides for experimentation.


