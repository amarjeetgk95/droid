/**
 * Utility for broker OAuth session authorization.
 *
 * Opens a centered popup window so the user stays in their dashboard context.
 * Communicates via multiple channels (window postMessage, BroadcastChannel, and fallback
 * popup-close detection) and triggers immediate dashboard sync without requiring a page refresh.
 */

export interface BrokerAuthOptions {
  provider: string;
  loginUrl: string;
  onSuccess?: () => void;
  onError?: (error: string) => void;
  onClose?: () => void;
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

  // 1. Cross-window postMessage listener
  const messageHandler = (event: MessageEvent) => {
    if (
      event.data &&
      (event.data.type === 'DROID_AUTH_SUCCESS' || event.data.type === 'BROKER_AUTHENTICATED')
    ) {
      notifySuccess();
      try {
        if (popup && !popup.closed) popup.close();
      } catch {}
    }
  };
  window.addEventListener('message', messageHandler);

  // 2. BroadcastChannel listener (works cross-tab and cross-window on same domain/origin)
  try {
    broadcastChannel = new BroadcastChannel('droid_auth_channel');
    broadcastChannel.onmessage = (event: MessageEvent) => {
      if (
        event.data &&
        (event.data.type === 'DROID_AUTH_SUCCESS' || event.data.type === 'BROKER_AUTHENTICATED')
      ) {
        notifySuccess();
        try {
          if (popup && !popup.closed) popup.close();
        } catch {}
      }
    };
  } catch {}

  // 3. Fallback: check when popup window closes
  checkTimer = setInterval(() => {
    try {
      if (!popup || popup.closed) {
        // If popup closed without explicit success message, check if auth timestamp updated in localStorage
        try {
          const lastTime = Number(localStorage.getItem('droid_last_auth_time') || 0);
          if (Date.now() - lastTime < 10000) {
            notifySuccess();
            return;
          }
        } catch {}

        // Fallback: popup closed, trigger sync anyway so UI updates
        if (!completed) {
          notifySuccess();
          if (onClose) onClose();
        }
        cleanup();
      }
    } catch {
      cleanup();
    }
  }, 600);

  const cleanup = () => {
    if (checkTimer) {
      clearInterval(checkTimer);
      checkTimer = null;
    }
    window.removeEventListener('message', messageHandler);
    if (broadcastChannel) {
      try {
        broadcastChannel.close();
      } catch {}
      broadcastChannel = null;
    }
  };

  return cleanup;
}
