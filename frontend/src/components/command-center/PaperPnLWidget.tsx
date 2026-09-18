'use client';

import React from 'react';
import { useMarketSession } from '@/hooks/useMarketSession';
import { usePaperTradingData } from '@/context/PaperTradingContext';
import { toNumber } from '@/lib/coerce';
import { Card } from '@/components/ui/card';
import { Gauge } from '@/components/ui/gauge';
import { Badge } from '@/components/ui/badge';
import { EmptyNote, fmtINR } from '@/components/ui/desk';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import Link from 'next/link';

function finite(v: unknown): number | null {
  return toNumber(v);
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
  const {
    portfolio,
    positions,
    loading,
    refreshing,
    error,
    positionsError,
    lastUpdated: lastAt,
    openPositionsCount: openCount,
  } = usePaperTradingData({ pollIntervalMs: 4000 });

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
                <div className="text-[10px] text-ink-3 uppercase font-semibold">Unrealized P&amp;L</div>
                <div className={`text-sm font-bold ${pnlClass(portfolio.unrealizedPnl)}`}>
                  {fmtSignedINR(portfolio.unrealizedPnl)}
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-surface-subtle border border-border font-mono">
                <div className="text-[10px] text-ink-3 uppercase font-semibold">Realized P&amp;L</div>
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
