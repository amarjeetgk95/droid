'use client';

import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { Badge } from '../shared/Badge';
import { errorMessage, finiteNumber } from './forgeLogic';

interface PerfView {
  winRate: number | null;
  profitFactor: number | null;
  avgRr: number | null;
  expectancy: number | null;
  total: number | null;
  completed: number | null;
}

type State =
  | { status: 'loading' }
  | { status: 'ready'; perf: PerfView }
  | { status: 'error'; error: string };

function fmt(value: number | null, suffix = ''): string {
  return value === null ? '—' : `${value}${suffix}`;
}

/**
 * Realized audit statistics from `GET /api/v1/signals/performance`. Renders
 * "—" for unpublished metrics and an explicit unavailable state on failure —
 * no hardcoded win rates or "all criteria passed" claims.
 */
export const ValidationGateway: React.FC = () => {
  const [state, setState] = useState<State>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await api.getSignalsPerformance();
        if (cancelled) return;
        setState({
          status: 'ready',
          perf: {
            winRate: finiteNumber(res?.win_rate_pct),
            profitFactor: finiteNumber(res?.profit_factor),
            avgRr: finiteNumber(res?.average_rr),
            expectancy: finiteNumber(res?.expectancy_r),
            total: finiteNumber(res?.total_signals),
            completed: finiteNumber(res?.completed_signals),
          },
        });
      } catch (e) {
        if (!cancelled) setState({ status: 'error', error: errorMessage(e, 'Performance ledger unavailable.') });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="p-3.5 rounded-lg bg-surface border border-border font-mono text-xs space-y-3 shadow-xs">
      <div className="flex items-center justify-between gap-2">
        <span className="text-ink font-semibold">STATISTICAL BACKTEST VALIDATION GATE</span>
        {state.status === 'ready' ? (
          <Badge variant="neutral" size="xs">
            AUDIT LEDGER
          </Badge>
        ) : state.status === 'error' ? (
          <Badge variant="warning" size="xs">
            UNAVAILABLE
          </Badge>
        ) : (
          <Badge variant="neutral" size="xs" dot={true}>
            LOADING
          </Badge>
        )}
      </div>

      {state.status === 'error' ? (
        <div role="alert" className="p-2.5 rounded bg-warn-wash border border-warn-line text-warn-ink text-[11px] leading-relaxed">
          Performance data unavailable — {state.error}
        </div>
      ) : null}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
        <div className="p-2 rounded bg-secondary border border-border">
          <div className="text-[10px] text-ink-3 font-semibold">WIN RATE</div>
          <div className="text-up-strong font-bold mt-0.5">
            {state.status === 'ready' ? fmt(state.perf.winRate, '%') : '—'}
          </div>
        </div>
        <div className="p-2 rounded bg-secondary border border-border">
          <div className="text-[10px] text-ink-3 font-semibold">PROFIT FACTOR</div>
          <div className="text-up-strong font-bold mt-0.5">
            {state.status === 'ready' ? fmt(state.perf.profitFactor) : '—'}
          </div>
        </div>
        <div className="p-2 rounded bg-secondary border border-border">
          <div className="text-[10px] text-ink-3 font-semibold">AVERAGE RR</div>
          <div className="text-ink font-bold mt-0.5">
            {state.status === 'ready' ? fmt(state.perf.avgRr) : '—'}
          </div>
        </div>
        <div className="p-2 rounded bg-secondary border border-border">
          <div className="text-[10px] text-ink-3 font-semibold">SAMPLE SIZE</div>
          <div className="text-ink font-bold mt-0.5">
            {state.status === 'ready'
              ? state.perf.total !== null
                ? `${state.perf.total} signals`
                : '—'
              : '—'}
          </div>
        </div>
      </div>

      {state.status === 'ready' ? (
        <div className="text-[10px] text-ink-3 leading-relaxed">
          Completed: {fmt(state.perf.completed)} · Expectancy:{' '}
          {state.perf.expectancy !== null ? `${state.perf.expectancy}R` : '—'}
        </div>
      ) : null}
    </div>
  );
};
