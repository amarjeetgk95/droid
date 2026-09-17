'use client';

import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { Badge } from '../shared/Badge';
import { directionToBias, errorMessage, finiteNumber } from './forgeLogic';

interface ExpectedMoveProps {
  underlying: string;
  spot: number | null;
  /** ATM IV as a fraction (null when not published). */
  iv: number | null;
  direction: 'CALL' | 'PUT';
  structuralTarget?: number | null;
  marketError?: string | null;
}

interface ProjectionView {
  spot: number;
  expectedMove: number | null;
  conservative: number | null;
  aggressive: number | null;
  sigmaMove: number | null;
  velocity: number | null;
  velocityAtr: number | null;
  fastEnough: boolean | null;
  assessment: string | null;
  calibration: number | null;
  ivSource: string | null;
  liveIv: number | null;
  rationale: string[];
}

type State =
  | { status: 'loading' }
  | { status: 'ready'; view: ProjectionView }
  | { status: 'error'; error: string };

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/**
 * Expected-move cone from POST /api/v1/options-intelligence/expected-move.
 * Requires a live spot + directional bias; bands are computed from the
 * published projection (never from fallback constants).
 */
export const ExpectedMoveProjection: React.FC<ExpectedMoveProps> = ({
  underlying,
  spot,
  iv,
  direction,
  structuralTarget,
  marketError,
}) => {
  const [state, setState] = useState<State>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;

    if (spot === null || spot <= 0) {
      setState({
        status: 'error',
        error: marketError ?? 'Live spot unavailable — cannot project an expected move.',
      });
      return () => {
        cancelled = true;
      };
    }

    setState({ status: 'loading' });
    void (async () => {
      try {
        const res = await api.projectExpectedMove({
          underlying,
          spot,
          direction: directionToBias(direction),
          horizon: 'INTRADAY',
          ...(iv !== null && iv > 0 ? { current_iv: iv } : {}),
          ...(structuralTarget !== null && structuralTarget !== undefined && structuralTarget > 0
            ? { structural_target: structuralTarget }
            : {}),
        });
        if (cancelled) return;
        const rec = asRecord(res);
        const projectedSpot = finiteNumber(rec?.spot_price);
        if (!rec || projectedSpot === null || projectedSpot <= 0) {
          setState({ status: 'error', error: 'Projection returned no spot price.' });
          return;
        }
        setState({
          status: 'ready',
          view: {
            spot: projectedSpot,
            expectedMove: finiteNumber(rec.expected_move_points),
            conservative: finiteNumber(rec.conservative_move_points),
            aggressive: finiteNumber(rec.aggressive_move_points),
            sigmaMove: finiteNumber(rec.iv_implied_1sigma_move),
            velocity: finiteNumber(rec.expected_velocity_pts_per_hour),
            velocityAtr: finiteNumber(rec.velocity_atr_per_hour),
            fastEnough: typeof rec.is_fast_enough_for_option === 'boolean' ? rec.is_fast_enough_for_option : null,
            assessment: typeof rec.velocity_assessment === 'string' ? rec.velocity_assessment : null,
            calibration: finiteNumber(rec.calibration_confidence),
            ivSource: typeof rec.iv_source === 'string' ? rec.iv_source : null,
            liveIv: finiteNumber(rec.live_iv),
            rationale: Array.isArray(rec.forecast_rationale)
              ? (rec.forecast_rationale as unknown[]).filter((v): v is string => typeof v === 'string')
              : [],
          },
        });
      } catch (e) {
        if (!cancelled) setState({ status: 'error', error: errorMessage(e, 'Expected move projection failed.') });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [underlying, spot, iv, direction, structuralTarget, marketError]);

  if (state.status === 'error') {
    return (
      <div className="p-3 rounded-lg bg-surface border border-border shadow-xs font-mono text-xs space-y-2">
        <div className="text-ink-2 font-semibold">EXPECTED MOVE CONE</div>
        <div role="alert" className="p-2.5 rounded bg-warn-wash border border-warn-line text-warn-ink text-[11px] leading-relaxed">
          Expected move unavailable — {state.error}
        </div>
      </div>
    );
  }

  if (state.status === 'loading') {
    return (
      <div className="p-3 rounded-lg bg-surface border border-border shadow-xs font-mono text-xs space-y-2">
        <div className="text-ink-2 font-semibold">EXPECTED MOVE CONE</div>
        <div role="status" className="text-[11px] text-ink-3">
          Projecting from live spot and IV…
        </div>
      </div>
    );
  }

  const view = state.view;
  const band = view.sigmaMove !== null && view.sigmaMove > 0 ? view.sigmaMove : view.expectedMove;
  const lower = band !== null ? view.spot - band : null;
  const upper = band !== null ? view.spot + band : null;

  return (
    <div className="p-3 rounded-lg bg-surface border border-border shadow-xs font-mono text-xs space-y-2">
      <div className="flex items-center justify-between gap-2 text-ink-2 font-semibold">
        <span>EXPECTED MOVE CONE {view.sigmaMove !== null ? '(±1σ IV)' : ''}</span>
        <span className="text-primary font-bold">
          {view.expectedMove !== null ? `±${view.expectedMove} pts` : '—'}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2 text-center pt-1">
        <div className="p-2 rounded bg-secondary border border-border">
          <div className="text-[10px] text-ink-3">LOWER BAND</div>
          <div className="text-down-strong font-bold mt-0.5">{lower !== null ? `₹${lower.toFixed(0)}` : '—'}</div>
        </div>
        <div className="p-2 rounded bg-secondary border border-border">
          <div className="text-[10px] text-ink-3">UNDERLYING SPOT</div>
          <div className="text-ink font-bold mt-0.5">₹{view.spot.toFixed(0)}</div>
        </div>
        <div className="p-2 rounded bg-secondary border border-border">
          <div className="text-[10px] text-ink-3">UPPER BAND</div>
          <div className="text-up-strong font-bold mt-0.5">{upper !== null ? `₹${upper.toFixed(0)}` : '—'}</div>
        </div>
      </div>

      <div className="text-[11px] text-ink-3 flex flex-wrap gap-x-4 gap-y-1">
        {view.conservative !== null ? <span>Conservative T1: {view.conservative} pts</span> : null}
        {view.aggressive !== null ? <span>Aggressive T2: {view.aggressive} pts</span> : null}
        {view.velocity !== null ? (
          <span>
            Velocity: {view.velocity} pts/h
            {view.velocityAtr !== null ? ` (${view.velocityAtr} ATR/h)` : ''}
          </span>
        ) : null}
        {view.calibration !== null ? <span>Calibration: {view.calibration}</span> : null}
        {view.ivSource !== null ? (
          <span>
            IV source: {view.ivSource}
            {view.liveIv !== null ? ` (${(view.liveIv * 100).toFixed(1)}%)` : ''}
          </span>
        ) : null}
      </div>

      <div className="flex items-center gap-2">
        {view.fastEnough !== null ? (
          <Badge variant={view.fastEnough ? 'success' : 'warning'} size="xs">
            {view.fastEnough ? 'FAST ENOUGH VS THETA' : 'TOO SLOW VS THETA'}
          </Badge>
        ) : null}
        {view.assessment ? <span className="text-[11px] text-ink-2">{view.assessment}</span> : null}
      </div>

      {view.rationale.length > 0 ? (
        <ul className="text-[10px] text-ink-3 leading-relaxed space-y-0.5">
          {view.rationale.map((line, i) => (
            <li key={i}>• {line}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
};
