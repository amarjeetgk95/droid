'use client';

import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { AIDailyBriefingResponse } from '@/lib/types';
import { useInstrument } from '@/context/InstrumentContext';
import { Bot, FileText, Loader2, Send, ShieldAlert, Waves, X } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * FloatingAICopilot — shell-level AI drawer.
 *
 * Z-SCALE (see AppShell): renders at z-40 so module drawers (z-60, `.sg-ovl`),
 * the mobile nav drawer (z-45) and command palette / modals (z-50) always stay
 * above it; toasts (z-70) and the route progress bar (z-100) sit above all.
 *
 * `AICopilotChat` (components/ai) is intentionally not reused: its API exposes
 * only `{ symbol, contextPage }` and renders a dashboard Card, so it cannot
 * host the copilot quick-prompts/briefing surface or a controlled drawer.
 */
interface FloatingAICopilotProps {
  isOpen: boolean;
  onClose: () => void;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  /** Real provider/model provenance when the backend reports it. */
  meta?: string;
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

const QUICK_PROMPTS = [
  {
    key: 'brief',
    label: 'Pre-Market Brief',
    icon: FileText,
    build: (instrument: string) => `Generate a comprehensive pre-market briefing for ${instrument}`,
  },
  {
    key: 'flow',
    label: 'Flow Breakdown',
    icon: Waves,
    build: (instrument: string) => `Analyze current options flow and PCR dynamics for ${instrument}`,
  },
  {
    key: 'risk',
    label: 'Risk Critique',
    icon: ShieldAlert,
    build: (instrument: string) => `Critique the active breakout setup and false-break risk for ${instrument}`,
  },
] as const;

function formatBriefing(b: AIDailyBriefingResponse): string {
  const levels = b.key_levels_to_watch;
  const sections: Array<string | null> = [
    b.executive_summary,
    levels
      ? `Key levels to watch — spot ${levels.spot} · pivot ${levels.pivot} · R1 ${levels.r1} · S1 ${levels.s1} · POC ${levels.poc} · VAH ${levels.vah} · VAL ${levels.val}`
      : null,
    b.options_pin_and_pivots ? `Options pin & pivots\n${b.options_pin_and_pivots}` : null,
    b.fii_dii_implication ? `FII/DII implication\n${b.fii_dii_implication}` : null,
    b.actionable_playbook?.length
      ? `Actionable playbook\n${b.actionable_playbook.map((step) => `• ${step}`).join('\n')}`
      : null,
  ];
  return sections.filter(Boolean).join('\n\n');
}

export const FloatingAICopilot: React.FC<FloatingAICopilotProps> = ({ isOpen, onClose }) => {
  const { instrument } = useInstrument();
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const onCloseRef = useRef(onClose);

  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    {
      role: 'assistant',
      content:
        'DROID Quantitative Copilot online. I can synthesize market intelligence, critique setups, project options moves, or explain active signals. Ask a question or use a quick prompt.',
      timestamp: new Date().toLocaleTimeString(),
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  // Modal semantics: initial focus, focus trap, Escape, scroll lock, restore.
  useEffect(() => {
    if (!isOpen) return;
    const dialog = dialogRef.current;
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;

    const focusable = (): HTMLElement[] => {
      if (!dialog) return [];
      return Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
        (el) => el.offsetParent !== null || el === document.activeElement,
      );
    };

    const initial = inputRef.current ?? focusable()[0] ?? dialog;
    initial?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab' || !dialog) return;

      const candidates = focusable();
      if (candidates.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = candidates[0];
      const last = candidates[candidates.length - 1];
      const active = document.activeElement;

      if (event.shiftKey) {
        if (active === first || active === dialog || !dialog.contains(active)) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last || !dialog.contains(active)) {
        event.preventDefault();
        first.focus();
      }
    };

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', handleKeyDown, true);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', handleKeyDown, true);
      previouslyFocused?.focus();
    };
  }, [isOpen]);

  const handleSend = useCallback(
    async (customPrompt?: string) => {
      const text = (customPrompt ?? input).trim();
      if (!text || loading) return;

      const timestamp = () => new Date().toLocaleTimeString();
      setMessages((prev) => [...prev, { role: 'user', content: text, timestamp: timestamp() }]);
      if (!customPrompt) setInput('');
      setLoading(true);

      try {
        const lower = text.toLowerCase();
        let content: string;
        let meta: string | undefined;

        if (lower.includes('briefing') || lower.includes('pre-market')) {
          const res = await api.getMarketBriefing({ instrument });
          const briefing = res.data;
          if (!briefing) {
            throw new Error('Briefing response contained no data for this instrument.');
          }
          content = formatBriefing(briefing);
          meta = briefing.provider_used ? `provider: ${briefing.provider_used}` : undefined;
        } else {
          const res = await api.chatAi({
            message: text,
            context: { instrument },
            context_page: 'floating-copilot',
          });
          content = res.reply?.trim()
            ? res.reply
            : 'The AI provider returned an empty reply. Check the AI engine configuration in Settings.';
          meta = [res.provider_used, res.model_used].filter(Boolean).join(' · ') || undefined;
        }

        setMessages((prev) => [...prev, { role: 'assistant', content, timestamp: timestamp(), meta }]);
      } catch (err) {
        const detail = err instanceof Error && err.message ? err.message : 'Unknown AI provider error.';
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: `AI request failed: ${detail}`,
            timestamp: timestamp(),
          },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [input, instrument, loading],
  );

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-40">
      {/* Backdrop: click to dismiss. Sits below module drawers (z-60). */}
      <div className="absolute inset-0 bg-scrim backdrop-blur-xs" onClick={onClose} aria-hidden="true" />

      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-border bg-card shadow-2xl outline-none animate-in slide-in-from-right duration-200"
      >
        {/* Header */}
        <div className="flex items-center justify-between gap-3 border-b border-border bg-surface-subtle px-4 py-3">
          <div className="flex items-center gap-2 min-w-0">
            <Bot className="h-4 w-4 shrink-0 text-primary" aria-hidden />
            <div className="min-w-0">
              <div id={titleId} className="flex items-center gap-2 font-mono text-sm font-semibold text-foreground">
                DROID COPILOT
                <span className="rounded-sm border border-accent-line bg-accent-wash px-1.5 py-0.5 text-[10px] text-accent-strong">
                  {instrument}
                </span>
              </div>
              <div className="text-[10px] font-mono text-ink-4">Market AI & signal validation</div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close AI Copilot"
            title="Close AI Copilot"
            className="rounded-lg p-1.5 text-ink-4 transition-colors hover:bg-muted hover:text-ink-2"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        {/* Quick prompts */}
        <div className="flex items-center gap-1.5 overflow-x-auto border-b border-border-subtle bg-surface-subtle/50 px-3 py-2">
          {QUICK_PROMPTS.map(({ key, label, icon: Icon, build }) => (
            <button
              key={key}
              type="button"
              onClick={() => void handleSend(build(instrument))}
              disabled={loading}
              className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-sm bg-muted px-2.5 py-1 text-[11px] font-mono text-ink-2 transition-colors hover:bg-muted-strong disabled:opacity-50"
            >
              <Icon className="h-3 w-3" aria-hidden />
              {label}
            </button>
          ))}
        </div>

        {/* Messages */}
        <div
          className="flex-1 space-y-3 overflow-y-auto bg-surface-subtle/30 p-4 text-xs"
          aria-live="polite"
        >
          {messages.map((m, idx) => (
            <div
              key={idx}
              className={cn('flex flex-col', m.role === 'user' ? 'items-end' : 'items-start')}
            >
              <div
                className={cn(
                  'max-w-[85%] whitespace-pre-wrap rounded-lg border p-3',
                  m.role === 'user'
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-border bg-card text-ink-2',
                )}
              >
                {m.content}
              </div>
              <div className="mt-1 flex items-center gap-1.5 px-1 font-mono text-[9px] text-ink-4">
                <span>{m.timestamp}</span>
                {m.meta ? <span>• {m.meta}</span> : null}
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex items-center gap-2 p-2 font-mono text-xs text-accent-strong">
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
              Synthesizing quantitative intelligence…
            </div>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-border bg-surface-subtle p-3">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void handleSend();
            }}
            className="flex items-center gap-2"
          >
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={`Ask Copilot about ${instrument}…`}
              aria-label={`Ask AI Copilot about ${instrument}`}
              disabled={loading}
              className="flex-1 rounded-lg border border-border-strong bg-card px-3 py-2 text-xs text-foreground focus:border-primary focus:outline-none disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 font-mono text-xs font-semibold text-primary-foreground transition-colors hover:bg-accent-strong disabled:opacity-40"
            >
              <Send className="h-3 w-3" aria-hidden />
              Send
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};
