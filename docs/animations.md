### Animation sets and how they work

The character is assembled from layered `AnimatedSprite`s with per-part texture sequences. Layers are rendered in this z-order:

1. body
2. feet
3. head
4. hands
5. mouth
6. eyes
7. hat

Textures are loaded and aliased in `src/main.ts` and typed in `DuckBuddy.ts` under `DuckTextures`. Each alias must map to an existing PNG in `public/assets`.

#### Eye animations
- Open: `eyesOpen`
- Blink: `eyesBlink1..3` then back to open, non-looping sequence. Triggered automatically every 2.5–6s while blinking is enabled.
- Happy: `eyesHappy` (static)
- Angry: `eyesAngry` (static)

#### Mouth animations
- Neutral talking: `mouthTalk1..3..2` looping
- Angry talking: `mouthAngry1..3..2` looping
- Static: `mouthStatic`

#### Feet animations
- Idle feet: `feetIdle` (static)
- Walking: `feet1..5..4..3..2` looping

#### State-to-animation mapping (simplified)
- `idle`: static parts, blinking on, idle bobbing on
- `walk`: feet loop on, idle bobbing applied to parts, horizontal movement driven externally
- `talk`: neutral talking mouth loop
- `happyTalk`: mouth loop + happy eyes, blinking disabled
- `angryTalk`: angry mouth loop + angry eyes
- `handsCrossed`: hands set to crossed texture

#### Adding a new animation/state
1. Add PNGs to `public/assets/` with consistent alignment (top-left origin). Keep the same canvas size as existing parts for pixel-perfect stacking.
2. In `src/main.ts`, add the paths to `assets` inside `loadDuckTextures()` and re-alias in the `DuckTextures` type if it’s a new alias.
3. In `src/DuckBuddy.ts`, update the `DuckTextures` type union to include the new alias(es).
4. In `DuckBuddy.setState()`, add a new `case` to define:
   - Which textures go into which part
   - Whether they loop
   - `animationSpeed` for the loop
   - Whether `blinkEnabled` should be true/false for this state
5. If needed, add micro-behavior in `update()` or helper functions (e.g., special bobbing rules). Keep all per-part movements integer pixel offsets to preserve crisp art.

#### Tips for authoring assets
- Use the same global canvas size for every body part PNG so their (0,0) aligns.
- Avoid semi-transparent edges on pixel art; sharp alpha edges read better at large scales.
- Keep motion arcs simple (2–5 frames) for an old-school feel.

#### Mirroring and facing
- Horizontal direction is set with `buddy.setFacing('left' | 'right')` which uses negative X scale internally. This persists across state switches and should be considered the default orientation for any new animation.


