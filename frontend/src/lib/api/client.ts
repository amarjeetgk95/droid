// Shared HTTP core. Backend is localhost-only; frontend stays on Firebase.
// NEXT_PUBLIC_API_URL override wins, else local backend.
const DEFAULT_API_URL = 'http://127.0.0.1:8000';

function resolveApiBase(): string {
  if (typeof window !== 'undefined') {
    // 1. URL search param: ?api=https://... (enables instant mobile testing without rebuild)
    try {
      const params = new URLSearchParams(window.location.search);
      const queryApi = params.get('api');
      if (queryApi && /^https?:\/\//i.test(queryApi)) {
        const clean = queryApi.replace(/\/+$/, '');
        localStorage.setItem('droid_custom_api_url', clean);
        return clean;
      }
    } catch {}

    // 2. Saved custom API URL in localStorage
    try {
      const saved = localStorage.getItem('droid_custom_api_url');
      if (saved && /^https?:\/\//i.test(saved)) {
        return saved.replace(/\/+$/, '');
      }
    } catch {}

    // 3. Ignore baked-in trycloudflare.com tunnels (ephemeral quick tunnels die quickly)
    const envUrl = process.env.NEXT_PUBLIC_API_URL;
    if (envUrl && !envUrl.includes('trycloudflare.com')) {
      return envUrl.replace(/\/+$/, '');
    }
    return DEFAULT_API_URL;
  }

  const envUrl = process.env.NEXT_PUBLIC_API_URL;
  if (envUrl && !envUrl.includes('trycloudflare.com')) {
    return envUrl.replace(/\/+$/, '');
  }
  return DEFAULT_API_URL;
}

export const API_BASE = resolveApiBase();


export type RequestOptions = RequestInit & {
  timeoutMs?: number;
  /** Max retry attempts (0 disables). Defaults to 2; network-error retries are limited to idempotent methods. */
  retry?: number;
};

const RETRYABLE_STATUSES = new Set([502, 503, 504]);
// Broker-token routes: a 401 here means the broker session expired, not the
// operator's platform session (see the `auth:unauthorized` dispatch below).
const BROKER_AUTH_PATH = /\/tokens\/|\/broker\//;
const MAX_RETRY_ATTEMPTS = 2;
const RETRY_BASE_DELAY_MS = 300;
const RETRY_MAX_DELAY_MS = 2_000;
const IDEMPOTENT_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'PUT', 'DELETE']);

function retryDelayMs(attempt: number): number {
  const ceiling = Math.min(RETRY_MAX_DELAY_MS, RETRY_BASE_DELAY_MS * 2 ** attempt);
  return ceiling / 2 + Math.random() * (ceiling / 2);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function combineSignals(
  signals: Array<AbortSignal | null | undefined>,
): { signal: AbortSignal; cleanup: () => void } {
  const list = signals.filter((s): s is AbortSignal => Boolean(s));
  if (list.length === 0) return { signal: new AbortController().signal, cleanup: () => {} };
  if (list.length === 1) return { signal: list[0], cleanup: () => {} };

  const anySignal = (AbortSignal as unknown as { any?: (s: AbortSignal[]) => AbortSignal }).any;
  if (typeof anySignal === 'function') {
    return { signal: anySignal.call(AbortSignal, list), cleanup: () => {} };
  }

  const controller = new AbortController();
  const listeners: Array<{ signal: AbortSignal; handler: () => void }> = [];
  for (const signal of list) {
    if (signal.aborted) {
      controller.abort((signal as AbortSignal & { reason?: unknown }).reason);
      return { signal: controller.signal, cleanup: () => {} };
    }
    const handler = () =>
      controller.abort((signal as AbortSignal & { reason?: unknown }).reason);
    signal.addEventListener('abort', handler, { once: true });
    listeners.push({ signal, handler });
  }
  return {
    signal: controller.signal,
    cleanup: () => listeners.forEach(({ signal, handler }) => signal.removeEventListener('abort', handler)),
  };
}

/**
 * HTTP error carrying the response status.
 *
 * Callers used to get a bare `Error` with a message, so nothing could tell a
 * 404 (route absent on this backend build) from a 503 (real backend failure)
 * without string-matching the detail text. Still an `Error`, so existing
 * `instanceof Error` handling keeps working.
 */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** True only for an {@link ApiError} carrying one of `statuses`.
 *  Network/timeout failures are plain Errors (no status) and return false. */
export function isApiErrorStatus(err: unknown, ...statuses: number[]): boolean {
  return err instanceof ApiError && statuses.includes(err.status);
}

export class ApiCore {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
  }

  getBaseUrl(): string {
    return this.baseUrl;
  }

  getToken(): string | null {
    return this.token;
  }

  setToken(token: string | null) {
    this.token = token;
  }

  async request<T>(path: string, options?: RequestOptions): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((options?.headers as Record<string, string>) || {}),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    const url = `${this.baseUrl}${cleanPath}`;

    // Adaptive timeout: 180s for AI inference / import / historical scans; 60s for standard requests (accommodates cloud cold-starts)
    const isHeavy = cleanPath.includes('/ai/');
    const timeoutMs = options?.timeoutMs ?? (isHeavy ? 180_000 : 60_000);

    const method = (options?.method || 'GET').toUpperCase();
    const idempotent = IDEMPOTENT_METHODS.has(method);
    const maxRetries = Math.max(0, options?.retry ?? MAX_RETRY_ATTEMPTS);

    let response: Response | null = null;
    let attempt = 0;

    for (;;) {
      const controller = new AbortController();
      let timedOut = false;
      const timeoutId = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, timeoutMs);
      const callerSignal = options?.signal ?? null;
      const combined = combineSignals([callerSignal, controller.signal]);

      try {
        response = await fetch(url, {
          ...options,
          headers,
          signal: combined.signal,
        });
      } catch (err) {
        if (callerSignal?.aborted && !timedOut) {
          throw err;
        }
        if (timedOut) {
          const timeoutSec = Math.round(timeoutMs / 1000);
          throw new Error(
            `Request to ${this.baseUrl} timed out after ${timeoutSec}s. (The server may be waking up from idle sleep or processing a large dataset \u2014 please retry)`,
          );
        }
        // Network-level failures are only safe to retry when the request is idempotent.
        if (idempotent && attempt < maxRetries) {
          await sleep(retryDelayMs(attempt));
          attempt += 1;
          continue;
        }
        throw new Error(`Cannot reach backend at ${this.baseUrl}. Make sure the backend server is running.`);
      } finally {
        clearTimeout(timeoutId);
        combined.cleanup();
      }

      // Gateway failures (502/503/504) mean no authoritative response was produced;
      // a bounded re-issue is safe regardless of method.
      if (RETRYABLE_STATUSES.has(response.status) && attempt < maxRetries && !callerSignal?.aborted) {
        void response.body?.cancel().catch(() => {});
        await sleep(retryDelayMs(attempt));
        attempt += 1;
        response = null;
        continue;
      }
      break;
    }

    if (!response) {
      throw new Error(`Cannot reach backend at ${this.baseUrl}. Make sure the backend server is running.`);
    }

    const contentType = response.headers.get('content-type') || '';

    if (!response.ok) {
      // Global 401 signal — lets AuthProvider/logout listeners react instead of
      // silent infinite 401 polling loops. `kind` distinguishes broker-token
      // expiry (gateway concern) from platform-session expiry (terminal logout).
      if (response.status === 401 && typeof window !== 'undefined') {
        const kind = BROKER_AUTH_PATH.test(cleanPath) ? 'broker' : 'session';
        window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: { url, kind } }));
      }
      if (contentType.includes('application/json')) {
        const error: unknown = await response.json().catch(() => ({ detail: response?.statusText }));
        const record = (error && typeof error === 'object' ? error : {}) as Record<string, unknown>;
        const rawDetail = record.detail ?? record.error ?? record.message;
        const detail =
          typeof rawDetail === 'string' && rawDetail
            ? rawDetail
            : `API Error ${response.status}: ${response.statusText}`;
        const hint = typeof record.hint === 'string' ? ` Hint: ${record.hint}` : '';
        const extra =
          detail.toLowerCase().includes('paid models are disabled')
            ? ' Hint: Select a FREE OpenRouter model (prompt=0 & completion=0). Try Auto \u2014 Best Free, or enable Allow Paid Models in Settings. Catalog will fallback to cached models if OpenRouter is temporarily unavailable.'
            : hint;
        const retry =
          response.status === 502 && detail.toLowerCase().includes('openrouter catalog')
            ? ' (Retrying will use cached model list if available)'
            : '';
        throw new ApiError(`${detail}${extra}${retry}`, response.status);
      }
      throw new ApiError(
        `Backend at ${this.baseUrl} returned error ${response.status} (${response.statusText}).`,
        response.status,
      );
    }

    if (!contentType.includes('application/json')) {
      throw new ApiError(
        `Backend at ${this.baseUrl} returned non-JSON response (${contentType || 'HTML'}). Make sure the backend server is running and accessible.`,
        response.status,
      );
    }

    try {
      return (await response.json()) as T;
    } catch {
      throw new ApiError(
        `Backend at ${this.baseUrl} returned a malformed JSON body (HTTP ${response.status}).`,
        response.status,
      );
    }
  }
}
