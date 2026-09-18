'use client';

import React, { useCallback, useRef, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { useInstrument, type SupportedInstrument } from '@/context/InstrumentContext';
import { useMarketSession } from '@/hooks/useMarketSession';
import { api } from '@/lib/api';
import { PriceDisplay } from '@/components/ui/price-display';
import { Badge, type BadgeVariant } from '@/components/ui/badge';
import { EmptyNote } from '@/components/ui/desk';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import type { DataStatus, IndexCard } from '@/lib/types';

interface DashboardSummaryData {
  cards: IndexCard[];
  errors: Record<string, string>;
  degraded: boolean;
  generated_at: string;
}

const SELECTABLE_INSTRUMENTS = new Set<string>(['NIFTY', 'BANKNIFTY', 'SENSEX']);

function isSelectable(symbol: string): symbol is SupportedInstrument {
  return SELECTABLE_INSTRUMENTS.has(symbol.toUpperCase());
}

function statusVariant(status: DataStatus | undefined): BadgeVariant {
  switch (String(status ?? '').toUpperCase()) {
    case 'LIVE':
      return 'success';
    case 'DEGRADED':
    case 'STALE':
      return 'warning';
    case 'CLOSED':
      return 'neutral';
    default:
      return 'danger';
  }
}

function readSummary(payload: unknown): DashboardSummaryData {
  const raw = (payload ?? {}) as Record<string, unknown>;
  const cards = Array.isArray(raw.cards) ? (raw.cards as IndexCard[]) : [];
  const errors =
    raw.errors && typeof raw.errors === 'object'
      ? (raw.errors as Record<string, string>)
      : {};
  return {
    cards: cards.filter((c) => c && typeof c === 'object'),
    errors,
    degraded: raw.degraded === true,
    generated_at: typeof raw.generated_at === 'string' ? raw.generated_at : '',
  };
}

function resolvePrice(card: IndexCard): { price: number | null; change: number | null; changePct: number | null } {
  const ltp = Number(card.ltp);
  if (!Number.isFinite(ltp) || ltp <= 0) return { price: null, change: null, changePct: null };
  const change = Number(card.change);
  const changePct = Number(card.change_percent);
  return {
    price: ltp,
    change: Number.isFinite(change) ? change : null,
    changePct: Number.isFinite(changePct) ? changePct : null,
  };
}

export const MarketPulseBar: React.FC = () => {
  const { instrument, setInstrument } = useInstrument();
  const { isOpen } = useMarketSession();
  const [summary, setSummary] = useState<DashboardSummaryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadedRef = useRef(false);
  const hasDataRef = useRef(false);

  const load = useCallback(async () => {
    const initial = !loadedRef.current;
    if (initial) setLoading(true);
    else setRefreshing(true);
    try {
      const res = await api.getDashboardSummary();
      if (res?.data) {
        setSummary(readSummary(res.data));
        hasDataRef.current = true;
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Dashboard summary unavailable');
    } finally {
      loadedRef.current = true;
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  usePolling(() => {
    if (!isOpen && hasDataRef.current) return;
    return load();
  }, 8000);

  const cards = summary?.cards ?? [];
  const errors = summary ? Object.entries(summary.errors) : [];

  return (
    <div className="space-y-2">
      {loading && !summary ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="p-3.5 rounded-xl border border-border bg-card">
              <div className="skel" style={{ height: 13, width: 90, marginBottom: 10 }}>.</div>
              <div className="skel" style={{ height: 22, width: 150, marginBottom: 10 }}>.</div>
              <div className="skel" style={{ height: 10, width: 120 }}>.</div>
            </div>
          ))}
        </div>
      ) : cards.length === 0 ? (
        <div className="p-4 rounded-xl border border-border bg-card">
          <EmptyNote>
            {error
              ? `Market pulse unavailable — ${error}`
              : 'No index cards returned by the dashboard summary.'}
          </EmptyNote>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {cards.map((card) => {
            const symbol = String(card.symbol ?? '').toUpperCase();
            const selectable = isSelectable(symbol);
            const isSelected = selectable && instrument === symbol;
            const { price, change, changePct } = resolvePrice(card);
            const badge = statusVariant(card.status);
            return (
              <div
                key={symbol || String(card.display_name ?? '')}
                onClick={() => {
                  if (selectable) setInstrument(symbol);
                }}
                className={`p-3.5 rounded-xl border transition-all duration-200 ${
                  selectable ? 'cursor-pointer' : ''
                } ${
                  isSelected
                    ? 'bg-accent-wash border-primary ring-1 ring-primary/40'
                    : 'bg-card border-border hover:border-border-strong'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-mono font-bold text-sm tracking-wide text-foreground truncate">
                      {card.display_name || symbol || '—'}
                    </span>
                    <Badge variant={badge} size="xs">
                      {card.status || 'UNKNOWN'}
                    </Badge>
                  </div>
                  {isSelected && (
                    <span className="text-[10px] font-mono font-bold text-primary bg-accent-wash px-1.5 py-0.5 rounded border border-accent-line">
                      ACTIVE
                    </span>
                  )}
                </div>

                <div className="flex items-baseline justify-between mb-2">
                  {price !== null ? (
                    <PriceDisplay
                      price={price}
                      change={change ?? undefined}
                      changePct={changePct ?? undefined}
                      size="lg"
                    />
                  ) : (
                    <span className="text-xs font-mono text-ink-3">Quote unavailable</span>
                  )}
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-border-subtle text-[11px] font-mono text-ink-3">
                  <span>
                    O {Number.isFinite(card.open) && card.open > 0 ? card.open.toFixed(2) : '—'} · H{' '}
                    {Number.isFinite(card.high) && card.high > 0 ? card.high.toFixed(2) : '—'} · L{' '}
                    {Number.isFinite(card.low) && card.low > 0 ? card.low.toFixed(2) : '—'}
                  </span>
                  <span className="text-ink-4">{card.provider || '—'}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <span className="text-[11px] font-mono text-ink-3">
          {error
            ? `Degraded — last known summary. ${error}`
            : errors.length > 0
              ? `Partial summary — missing: ${errors.map(([k]) => k).join(', ')}`
              : summary
                ? 'All summary legs reported'
                : ''}
        </span>
        <FreshnessClock
          lastAt={summary?.generated_at || null}
          fetching={refreshing}
          marketClosed={!isOpen}
          dataQuality={summary?.degraded ? 'DEGRADED' : null}
          sourceLabel="REST · summary"
        />
      </div>
    </div>
  );
};
