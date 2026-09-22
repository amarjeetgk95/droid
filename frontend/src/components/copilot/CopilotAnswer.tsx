'use client';

/* Reusable bird-eye AI answer card: badge + 1-2 line verdict, max 3
   bullets, max 4 level chips, collapsed <details> for the full text.
   Pure render — no timers, no fetch; safe to re-parse every render
   while streaming. */

import type { CSSProperties, ReactNode } from 'react';
import { toBirdView, type BirdBias } from '@/lib/copilotView';
import { biasTone } from '@/lib/copilot';
import { aiMockProvenance, isMockAiProvider, MOCK_AI_SOURCE_LABEL } from '@/lib/api/ai';

export interface CopilotAnswerProps {
  raw: string;
  confidence?: number | null;
  providerLabel?: string | null;
  /** Raw provider id from the API payload (e.g. `mock_ai`). */
  provider?: string | null;
  /** Explicit `is_mock` flag from the API payload, when exposed by the caller. */
  isMock?: boolean | null;
}

const BIAS_LABEL: Record<BirdBias, string> = {
  bull: 'BULLISH',
  bear: 'BEARISH',
  neut: 'NEUTRAL',
  warn: 'WATCH',
  info: 'INFO',
};

function renderBold(text: string): ReactNode[] {
  const parts = text.split('**');
  if (parts.length === 1) return [text];
  const closed = parts.length % 2 === 1;
  return parts.map((part, i) => {
    const isBold = i % 2 === 1 && (closed || i < parts.length - 1);
    return isBold ? <b key={i}>{part}</b> : <span key={i}>{part}</span>;
  });
}

const VERDICT_CLAMP: CSSProperties = {
  display: '-webkit-box',
  WebkitLineClamp: 2,
  WebkitBoxOrient: 'vertical',
  overflow: 'hidden',
  minWidth: 0,
};

const PRE_WRAP: CSSProperties = { whiteSpace: 'pre-wrap', wordBreak: 'break-word' };

/** Structured level type from a payload object, when present. */
function levelType(lv: unknown): string | null {
  if (lv === null || typeof lv !== 'object') return null;
  const o = lv as Record<string, unknown>;
  for (const key of ['type', 'kind', 'level_type']) {
    const value = o[key];
    if (typeof value === 'string' && value.trim()) return value.trim().toUpperCase();
  }
  return null;
}

function levelText(lv: unknown): string {
  if (typeof lv === 'string') return lv;
  if (lv !== null && typeof lv === 'object') {
    const o = lv as Record<string, unknown>;
    const type = levelType(lv);
    const label = typeof o.label === 'string' ? o.label : '';
    const value = typeof o.value === 'string' ? o.value : typeof o.value === 'number' ? String(o.value) : '';
    const named = type && label && !label.toUpperCase().includes(type) ? `${type} ${label}` : label;
    const joined = named && value ? `${named} ${value}` : named || value;
    if (joined) return joined;
  }
  return String(lv ?? '');
}

export function CopilotAnswer({
  raw,
  confidence = null,
  providerLabel = null,
  provider = null,
  isMock = null,
}: CopilotAnswerProps) {
  if (!raw.trim()) return <p className="sg-empty">No analysis returned.</p>;
  const view = toBirdView(raw);
  // A missing direction is UNKNOWN, not a NEUTRAL fact.
  const biasMissing = view.bias === 'neut' && !/\bNEUTRAL\b/i.test(raw);
  const tone = biasMissing ? 'neut' : biasTone(view.bias);
  const biasText = biasMissing ? 'UNKNOWN' : BIAS_LABEL[view.bias];
  const verdict = String(view.verdict ?? '').trim();
  const bullets = ((view.bullets ?? []) as unknown[]).map((b) => String(b ?? '')).filter((s) => s.trim()).slice(0, 3);
  const levels = ((view.levels ?? []) as unknown[]).slice(0, 4);
  const rest = String(view.rest ?? '').trim();
  const confOk = typeof confidence === 'number' && Number.isFinite(confidence);
  const confText = confOk ? `${Math.round((confidence as number) <= 1 ? (confidence as number) * 100 : (confidence as number))}%` : null;
  const providerTokens = providerLabel ? providerLabel.split('·').map((part) => part.trim()) : [];
  // MOCK provenance from the API payload's provider id (plus providerLabel
  // tokens for callers that only forward the display label).
  const payloadMock = aiMockProvenance(provider, null);
  const mock =
    isMock === true ||
    payloadMock.isMock ||
    providerTokens.some((part) => isMockAiProvider(part));
  const mockLabel = payloadMock.label ?? MOCK_AI_SOURCE_LABEL;
  const meta = [confText, mock ? 'MOCK' : null, providerLabel].filter(Boolean).join(' · ') || null;
  const detailsText = rest || raw;
  const truncated = rest.length >= 2000 && raw.trim().length > rest.length;

  return (
    <div className="card">
      <div className="card-hd">
        <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, flex: 1 }}>
          <span className={`badge b-${tone}`} title={biasMissing ? 'No directional bias found in the response.' : `Bias: ${biasText}`}>
            {biasText}
          </span>
          {mock ? (
            <span className="badge b-warn" title={mockLabel}>
              MOCK
            </span>
          ) : null}
          {verdict ? (
            <span aria-label="AI verdict" style={VERDICT_CLAMP}>
              {renderBold(verdict)}
            </span>
          ) : null}
        </span>
        {meta ? <span className="card-meta">{meta}</span> : null}
      </div>
      <div className="card-bd">
        {bullets.length > 0 ? (
          <ul className="sg-list">
            {bullets.map((b, i) => (
              <li key={i}>
                <span aria-hidden="true">• </span>
                {renderBold(b)}
              </li>
            ))}
          </ul>
        ) : null}
        {levels.length > 0 ? (
          <span className="stat-chips">
            {levels.map((lv, i) => (
              <span key={i} className="stat-chip" title={levelText(lv)}>
                {renderBold(levelText(lv))}
              </span>
            ))}
          </span>
        ) : null}
        <details className="sg-disc">
          <summary>Details</summary>
          <div style={PRE_WRAP}>{detailsText}</div>
          {truncated ? (
            <p className="sg-note">
              Truncated for display ({raw.trim().length.toLocaleString()} chars in the full response); the
              full stream text was received.
            </p>
          ) : null}
          <p className="sg-note">
            Source: {providerLabel ?? 'provider not reported'}
            {mock ? ` · ${mockLabel}` : ''}
          </p>
        </details>
      </div>
    </div>
  );
}

export default CopilotAnswer;
