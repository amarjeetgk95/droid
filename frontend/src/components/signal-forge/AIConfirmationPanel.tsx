'use client';

import React, { useState } from 'react';
import { api } from '@/lib/api';
import { Badge, type BadgeVariant } from '@/components/ui/badge';
import {
  errorMessage,
  finiteNumber,
  parseAIConfirmation,
  type AIConfirmationView,
  type AIHorizonOutput,
} from './forgeLogic';

interface AIConfirmationPanelProps {
  payload: Record<string, unknown>;
}

const STATUS_TONE: Record<string, BadgeVariant> = {
  CONFIRMED: 'success',
  WATCH: 'warning',
  UNCERTAIN: 'warning',
  REJECTED: 'danger',
  NOT_ELIGIBLE: 'danger',
  ERROR: 'danger',
  UNAVAILABLE: 'warning',
  TIMEOUT: 'warning',
};

const UNAVAILABLE_STATUSES = new Set(['ERROR', 'UNAVAILABLE', 'TIMEOUT', 'NOT_ELIGIBLE']);

const DECISION_TONE: Record<string, BadgeVariant> = {
  CONFIRM: 'success',
  REJECT: 'danger',
  WATCH: 'warning',
  UNCERTAIN: 'warning',
};

const HorizonCard: React.FC<{ title: string; horizon: AIHorizonOutput }> = ({ title, horizon }) => (
  <div className="p-2.5 rounded border border-border bg-secondary space-y-1.5">
    <div className="flex items-center justify-between gap-2">
      <span className="text-ink-2 font-bold">{title}</span>
      <Badge variant={DECISION_TONE[horizon.decision] ?? 'neutral'} size="xs">
        {horizon.decision}
      </Badge>
    </div>
    <div className="text-[11px] text-ink-3">
      Direction: <span className="text-ink-2">{horizon.direction}</span>
      {' · '}
      Confidence:{' '}
      <span className="text-ink-2">{horizon.confidence !== null ? `${horizon.confidence}/100` : '—'}</span>
      {horizon.max_holding_minutes !== null ? ` · Max hold ${horizon.max_holding_minutes}m` : ''}
    </div>
    {horizon.reasoning.length > 0 ? (
      <ul className="text-[11px] text-ink-2 space-y-0.5">
        {horizon.reasoning.map((line, i) => (
          <li key={i}>• {line}</li>
        ))}
      </ul>
    ) : (
      <div className="text-[11px] text-ink-3">No reasoning published.</div>
    )}
    {horizon.invalidation_conditions.length > 0 ? (
      <div className="text-[11px] text-warn-ink">
        Invalidates if: {horizon.invalidation_conditions.join('; ')}
      </div>
    ) : null}
  </div>
);

/**
 * AI confirmation is a reasoning layer only. The panel renders exactly what
 * `/api/v1/institutional/ai/confirm` returns (`ai_status`, horizon decisions,
 * overall assessment) and shows an explicit unavailable state on failure —
 * it never presents a fabricated APPROVED verdict.
 */
export const AIConfirmationPanel: React.FC<AIConfirmationPanelProps> = ({ payload }) => {
  const [view, setView] = useState<AIConfirmationView | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const instrument = typeof payload.underlying === 'string' ? payload.underlying : '';

  const handleRunConfirmation = async () => {
    if (loading) return;
    if (!instrument) {
      setFetchError('Instrument unavailable — cannot run AI confirmation.');
      return;
    }
    setLoading(true);
    setFetchError(null);
    try {
      const res = await api.confirmAI({
        instrument_id: instrument,
        // Proposed setup context only; the backend builds the market context.
        short_horizon: {
          direction: payload.direction ?? null,
          strategy: payload.strategy ?? null,
          timeframe: payload.timeframe ?? null,
          trigger: finiteNumber(payload.trigger),
          stop_loss: finiteNumber(payload.stop_loss),
          target_1: finiteNumber(payload.target_1),
          target_2: finiteNumber(payload.target_2),
        },
      });
      setView(parseAIConfirmation(res));
    } catch (e) {
      setView(null);
      setFetchError(errorMessage(e, 'AI confirmation request failed.'));
    } finally {
      setLoading(false);
    }
  };

  const status = view?.ai_status ?? null;
  const unavailable = status !== null && UNAVAILABLE_STATUSES.has(status);
  const overall = view?.overall ?? null;
  const bias = overall && typeof overall.market_bias === 'string' ? overall.market_bias : null;
  const breakoutQuality = finiteNumber(overall?.breakout_quality);
  const falseBreakoutRisk = finiteNumber(overall?.false_breakout_risk);

  return (
    <div className="p-3.5 rounded-lg bg-surface border border-border shadow-xs font-mono text-xs space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span aria-hidden="true" className="text-sm">
            🤖
          </span>
          <span className="text-ink font-semibold">AI COGNITIVE VALIDATION</span>
          {status ? (
            <Badge variant={STATUS_TONE[status] ?? 'neutral'} size="xs" dot={true}>
              {unavailable ? `AI ${status} — UNAVAILABLE` : `AI ${status}`}
            </Badge>
          ) : (
            <Badge variant="neutral" size="xs">
              NOT RUN
            </Badge>
          )}
        </div>

        <button
          type="button"
          onClick={handleRunConfirmation}
          disabled={loading || !instrument}
          className="px-2.5 py-1 rounded border border-accent-line bg-accent-wash hover:bg-accent-line text-primary text-[11px] font-semibold transition-all disabled:opacity-50"
        >
          {loading ? 'Analyzing…' : 'Run AI Confirmation'}
        </button>
      </div>

      {fetchError ? (
        <div role="alert" className="p-2 rounded bg-down-wash border border-down-line text-down-strong text-[11px] leading-relaxed">
          AI unavailable — {fetchError}
        </div>
      ) : null}

      {!view && !fetchError ? (
        <div className="p-2 rounded bg-secondary text-ink-3 text-[11px] leading-relaxed border border-border">
          Not yet run. AI confirmation is an optional reasoning layer — it never overrides the
          deterministic risk gates.
        </div>
      ) : null}

      {view ? (
        <>
          {view.error ? (
            <div role="alert" className="p-2 rounded bg-warn-wash border border-warn-line text-warn-ink text-[11px] leading-relaxed">
              {unavailable ? 'AI unavailable' : 'AI note'} — {view.error}
            </div>
          ) : null}

          {overall ? (
            <div className="p-2 rounded bg-secondary border border-border text-[11px] text-ink-2 flex flex-wrap gap-x-4 gap-y-1">
              {bias ? (
                <span>
                  Market bias: <span className="text-ink font-bold">{bias}</span>
                </span>
              ) : null}
              {breakoutQuality !== null ? <span>Breakout quality: {breakoutQuality}</span> : null}
              {falseBreakoutRisk !== null ? <span>False-breakout risk: {falseBreakoutRisk}</span> : null}
            </div>
          ) : null}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {view.short_horizon ? (
              <HorizonCard title="SHORT HORIZON" horizon={view.short_horizon} />
            ) : (
              <div className="p-2.5 rounded border border-border bg-secondary text-[11px] text-ink-3">
                Short-horizon output not published.
              </div>
            )}
            {view.continuation ? (
              <HorizonCard title="CONTINUATION" horizon={view.continuation} />
            ) : (
              <div className="p-2.5 rounded border border-border bg-secondary text-[11px] text-ink-3">
                Continuation output not published.
              </div>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
};
