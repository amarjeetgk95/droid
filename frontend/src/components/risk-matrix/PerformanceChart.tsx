'use client';

import React, { useCallback, useMemo, useRef, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { api } from '@/lib/api';
import { linearScale, polylinePoints } from '@/lib/chartGeometry';
import { Card } from '../shared/Card';
import {
  type AuditTradeLike,
  buildEquityCurve,
  finiteNumber,
  signedINR,
  valueToneClass,
} from './riskUtils';

const VIEW_W = 500;
const VIEW_H = 100;
const PAD_Y = 12;

function messageOf(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback;
}

function fmtDay(ms: number): string {
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
}

/**
 * Cumulative REALIZED P&L, derived from settled audit-ledger trades
 * (`actual_pnl_inr` with an exit/creation timestamp). Open MTM is excluded —
 * mixing it in would make the curve disagree with settled performance KPIs.
 */
export const PerformanceChart: React.FC = () => {
  const [trades, setTrades] = useState<AuditTradeLike[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const requestSeqRef = useRef(0);

  const fetchTrades = useCallback(async () => {
    const seq = ++requestSeqRef.current;
    try {
      const res = await api.getSignalsAudit({ limit: 200 });
      if (seq !== requestSeqRef.current) return;
      setTrades(Array.isArray(res?.trades) ? (res.trades as AuditTradeLike[]) : []);
      setError(null);
      setUpdatedAt(Date.now());
    } catch (err) {
      if (seq !== requestSeqRef.current) return;
      setError(messageOf(err, 'Equity source unavailable'));
    } finally {
      if (seq === requestSeqRef.current) setLoading(false);
    }
  }, []);

  usePolling(fetchTrades, 15000);

  const curve = useMemo(() => buildEquityCurve(trades), [trades]);
  const settledCount = useMemo(
    () =>
      trades.filter((t) => !t.economics_unavailable && finiteNumber(t.actual_pnl_inr) !== null).length,
    [trades],
  );

  const geometry = useMemo(() => {
    if (!curve) return null;
    const points = curve.points;
    const minT = points[0].t;
    const maxT = points[points.length - 1].t;
    const values = points.map((p) => p.cumulative);
    const minV = Math.min(0, ...values);
    const maxV = Math.max(0, ...values);
    const spanV = maxV - minV;
    const xScale = linearScale([minT, maxT], [0, VIEW_W]);
    const yScale = linearScale([minV, maxV], [VIEW_H - PAD_Y, PAD_Y]);
    const xOf = (i: number) =>
      maxT > minT ? xScale(points[i].t) : (i / (points.length - 1)) * VIEW_W;
    const yOf = (v: number) => (spanV > 0 ? yScale(v) : VIEW_H / 2);
    return {
      polyline: polylinePoints(points.map((p, i) => ({ x: xOf(i), y: yOf(p.cumulative) }))),
      zeroY: minV < 0 && maxV > 0 ? yOf(0) : null,
    };
  }, [curve]);

  const initialLoading = loading && trades.length === 0 && !error;
  const unavailable = !!error && trades.length === 0;

  return (
    <Card
      title="CUMULATIVE REALIZED P&L & MAXIMUM DRAWDOWN"
      subtitle="Settled audit-ledger trades only (actual_pnl_inr); open mark-to-market is excluded"
    >
      <div className="space-y-3 font-mono text-xs">
        {error && trades.length > 0 && (
          <div role="alert" className="p-2 rounded bg-warn-wash border border-warn-line text-warn-strong">
            Refresh failed ({error}) — showing last known curve
            {updatedAt ? ` from ${new Date(updatedAt).toLocaleTimeString('en-IN')}` : ''}.
          </div>
        )}

        {initialLoading && (
          <p className="p-3 rounded border border-dashed border-border-strong text-ink-3">
            Loading settled trades…
          </p>
        )}

        {unavailable && (
          <div className="p-3 rounded border border-down-line bg-down-wash text-down-strong space-y-2">
            <p>Equity curve unavailable — {error}.</p>
            <button
              type="button"
              onClick={() => void fetchTrades()}
              className="px-2.5 py-1 rounded border border-down-line bg-surface hover:bg-down-wash font-semibold"
            >
              Retry
            </button>
          </div>
        )}

        {!initialLoading && !unavailable && !curve && (
          <p className="p-3 rounded border border-dashed border-border-strong text-ink-3">
            Cumulative curve unavailable — {settledCount === 0 ? 'no settled trades' : 'fewer than two settled trades'} with
            recorded realised P&amp;L in the audit ledger. The chart is not drawn from placeholder data.
          </p>
        )}

        {curve && geometry && (
          <>
            <div className="relative h-44 bg-surface-subtle rounded-lg p-3 border border-border flex flex-col justify-between overflow-hidden">
              <div className="absolute inset-0 flex flex-col justify-between p-3 opacity-25 pointer-events-none">
                <div className="border-b border-dashed border-border-strong" />
                <div className="border-b border-dashed border-border-strong" />
                <div className="border-b border-dashed border-border-strong" />
              </div>

              <div className="flex items-center justify-between text-ink-2 text-[11px] z-10">
                <span>PEAK: {signedINR(curve.peak, 0)}</span>
                <span className={`font-bold ${valueToneClass(curve.current)}`}>
                  CURRENT: {signedINR(curve.current, 0)}
                </span>
              </div>

              <svg
                className="w-full h-24 my-auto z-10"
                viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
                preserveAspectRatio="none"
                role="img"
                aria-label={`Cumulative realized P&L curve across ${settledCount} settled trades; current ${signedINR(curve.current, 0)}`}
              >
                {geometry.zeroY !== null && (
                  <line
                    x1="0"
                    x2={VIEW_W}
                    y1={geometry.zeroY}
                    y2={geometry.zeroY}
                    stroke="var(--ds-border-strong)"
                    strokeWidth="1"
                    strokeDasharray="4 4"
                  />
                )}
                <polyline
                  fill="none"
                  stroke={curve.current >= 0 ? 'var(--ds-bull)' : 'var(--ds-bear)'}
                  strokeWidth="2.5"
                  points={geometry.polyline}
                />
              </svg>

              <div className="flex items-center justify-between text-ink-3 text-[10px] z-10">
                <span>START {fmtDay(curve.points[0].t)}</span>
                <span>
                  MAX DD: {signedINR(-curve.maxDrawdown, 0)}
                  {curve.maxDrawdownPct !== null ? ` (${curve.maxDrawdownPct.toFixed(2)}%)` : ''}
                </span>
                <span>END {fmtDay(curve.points[curve.points.length - 1].t)}</span>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] text-ink-3">
              <span>Settled trades plotted: {settledCount}</span>
              <span>Peak-to-trough drawdown measured on realized P&amp;L only</span>
            </div>
          </>
        )}
      </div>
    </Card>
  );
};
