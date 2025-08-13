import './style.css'
import { Application, Assets } from 'pixi.js'
import { DuckBuddy } from './DuckBuddy'
import type { DuckTextures } from './DuckBuddy'
import { createLogger } from './logger'

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
  buddy.position.set(app.renderer.width / 2, app.renderer.height / 2 + 40)
  app.stage.addChild(buddy)

  // drive per-frame updates
  app.ticker.add((t) => buddy.update(t.deltaMS))

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
      case '5': buddy.setState('handsCrossed'); break
      case 'h': buddy.setHat('hat1'); break
      case 'H': buddy.setHat(null); break
    }
  })
}

main().catch((err) => log.error('Failed to initialize', { err }))
