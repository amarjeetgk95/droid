'use client';

import { memo } from 'react';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import { useOptionalLiveMarketContext } from '@/context/LiveMarketContext';
import { fmtNum, fmtSigned } from '@/components/ui/desk';

interface MarketPulseBarProps {
  onSelectInstrument?: (inst: string) => void;
  selectedInstrument?: string;
}

function normalizeSymbol(sym: string): string {
  return (sym ?? '').replace(/^(NSE|BSE):/i, '').trim().toUpperCase();
}

function isSelectedCard(sym: string, selected: string): boolean {
  const s = normalizeSymbol(sym);
  const sel = normalizeSymbol(selected);
  const sIsBank = s.includes('BANKNIFTY');
  const selIsBank = sel.includes('BANKNIFTY');
  if (selIsBank) return sIsBank;
  if (sel === 'NIFTY 50' || sel === 'NIFTY') {
    return (s === 'NIFTY 50' || s === 'NIFTY') && !sIsBank;
  }
  if (sel.includes('SENSEX')) return s.includes('SENSEX');
  if (sel.includes('VIX')) return s.includes('VIX');
  return s === sel;
}

function resolveSelectTarget(sym: string): string | null {
  const s = normalizeSymbol(sym);
  if (s.includes('BANKNIFTY')) return 'BANKNIFTY';
  if (s.includes('SENSEX')) return 'SENSEX';
  if (s.includes('VIX')) return null;
  if (s === 'NIFTY 50' || s === 'NIFTY' || (s.includes('NIFTY') && !s.includes('BANK'))) {
    return 'NIFTY 50';
  }
  return null;
}

export const MarketPulseBar = memo(function MarketPulseBar({
  onSelectInstrument,
  selectedInstrument = 'NIFTY 50',
}: MarketPulseBarProps) {
  const market = useOptionalMarketDataContext();
  const live = useOptionalLiveMarketContext();

  const cards = live?.cards && live.cards.length > 0 ? live.cards : market?.cards ?? [];
  const breadth = market?.breadth ?? null;
  const marketStatus = market?.marketStatus ?? null;
  const streamState = live?.streamState ?? market?.streamState ?? 'CONNECTING';
  const ticksFresh = live?.ticksFresh ?? market?.ticksFresh ?? false;

  const isClosed = marketStatus?.session === 'CLOSED' || marketStatus?.is_trading_day === false;
  const isLive = !isClosed && streamState === 'CONNECTED' && ticksFresh;

  // Filter core indices: NIFTY 50, BANKNIFTY, SENSEX, INDIA VIX
  const primaryCards = cards.filter((c) => {
    const s = (c.symbol ?? '').toUpperCase();
    return s.includes('NIFTY') || s.includes('SENSEX') || s.includes('VIX');
  });

  const adv =
    breadth?.advancing ?? (breadth as unknown as { advances?: number })?.advances ?? 0;
  const dec =
    breadth?.declining ?? (breadth as unknown as { declines?: number })?.declines ?? 0;
  const total = adv + dec;
  const advPct = total > 0 ? Math.round((adv / total) * 100) : 0;

  return (
    <div
      className="w-full px-3 sm:px-4 py-2 flex flex-wrap items-center gap-2 text-xs select-none"
      style={{ background: 'var(--ds-surface)', borderBottom: '1px solid var(--ds-border)' }}
    >
      {/* Index ticker items — light seg style */}
      <div className="flex items-center gap-1.5 overflow-x-auto py-0.5 min-w-0" role="tablist" aria-label="Index selector">
        {primaryCards.map((card) => {
          const sym = card.symbol ?? '';
          const cleanName = normalizeSymbol(sym).replace(' 50', '');
          const isSelected = isSelectedCard(sym, selectedInstrument);
          const chgPct = card.change_percent ?? 0;
          const isUp = (card.change ?? 0) >= 0;
          const selectTarget = resolveSelectTarget(sym);

          return (
            <button
              key={sym}
              type="button"
              role="tab"
              aria-selected={isSelected}
              onClick={() => {
                if (selectTarget) onSelectInstrument?.(selectTarget);
              }}
              className="flex items-center gap-2 px-2.5 py-1 rounded transition-colors cursor-pointer text-left whitespace-nowrap border"
              style={
                isSelected
                  ? {
                      borderColor: 'var(--ds-accent)',
                      background: 'var(--ds-accent-wash)',
                      color: 'var(--ds-ink)',
                      fontWeight: 700,
                    }
                  : {
                      borderColor: 'var(--ds-border)',
                      background: 'var(--ds-surface-subtle)',
                      color: 'var(--ds-ink)',
                    }
              }
            >
              <span className="font-bold" style={{ fontSize: 11, color: 'var(--ds-text-secondary)' }}>
                {cleanName}
              </span>
              <span className="mono font-bold" style={{ fontSize: 12 }}>
                {card.ltp ? fmtNum(card.ltp, 1) : '—'}
              </span>
              <span
                className="mono font-bold"
                style={{ fontSize: 11, color: isUp ? 'var(--ds-bull-strong)' : 'var(--ds-bear-strong)' }}
              >
                {fmtSigned(chgPct, 2)}%
              </span>
            </button>
          );
        })}
      </div>

      {/* Breadth & session status strip */}
      <div className="flex items-center gap-2 shrink-0 ml-auto mono" style={{ fontSize: 11 }}>
        {(adv > 0 || dec > 0) && (
          <div
            className="hidden sm:flex items-center gap-2 px-2 py-1 rounded border"
            style={{ background: 'var(--ds-surface-subtle)', borderColor: 'var(--ds-border)' }}
            title={`Advances ${adv}, declines ${dec}`}
          >
            <span className="font-bold v-bull">{adv}▲</span>
            <div className="w-16 h-1.5 rounded-full overflow-hidden flex" style={{ background: 'var(--ds-bear-wash)' }}>
              <div
                className="h-full transition-all duration-300"
                style={{ width: `${advPct}%`, background: 'var(--ds-bull)' }}
              />
            </div>
            <span className="font-bold v-bear">▼{dec}</span>
          </div>
        )}

        <span className={`feed-pill ${isLive ? 'feed-pill--on' : isClosed ? 'feed-pill--idle' : 'feed-pill--warn'}`}>
          <i />
          {isClosed ? 'CLOSED' : isLive ? 'LIVE' : 'SYNCING'}
        </span>
      </div>
    </div>
  );
});
