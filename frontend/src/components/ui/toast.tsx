'use client';

/**
 * Toast — lightweight in-app notification host (UI plan Phase 2, EXECUTION_SAFETY.md).
 *
 * Action feedback must be visible even when the user has scrolled away from
 * the affected row. No dependency: one context + one host, styled with the
 * existing design tokens. aria-live=polite so screen readers announce outcomes.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

export type ToastTone = 'success' | 'error' | 'info' | 'warning';

export type ToastItem = {
  id: number;
  tone: ToastTone;
  message: string;
  detail?: string;
};

const AUTO_DISMISS_MS = 4500;
const MAX_TOASTS = 4;

type ToastContextValue = {
  /** Show a toast; returns its id. `detail` renders as a secondary mono line. */
  push: (tone: ToastTone, message: string, detail?: string) => number;
  success: (message: string, detail?: string) => number;
  error: (message: string, detail?: string) => number;
  info: (message: string, detail?: string) => number;
  warning: (message: string, detail?: string) => number;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextIdRef = useRef(1);
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const push = useCallback(
    (tone: ToastTone, message: string, detail?: string) => {
      const id = nextIdRef.current++;
      setToasts((prev) => {
        const next = [...prev, { id, tone, message, detail }];
        // Cap visible toasts; drop oldest.
        return next.length > MAX_TOASTS ? next.slice(next.length - MAX_TOASTS) : next;
      });
      const timer = setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
      timersRef.current.set(id, timer);
      return id;
    },
    [dismiss],
  );

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((t) => clearTimeout(t));
      timers.clear();
    };
  }, []);

  const value = useMemo<ToastContextValue>(
    () => ({
      push,
      success: (m, d) => push('success', m, d),
      error: (m, d) => push('error', m, d),
      info: (m, d) => push('info', m, d),
      warning: (m, d) => push('warning', m, d),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="toast-host"
        role="region"
        aria-label="Notifications"
      >
        <div aria-live="polite" className="sr-only">
          {toasts.map((t) => t.message).join('. ')}
        </div>
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast--${t.tone}`}>
            <i aria-hidden="true" />
            <div className="toast__body">
              <span className="toast__msg">{t.message}</span>
              {t.detail ? <span className="toast__detail">{t.detail}</span> : null}
            </div>
            <button
              type="button"
              className="toast__x"
              aria-label="Dismiss notification"
              onClick={() => dismiss(t.id)}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/** Must be called under a ToastProvider. */
export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}
