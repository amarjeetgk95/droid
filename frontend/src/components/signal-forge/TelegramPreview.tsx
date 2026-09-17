'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { errorMessage } from './forgeLogic';

interface TelegramPreviewProps {
  payload: Record<string, unknown>;
}

const DEBOUNCE_MS = 400;

/**
 * Telegram rendering preview. Debounced + aborted per payload change; on any
 * failure the panel shows an error stub instead of a fabricated alert.
 */
export const TelegramPreview: React.FC<TelegramPreviewProps> = ({ payload }) => {
  const [previewText, setPreviewText] = useState<string | null>(null);
  const [disclaimer, setDisclaimer] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const payloadKey = useMemo(() => JSON.stringify(payload), [payload]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      setError(null);
      void (async () => {
        try {
          const parsed = JSON.parse(payloadKey) as Record<string, unknown>;
          // Empty level inputs are omitted, not sent as '' (a 422 on the
          // preview route would replace a real formatting with an error).
          const body: Record<string, unknown> = {};
          for (const [key, value] of Object.entries(parsed)) {
            if (value === '' || value === undefined || value === null) continue;
            body[key] = value;
          }
          const res = await api.previewSignal(body, { signal: controller.signal });
          if (controller.signal.aborted) return;
          if (typeof res?.preview === 'string' && res.preview) {
            setPreviewText(res.preview);
            setDisclaimer(typeof res.disclaimer === 'string' ? res.disclaimer : null);
          } else {
            setPreviewText(null);
            setDisclaimer(null);
            setError('Backend returned no preview text.');
          }
        } catch (e) {
          if (controller.signal.aborted) return;
          setPreviewText(null);
          setDisclaimer(null);
          setError(errorMessage(e, 'Preview request failed.'));
        } finally {
          if (!controller.signal.aborted) setLoading(false);
        }
      })();
    }, DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [payloadKey]);

  return (
    <div className="p-3 rounded-lg bg-surface border border-border font-mono text-xs space-y-2 shadow-xs">
      <div className="flex items-center justify-between text-ink-2 font-semibold border-b border-border-subtle pb-1.5">
        <span className="flex items-center gap-1.5">
          <span aria-hidden="true">📱</span> TELEGRAM ALERT PREVIEW
        </span>
        {loading ? (
          <span className="text-[10px] text-primary animate-pulse font-semibold">Formatting…</span>
        ) : null}
      </div>

      {error ? (
        <div
          role="alert"
          className="text-down-strong text-[11px] leading-relaxed bg-down-wash border border-down-line rounded p-2.5"
        >
          Preview unavailable — {error}
        </div>
      ) : (
        <div className="whitespace-pre-wrap text-ink text-[11px] leading-relaxed bg-secondary p-2.5 rounded border border-border">
          {previewText ?? 'Waiting for payload fields…'}
        </div>
      )}

      {disclaimer ? <div className="text-[10px] text-ink-3 leading-relaxed">{disclaimer}</div> : null}
    </div>
  );
};
