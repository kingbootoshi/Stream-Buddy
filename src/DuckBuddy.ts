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
export type DuckState = 'idle' | 'walk' | 'talk' | 'happyTalk' | 'angryTalk' | 'handsCrossed';

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
  private blinkEnabled = true; // gate for automated blinking
  private walkPhase = 0;    // controls bobbing motion
  private walkBaseY: number | null = null; // preserves original Y during walk
  private bobPhase = 0;     // phase for idle bobbing
  private bobAmplitudePx = 1; // max idle offset in source pixels (integer)
  private bobSpeed = 0.004;   // phase increment multiplier per ms
  private headBobFactor = 1.5;  // scale head offset relative to body (1 = same)
  private headFollowsBody = true; // keep head at least as far down as body to avoid neck gap
  private baseYByPart: Record<Part, number> = {
    body: 0, feet: 0, head: 0, hands: 0, mouth: 0, eyes: 0, hat: 0,
  };

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
    // record default Y for pixel-perfect bobbing offsets
    (Object.keys(this.parts) as Part[]).forEach((key) => {
      this.baseYByPart[key] = this.parts[key].y;
    });

    this.setHat(null);
    this.setState('idle');
  }

  /** Update tick; call every frame with delta time in milliseconds. */
  update(dt: number): void {
    this.elapsed += dt;

    // Always enforce caller's configured base pixel scale; no size wobble.
    this.scale.set(this.baseScale);

    // schedule blinks only when enabled for the current state
    if (this.blinkEnabled && this.elapsed >= this.nextBlinkIn) {
      this.playBlink();
      this.elapsed = 0;
      this.nextBlinkIn = this.randBlinkMs();
    }

    if (this.state === 'walk') {
      // Capture base Y once to avoid teleporting when we override position
      if (this.walkBaseY == null) this.walkBaseY = this.y;
      this.walkPhase += dt * 0.012; // speed
      this.y = this.walkBaseY + Math.sin(this.walkPhase) * 2; // bobbing about base
      // Disable per-part idle bobbing while walking; restore to base Y.
      this.applyPartOffsets(0, 0);
    } else {
      // Pixel-perfect idle bobbing: move torso and head clusters by integer px.
      this.bobPhase += dt * this.bobSpeed; // slower than walk bob
      const s = Math.sin(this.bobPhase);
      // Prevent torso from moving up relative to the feet by clamping
      // negative (upward) offsets to 0px. This keeps the seam one-pixel thick.
      const bodyOffset = Math.max(0, Math.round(s * this.bobAmplitudePx));
      // Head follows body down to keep the neck seam one pixel. It can move
      // more than body (factor > 1) but never less when following is enabled.
      const headRaw = Math.round(s * this.bobAmplitudePx * this.headBobFactor);
      const headDown = Math.max(0, headRaw);
      const headOffset = this.headFollowsBody ? Math.max(bodyOffset, headDown) : headDown;
      this.applyPartOffsets(bodyOffset, headOffset);
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

    // default: enable blinking, then specialize per state
    this.blinkEnabled = true;

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

      case 'happyTalk': {
        // happy eyes + neutral talking mouth
        const talkSeq = [
          this.tex.mouthTalk1, this.tex.mouthTalk2, this.tex.mouthTalk3,
          this.tex.mouthTalk2,
        ];
        this.parts.mouth.textures = talkSeq;
        this.parts.mouth.animationSpeed = 0.22;
        this.parts.mouth.loop = true;
        this.parts.mouth.play();
        this.parts.eyes.textures = [this.tex.eyesHappy];
        this.parts.eyes.gotoAndStop(0);
        // Keep happy eyes; disable auto blink while in this state
        this.blinkEnabled = false;
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
      // Ensure part Y starts from base when entering non-walk states
      this.applyPartOffsets(0, 0);
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
   * Apply pixel-art bobbing offsets to grouped parts.
   *
   * - bodyGroupOffset: applied to torso-related parts (body, hands)
   * - headGroupOffset: applied to head-related parts (head, eyes, mouth, hat)
   *
   * Offsets are in source pixels (pre-scale). Values are rounded externally
   * to preserve crisp edges.
   */
  private applyPartOffsets(bodyGroupOffset: number, headGroupOffset: number): void {
    // Torso cluster
    this.parts.body.y  = this.baseYByPart.body  + bodyGroupOffset;
    this.parts.hands.y = this.baseYByPart.hands + bodyGroupOffset;
    // Head cluster
    this.parts.head.y  = this.baseYByPart.head  + headGroupOffset;
    this.parts.eyes.y  = this.baseYByPart.eyes  + headGroupOffset;
    this.parts.mouth.y = this.baseYByPart.mouth + headGroupOffset;
    this.parts.hat.y   = this.baseYByPart.hat   + headGroupOffset;
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

  /**
   * Configure idle bobbing at runtime.
   *
   * - amplitudePx: how many source pixels to move up/down at peaks (int suggested)
   * - speed: phase speed multiplier (higher = faster)
   * - headFactor: head offset relative to body (e.g., 0.8 = subtler head)
   */
  public setIdleBob(params: { amplitudePx?: number; speed?: number; headFactor?: number; headFollowsBody?: boolean }): void {
    if (params.amplitudePx != null) this.bobAmplitudePx = Math.max(0, params.amplitudePx | 0);
    if (params.speed != null) this.bobSpeed = Math.max(0, params.speed);
    if (params.headFactor != null) this.headBobFactor = params.headFactor;
    if (params.headFollowsBody != null) this.headFollowsBody = params.headFollowsBody;
  }
}


