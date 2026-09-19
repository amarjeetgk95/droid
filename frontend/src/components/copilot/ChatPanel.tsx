'use client';

/* Streaming chat tab: POST /api/v1/ai/chat/stream via useAiChat.
   Tokens append as they arrive; stop aborts via AbortController. */

import { useEffect, useState } from 'react';
import { useAiChat } from '@/hooks/useCopilot';
import { sortModelOptions, type ModelOption } from '@/lib/copilot';
import { useToast } from '@/components/ui/toast';

const PRE_WRAP = { whiteSpace: 'pre-wrap', wordBreak: 'break-word' } as const;

export function ChatPanel({
  models,
  modelsLoading,
  settingsModel,
}: {
  models: ModelOption[];
  modelsLoading: boolean;
  settingsModel: string | null;
}) {
  const [draft, setDraft] = useState('');
  const [model, setModel] = useState('');
  const chat = useAiChat({ model: model || null });
  const { push } = useToast();
  const sorted = sortModelOptions(models);

  useEffect(() => {
    if (chat.streamError) push('error', chat.streamError, chat.streamHint ?? undefined);
  }, [chat.streamError, chat.streamHint, push]);

  const handleSend = () => {
    if (!draft.trim() || chat.sending) return;
    chat.send(draft);
    setDraft('');
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="ds-filters">
        <label className="field">
          <span className="field-l">Model</span>
          <select
            className="input"
            value={model}
            disabled={modelsLoading}
            onChange={(e) => setModel(e.target.value)}
            title="Model picker fed by GET /api/v1/ai/models — blank uses the Settings default"
          >
            <option value="">Settings default{settingsModel ? `: ${settingsModel}` : ''}</option>
            {sorted.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
                {m.isFree ? ' (free)' : ''}
              </option>
            ))}
          </select>
        </label>
        <span className="stat-chips">
          <span className="stat-chip">
            provider <b>{chat.provider}</b>
          </span>
          <span className="stat-chip">
            model <b>{chat.modelId ?? 'auto'}</b>
          </span>
        </span>
        <button type="button" className="btn" disabled={chat.messages.length === 0 || chat.sending} onClick={chat.clear}>
          Clear
        </button>
      </div>

      {chat.keyHint ? (
        <p className="sg-note">
          {chat.keyHint} <a href="/settings">Open Settings →</a>
        </p>
      ) : null}

      <div className="panel" aria-live="polite" aria-label="Copilot conversation">
        {chat.messages.length === 0 ? (
          <p className="sg-empty">
            Ask about market structure, option walls, or a setup — the copilot grounds itself with live quant
            tools before answering. Heavy inference can take up to 180s.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {chat.messages.map((m) => (
              <div key={m.id}>
                <span className="sg-sym">{m.role === 'user' ? 'you' : 'copilot'}</span>
                {m.reasoning ? <p className="sg-note">reasoning: {m.reasoning}</p> : null}
                {m.toolNotes.map((note, i) => (
                  <p key={i} className="sg-note">
                    {note}
                  </p>
                ))}
                {m.content ? <p style={PRE_WRAP}>{m.content}</p> : null}
                {!m.content && m.pending ? <p className="sg-note">thinking…</p> : null}
                {m.role === 'assistant' && (m.provider || m.model) ? (
                  <p className="card-meta">
                    {m.provider ?? '—'} · {m.model ?? '—'}
                  </p>
                ) : null}
                {m.error ? <p className="sg-err">{m.error}</p> : null}
              </div>
            ))}
          </div>
        )}
      </div>

      {chat.streamError && chat.streamHint ? <p className="sg-note">{chat.streamHint}</p> : null}

      <div className="ds-filters">
        <label className="field" style={{ flexGrow: 1 }}>
          <span className="field-l">Message (Enter to send)</span>
          <input
            className="input"
            value={draft}
            disabled={chat.sending}
            placeholder="e.g. Is NIFTY above its call wall into expiry?"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
        </label>
        {chat.sending ? (
          <button type="button" className="btn btn-sell" onClick={chat.stop} title="Abort the in-flight stream">
            Stop
          </button>
        ) : (
          <button type="button" className="btn btn-primary" disabled={!draft.trim()} onClick={handleSend}>
            Send
          </button>
        )}
      </div>
      {chat.sending ? <p className="sg-note">Streaming… press Stop to abort the request.</p> : null}
    </div>
  );
}
