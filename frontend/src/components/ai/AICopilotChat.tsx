'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { AIChatMessage } from '@/lib/types';
import { buildChatBase, missingKeyHint, resolveAISettings, toBackendSymbol, useAISettings } from '@/lib/aiPayload';
import { Card, EmptyNote } from '@/components/ui/desk';
import { MarkdownMessage } from './markdown';
import { AIProvenanceNote } from './AIProvenanceNote';

/** No stream activity for this long aborts the request (provider stall guard). */
const STREAM_TIMEOUT_MS = 30_000;
/** Distance from the bottom within which the transcript keeps auto-scrolling. */
const STICK_SLACK_PX = 48;

const SUGGESTIONS = [
  'What is the current market regime?',
  'Where are the key options walls?',
  'Is this breakout real or a trap?',
  'Which levels matter most today?',
];

export function AICopilotChat({ symbol, contextPage }: { symbol: string; contextPage?: string }) {
  const aiSettings = useAISettings();
  const [messages, setMessages] = useState<AIChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [reasoning, setReasoning] = useState('');
  const [toolNote, setToolNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stopped, setStopped] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const inFlightRef = useRef(false);
  const settledRef = useRef(true);
  const abortedByUserRef = useRef(false);
  const timedOutRef = useRef(false);
  const timerRef = useRef<number | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const stickRef = useRef(true);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const backendSymbol = toBackendSymbol(symbol);
  const resolved = resolveAISettings(aiSettings);
  const keyHint = missingKeyHint(aiSettings);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // Abort any in-flight stream when the card unmounts (and never leave a timer behind).
  useEffect(
    () => () => {
      clearTimer();
      settledRef.current = true;
      inFlightRef.current = false;
      abortRef.current?.abort();
      abortRef.current = null;
    },
    [clearTimer],
  );

  // Follow the newest message / streamed tokens, but only while the user is
  // already pinned to the bottom (scrolling up opts out until they return).
  useEffect(() => {
    const el = listRef.current;
    if (!el || !stickRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, reasoning, toolNote]);

  const onTranscriptScroll = () => {
    const el = listRef.current;
    if (!el) return;
    stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight <= STICK_SLACK_PX;
  };

  const sendText = (raw: string) => {
    const text = raw.trim();
    if (!text || inFlightRef.current) return;
    setError(null);
    setReasoning('');
    setToolNote(null);
    setStopped(false);
    const history: AIChatMessage[] = [...messages, { role: 'user', content: text }];
    setMessages(history);
    setInput('');
    setStreaming(true);
    stickRef.current = true;
    inFlightRef.current = true;
    settledRef.current = false;
    abortedByUserRef.current = false;
    timedOutRef.current = false;

    const base = buildChatBase(aiSettings, backendSymbol, contextPage || 'ai-copilot');
    const payload = { ...base, messages: history, temperature: 0.3 };
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    let acc = '';
    let rsn = '';

    const armTimeout = () => {
      clearTimer();
      timerRef.current = window.setTimeout(() => {
        timedOutRef.current = true;
        ctrl.abort();
      }, STREAM_TIMEOUT_MS);
    };

    const finish = (providerFailed: boolean) => {
      if (settledRef.current) return;
      settledRef.current = true;
      inFlightRef.current = false;
      clearTimer();
      if (abortRef.current === ctrl) abortRef.current = null;
      setStreaming(false);
      setToolNote(null);
      if (timedOutRef.current) {
        setError(
          `No stream activity for ${Math.round(STREAM_TIMEOUT_MS / 1000)}s — the response was stopped. Partial output, if any, is shown above.`,
        );
        setStopped(true);
      } else if (abortedByUserRef.current) {
        setStopped(true);
      } else if (!providerFailed && !acc) {
        setError('The AI provider returned an empty response.');
      }
    };

    armTimeout();

    void api.streamAIChat(
      payload as Parameters<typeof api.streamAIChat>[0],
      (chunk) => {
        armTimeout();
        if (chunk.type === 'content') {
          acc += chunk.delta || '';
          setMessages([...history, { role: 'assistant', content: acc }]);
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
        finish(true);
      },
      () => finish(false),
      ctrl.signal,
    );
  };

  const stop = () => {
    if (!abortRef.current) return;
    abortedByUserRef.current = true;
    abortRef.current.abort();
  };

  const clear = () => {
    if (inFlightRef.current) return;
    setMessages([]);
    setReasoning('');
    setError(null);
    setStopped(false);
    setToolNote(null);
  };

  const lastIndex = messages.length - 1;
  const lastIsAssistant = messages[lastIndex]?.role === 'assistant';
  const completedReplies = messages.filter(
    (m, i) => m.role === 'assistant' && !(streaming && i === lastIndex),
  );

  return (
    <Card
      title="AI Copilot"
      meta={`${backendSymbol} · ${resolved.provider}:${resolved.model} · tools on`}
      action={
        messages.length ? (
          <button type="button" className="btn" onClick={clear} disabled={streaming}>
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
      <div
        ref={listRef}
        onScroll={onTranscriptScroll}
        role="log"
        aria-label="Copilot conversation"
        aria-live="off"
        aria-busy={streaming}
        style={{ display: 'grid', gap: 8, maxHeight: 380, overflowY: 'auto', marginBottom: 10 }}
      >
        {messages.length === 0 ? (
          <div>
            <EmptyNote>
              Ask about {backendSymbol} — regime, levels, options walls, or &ldquo;is this breakout real?&rdquo;. Copilot can call live quant tools.
            </EmptyNote>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  className="btn"
                  style={{ fontSize: 11.5 }}
                  disabled={streaming}
                  onClick={() => {
                    setInput(suggestion);
                    inputRef.current?.focus();
                  }}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
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
                whiteSpace: m.role === 'user' ? 'pre-wrap' : undefined,
              }}
            >
              <div className="faint" style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.06em', marginBottom: 2 }}>
                {m.role === 'user' ? 'YOU' : 'COPILOT'}
                {stopped && i === lastIndex && m.role === 'assistant' ? (
                  <span className="badge b-warn" style={{ marginLeft: 6 }}>STOPPED</span>
                ) : null}
              </div>
              {m.role === 'assistant' ? <MarkdownMessage content={m.content} /> : m.content}
            </div>
          ))
        )}
        {reasoning ? (
          <details style={{ fontSize: 12 }} className="muted">
            <summary style={{ cursor: 'pointer' }}>Reasoning trace</summary>
            <div style={{ whiteSpace: 'pre-wrap', marginTop: 4 }}>{reasoning}</div>
          </details>
        ) : null}
        {toolNote ? <p role="status" className="muted" style={{ fontSize: 12, margin: 0 }}>{toolNote}</p> : null}
        {streaming && !lastIsAssistant ? (
          <p role="status" className="muted" style={{ fontSize: 12, margin: 0 }}>Thinking…</p>
        ) : null}
        {stopped && !streaming ? (
          <p role="status" className="muted" style={{ fontSize: 12, margin: 0 }}>
            {lastIsAssistant
              ? 'Stopped — partial response shown above.'
              : 'Stopped before any response was received.'}
          </p>
        ) : null}
      </div>
      {/* Screen-reader announcer: completed assistant replies only, one announcement per reply. */}
      <div className="sr-only" role="log" aria-live="polite" aria-label="Copilot replies">
        {completedReplies.map((m, i) => (
          <div key={i}>{m.content}</div>
        ))}
      </div>
      <div role="alert" style={{ color: 'var(--ds-bear)', fontSize: 12, marginBottom: error ? 8 : 0 }}>
        {error}
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              if (e.nativeEvent.isComposing) return;
              e.preventDefault();
              sendText(input);
            }
          }}
          rows={1}
          placeholder={`Ask about ${backendSymbol}… (Enter to send, Shift+Enter for a new line)`}
          aria-label="Ask AI Copilot"
          style={{
            flex: 1,
            background: 'var(--ds-inset)',
            border: '1px solid var(--ds-border)',
            borderRadius: 10,
            padding: '9px 12px',
            fontSize: 13,
            resize: 'none',
            minHeight: 38,
            maxHeight: 120,
            fontFamily: 'inherit',
          }}
        />
        {streaming ? (
          <button type="button" className="btn" onClick={stop}>Stop</button>
        ) : (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => sendText(input)}
            disabled={!input.trim()}
          >
            Send
          </button>
        )}
      </div>
      <div style={{ marginTop: 8 }}>
        <AIProvenanceNote
          provider={`${resolved.provider}:${resolved.model}`}
          contextPage={contextPage}
        />
      </div>
    </Card>
  );
}

export default AICopilotChat;
