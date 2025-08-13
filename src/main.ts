import './style.css'
import { Application, Assets, SCALE_MODES, Texture } from 'pixi.js'
import { DuckBuddy } from './DuckBuddy'
import type { DuckTextures } from './DuckBuddy'
import { createLogger } from './logger'
import { OverlayController } from './overlay-controller'

const log = createLogger('overlay')

/**
 * Load and alias all textures used by the DuckBuddy rig.
 * Adjust paths if your asset folder differs.
 */
async function loadDuckTextures(): Promise<DuckTextures> {
  const assets = {
    body: '/assets/Body.png',
    head: '/assets/Head.png',

    eyesOpen: '/assets/Eyes.png',
    eyesBlink1: '/assets/Eyes_Blinking1.png',
    eyesBlink2: '/assets/Eyes_Blinking2.png',
    eyesBlink3: '/assets/Eyes_Blinking3.png',
    eyesHappy: '/assets/Eyes_Happy.png',
    eyesAngry: '/assets/Eyes_Angry.png',

    mouthStatic: '/assets/Mouth.png',
    mouthTalk1: '/assets/Mouth_Talking1.png',
    mouthTalk2: '/assets/Mouth_Talking2.png',
    mouthTalk3: '/assets/Mouth_Talking3.png',

    mouthAngry1: '/assets/Mouth_Talking_Angry1.png',
    mouthAngry2: '/assets/Mouth_Talking_Angry2.png',
    mouthAngry3: '/assets/Mouth_Talking_Angry3.png',

    hands: '/assets/Hands.png',
    handsCrossed: '/assets/Hands_Crossed.png',
    handsPointing: '/assets/Hands_Pointing.png',

    feetIdle: '/assets/Feet.png',
    feet1: '/assets/Feet_Walking1.png',
    feet2: '/assets/Feet_Walking2.png',
    feet3: '/assets/Feet_Walking3.png',
    feet4: '/assets/Feet_Walking4.png',
    feet5: '/assets/Feet_Walking5.png',

    hat1: '/assets/Hat1.png',
    hat2: '/assets/Hat2.png',
    hat3: '/assets/Hat3.png',
  } as const

  const entries = Object.entries(assets)
  const loaded = await Promise.all(entries.map(([alias, src]) => Assets.load({ alias, src })))
  const textures = Object.fromEntries(loaded.map((t, i) => [entries[i][0], t])) as DuckTextures
  return textures
}

async function main() {
  // Initialize Assets (required in v8)
  await Assets.init({ basePath: '/' })

  // Create app and initialize with modern API (v8)
  const app = new Application()
  await app.init({ backgroundAlpha: 0, resizeTo: window })
  document.body.appendChild(app.canvas as HTMLCanvasElement)

  const textures = await loadDuckTextures()
  log.info('Textures loaded')

  const buddy = new DuckBuddy(textures)
  buddy.position.set(app.screen.width / 2, app.screen.height / 2)
  app.stage.addChild(buddy)

  // Connect overlay controller to backend WS control-plane
  const overlayWs = (import.meta as any).env?.VITE_OVERLAY_WS_URL || 'ws://127.0.0.1:8710/ws/overlay'
  const controller = new OverlayController(overlayWs, buddy)
  controller.start()

  // Ensure pixel-art textures stay sharp at large scales by forcing
  // nearest-neighbor sampling and disabling mipmaps on every baseTexture.
  // Doc note: In PixiJS v8, sampling is controlled via BaseTexture scaleMode
  // and mipmapping via BaseTexture.mipmap.
  ;(Object.values(textures) as Texture[]).forEach((tex) => {
    // Defensive: some entries (like hat when hidden) may be Texture.EMPTY
    const base = tex.baseTexture;
    base.scaleMode = SCALE_MODES.NEAREST;
  })

  // Scale the 64x64 rig to 10x while preserving crisp pixels. Breathing logic
  // multiplies against this base so it won’t reset our scale.
  buddy.setPixelScale(10)

  // --- Simple horizontal auto-walk controller ---------------------------------
  /**
   * Runtime controller for autonomous side-to-side walking.
   *
   * Rules:
   * - Only moves when the rig is in `walk` state
   * - Keeps Y position stable (X only), letting the rig handle tiny bobbing
   * - Randomly flips direction over time and also bounces at the edges
   */
  const walkCtrl = {
    direction: 1 as 1 | -1,          // 1 moves right, -1 moves left
    // Increase speed by 1.5x as requested (was 48)
    speedPxPerSec: 72,                // horizontal speed in screen pixels per second
    edgeMarginPx: 32,                 // soft margin to avoid hugging screen edge
    flipTimerMs: 0,                   // accumulates time until next random flip
    nextFlipInMs: 1500 + Math.random() * 2500, // randomized initial flip window
  }

  // Start walking by default for the requested behavior
  buddy.setState('walk')

  // drive per-frame updates (animation + controller)
  app.ticker.add((t) => {
    const dtMs = t.deltaMS
    buddy.update(dtMs)
    controller.update(dtMs)

    // Move only while in 'walk' state; pause movement in other states
    if (buddy.getState() !== 'walk') return

    // Compute dynamic bounds each frame so we use the full browser width
    // while keeping the character fully visible at the edges. We derive a
    // half-width from the rendered size (post-scale, post-mirror).
    const halfW = Math.max(0, Math.round(buddy.width / 2))
    const minX = halfW
    const maxX = Math.max(minX, app.screen.width - halfW)

    // Random direction flip over time
    walkCtrl.flipTimerMs += dtMs
    if (walkCtrl.flipTimerMs >= walkCtrl.nextFlipInMs) {
      walkCtrl.direction = (walkCtrl.direction === 1 ? -1 : 1)
      walkCtrl.flipTimerMs = 0
      walkCtrl.nextFlipInMs = 1500 + Math.random() * 2500
      log.debug('Random flip', { direction: walkCtrl.direction })
    }

    // Integrate horizontal motion
    const dx = walkCtrl.direction * walkCtrl.speedPxPerSec * (dtMs / 1000)
    buddy.x += dx

    // Face where we're going and snap to integer pixels for choppier walk
    buddy.setFacing(walkCtrl.direction === 1 ? 'right' : 'left')
    buddy.x = Math.round(buddy.x)

    // Edge bounce with clamping
    if (buddy.x <= minX) {
      buddy.x = minX
      if (walkCtrl.direction === -1) {
        walkCtrl.direction = 1
        walkCtrl.flipTimerMs = 0
        log.debug('Edge bounce -> right')
      }
    } else if (buddy.x >= maxX) {
      buddy.x = maxX
      if (walkCtrl.direction === 1) {
        walkCtrl.direction = -1
        walkCtrl.flipTimerMs = 0
        log.debug('Edge bounce -> left')
      }
    }
  })

  // Expose simple control API for OBS or devtools
  // window.duckBuddy.setState('talk'); window.duckBuddy.setHat('hat2')
  ;(window as unknown as { duckBuddy: DuckBuddy }).duckBuddy = buddy

  // Keyboard controls for quick testing in a browser
  window.addEventListener('keydown', (e) => {
    switch (e.key) {
      case '1': buddy.setState('idle'); break
      case '2': buddy.setState('walk'); break
      case '3': buddy.setState('talk'); break
      case '4': buddy.setState('angryTalk'); break
      case '6': buddy.setState('happyTalk'); break
      case '5': buddy.setState('handsCrossed'); break
      case 'h': {
        // Cycle through hats: hat1 -> hat2 -> hat3 -> none -> hat1 ...
        const current = (buddy as any).currentHat as 'hat1' | 'hat2' | 'hat3' | null | undefined
        const next = current === 'hat1' ? 'hat2' : current === 'hat2' ? 'hat3' : current === 'hat3' ? null : 'hat1'
        buddy.setHat(next)
        ;(buddy as any).currentHat = next
        break
      }
      case 'H': buddy.setHat(null); (buddy as any).currentHat = null; break
    }
  })
}

main().catch((err) => log.error('Failed to initialize', { err }))
