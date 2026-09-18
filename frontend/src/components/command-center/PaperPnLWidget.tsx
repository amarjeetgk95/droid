'use client';

import React, { useCallback, useRef, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { useMarketSession } from '@/hooks/useMarketSession';
import { api } from '@/lib/api';
import { toNumber } from '@/lib/coerce';
import { Card } from '@/components/ui/card';
import { Gauge } from '@/components/ui/gauge';
import { Badge } from '@/components/ui/badge';
import { EmptyNote, fmtINR } from '@/components/ui/desk';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import type { VirtualPosition } from '@/lib/types';
import Link from 'next/link';

interface PortfolioView {
  virtualCapital: number | null;
  availableMargin: number | null;
  usedMargin: number | null;
  marginUtilPct: number | null;
  realizedPnl: number | null;
  unrealizedPnl: number | null;
  totalPnl: number | null;
  openPositionsCount: number | null;
}

function finite(v: unknown): number | null {
  return toNumber(v);
}

function parsePortfolio(payload: unknown): PortfolioView | null {
  if (!payload || typeof payload !== 'object') return null;
  const o = payload as Record<string, unknown>;
  const virtualCapital = finite(o.virtual_capital);
  const availableMargin = finite(o.available_margin);
  const usedMargin = finite(o.used_margin);
  const realizedPnl = finite(o.total_realized_pnl);
  const unrealizedPnl = finite(o.total_unrealized_pnl);
  const totalField = finite(o.total_portfolio_pnl);
  const totalPnl =
    totalField ??
    (realizedPnl !== null && unrealizedPnl !== null ? realizedPnl + unrealizedPnl : null);
  let marginUtilPct = finite(o.margin_utilization_pct);
  if (marginUtilPct === null && usedMargin !== null && virtualCapital !== null && virtualCapital > 0) {
    marginUtilPct = (usedMargin / virtualCapital) * 100;
  }
  return {
    virtualCapital,
    availableMargin,
    usedMargin,
    marginUtilPct,
    realizedPnl,
    unrealizedPnl,
    totalPnl,
    openPositionsCount: finite(o.open_positions_count),
  };
}

function pnlClass(v: number | null): string {
  if (v === null) return 'text-ink-3';
  return v >= 0 ? 'text-up-strong' : 'text-down-strong';
}

function fmtSignedINR(v: number | null): string {
  if (v === null) return '—';
  return `${v > 0 ? '+' : ''}${fmtINR(v)}`;
}

export const PaperPnLWidget: React.FC = () => {
  const { isOpen } = useMarketSession();
  const [portfolio, setPortfolio] = useState<PortfolioView | null>(null);
  const [positions, setPositions] = useState<VirtualPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [positionsError, setPositionsError] = useState<string | null>(null);
  const [lastAt, setLastAt] = useState<Date | null>(null);
  const loadedRef = useRef(false);
  const hasDataRef = useRef(false);

  const load = useCallback(async () => {
    const initial = !loadedRef.current;
    if (initial) setLoading(true);
    else setRefreshing(true);
    const [portfolioRes, positionsRes] = await Promise.allSettled([
      api.getPaperPortfolio(),
      api.getPaperPositions(),
    ]);

    const failures: string[] = [];

    if (portfolioRes.status === 'fulfilled') {
      const parsed = parsePortfolio(portfolioRes.value?.data);
      if (parsed !== null) setPortfolio(parsed);
      else failures.push('portfolio payload unusable');
    } else {
      failures.push(
        portfolioRes.reason instanceof Error ? portfolioRes.reason.message : 'portfolio unavailable',
      );
    }

    if (positionsRes.status === 'fulfilled') {
      const rows = Array.isArray(positionsRes.value?.data) ? positionsRes.value.data : [];
      setPositions(rows.filter((p) => p && p.is_open !== false));
      setPositionsError(null);
    } else {
      failures.push(
        positionsRes.reason instanceof Error ? positionsRes.reason.message : 'positions unavailable',
      );
      setPositionsError(
        positionsRes.reason instanceof Error ? positionsRes.reason.message : 'positions unavailable',
      );
    }

    setError(failures.length > 0 ? failures.join(' · ') : null);
    if (failures.length < 2) {
      setLastAt(new Date());
      hasDataRef.current = true;
    }
    loadedRef.current = true;
    setLoading(false);
    setRefreshing(false);
  }, []);

  usePolling(() => {
    if (!isOpen && hasDataRef.current) return;
    return load();
  }, 4000);

  const openCount = portfolio?.openPositionsCount ?? positions.length;

  return (
    <Card
      title="PAPER TRADING PORTFOLIO"
      subtitle="Virtual execution desk with real-time mark-to-market accounting"
      headerAction={
        <Link
          href="/execute"
          className="text-xs font-mono text-primary hover:opacity-80 underline"
        >
          View Full Cockpit →
        </Link>
      }
    >
      <div className="space-y-4">
        {loading && portfolio === null ? (
          <div style={{ display: 'grid', gap: 10 }}>
            <div className="skel" style={{ height: 54, width: '100%' }}>.</div>
            <div className="skel" style={{ height: 14, width: '100%' }}>.</div>
            <div className="skel" style={{ height: 40, width: '100%' }}>.</div>
          </div>
        ) : portfolio === null ? (
          <EmptyNote>{error ? `Paper portfolio unavailable — ${error}` : 'Paper portfolio unavailable.'}</EmptyNote>
        ) : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div className="p-2.5 rounded-lg bg-surface-subtle border border-border font-mono">
                <div className="text-[10px] text-ink-3 uppercase font-semibold">Available Margin</div>
                <div className="text-sm font-bold text-foreground">
                  {portfolio.availableMargin !== null ? fmtINR(portfolio.availableMargin) : '—'}
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-surface-subtle border border-border font-mono">
                <div className="text-[10px] text-ink-3 uppercase font-semibold">Unrealized P&L</div>
                <div className={`text-sm font-bold ${pnlClass(portfolio.unrealizedPnl)}`}>
                  {fmtSignedINR(portfolio.unrealizedPnl)}
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-surface-subtle border border-border font-mono">
                <div className="text-[10px] text-ink-3 uppercase font-semibold">Realized P&L</div>
                <div className={`text-sm font-bold ${pnlClass(portfolio.realizedPnl)}`}>
                  {fmtSignedINR(portfolio.realizedPnl)}
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-surface-subtle border border-border font-mono">
                <div className="text-[10px] text-ink-3 uppercase font-semibold">Net Book MTM</div>
                <div className={`text-sm font-bold ${pnlClass(portfolio.totalPnl)}`}>
                  {fmtSignedINR(portfolio.totalPnl)}
                </div>
              </div>
            </div>

            {portfolio.marginUtilPct !== null ? (
              <Gauge
                value={portfolio.marginUtilPct}
                label="Margin Utilization"
                sublabel={
                  portfolio.usedMargin !== null && portfolio.virtualCapital !== null
                    ? `${fmtINR(portfolio.usedMargin)} of ${fmtINR(portfolio.virtualCapital)} allocated`
                    : 'Allocation detail unavailable'
                }
                thresholds={{ warning: 60, danger: 85 }}
              />
            ) : (
              <EmptyNote>Margin utilization unavailable.</EmptyNote>
            )}
          </>
        )}

        <div className="pt-2">
          <div className="text-xs font-mono text-ink-2 mb-2 font-semibold flex items-center justify-between">
            <span>OPEN POSITIONS ({openCount})</span>
          </div>
          {positions.length === 0 ? (
            <div className="text-center py-4 text-xs font-mono text-ink-4 border border-border rounded bg-surface-subtle/50">
              {positionsError ? `Positions unavailable — ${positionsError}` : 'No open paper positions'}
            </div>
          ) : (
            <div className="space-y-1.5 font-mono text-xs">
              {positions.slice(0, 3).map((pos) => (
                <div
                  key={pos.position_id}
                  className="flex items-center justify-between p-2 rounded bg-surface-subtle border border-border"
                >
                  <div className="flex items-center gap-2">
                    <Badge variant={pos.side === 'BUY' ? 'bull' : 'bear'} size="xs">
                      {pos.side}
                    </Badge>
                    <span className="font-semibold text-foreground">{pos.symbol}</span>
                    <span className="text-ink-3">x{pos.quantity}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`font-semibold ${pnlClass(finite(pos.unrealized_pnl))}`}>
                      {fmtSignedINR(finite(pos.unrealized_pnl))}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-[11px] font-mono text-ink-3">
            {error ? `Degraded — ${portfolio !== null ? 'showing last known values. ' : ''}${error}` : ''}
          </span>
          <FreshnessClock
            lastAt={lastAt}
            fetching={refreshing}
            marketClosed={!isOpen}
            dataQuality={error ? 'DEGRADED' : null}
            sourceLabel="REST · 4s poll"
          />
        </div>
      </div>
    </Card>
  );
};
