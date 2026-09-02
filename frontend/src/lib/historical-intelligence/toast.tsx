'use client';

import * as React from 'react';
import { CheckCircle2, AlertTriangle, XCircle, Info, X } from 'lucide-react';
import { cn } from '@/lib/utils';

export type ToastTone = 'ok' | 'warn' | 'danger' | 'info';

export interface Toast {
  id: string;
  tone: ToastTone;
  title: string;
  description?: string;
}

interface ToastContextValue {
  toast: (t: Omit<Toast, 'id'>) => void;
  dismiss: (id: string) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

const TONE_STYLES: Record<ToastTone, { border: string; bg: string; text: string; icon: React.ReactNode }> = {
  ok: { border: 'border-green-500/40', bg: 'bg-green-500/10', text: 'text-green-600', icon: <CheckCircle2 className="w-4 h-4" /> },
  warn: { border: 'border-amber-500/40', bg: 'bg-amber-500/10', text: 'text-amber-600', icon: <AlertTriangle className="w-4 h-4" /> },
  danger: { border: 'border-red-500/40', bg: 'bg-red-500/10', text: 'text-red-500', icon: <XCircle className="w-4 h-4" /> },
  info: { border: 'border-border', bg: 'bg-card', text: 'text-foreground', icon: <Info className="w-4 h-4" /> },
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);

  const dismiss = React.useCallback((id: string) => {
    setToasts((cur) => cur.filter((t) => t.id !== id));
  }, []);

  const toast = React.useCallback((t: Omit<Toast, 'id'>) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setToasts((cur) => [...cur, { ...t, id }]);
    window.setTimeout(() => dismiss(id), 4500);
  }, [dismiss]);

  return (
    <ToastContext.Provider value={{ toast, dismiss }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-1.5 w-80 max-w-[calc(100vw-2rem)]">
        {toasts.map((t) => {
          const s = TONE_STYLES[t.tone];
          return (
            <div
              key={t.id}
              role="status"
              className={cn('rounded-lg border p-3 shadow-sm flex items-start gap-2 text-sm', s.border, s.bg, s.text)}
            >
              <div className="mt-0.5 shrink-0">{s.icon}</div>
              <div className="flex-1 min-w-0">
                <p className="font-semibold">{t.title}</p>
                {t.description && <p className="text-xs mt-0.5 opacity-90">{t.description}</p>}
              </div>
              <button
                onClick={() => dismiss(t.id)}
                className="p-0.5 rounded hover:bg-black/10"
                aria-label="Dismiss notification"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext);
  if (!ctx) {
    return {
      toast: (t) => {
        if (typeof console !== 'undefined') console.warn('ToastProvider not mounted:', t.title);
      },
      dismiss: () => {},
    };
  }
  return ctx;
}