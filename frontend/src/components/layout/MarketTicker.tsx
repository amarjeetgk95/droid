import { memo, useMemo } from 'react';
import { IndexCard } from '@/lib/types';
import { safeInt } from '@/lib/utils';
import { useOptionalLiveMarketContext } from '@/context/LiveMarketContext';

const EQUITY_ORDER = ['NIFTY 50', 'BANKNIFTY', 'SENSEX'];

function findEquityCard(cards: IndexCard[], wanted: string): IndexCard | undefined {
  const w = wanted.toUpperCase();
  // Exact symbol / display_name match first.
  let hit = cards.find((c) => (c.symbol || '').toUpperCase() === w || (c.display_name || '').toUpperCase() === w);
  if (hit) return hit;
  // NIFTY 50 is stored under several aliases across providers.
  if (w === 'NIFTY 50') {
    hit = cards.find((c) => {
      const s = `${c.symbol || ''} ${c.display_name || ''}`.toUpperCase();
      return s.includes('NIFTY50') || /(^|\s)NIFTY(\s|$)/.test(s);
    });
    if (hit) return hit;
  }
  return undefined;
}

function isCryptoCard(card: Pick<IndexCard, 'symbol' | 'provider'>): boolean {
  const sym = (card.symbol || '').toUpperCase();
  const prov = (card.provider || '').toLowerCase();
  return prov.includes('binance') || sym.endsWith('USDT') || sym.endsWith('BTC');
}

function formatLtp(card: IndexCard): string {
  const n = Number(card.ltp);
  if (!Number.isFinite(n)) return '—';
  return n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatChange(card: IndexCard): string {
  const n = Number(card.change);
  if (!Number.isFinite(n)) return '—';
  if (n === 0) {
    return (0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  const prefix = n > 0 ? '+' : '-';
  return `${prefix}${Math.abs(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function MarketTickerInner({ cards: cardsProp, loading: loadingProp }: { cards?: IndexCard[]; loading?: boolean }) {
  // Prefer live tick-merged cards from LiveMarketContext; fall back to props
  // for isolated usage (stories/tests) without a provider.
  let contextCards: IndexCard[] | undefined;
  let contextLoading: boolean | undefined;
  try {
    const live = useOptionalLiveMarketContext();
    contextCards = live?.cards;
    contextLoading = live?.loading;
  } catch {
    // No provider — use props.
  }
  const baseCards = useMemo(() => cardsProp ?? contextCards ?? [], [cardsProp, contextCards]);
  const baseLoading = loadingProp ?? contextLoading ?? false;

  const cards = useMemo<IndexCard[]>(() => {
    // Always exclude crypto — ticker is equity-only (NIFTY 50 / BANKNIFTY / SENSEX).
    const nonCrypto = baseCards.filter((c) => !isCryptoCard(c));
    const equities: IndexCard[] = [];
    for (const wanted of EQUITY_ORDER) {
      const hit = findEquityCard(nonCrypto, wanted);
      if (hit) equities.push(hit);
    }
    // If FYERS snapshot hasn't arrived yet, fall back to any non-crypto cards
    // so the strip isn't empty while loading.
    if (equities.length === 0 && nonCrypto.length > 0) return nonCrypto.slice(0, 3);
    if (equities.length > 0) return equities;
    return nonCrypto;
  }, [baseCards]);

  const loading = baseLoading && cards.length === 0;
  const loopCards = useMemo(() => (!cards || cards.length === 0 ? [] : [...cards]), [cards]);

  if (loading) {
    return (
      <div className="h-11 border-b border-border bg-card/85 backdrop-blur-xl overflow-hidden flex items-center px-5 gap-6">
        <div className="flex items-center gap-6">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-center gap-2.5 animate-pulse">
              <div className="h-3.5 w-20 bg-muted rounded-full" />
              <div className="h-3.5 w-16 bg-muted rounded-full" />
              <div className="h-5 w-16 bg-muted rounded-full" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!cards || cards.length === 0) return null;

  return (
    <div className="group relative h-11 border-b border-border bg-card/85 backdrop-blur-xl overflow-hidden flex items-center shadow-[0_1px_2px_rgb(15_30_51/0.04)]">
      <div className="flex items-center gap-10 whitespace-nowrap overflow-x-auto px-5">
        {loopCards.map((card, idx) => {
          const changeVal = Number(card.change) || 0;
          const isPos = changeVal > 0;
          const isNeutral = changeVal === 0;
          const changePct = Number(card.change_percent) || 0;
          const closed = card.status === 'CLOSED';
          const sessionLabel = closed ? 'Closed' : (card.status || '—');
          return (
            <div key={`${card.symbol}-${idx}`} className="flex items-center gap-10 shrink-0">
              <div
                className={`flex items-center gap-2.5 text-[13px] shrink-0 ${closed ? 'opacity-70' : ''}`}
                title={`${card.display_name || card.symbol} • Day change • ${sessionLabel} • Vol ${safeInt(card.volume)} • OI ${card.open_interest != null ? safeInt(card.open_interest) : '—'}`}
              >
                <span className="font-bold text-foreground tracking-tight">
                  {card.display_name || card.symbol}
                </span>
                <span className="tabular-nums font-semibold text-foreground">{formatLtp(card)}</span>
                <span
                  className={`tabular-nums inline-flex items-center gap-1 font-bold px-2.5 py-1 rounded-full text-[11.5px] leading-none border ${
                    isNeutral
                      ? 'text-muted-foreground bg-secondary border-border'
                      : isPos
                        ? 'text-emerald-700 bg-emerald-500/10 border-emerald-500/25'
                        : 'text-rose-700 bg-rose-500/10 border-rose-500/25'
                  }`}
                >
                  <span className="text-[9px] leading-none">{isNeutral ? '—' : isPos ? '▲' : '▼'}</span>
                  {Math.abs(changePct).toFixed(2)}%
                </span>
                <span className="hidden sm:inline text-xs text-muted-foreground tabular-nums font-medium">
                  {formatChange(card)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export const MarketTicker = memo(MarketTickerInner);

