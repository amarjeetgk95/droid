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


export type RequestOptions = RequestInit & { timeoutMs?: number };

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

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    let response: Response;
    try {
      response = await fetch(url, {
        ...options,
        headers,
        signal: options?.signal ?? controller.signal,
      });
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        const timeoutSec = Math.round(timeoutMs / 1000);
        throw new Error(
          `Request to ${this.baseUrl} timed out after ${timeoutSec}s. (The server may be waking up from idle sleep or processing a large dataset \u2014 please retry)`,
        );
      }
      throw new Error(`Cannot reach backend at ${this.baseUrl}. Make sure the backend server is running.`);
    } finally {
      clearTimeout(timeoutId);
    }

    const contentType = response.headers.get('content-type') || '';

    if (!response.ok) {
      // Global 401 signal — lets AuthProvider/logout listeners react instead of
      // silent infinite 401 polling loops.
      if (response.status === 401 && typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: { url } }));
      }
      if (contentType.includes('application/json')) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        // Surface FREE-only guard hint and catalog fallback clearly
        const detail = error.detail || error.error || error.message || `API Error ${response.status}: ${response.statusText}`;
        const hint = error.hint ? ` Hint: ${error.hint}` : '';
        const extra =
          error.detail && error.detail.toLowerCase().includes('paid models are disabled')
            ? ' Hint: Select a FREE OpenRouter model (prompt=0 & completion=0). Try Auto \u2014 Best Free, or enable Allow Paid Models in Settings. Catalog will fallback to cached models if OpenRouter is temporarily unavailable.'
            : hint;
        const retry =
          response.status === 502 && error.detail && error.detail.toLowerCase().includes('openrouter catalog')
            ? ' (Retrying will use cached model list if available)'
            : '';
        throw new Error(`${detail}${extra}${retry}`);
      } else {
        throw new Error(`Backend at ${this.baseUrl} returned error ${response.status} (${response.statusText}).`);
      }
    }

    if (!contentType.includes('application/json')) {
      throw new Error(
        `Backend at ${this.baseUrl} returned non-JSON response (${contentType || 'HTML'}). Make sure the backend server is running and accessible.`,
      );
    }

    return response.json();
  }
}
