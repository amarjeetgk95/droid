'use client';

import { useRef, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { AIChatMessage } from '@/lib/types';
import { buildChatBase, missingKeyHint, resolveAISettings, toBackendSymbol, useAISettings } from '@/lib/aiPayload';
import { Card, EmptyNote } from '@/components/ui/desk';

export function AICopilotChat({ symbol, contextPage }: { symbol: string; contextPage?: string }) {
  const aiSettings = useAISettings();
  const [messages, setMessages] = useState<AIChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [reasoning, setReasoning] = useState('');
  const [toolNote, setToolNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const backendSymbol = toBackendSymbol(symbol);
  const resolved = resolveAISettings(aiSettings);
  const keyHint = missingKeyHint(aiSettings);

  const send = () => {
    const text = input.trim();
    if (!text || streaming) return;
    setError(null);
    setReasoning('');
    setToolNote(null);
    const next: AIChatMessage[] = [...messages, { role: 'user', content: text }];
    setMessages(next);
    setInput('');
    setStreaming(true);

    const base = buildChatBase(aiSettings, backendSymbol, contextPage || 'ai-copilot');
    const payload = { ...base, messages: next, temperature: 0.3 };
    let acc = '';
    let rsn = '';
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    void api.streamAIChat(
      payload as Parameters<typeof api.streamAIChat>[0],
      (chunk) => {
        if (chunk.type === 'content') {
          acc += chunk.delta || '';
          const snapshot = acc;
          setMessages([...next, { role: 'assistant', content: snapshot }]);
        } else if (chunk.type === 'reasoning') {
          rsn += chunk.reasoning_delta || chunk.delta || '';
          setReasoning(rsn);
        } else if (chunk.type === 'tool_call') {
          const name = chunk.tool_call?.function?.name || 'quant tool';
          setToolNote(`Running ${name} against live quant engines…`);
        } else if (chunk.type === 'tool_result') {
          setToolNote(null);
        }
      },
      (err) => {
        setError(err);
        setStreaming(false);
      },
      () => setStreaming(false),
      ctrl.signal,
    );
  };

  const stop = () => abortRef.current?.abort();

  return (
    <Card
      title="AI Copilot"
      meta={`${backendSymbol} · ${resolved.provider}:${resolved.model} · tools on`}
      action={
        messages.length ? (
          <button type="button" className="btn" onClick={() => { setMessages([]); setReasoning(''); setError(null); }} disabled={streaming}>
            Clear
          </button>
        ) : undefined
      }
    >
      {keyHint ? (
        <p className="muted" style={{ margin: '0 0 10px', fontSize: 12 }}>
          {keyHint} <Link href="/settings" style={{ textDecoration: 'underline' }}>Open Settings → AI Engine</Link>
        </p>
      ) : null}
      <div style={{ display: 'grid', gap: 8, maxHeight: 380, overflowY: 'auto', marginBottom: 10 }} aria-live="polite">
        {messages.length === 0 ? (
          <EmptyNote>Ask about {backendSymbol} — regime, levels, options walls, or &ldquo;is this breakout real?&rdquo;. Copilot can call live quant tools.</EmptyNote>
        ) : (
          messages.map((m, i) => (
            <div
              key={i}
              style={{
                justifySelf: m.role === 'user' ? 'end' : 'start',
                maxWidth: '88%',
                background: m.role === 'user' ? 'var(--ds-bull-wash)' : 'var(--ds-inset)',
                border: '1px solid var(--ds-border)',
                borderRadius: 12,
                padding: '8px 12px',
                fontSize: 13,
                lineHeight: 1.55,
                whiteSpace: 'pre-wrap',
              }}
            >
              <div className="faint" style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.06em', marginBottom: 2 }}>
                {m.role === 'user' ? 'YOU' : 'COPILOT'}
              </div>
              {m.content}
            </div>
          ))
        )}
        {reasoning ? (
          <details style={{ fontSize: 12 }} className="muted">
            <summary style={{ cursor: 'pointer' }}>Reasoning trace</summary>
            <div style={{ whiteSpace: 'pre-wrap', marginTop: 4 }}>{reasoning}</div>
          </details>
        ) : null}
        {toolNote ? <p className="muted" style={{ fontSize: 12, margin: 0 }}>{toolNote}</p> : null}
        {streaming && messages[messages.length - 1]?.role === 'user' ? (
          <p className="muted" style={{ fontSize: 12, margin: 0 }}>Thinking…</p>
        ) : null}
      </div>
      {error ? <p style={{ color: 'var(--ds-bear)', fontSize: 12 }}>{error}</p> : null}
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder={`Ask about ${backendSymbol}…`}
          aria-label="Ask AI Copilot"
          style={{ flex: 1, background: 'var(--ds-inset)', border: '1px solid var(--ds-border)', borderRadius: 10, padding: '9px 12px', fontSize: 13 }}
        />
        {streaming ? (
          <button type="button" className="btn" onClick={stop}>Stop</button>
        ) : (
          <button type="button" className="btn btn-primary" onClick={send} disabled={!input.trim()}>Send</button>
        )}
      </div>
    </Card>
  );
}

export default AICopilotChat;
