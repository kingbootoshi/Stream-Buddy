/**
 * Minimal client-side logger with console-level routing.
 *
 * Why: In Node we would use Winston, but for a browser overlay we avoid
 * bundling server-oriented transports. This wrapper mirrors the API surface we
 * commonly use, so future migration to Winston in a web-worker is trivial.
 */
type LogMethod = (message: string, meta?: Record<string, unknown>) => void;

class BrowserLogger {
  private readonly scope: string;
  public info: LogMethod;
  public warn: LogMethod;
  public error: LogMethod;
  public debug: LogMethod;

  constructor(scope: string) {
    this.scope = scope;
    this.info = (message, meta) => console.info(`[INFO] [${this.scope}] ${message}`, meta ?? '');
    this.warn = (message, meta) => console.warn(`[WARN] [${this.scope}] ${message}`, meta ?? '');
    this.error = (message, meta) => console.error(`[ERROR] [${this.scope}] ${message}`, meta ?? '');
    this.debug = (message, meta) => console.debug(`[DEBUG] [${this.scope}] ${message}`, meta ?? '');
  }
}

/** Create a namespaced logger. */
export const createLogger = (scope: string) => new BrowserLogger(scope);


