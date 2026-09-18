'use client';

import React from 'react';
import { useRiskPerformance } from '@/context/RiskDataContext';
import { UNAVAILABLE, finiteNumber, signedNumber, valueToneClass } from './riskUtils';

function winRateTone(completed: number, winRate: number | null): string {
  if (completed === 0 || winRate === null) return valueToneClass(null);
  if (winRate >= 50) return valueToneClass(1);
  if (winRate > 0) return 'text-warn-strong';
  return valueToneClass(-1);
}

function profitFactorTone(completed: number, pf: number | null): string {
  if (completed === 0 || pf === null) return valueToneClass(null);
  if (pf >= 1) return valueToneClass(1);
  if (pf > 0) return 'text-warn-strong';
  return valueToneClass(-1);
}

/**
 * Signal performance KPIs from `/signals/performance` (FSM outcome tracker).
 * No seeded metrics: an empty or failed response renders an explicit
 * unavailable state instead of plausible-looking numbers.
 */
export const PerformanceCards: React.FC = () => {
  const { data: perf, loading, error, updatedAt, refresh } = useRiskPerformance();

  if (loading && !perf && !error) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-xs" aria-busy="true">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="p-3.5 rounded-xl border border-border bg-card shadow-xs">
            <div className="text-[10px] text-ink-3 uppercase">Loading…</div>
            <div className="text-xl font-bold text-ink-4 mt-1">—</div>
          </div>
        ))}
      </div>
    );
  }

  if (!perf) {
    return (
      <div
        role="alert"
        className="p-3.5 rounded-xl border border-down-line bg-down-wash text-down-strong font-mono text-xs flex items-center justify-between gap-3"
      >
        <span>Performance metrics unavailable — {error ?? 'no data returned'}.</span>
        <button
          type="button"
          onClick={() => void refresh()}
          className="px-2.5 py-1 rounded border border-down-line bg-surface hover:bg-down-wash font-semibold"
        >
          Retry
        </button>
      </div>
    );
  }

  const total = finiteNumber(perf.total_signals);
  const winners = finiteNumber(perf.winning_signals);
  const losers = finiteNumber(perf.losing_signals);
  const winRate = finiteNumber(perf.win_rate_pct);
  const profitFactor = finiteNumber(perf.profit_factor);
  const expectancy = finiteNumber(perf.expectancy_r);
  const averageRr = finiteNumber(perf.average_rr);
  const completed = winners !== null && losers !== null ? winners + losers : 0;

  return (
    <div className="space-y-2 font-mono text-xs">
      {error && (
        <div role="alert" className="p-2 rounded bg-warn-wash border border-warn-line text-warn-strong">
          Refresh failed ({error}) — showing last known metrics
          {updatedAt ? ` from ${new Date(updatedAt).toLocaleTimeString('en-IN')}` : ''}.
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3.5 rounded-xl border border-border bg-card shadow-xs">
          <div className="text-[10px] text-ink-3 uppercase">Empirical Win Rate</div>
          <div className={`text-xl font-bold mt-1 ${winRateTone(completed, winRate)}`}>
            {completed === 0 || winRate === null ? UNAVAILABLE : `${winRate.toFixed(1)}%`}
          </div>
          <div className="text-[10px] text-ink-3 mt-1">
            {winners ?? 0}W / {losers ?? 0}L of {total ?? UNAVAILABLE}
            {completed === 0 ? ' · no completed trades yet' : ''}
          </div>
        </div>

        <div className="p-3.5 rounded-xl border border-border bg-card shadow-xs">
          <div className="text-[10px] text-ink-3 uppercase">Profit Factor</div>
          <div className={`text-xl font-bold mt-1 ${profitFactorTone(completed, profitFactor)}`}>
            {completed === 0 || profitFactor === null ? UNAVAILABLE : profitFactor.toFixed(2)}
          </div>
          <div className="text-[10px] text-ink-3 mt-1">Gross Win / Gross Loss</div>
        </div>

        <div className="p-3.5 rounded-xl border border-border bg-card shadow-xs">
          <div className="text-[10px] text-ink-3 uppercase">Mathematical Expectancy</div>
          <div className={`text-xl font-bold mt-1 ${valueToneClass(expectancy)}`}>
            {expectancy === null ? UNAVAILABLE : `${signedNumber(expectancy, 2)} R`}
          </div>
          <div className="text-[10px] text-ink-3 mt-1">Per Unit Risked</div>
        </div>

        <div className="p-3.5 rounded-xl border border-border bg-card shadow-xs">
          <div className="text-[10px] text-ink-3 uppercase">Average Realized R:R</div>
          <div className={`text-xl font-bold mt-1 ${averageRr !== null && averageRr > 0 ? 'text-primary' : 'text-ink-2'}`}>
            {averageRr !== null && averageRr > 0 ? `1:${averageRr.toFixed(2)}` : UNAVAILABLE}
          </div>
          <div className="text-[10px] text-ink-3 mt-1">
            {averageRr !== null && averageRr > 0 ? 'Risk-to-Reward Ratio' : 'No winning trades recorded'}
          </div>
        </div>
      </div>
    </div>
  );
};
