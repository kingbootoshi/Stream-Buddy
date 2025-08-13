import type { DuckBuddy } from './DuckBuddy'
import { createLogger } from './logger'

/**
 * OverlayController: connects to the backend WS control-plane and maps
 * events to DuckBuddy animation states while running an idle/walk scheduler.
 *
 * Why: Decouple voice pipeline from rendering; keep the animation logic
 * deterministic and recoverable on reconnect via snapshot.
 */
type Mood = 'neutral' | 'happy' | 'angry'

type Snapshot = {
  listening: boolean
  talking: boolean
  mood: Mood
  hat: 'hat1' | 'hat2' | 'hat3' | null
  forcedState: 'idle' | 'walk' | 'handsCrossed' | null
}

type ServerEvent =
  | { v: 1; type: 'hello'; data: Snapshot }
  | { v: 1; type: 'listen_on' | 'listen_off' | 'stop_talking' }
  | { v: 1; type: 'start_talking'; data: { mood: Mood } }
  | { v: 1; type: 'set_hat'; data: { hat: 'hat1' | 'hat2' | 'hat3' | null } }
  | { v: 1; type: 'force_state'; data: { state: 'idle' | 'walk' | 'handsCrossed' | null } }
  | { v: 1; type: 'ping' }
  | { v: 1; type: string; data?: any }

export class OverlayController {
  private log = createLogger('overlay-ws')
  private ws!: WebSocket
  private url: string
  private buddy: DuckBuddy
  private reconnectMs = 1000
  private readonly maxReconnectMs = 8000
  private talking = false
  private listening = false
  private defaultMood: Mood = 'neutral'
  private forcedState: 'idle' | 'walk' | 'handsCrossed' | null = null

  // Idle/walk scheduler for background behavior
  private isRoaming = true
  private cycleTimer = 0
  private nextCycle = 2500 + Math.random() * 4000

  constructor(url: string, buddy: DuckBuddy) {
    this.url = url
    this.buddy = buddy
  }

  /** Establish WS connection with exponential backoff. */
  start(): void {
    this.connect()
  }

  /** Advance controller timers each frame. */
  update(dtMs: number): void {
    if (this.talking) return
    if (this.forcedState) return
    this.cycleTimer += dtMs
    if (this.cycleTimer >= this.nextCycle) {
      this.isRoaming = !this.isRoaming
      this.buddy.setState(this.isRoaming ? 'walk' : 'idle')
      this.cycleTimer = 0
      this.nextCycle = 2500 + Math.random() * 4000
    }
  }

  private connect(): void {
    this.ws = new WebSocket(this.url)
    this.ws.onopen = () => {
      this.log.info('WS connected')
      this.reconnectMs = 1000
      this.send({ v: 1, type: 'ready', data: { client: 'overlay@1' } })
    }
    this.ws.onmessage = (ev) => this.handle(JSON.parse(ev.data) as ServerEvent)
    this.ws.onerror = () => {
      this.log.warn('WS error')
      try {
        this.ws.close()
      } catch {}
    }
    this.ws.onclose = () => {
      this.log.warn('WS closed; reconnecting')
      setTimeout(() => this.connect(), (this.reconnectMs = Math.min(this.maxReconnectMs, this.reconnectMs * 1.5)))
    }
  }

  private send(msg: any): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg))
  }

  private handle(evt: ServerEvent): void {
    this.log.debug('evt', { type: (evt as any).type })
    switch (evt.type) {
      case 'hello': {
        const s = evt.data as Snapshot
        this.listening = s.listening
        this.talking = s.talking
        this.defaultMood = s.mood
        this.forcedState = s.forcedState
        if (s.hat !== undefined) this.buddy.setHat(s.hat)
        if (this.forcedState) this.applyForced(this.forcedState)
        else if (s.talking) this.applyTalking(s.mood)
        else if (s.listening) this.buddy.setState('handsCrossed')
        else this.buddy.setState('walk')
        break
      }
      case 'listen_on':
        this.listening = true
        this.buddy.setState('handsCrossed')
        break
      case 'listen_off':
        this.listening = false
        this.forcedState = null
        this.talking = false
        this.buddy.setState('walk')
        break
      case 'start_talking':
        this.talking = true
        this.applyTalking((evt as any).data?.mood ?? this.defaultMood)
        break
      case 'stop_talking':
        this.talking = false
        if (!this.forcedState) this.buddy.setState('walk')
        break
      case 'set_hat':
        this.buddy.setHat((evt as any).data.hat)
        break
      case 'force_state':
        this.applyForced((evt as any).data.state)
        break
      case 'ping':
        this.send({ v: 1, type: 'pong' })
        break
    }
  }

  private applyTalking(mood: Mood): void {
    const map = { neutral: 'talk', happy: 'happyTalk', angry: 'angryTalk' } as const
    this.buddy.setState(map[mood])
  }

  private applyForced(state: 'idle' | 'walk' | 'handsCrossed' | null): void {
    this.forcedState = state
    if (state) this.buddy.setState(state)
    else this.buddy.setState(this.talking ? 'talk' : 'walk')
  }
}


