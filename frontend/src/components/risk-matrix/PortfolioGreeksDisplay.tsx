'use client';

import React, { useCallback, useRef, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { api } from '@/lib/api';
import { fmtNum } from '@/components/ui/desk';
import { Card } from '../shared/Card';
import { UNAVAILABLE, finiteNumber, signedINR, signedNumber, valueToneClass } from './riskUtils';

type GreeksSummary = {
  total_delta?: unknown;
  total_gamma?: unknown;
  total_theta_day?: unknown;
  total_vega?: unknown;
  gross_delta?: unknown;
  gross_gamma?: unknown;
  gross_theta_day?: unknown;
  gross_vega?: unknown;
  total_open_positions?: unknown;
};

function messageOf(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback;
}

function gross(label: string, v: unknown, digits: number): string {
  const n = finiteNumber(v);
  return n === null ? `${label} ${UNAVAILABLE}` : `${label} ${fmtNum(n, digits)}`;
}

/**
 * Portfolio greeks from the shared `PortfolioGreeksSummary` ledger
 * (`total_delta/total_gamma/total_theta_day/total_vega` + gross aggregates).
 * Sign is rendered from the value itself and the tone follows the sign, so a
 * negative theta is never painted green and a value never prints `+-`.
 */
export const PortfolioGreeksDisplay: React.FC = () => {
  const [summary, setSummary] = useState<GreeksSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const requestSeqRef = useRef(0);

  const fetchGreeks = useCallback(async () => {
    const seq = ++requestSeqRef.current;
    try {
      const res = await api.getPortfolioGreeksSummary();
      if (seq !== requestSeqRef.current) return;
      setSummary(res ?? null);
      setError(null);
      setUpdatedAt(Date.now());
    } catch (err) {
      if (seq !== requestSeqRef.current) return;
      setError(messageOf(err, 'Portfolio greeks unavailable'));
    } finally {
      if (seq === requestSeqRef.current) setLoading(false);
    }
  }, []);

  usePolling(fetchGreeks, 5000);

  const initialLoading = loading && summary === null;
  const unavailable = !!error && summary === null;
  const positions = summary ? finiteNumber(summary.total_open_positions) : null;
  const hasNoPositions = positions === 0;

  const cards = summary
    ? [
        {
          key: 'delta',
          label: 'Net Delta (Δ)',
          value: signedNumber(summary.total_delta, 1),
          sub: `${gross('Gross Δ', summary.gross_delta, 1)} · ₹ change / ₹1 spot move`,
          tone: valueToneClass(finiteNumber(summary.total_delta)),
        },
        {
          key: 'gamma',
          label: 'Net Gamma (Γ)',
          value: signedNumber(summary.total_gamma, 3),
          sub: `${gross('Gross Γ', summary.gross_gamma, 4)} · Δ acceleration rate`,
          tone: valueToneClass(finiteNumber(summary.total_gamma)),
        },
        {
          key: 'theta',
          label: 'Net Theta (Θ)',
          value: `${signedINR(summary.total_theta_day, 0)}/day`,
          sub: `${gross('Gross Θ', summary.gross_theta_day, 0)}/day · calendar time decay`,
          tone: valueToneClass(finiteNumber(summary.total_theta_day)),
        },
        {
          key: 'vega',
          label: 'Net Vega (ν)',
          value: signedINR(summary.total_vega, 0),
          sub: `${gross('Gross V', summary.gross_vega, 0)} · ₹ change / +1% IV move`,
          tone: valueToneClass(finiteNumber(summary.total_vega)),
        },
      ]
    : [];

  return (
    <Card
      title="PORTFOLIO GREEKS SENSITIVITY MATRIX"
      subtitle="Aggregate first and second-order derivatives exposure across all books"
      headerAction={
        positions !== null ? (
          <span className="text-[10px] text-ink-3 font-mono">
            {positions} open position{positions === 1 ? '' : 's'}
          </span>
        ) : undefined
      }
    >
      <div className="space-y-3 font-mono text-xs">
        {error && summary !== null && (
          <div role="alert" className="p-2 rounded bg-warn-wash border border-warn-line text-warn-strong">
            Refresh failed ({error}) — showing last known greeks
            {updatedAt ? ` from ${new Date(updatedAt).toLocaleTimeString('en-IN')}` : ''}.
          </div>
        )}

        {initialLoading && (
          <p className="p-3 rounded border border-dashed border-border-strong text-ink-3">
            Loading portfolio greeks…
          </p>
        )}

        {unavailable && (
          <div className="p-3 rounded border border-down-line bg-down-wash text-down-strong space-y-2">
            <p>Portfolio greeks unavailable — {error}.</p>
            <button
              type="button"
              onClick={() => void fetchGreeks()}
              className="px-2.5 py-1 rounded border border-down-line bg-surface hover:bg-down-wash font-semibold"
            >
              Retry
            </button>
          </div>
        )}

        {hasNoPositions && (
          <p className="p-2 rounded border border-dashed border-border-strong text-ink-3">
            No open positions in the greeks ledger — aggregates are zero by construction.
          </p>
        )}

        {!initialLoading && !unavailable && !summary && (
          <p className="p-3 rounded border border-dashed border-border-strong text-ink-3">
            No greeks summary returned by the backend — no aggregate exposure is available.
          </p>
        )}

        {summary && !unavailable && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {cards.map((c) => (
              <div key={c.key} className="p-2.5 rounded-lg bg-surface-subtle border border-border">
                <div className="text-[10px] text-ink-3 uppercase">{c.label}</div>
                <div className={`text-base font-bold mt-0.5 ${c.tone}`}>{c.value}</div>
                <div className="text-[10px] text-ink-3 mt-1">{c.sub}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
};
