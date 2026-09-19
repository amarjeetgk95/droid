'use client';

import { useCallback, useEffect, useState } from 'react';
import { Copy } from 'lucide-react';
import type { SwingSetupDTO, SwingThesisResponse } from '@/lib/api/swing';
import { Modal } from '@/components/ui/modal';
import { useToast } from '@/components/ui/toast';

function contextValue(value: unknown): string {
  if (Array.isArray(value)) return value.length > 0 ? value.join(' · ') : '—';
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

function contextEntries(context: Record<string, unknown>): Array<[string, unknown]> {
  return Object.entries(context);
}

export function SwingThesisModal({
  setup,
  onClose,
  fetchThesis,
}: {
  setup: SwingSetupDTO | null;
  onClose: () => void;
  fetchThesis: (setupId: string) => Promise<SwingThesisResponse | null>;
}) {
  const { push } = useToast();
  const [payload, setPayload] = useState<SwingThesisResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!setup) {
      setPayload(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setPayload(null);
    void (async () => {
      const result = await fetchThesis(setup.setup_id);
      if (cancelled) return;
      setPayload(result);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [setup, fetchThesis]);

  const copyPrompt = useCallback(async () => {
    if (!payload?.structured_prompt) return;
    try {
      await navigator.clipboard.writeText(payload.structured_prompt);
      push('success', 'Thesis prompt copied to the clipboard.');
    } catch {
      push('error', 'Clipboard unavailable — select the prompt and copy manually.');
    }
  }, [payload, push]);

  return (
    <Modal
      isOpen={setup !== null}
      onClose={onClose}
      title={setup ? `AI Thesis Prompt — ${setup.contract_symbol}` : 'AI Thesis Prompt'}
      maxWidth="2xl"
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            Close
          </button>
          <button
            type="button"
            className="btn btn-primary btn-ic"
            disabled={!payload?.structured_prompt}
            onClick={() => void copyPrompt()}
          >
            <Copy size={13} />
            Copy prompt
          </button>
        </>
      }
    >
      {loading ? (
        <p className="sg-empty">Building the structured thesis prompt…</p>
      ) : !payload ? (
        <p className="sg-empty">
          Thesis prompt unavailable for this setup. The backend builds it from the latest scan
          record — rescan if the setup is stale.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="sg-kvlist">
            {contextEntries(payload.context).map(([key, value]) => (
              <div key={key} className="sg-kv">
                <span className="l">{key.replace(/_/g, ' ')}</span>
                <span className="v">{contextValue(value)}</span>
              </div>
            ))}
          </div>
          <pre
            className="mono"
            style={{
              margin: 0,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              padding: '10px 12px',
              border: '1px solid var(--ds-border)',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--ds-inset)',
              maxHeight: 360,
              overflow: 'auto',
            }}
          >
            {payload.structured_prompt}
          </pre>
        </div>
      )}
    </Modal>
  );
}
