import { AnimatedSprite, Container, Texture } from 'pixi.js';

/**
 * DuckBuddy: simple paper-doll character rig composed of layered sprites.
 *
 * Why: Keeps each body part independent (eyes, mouth, etc.) so we can swap
 * textures and animate parts without redrawing into a single bitmap.
 *
 * How: Uses PixiJS Containers + AnimatedSprite. Each part is its own
 * AnimatedSprite so we can loop frames (e.g., walking feet, talking mouth)
 * while leaving other parts static. Timing is dt-based to be framerate-agnostic.
 */
export type DuckState = 'idle' | 'walk' | 'talk' | 'angryTalk' | 'handsCrossed';

/**
 * Texture map for all required parts. Filenames must exist in `public/assets`.
 * Adjust aliases if your asset names differ.
 */
export type DuckTextures = Record<
  | 'body' | 'head'
  | 'eyesOpen' | 'eyesBlink1' | 'eyesBlink2' | 'eyesBlink3' | 'eyesHappy' | 'eyesAngry'
  | 'mouthStatic' | 'mouthTalk1' | 'mouthTalk2' | 'mouthTalk3'
  | 'mouthAngry1' | 'mouthAngry2' | 'mouthAngry3'
  | 'hands' | 'handsCrossed' | 'handsPointing'
  | 'feetIdle' | 'feet1' | 'feet2' | 'feet3' | 'feet4' | 'feet5'
  | 'hat1' | 'hat2' | 'hat3'
  , Texture
>;

type Part = 'body' | 'feet' | 'head' | 'hands' | 'mouth' | 'eyes' | 'hat';

export class DuckBuddy extends Container {
  private tex: DuckTextures;
  private parts: Record<Part, AnimatedSprite>;
  private state: DuckState = 'idle';
  
  /**
   * Base uniform scale for the character (e.g., 10 for 10x). The idle
   * breathing animation multiplies against this so we never stomp caller scale.
   */
  private baseScale = 1;

  // timers/state for micro-behaviors
  private elapsed = 0;      // ms since last blink timer reset
  private nextBlinkIn = this.randBlinkMs();
  private walkPhase = 0;    // controls bobbing motion
  private walkBaseY: number | null = null; // preserves original Y during walk

  constructor(tex: DuckTextures) {
    super();
    this.tex = tex;
    this.sortableChildren = true; // honor zIndex for stable layering

    // factory for parts
    const makePart = (frames: Texture[] | Texture, z: number): AnimatedSprite => {
      const textures = Array.isArray(frames) ? frames : [frames];
      const sprite = new AnimatedSprite(textures);
      // Use top-left origin so all assets that were authored to align at (0,0)
      // in Photoshop will align perfectly here as well.
      sprite.anchor.set(0, 0);
      sprite.zIndex = z;
      sprite.animationSpeed = 0.12;
      sprite.play();
      this.addChild(sprite);
      return sprite;
    };

    // create parts and layer order
    this.parts = {
      body:  makePart(this.tex.body, 0),
      feet:  makePart(this.tex.feetIdle, 1),
      head:  makePart(this.tex.head, 2),
      hands: makePart(this.tex.hands, 3),
      mouth: makePart(this.tex.mouthStatic, 4),
      eyes:  makePart(this.tex.eyesOpen, 5),
      hat:   makePart(this.tex.hat1 ?? Texture.EMPTY, 6),
    };

    // All parts share the same origin (0,0). If your art needs nudging,
    // adjust these offsets; default is zero for pixel-perfect stack.
    this.parts.feet.position.set(0, 0);
    this.parts.mouth.position.set(0, 0);
    this.parts.eyes.position.set(0, 0);
    this.parts.hands.position.set(0, 0);
    this.parts.hat.position.set(0, 0);

    // Center the whole rig for easier placement while keeping per-part
    // origin at (0,0). We derive pivot from the body texture size.
    const w = this.tex.body.width;
    const h = this.tex.body.height;
    this.pivot.set(w / 2, h / 2);

    this.setHat(null);
    this.setState('idle');
  }

  /** Update tick; call every frame with delta time in milliseconds. */
  update(dt: number): void {
    this.elapsed += dt;

    // subtle idle "breath" scale when not walking
    if (this.state !== 'walk') {
      const t = performance.now() * 0.002;
      const breathe = 1 + Math.sin(t) * 0.005;
      // Keep crisp pixel look by scaling uniformly from the configured base
      this.scale.set(this.baseScale * breathe);
    } else {
      // While walking keep exact base scale (no breathing wobble)
      this.scale.set(this.baseScale);
    }

    // schedule blinks during any state except while a blink animation is in progress
    if (this.elapsed >= this.nextBlinkIn) {
      this.playBlink();
      this.elapsed = 0;
      this.nextBlinkIn = this.randBlinkMs();
    }

    if (this.state === 'walk') {
      // Capture base Y once to avoid teleporting when we override position
      if (this.walkBaseY == null) this.walkBaseY = this.y;
      this.walkPhase += dt * 0.012; // speed
      this.y = this.walkBaseY + Math.sin(this.walkPhase) * 2; // bobbing about base
    }
  }

  /** Change the rig's high-level state; resets part animations accordingly. */
  setState(next: DuckState): void {
    if (this.state === next) return;
    this.state = next;

    // reset default frames for all parts
    this.parts.eyes.textures = [this.tex.eyesOpen];
    this.parts.eyes.gotoAndStop(0);
    this.parts.mouth.textures = [this.tex.mouthStatic];
    this.parts.mouth.gotoAndStop(0);
    this.parts.hands.textures = [this.tex.hands];
    this.parts.hands.gotoAndStop(0);
    this.parts.feet.textures = [this.tex.feetIdle];
    this.parts.feet.gotoAndStop(0);

    switch (next) {
      case 'idle':
        // no-op; blink/breathe handled in update()
        break;

      case 'walk': {
        // remember current vertical position for bobbing reference
        this.walkBaseY = this.y;
        const walkSeq = [
          this.tex.feet1, this.tex.feet2, this.tex.feet3,
          this.tex.feet4, this.tex.feet5, this.tex.feet4,
          this.tex.feet3, this.tex.feet2,
        ];
        this.parts.feet.textures = walkSeq;
        this.parts.feet.animationSpeed = 0.18;
        this.parts.feet.loop = true;
        this.parts.feet.play();
        break;
      }

      case 'talk': {
        // neutral talking loop (3 frames available)
        const talkSeq = [
          this.tex.mouthTalk1, this.tex.mouthTalk2, this.tex.mouthTalk3,
          this.tex.mouthTalk2,
        ];
        this.parts.mouth.textures = talkSeq;
        this.parts.mouth.animationSpeed = 0.22;
        this.parts.mouth.loop = true;
        this.parts.mouth.play();
        break;
      }

      case 'angryTalk': {
        const talkSeq = [
          this.tex.mouthAngry1, this.tex.mouthAngry2, this.tex.mouthAngry3,
          this.tex.mouthAngry2,
        ];
        this.parts.mouth.textures = talkSeq;
        this.parts.mouth.animationSpeed = 0.24;
        this.parts.mouth.loop = true;
        this.parts.mouth.play();
        this.parts.eyes.textures = [this.tex.eyesAngry];
        this.parts.eyes.gotoAndStop(0);
        break;
      }

      case 'handsCrossed': {
        this.parts.hands.textures = [this.tex.handsCrossed];
        this.parts.hands.gotoAndStop(0);
        break;
      }
    }
    if (next !== 'walk') {
      // reset walk offset when leaving walk state
      if (this.walkBaseY != null) this.y = this.walkBaseY;
      this.walkBaseY = null;
    }
  }

  /** Set or hide hat by alias; pass null to hide. */
  setHat(alias: 'hat1' | 'hat2' | 'hat3' | null): void {
    if (!alias) {
      this.parts.hat.visible = false;
      return;
    }
    this.parts.hat.visible = true;
    this.parts.hat.textures = [this.tex[alias]];
    this.parts.hat.gotoAndStop(0);
  }

  /** One-shot blink sequence (open → 1 → 2 → 3 → 2 → 1 → open). */
  private playBlink(): void {
    const seq = [
      this.tex.eyesBlink1, this.tex.eyesBlink2, this.tex.eyesBlink3,
      this.tex.eyesBlink2, this.tex.eyesBlink1, this.tex.eyesOpen,
    ];
    this.parts.eyes.textures = seq;
    this.parts.eyes.loop = false;
    this.parts.eyes.animationSpeed = 0.45;
    this.parts.eyes.onComplete = () => {
      this.parts.eyes.textures = [this.tex.eyesOpen];
      this.parts.eyes.gotoAndStop(0);
    };
    this.parts.eyes.gotoAndPlay(0);
  }

  /** Returns a natural blink interval in milliseconds (2.5s–6s). */
  private randBlinkMs(): number {
    return 2500 + Math.random() * 3500;
  }

  /**
   * Set the pixel-art scale multiplier.
   *
   * Why: We want to scale a 64x64 character cleanly (nearest-neighbor) without
   * the breathing animation resetting it back to ~1. This method updates the
   * base factor used by all internal animations.
   */
  public setPixelScale(multiplier: number): void {
    this.baseScale = Math.max(0.0001, multiplier);
    this.scale.set(this.baseScale);
  }
}


