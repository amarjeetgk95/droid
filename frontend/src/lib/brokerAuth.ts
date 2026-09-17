/**
 * Utility for broker OAuth session authorization.
 *
 * Opens a centered popup window so the user stays in their dashboard context.
 * Success is accepted from trusted message channels (window postMessage,
 * BroadcastChannel) or, as a last resort, the callback page's localStorage
 * marker. Cancelling the popup must never look like success.
 */

export interface BrokerAuthOptions {
  provider: string;
  loginUrl: string;
  onSuccess?: () => void;
  onError?: (error: string) => void;
  onClose?: () => void;
}

/** localStorage marker written by the backend OAuth callback page. */
const AUTH_TIME_KEY = 'droid_last_auth_time';
const AUTH_PROVIDER_KEY = 'droid_last_auth_provider';

/** How long after the callback marker a popup-close may still mean success. */
const CLOSE_FALLBACK_WINDOW_MS = 10_000;

const SUCCESS_MESSAGE_TYPES = new Set(['DROID_AUTH_SUCCESS', 'BROKER_AUTHENTICATED']);

function isSuccessMessage(data: unknown): boolean {
  if (!data || typeof data !== 'object') return false;
  return SUCCESS_MESSAGE_TYPES.has((data as { type?: unknown }).type as string);
}

export function openBrokerAuth({
  provider,
  loginUrl,
  onSuccess,
  onError,
  onClose,
}: BrokerAuthOptions): () => void {
  if (typeof window === 'undefined') return () => {};

  const width = 600;
  const height = 760;
  const left = window.screenX + Math.max(0, (window.outerWidth - width) / 2);
  const top = window.screenY + Math.max(0, (window.outerHeight - height) / 2);

  // Append return URL so backend callback can redirect directly back to current origin
  const origin = window.location.origin;
  const urlObj = new URL(loginUrl, origin);
  urlObj.searchParams.set('redirect_to', origin);
  const fullLoginUrl = urlObj.toString();

  // Only this app and the broker-login backend may claim a successful auth.
  // Any other window that can reach `window.opener` is untrusted.
  const allowedOrigins = new Set([origin, urlObj.origin]);

  const popup = window.open(
    fullLoginUrl,
    `${provider}_oauth_popup`,
    `width=${width},height=${height},left=${left},top=${top},status=no,menubar=no,toolbar=no,scrollbars=yes,resizable=yes`,
  );

  // If popup blocker intervened, fall back to direct navigation or show notification
  if (!popup || popup.closed || typeof popup.closed === 'undefined') {
    if (onError) onError('Popup was blocked by your browser. Please allow popups for this site.');
    window.location.href = fullLoginUrl;
    return () => {};
  }

  let completed = false;
  let broadcastChannel: BroadcastChannel | null = null;
  let checkTimer: ReturnType<typeof setInterval> | null = null;

  const cleanup = () => {
    if (checkTimer) {
      clearInterval(checkTimer);
      checkTimer = null;
    }
    window.removeEventListener('message', messageHandler);
    if (broadcastChannel) {
      try {
        broadcastChannel.close();
      } catch {
        // Best-effort close during cleanup; the reference is dropped next
        // line regardless and a failure must never abort teardown.
      }
      broadcastChannel = null;
    }
  };

  const notifySuccess = () => {
    if (completed) return;
    completed = true;

    // Trigger custom DOM event that any React component (Header, Context, etc.) can listen to
    window.dispatchEvent(
      new CustomEvent('broker:authenticated', {
        detail: { provider, timestamp: Date.now() },
      }),
    );

    if (onSuccess) onSuccess();
    cleanup();
  };

  const handleAuthMessage = (event: MessageEvent, allowEmptyOrigin: boolean) => {
    // Validate the sender origin in BOTH listeners. BroadcastChannel deliveries
    // are same-origin by construction and some engines report an empty origin
    // for them, so only that channel tolerates an empty value.
    const trustedOrigin =
      allowedOrigins.has(event.origin) || (allowEmptyOrigin && event.origin === '');
    if (!trustedOrigin) return;
    if (!isSuccessMessage(event.data)) return;

    notifySuccess();
    try {
      if (popup && !popup.closed) popup.close();
    } catch {
      // popup.close() is best-effort; the success event was already delivered
      // and the close-fallback interval will still observe the popup.
    }
  };

  // 1. Cross-window postMessage listener
  const messageHandler = (event: MessageEvent) => handleAuthMessage(event, false);
  window.addEventListener('message', messageHandler);

  // 2. BroadcastChannel listener (same-origin channel)
  try {
    broadcastChannel = new BroadcastChannel('droid_auth_channel');
    broadcastChannel.onmessage = (event: MessageEvent) => handleAuthMessage(event, true);
  } catch {
    // Feature-detect: BroadcastChannel unsupported. Non-fatal — the
    // postMessage listener and popup-close fallback still cover auth success.
  }

  // 3. Fallback: check when popup window closes
  checkTimer = setInterval(() => {
    let closed = true;
    try {
      closed = !popup || popup.closed;
    } catch {
      closed = true;
    }
    if (!closed) return;

    // The popup closed. The ONLY evidence of success is the callback page's
    // localStorage marker written moments ago for THIS provider. A cancelled
    // or abandoned OAuth must never flash success or trigger refetches.
    let succeeded = false;
    try {
      const lastTime = Number(localStorage.getItem(AUTH_TIME_KEY) || 0);
      const lastProvider = (localStorage.getItem(AUTH_PROVIDER_KEY) || '').toLowerCase();
      const providerMatches = !lastProvider || lastProvider === provider.toLowerCase();
      succeeded = lastTime > 0 && Date.now() - lastTime < CLOSE_FALLBACK_WINDOW_MS && providerMatches;
    } catch {
      succeeded = false;
    }

    if (succeeded) {
      notifySuccess();
      return;
    }

    cleanup();
    if (onClose) onClose();
  }, 600);

  return cleanup;
}
