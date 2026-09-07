import { memo, useEffect, useMemo, useState } from 'react';
import { CryptoTicker, IndexCard } from '@/lib/types';
import { safeInt } from '@/lib/utils';
import { useOptionalLiveMarketContext } from '@/context/LiveMarketContext';
import { api } from '@/lib/api';
import { fetchLiveBinanceTickers } from '@/lib/binanceLive';

const EQUITY_ORDER = ['NIFTY 50', 'BANKNIFTY', 'SENSEX'];
const CRYPTO_ORDER = ['BTCUSDT', 'ETHUSDT'];
const CRYPTO_POLL_MS = 20000;

function isCryptoCard(card: Pick<IndexCard, 'symbol' | 'provider'>): boolean {
  const sym = (card.symbol || '').toUpperCase();
  const prov = (card.provider || '').toLowerCase();
  return prov.includes('binance') || sym.endsWith('USDT') || sym.endsWith('BTC');
}

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

function cryptoToCard(t: CryptoTicker): IndexCard {
  const sym = (t.symbol || '').toUpperCase();
  const base = (t.base_asset || t.asset || sym.replace(/USDT$|BTC$/, '') || sym).toUpperCase();
  const price = Number(t.price) || 0;
  const change = Number(t.change_24h) || 0;
  const changePct = Number(t.change_percent_24h) || 0;
  return {
    symbol: sym,
    display_name: base,
    ltp: price,
    change,
    change_percent: changePct,
    open: price,
    high: Number(t.high_24h) || price,
    low: Number(t.low_24h) || price,
    previous_close: price - change,
    volume: Number(t.volume_24h_quote) || 0,
    open_interest: null,
    sparkline: Array.isArray(t.sparkline) ? t.sparkline : [],
    // Crypto trades 24/7 — never force CLOSED when NSE is shut.
    status: 'LIVE',
    timestamp: t.last_updated || null,
    provider: t.provider || 'binance',
  };
}

function formatLtp(card: IndexCard): string {
  const n = Number(card.ltp);
  if (!Number.isFinite(n)) return '—';
  if (isCryptoCard(card)) {
    return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  return n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatChange(card: IndexCard): string {
  const n = Number(card.change);
  if (!Number.isFinite(n)) return '—';
  if (n === 0) {
    return isCryptoCard(card)
      ? `$${(0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : (0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  const prefix = n > 0 ? '+' : '-';
  if (isCryptoCard(card)) {
    return `${prefix}$${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
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
  const usingProps = cardsProp !== undefined;
  const baseCards = useMemo(() => cardsProp ?? contextCards ?? [], [cardsProp, contextCards]);
  const baseLoading = loadingProp ?? contextLoading ?? false;

  // --- Hybrid crypto leg: BTC/ETH via backend (fallback direct Binance) ---
  // Only in live mode (no explicit cards prop) so stories/tests stay isolated.
  const [cryptoTickers, setCryptoTickers] = useState<CryptoTicker[]>([]);
  useEffect(() => {
    if (usingProps || typeof window === 'undefined') return;
    let stopped = false;
    const fetchCrypto = async () => {
      if (document.hidden) return;
      try {
        const res = await api.getCryptoTickers();
        if (!stopped && res?.data && Array.isArray(res.data) && res.data.length > 0) {
          setCryptoTickers(res.data);
          return;
        }
      } catch {
        // Fall through to direct Binance mirror.
      }
      try {
        const direct = await fetchLiveBinanceTickers();
        if (!stopped && direct.length > 0) setCryptoTickers(direct);
      } catch {
        // Keep last-known crypto; ticker must never blank on poll failure.
      }
    };
    void fetchCrypto();
    const id = setInterval(() => void fetchCrypto(), CRYPTO_POLL_MS);
    const onVis = () => {
      if (!document.hidden) void fetchCrypto();
    };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      stopped = true;
      clearInterval(id);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [usingProps]);

  const cards = useMemo<IndexCard[]>(() => {
    // Isolated prop mode: preserve legacy behavior exactly.
    if (usingProps) return baseCards;
    const equities: IndexCard[] = [];
    for (const wanted of EQUITY_ORDER) {
      const hit = findEquityCard(baseCards, wanted);
      if (hit) equities.push(hit);
    }
    // If FYERS snapshot hasn't arrived yet, fall back to any non-crypto cards
    // so the strip isn't empty while loading (deduped by symbol).
    if (equities.length === 0) {
      const nonCrypto = baseCards.filter((c) => !isCryptoCard(c));
      if (nonCrypto.length > 0) return nonCrypto.slice(0, 3);
    }
    const bySymbol = new Map(baseCards.map((c) => [(c.symbol || '').toUpperCase(), c]));
    const cryptoCards: IndexCard[] = [];
    // Prefer freshly polled crypto (24/7 LIVE); fall back to context cards
    // when the poll hasn't returned yet (e.g. crypto-provider mode).
    const pollBySymbol = new Map(cryptoTickers.map((t) => [(t.symbol || '').toUpperCase(), t]));
    for (const sym of CRYPTO_ORDER) {
      const polled = pollBySymbol.get(sym);
      if (polled) {
        cryptoCards.push(cryptoToCard(polled));
        continue;
      }
      const ctx = bySymbol.get(sym);
      if (ctx) {
        cryptoCards.push(ctx.status === 'LIVE' ? ctx : { ...ctx, status: 'LIVE' });
      }
    }
    const merged = [...equities, ...cryptoCards];
    if (merged.length > 0) return merged;
    return baseCards;
  }, [baseCards, cryptoTickers, usingProps]);

  const equityCount = useMemo(() => {
    if (usingProps) return 0;
    let n = 0;
    for (const c of cards) {
      if (!isCryptoCard(c)) n += 1;
      else break;
    }
    return n;
  }, [cards, usingProps]);

  const loading = baseLoading && cards.length === 0;
  const loopCards = useMemo(() => (!cards || cards.length === 0 ? [] : [...cards, ...cards]), [cards]);

  if (loading) {
    return (
      <div className="h-8 border-b border-border bg-card overflow-hidden flex items-center px-4 gap-6">
        <div className="flex items-center gap-6">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center gap-2 animate-pulse">
              <div className="h-3 w-16 bg-muted rounded" />
              <div className="h-3 w-12 bg-muted rounded" />
              <div className="h-3 w-10 bg-muted rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!cards || cards.length === 0) return null;

  return (
    <div className="group relative h-8 border-b border-border bg-card overflow-hidden flex items-center">
      {/* edge fades */}
      <div className="pointer-events-none absolute left-0 top-0 bottom-0 w-12 bg-gradient-to-r from-card to-transparent z-10" />
      <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-12 bg-gradient-to-l from-card to-transparent z-10" />

      <div className="flex items-center gap-8 whitespace-nowrap animate-marquee group-hover:[animation-play-state:paused] will-change-transform">
        {loopCards.map((card, idx) => {
          const changeVal = Number(card.change) || 0;
          const isPos = changeVal > 0;
          const isNeutral = changeVal === 0;
          const changePct = Number(card.change_percent) || 0;
          const crypto = isCryptoCard(card);
          const closed = card.status === 'CLOSED';
          const posInLoop = idx % cards.length;
          const showDivider = !usingProps && equityCount > 0 && posInLoop === equityCount;
          const basisLabel = crypto ? '24h change' : 'Day change';
          const sessionLabel = crypto ? 'LIVE 24/7' : closed ? 'Closed' : (card.status || '—');
          return (
            <div key={`${card.symbol}-${idx}`} className="flex items-center gap-8 shrink-0">
              {showDivider && <span aria-hidden className="h-4 w-px bg-border/80" />}
              <div
                className={`flex items-center gap-2 text-xs shrink-0 ${closed && !crypto ? 'opacity-70' : ''}`}
                title={`${card.display_name || card.symbol}${crypto ? ' / USDT' : ''} • ${basisLabel} • ${sessionLabel} • Vol ${safeInt(card.volume)}${!crypto ? ` • OI ${card.open_interest != null ? safeInt(card.open_interest) : '—'}` : ''}`}
              >
                <span className="font-bold text-foreground tracking-tight">
                  {card.display_name || card.symbol}
                  {crypto && <span className="ml-0.5 font-normal text-muted-foreground">/USDT</span>}
                </span>
                <span className="tabular-nums font-semibold text-foreground">{formatLtp(card)}</span>
                <span
                  className={`tabular-nums inline-flex items-center gap-0.5 font-semibold px-1.5 py-0.5 rounded text-[11px] leading-none border ${
                    isNeutral
                      ? 'text-muted-foreground bg-secondary border-border'
                      : isPos
                        ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                        : 'text-rose-600 dark:text-rose-400 bg-rose-500/10 border-rose-500/20'
                  }`}
                >
                  <span className="text-[9px] leading-none">{isNeutral ? '—' : isPos ? '▲' : '▼'}</span>
                  {Math.abs(changePct).toFixed(2)}%
                </span>
                <span className="hidden sm:inline text-[11px] text-muted-foreground tabular-nums">
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

