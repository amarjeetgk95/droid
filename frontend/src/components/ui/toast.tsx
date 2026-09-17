'use client';

/**
 * Toast — lightweight in-app notification host (UI plan Phase 2, EXECUTION_SAFETY.md).
 *
 * Action feedback must be visible even when the user has scrolled away from
 * the affected row. No dependency: one context + one host, styled with the
 * existing design tokens.
 *
 * Accessibility: each toast is its own live region (`status` for
 * info/success/warning, assertive `alert` for errors) so a new toast is
 * announced once without re-reading the whole list. Auto-dismiss pauses while
 * the pointer or keyboard focus is inside a toast.
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
  /** Message-first shorthand: `show(message, tone, detail?)`. */
  show: (message: string, tone?: ToastTone, detail?: string) => number;
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
  const deadlinesRef = useRef<Map<number, number>>(new Map());
  const remainingRef = useRef<Map<number, number>>(new Map());
  const pausedRef = useRef<Set<number>>(new Set());

  const clearTimer = useCallback((id: number) => {
    const timer = timersRef.current.get(id);
    if (timer) clearTimeout(timer);
    timersRef.current.delete(id);
  }, []);

  const dismiss = useCallback(
    (id: number) => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
      clearTimer(id);
      deadlinesRef.current.delete(id);
      remainingRef.current.delete(id);
      pausedRef.current.delete(id);
    },
    [clearTimer],
  );

  const schedule = useCallback(
    (id: number) => {
      const remaining = remainingRef.current.get(id) ?? AUTO_DISMISS_MS;
      deadlinesRef.current.set(id, Date.now() + remaining);
      clearTimer(id);
      timersRef.current.set(id, setTimeout(() => dismiss(id), remaining));
    },
    [clearTimer, dismiss],
  );

  const pause = useCallback((id: number) => {
    if (pausedRef.current.has(id)) return;
    pausedRef.current.add(id);
    const deadline = deadlinesRef.current.get(id);
    remainingRef.current.set(id, deadline ? Math.max(0, deadline - Date.now()) : AUTO_DISMISS_MS);
    const timer = timersRef.current.get(id);
    if (timer) clearTimeout(timer);
    timersRef.current.delete(id);
  }, []);

  const resume = useCallback(
    (id: number) => {
      if (!pausedRef.current.has(id)) return;
      pausedRef.current.delete(id);
      schedule(id);
    },
    [schedule],
  );

  const push = useCallback(
    (tone: ToastTone, message: string, detail?: string) => {
      const id = nextIdRef.current++;
      setToasts((prev) => {
        const next = [...prev, { id, tone, message, detail }];
        // Cap visible toasts; drop oldest.
        return next.length > MAX_TOASTS ? next.slice(next.length - MAX_TOASTS) : next;
      });
      remainingRef.current.set(id, AUTO_DISMISS_MS);
      schedule(id);
      return id;
    },
    [schedule],
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
      show: (message, tone = 'info', detail) => push(tone, message, detail),
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
      <div className="toast-host" role="region" aria-label="Notifications">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`toast toast--${t.tone}`}
            role={t.tone === 'error' ? 'alert' : 'status'}
            aria-live={t.tone === 'error' ? 'assertive' : 'polite'}
            aria-atomic="true"
            onMouseEnter={() => pause(t.id)}
            onMouseLeave={() => resume(t.id)}
            onFocus={() => pause(t.id)}
            onBlur={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget as Node | null)) resume(t.id);
            }}
          >
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
