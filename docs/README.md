## Duck Buddy – Backend/Frontend Coordination

This project wires a Pipecat voice backend to a PixiJS overlay for OBS. The
backend stays fully local (no WebRTC), while a tiny control plane broadcasts
animation cues over WebSocket so the overlay animates in sync with speech.

Key links:
- Backend control server: `backend/overlay_server.py`
- Voice pipeline: `backend/main.py`
- Overlay controller: `src/overlay-controller.ts`
- Full integration guide: `docs/integration-voice-agent.md`

Highlights:
- Push‑to‑talk: mic muted by default; toggle listening with a hotkey
- Echo prevention: STT is muted during TTS (no self-hear/feedback)
- Stateful WS with snapshot for robust reconnect in OBS

### Duck Buddy Overlay — Developer Guide

This project renders a pixel-art companion (“Quest Boo”) using PixiJS v8. The character is a paper-doll rig built from layered sprites so face, mouth, hands, feet, hat, etc. can animate independently. This guide orients new contributors and backend integrators.

#### Key files
- `src/DuckBuddy.ts`: Rig implementation and simple state machine. Manages layered parts, blinking, bobbing, walking, talking variants, and facing (horizontal mirroring).
- `src/main.ts`: App bootstrap, asset loading, renderer setup, and a small “auto-walk” controller that moves the character horizontally.
- `public/assets/*`: All PNG layers used by the rig. Filenames are referenced by alias in `src/main.ts` and typed in `DuckBuddy.ts`.
- `src/logger.ts`: Minimal browser logger with console routing. Keep logs structured; switch to Winston-in-worker later if needed.

#### Runtime architecture
- Pixi v8 `Application` is initialized in `src/main.ts`. `DuckBuddy` is added to stage.
- A ticker calls `buddy.update(deltaMS)` each frame.
- The rig applies per-part animations internally (idle bobbing, blinking, mouth/feet loops).
- An external controller in `main.ts` moves the character horizontally while state is `walk` and flips facing using `buddy.setFacing()`.

#### States the rig understands
- `idle`: Stationary with subtle bobbing and natural blinking.
- `walk`: Feet loop and body bobs; horizontal motion is controlled externally and only occurs while this state is active.
- `talk`: Neutral talking mouth loop, default eyes.
- `happyTalk`: Talking mouth loop + happy eyes; blinking disabled to keep expression fixed.
- `angryTalk`: Angry mouth loop + angry eyes.
- `handsCrossed`: Static pose for hands.

Call `buddy.setState(state)` to switch. Call `buddy.getState()` to read current state.

#### Facing (left/right)
- Use `buddy.setFacing('left' | 'right')`. The rig mirrors by setting a negative X scale internally and persists across state switches. This is the default behavior for all future animation changes.

#### Pixel scale and crisp rendering
- Call `buddy.setPixelScale(multiplier)` to scale the rig without blur. `main.ts` sets `SCALE_MODES.NEAREST` on all textures to keep pixels sharp.

#### Logging
- Import `createLogger` from `src/logger.ts` to log with a scope name. Prefer structured meta objects. Example: `log.info('Textures loaded', { count })`.

#### Keyboard quick-test shortcuts (dev only)
- `1` idle, `2` walk, `3` talk, `4` angryTalk, `6` happyTalk, `5` handsCrossed, `h` cycle hats, `H` remove hat.

#### Where to look next
- Animation details and how to add new animations: see `docs/animations.md`.
- Voice agent integration plan and front-end API: see `docs/integration-voice-agent.md`.


