'use client';

import { memo, useMemo, useEffect, useRef, useState, useCallback } from 'react';
import { IndexCard } from '@/lib/types';
import { safeInt } from '@/lib/utils';
import { toNumber } from '@/lib/coerce';
import { useOptionalLiveMarketContext } from '@/context/LiveMarketContext';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import { TrendingUp, TrendingDown, RefreshCw } from 'lucide-react';
import { isCryptoCard, resolveCardSymbol } from '@/lib/symbols';

export interface MarketTickerProps {
  cards?: IndexCard[];
  loading?: boolean;
  onSelectSymbol?: (symbol: string) => void;
}

const PRIMARY_BENCHMARKS = [
  'NIFTY 50',
  'BANKNIFTY',
  'SENSEX',
  'INDIA VIX',
  'FINNIFTY',
  'MIDCPNIFTY',
] as const;

/** Fallback placeholders ensuring zero CLS and stable structure even on cold starts or network loss */
const FALLBACK_BENCHMARKS: Array<Pick<IndexCard, 'symbol' | 'display_name' | 'ltp' | 'change' | 'change_percent'>> = [
  { symbol: 'NIFTY 50', display_name: 'NIFTY 50', ltp: 0, change: 0, change_percent: 0 },
  { symbol: 'BANKNIFTY', display_name: 'BANKNIFTY', ltp: 0, change: 0, change_percent: 0 },
  { symbol: 'SENSEX', display_name: 'SENSEX', ltp: 0, change: 0, change_percent: 0 },
  { symbol: 'INDIA VIX', display_name: 'INDIA VIX', ltp: 0, change: 0, change_percent: 0 },
];

/**
 * Broker cards may carry grouped digits ("23,259.30"); `toNumber` is strict
 * about those, so strip separators first and delegate all finite-number
 * coercion to the shared helper.
 */
function cardNumber(val: unknown): number | null {
  if (typeof val === 'string') {
    return toNumber(val.replace(/,/g, ''), { rejectBlankString: true });
  }
  return toNumber(val);
}

/** Formats price using Indian Numbering System (e.g. 23,259.30) */
export function formatIndianPrice(val: number | null | undefined): string {
  const n = cardNumber(val);
  if (n === null || n <= 0) return '—';
  return n.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Formats signed points change (e.g. +142.50 or -218.50) */
export function formatPointsChange(change: number | null | undefined): string {
  const n = cardNumber(change);
  if (n === null) return '—';
  if (Math.abs(n) < 0.001) return '0.00';
  const prefix = n > 0 ? '+' : '-';
  return `${prefix}${Math.abs(n).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

/** Robust alias matching across broker conventions */
export function matchBenchmarkAlias(card: IndexCard, wanted: string): boolean {
  const w = wanted.toUpperCase().trim();
  const sym = (card.symbol || '').toUpperCase().trim();
  const name = (card.display_name || '').toUpperCase().trim();
  const joined = `${sym} ${name}`;

  if (sym === w || name === w) return true;

  if (w === 'NIFTY 50') {
    return (
      joined.includes('NIFTY50') ||
      joined.includes('NIFTY 50') ||
      joined.includes('NSE:NIFTY50-INDEX') ||
      (/(^|\s)NIFTY(\s|$)/.test(joined) && !joined.includes('BANK') && !joined.includes('FIN') && !joined.includes('MIDCAP'))
    );
  }

  if (w === 'BANKNIFTY') {
    return (
      joined.includes('BANKNIFTY') ||
      joined.includes('NIFTY BANK') ||
      joined.includes('BANK_NIFTY') ||
      joined.includes('NIFTYBANK') ||
      joined.includes('NSE:NIFTYBANK-INDEX')
    );
  }

  if (w === 'SENSEX') {
    return joined.includes('SENSEX') || joined.includes('BSE_SENSEX') || joined.includes('BSE:SENSEX-INDEX');
  }

  if (w === 'FINNIFTY') {
    return (
      joined.includes('FINNIFTY') ||
      joined.includes('FIN_NIFTY') ||
      joined.includes('FIN SERVICE') ||
      joined.includes('NSE:FINNIFTY-INDEX')
    );
  }

  if (w === 'INDIA VIX') {
    return joined.includes('INDIA VIX') || joined.includes('INDIAVIX') || joined.includes('NSE:INDIAVIX-INDEX');
  }

  if (w === 'MIDCPNIFTY') {
    return joined.includes('MIDCPNIFTY') || joined.includes('MIDCAP SELECT') || joined.includes('MIDCAP');
  }

  return false;
}

/** Single Interactive Index Card Item */
function IndexCardItem({
  card,
  onSelect,
}: {
  card: IndexCard;
  onSelect?: (symbol: string) => void;
}) {
  const ltp = cardNumber(card.ltp) ?? 0;
  const prevClose = cardNumber(card.previous_close) ?? 0;

  // Defensive calculation: compute change & pct if missing or inconsistent
  let change = cardNumber(card.change) ?? NaN;
  let changePct = cardNumber(card.change_percent) ?? NaN;

  if (Number.isNaN(change) && ltp > 0 && prevClose > 0) {
    change = Number((ltp - prevClose).toFixed(2));
  }
  if (Number.isNaN(changePct) && prevClose > 0 && !Number.isNaN(change)) {
    changePct = Number(((change / prevClose) * 100).toFixed(2));
  }

  const isPos = change > 0;
  const isNeg = change < 0;
  const isNeutral = !isPos && !isNeg;

  // Real-time tick pulse / flash animation
  const prevLtpRef = useRef<number>(ltp);
  const [flash, setFlash] = useState<'up' | 'down' | null>(null);

  useEffect(() => {
    if (prevLtpRef.current > 0 && ltp > 0 && ltp !== prevLtpRef.current) {
      setFlash(ltp > prevLtpRef.current ? 'up' : 'down');
      const timer = setTimeout(() => setFlash(null), 850);
      prevLtpRef.current = ltp;
      return () => clearTimeout(timer);
    }
    prevLtpRef.current = ltp;
  }, [ltp]);

  const closed = card.status === 'CLOSED';
  const sessionLabel = closed ? 'Closed' : (card.status || 'Live');
  const displayName = card.display_name || card.symbol;
  const isVix = displayName.toUpperCase().includes('VIX');

  const handleClick = useCallback(() => {
    // The shell maps the resolved symbol onto the shared InstrumentContext.
    onSelect?.(resolveCardSymbol(displayName));
  }, [displayName, onSelect]);

  const formattedLtp = formatIndianPrice(ltp);
  const formattedChange = formatPointsChange(change);
  const formattedPct = Number.isNaN(changePct)
    ? '0.00%'
    : isPos
      ? `+${Math.abs(changePct).toFixed(2)}%`
      : isNeg
        ? `-${Math.abs(changePct).toFixed(2)}%`
        : '0.00%';
  const safeVol = card.volume ? safeInt(card.volume) : '—';
  const safeOi = card.open_interest != null ? safeInt(card.open_interest) : '—';
  const currency = isVix ? '' : '₹';

  return (
    <button
      type="button"
      onClick={handleClick}
      className={`group/item flex items-center gap-1.5 sm:gap-2 px-1.5 sm:px-2 py-0.5 rounded-[3px] border border-transparent hover:border-border/60 hover:bg-secondary/60  transition-all cursor-pointer shrink-0 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary ${
        closed ? 'opacity-80' : ''
      }`}
      title={`${displayName} • LTP: ${currency}${formattedLtp} (${formattedChange}) • Session: ${sessionLabel} • Vol: ${safeVol} • OI: ${safeOi} • Click to select this instrument`}
      aria-label={`${displayName} index at ${formattedLtp}, ${isPos ? 'up' : isNeg ? 'down' : 'unchanged'} by ${formattedPct}`}
    >
      {/* Symbol Name */}
      <span
        className={`font-semibold tracking-tight text-[11.5px] sm:text-[12px] whitespace-nowrap transition-colors ${
          isVix
            ? 'text-warn-strong group-hover/item:text-warn font-bold'
            : 'text-foreground group-hover/item:text-primary'
        }`}
      >
        {displayName}
      </span>

      {/* Live LTP with directional micro-flash */}
      <span
        className={`tabular-nums font-mono font-bold text-[12px] sm:text-[12.5px] px-1 py-0.5 rounded-[2px] transition-colors duration-200 ${
          flash === 'up'
            ? 'bg-up/15 text-up-strong '
            : flash === 'down'
              ? 'bg-down/15 text-down-strong '
              : 'text-foreground'
        }`}
      >
        {formattedLtp}
      </span>

      {/* Unified Directional Change Capsule (combines points & percentage into single sleek pill) */}
      <span
        className={`tabular-nums font-mono inline-flex items-center gap-1 font-semibold px-1.5 py-0.5 rounded-[3px] text-[10.5px] leading-tight border transition-colors ${
          isNeutral
            ? 'text-muted-foreground bg-secondary/80 border-border'
            : isPos
              ? 'text-up-strong  bg-up/10 border-up/20'
              : 'text-down-strong  bg-down/10 border-down/20'
        }`}
      >
        {isNeutral ? (
          <span className="text-[9px] opacity-70">0.00 (0.00%)</span>
        ) : isPos ? (
          <>
            <TrendingUp className="w-2.5 h-2.5 shrink-0 text-up " aria-hidden="true" />
            <span>{formattedChange}</span>
            <span className="opacity-80">({formattedPct})</span>
          </>
        ) : (
          <>
            <TrendingDown className="w-2.5 h-2.5 shrink-0 text-down " aria-hidden="true" />
            <span>{formattedChange}</span>
            <span className="opacity-80">({formattedPct})</span>
          </>
        )}
      </span>

    </button>
  );
}

/** Shimmer Skeleton matching exact ticker height and dimensions for Zero CLS */
export function MarketTickerSkeleton() {
  return (
    <div
      className="h-10 border-b border-border bg-card overflow-hidden flex items-center px-3 sm:px-4 md:px-6 gap-3 sm:gap-4 select-none"
      role="status"
      aria-label="Loading live market indices"
    >
      {/* Stream Status Placeholder */}
      <div className="flex items-center gap-1.5 shrink-0">
        <div className="w-1.5 h-1.5 rounded-full bg-muted animate-pulse" />
        <div className="h-3 w-8 sm:w-10 bg-muted rounded animate-pulse" />
      </div>

      <div className="h-4 w-px bg-border/60 shrink-0" />

      {/* Index Pills Shimmer (fits stationary row) */}
      <div className="flex items-center justify-start gap-3 sm:gap-6 w-full overflow-hidden">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className={`flex items-center gap-2 animate-pulse shrink-0 ${
              i === 2 ? 'hidden sm:flex' : ''
            }`}
          >
            <div className="h-3.5 w-14 bg-muted rounded" />
            <div className="h-3.5 w-12 bg-muted rounded font-mono" />
            <div className="h-4.5 w-12 bg-muted rounded-md" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Fallback State when completely disconnected, ensuring the UI remains robust */
function MarketTickerFallback({
  onRetry,
}: {
  onRetry?: () => void;
}) {
  return (
    <div className="h-11 border-b border-border bg-card/85 backdrop-blur-xl overflow-hidden flex items-center justify-between px-3 sm:px-4 md:px-6 select-none shadow-[0_1px_2px_rgb(15_30_51/0.04)]">
      <div className="flex items-center gap-2 sm:gap-3 overflow-hidden">
        {/* Offline Status Badge */}
        <span className="flex items-center gap-1.5 px-1.5 sm:px-2 py-0.5 rounded-md bg-secondary border border-border text-muted-foreground font-semibold text-[10px] sm:text-[10.5px] uppercase tracking-wider shrink-0">
          <span className="w-1.5 h-1.5 rounded-full bg-warn animate-pulse" />
          Offline
        </span>

        <div className="h-4 w-px bg-border/60 shrink-0" />

        {/* Static Fallback Placeholders */}
        <div className="flex items-center gap-4 sm:gap-6 text-[12px] sm:text-[12.5px] text-muted-foreground overflow-hidden">
          {FALLBACK_BENCHMARKS.map((f, i) => (
            <div
              key={f.symbol}
              className={`flex items-center gap-1.5 shrink-0 ${
                i === 2 ? 'hidden sm:flex' : i === 3 ? 'hidden md:flex' : ''
              }`}
            >
              <span className="font-bold text-foreground/80">{f.display_name}</span>
              <span className="font-mono text-muted-foreground/70">—</span>
            </div>
          ))}
        </div>
      </div>

      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-1 px-2 py-1 text-xs font-semibold text-muted-foreground hover:text-foreground bg-secondary hover:bg-secondary/80 border border-border rounded-md transition-colors cursor-pointer shrink-0"
          title="Retry connecting to live market feed"
        >
          <RefreshCw className="w-3 h-3" />
          <span className="hidden sm:inline">Reconnect</span>
        </button>
      )}
    </div>
  );
}

function MarketTickerInner({
  cards: cardsProp,
  loading: loadingProp,
  onSelectSymbol,
}: MarketTickerProps) {
  // Live market ticks + status from context. The "optional" hooks return null
  // (they never throw) when the provider is absent, e.g. isolated stories.
  const live = useOptionalLiveMarketContext();
  const contextCards = live?.cards;
  const contextLoading = live?.loading;
  const contextRefetch = live?.refetchCards;
  const streamState = live?.streamState;
  const ticksFresh = live?.ticksFresh;

  // Market session overview
  const market = useOptionalMarketDataContext();
  const marketSession = market?.marketStatus?.session;

  const baseCards = useMemo(() => cardsProp ?? contextCards ?? [], [cardsProp, contextCards]);
  const baseLoading = loadingProp ?? contextLoading ?? false;

  // Filter non-crypto benchmarks and order cleanly
  const orderedCards = useMemo<IndexCard[]>(() => {
    const nonCrypto = baseCards.filter((c) => !isCryptoCard(c));
    const matched: IndexCard[] = [];
    const usedIndices = new Set<number>();

    // Match primary benchmarks in canonical order
    for (const benchmark of PRIMARY_BENCHMARKS) {
      const hitIndex = nonCrypto.findIndex((c, i) => !usedIndices.has(i) && matchBenchmarkAlias(c, benchmark));
      if (hitIndex !== -1) {
        matched.push(nonCrypto[hitIndex]);
        usedIndices.add(hitIndex);
      }
    }

    // Append any remaining equity benchmark cards
    nonCrypto.forEach((c, i) => {
      if (!usedIndices.has(i)) {
        matched.push(c);
      }
    });

    return matched;
  }, [baseCards]);

  // Show skeleton if loading and no cached data exists
  if (baseLoading && orderedCards.length === 0) {
    return <MarketTickerSkeleton />;
  }

  // If loading finished but no cards are available, show robust fallback instead of collapsing (zero CLS)
  if (orderedCards.length === 0) {
    return <MarketTickerFallback onRetry={contextRefetch} />;
  }

  const isLive = streamState === 'CONNECTED' && ticksFresh;
  const isClosed = marketSession === 'CLOSED';

  // Responsive stationary visibility logic:
  // - On mobile (<sm): Show NIFTY 50 and BANKNIFTY cleanly (0, 1)
  // - On small screens (sm: 640px+): Show NIFTY 50, BANKNIFTY, INDIA VIX (0, 1, 2)
  // Always show all 4 core benchmarks (NIFTY 50, BANKNIFTY, SENSEX, INDIA VIX)
  // - 0..3: Always visible
  // - 4 (FINNIFTY): Visible on wide screens (xl: 1280px+)
  // - 5+ (MIDCPNIFTY + rest): Visible on ultra-wide screens (2xl: 1536px+)
  const getItemVisibilityClass = (idx: number) => {
    if (idx < 4) return 'flex';
    if (idx === 4) return 'hidden xl:flex';
    return 'hidden 2xl:flex';
  };

  return (
    <nav
      role="region"
      aria-label="Live Market Indices Ribbon"
      className="relative h-10 border-b border-border bg-card flex items-center px-2.5 sm:px-4 md:px-5 select-none text-[12px] sm:text-[12.5px] z-20 overflow-hidden"
    >
      {/* Stream Status Chip */}
      <div
        className="flex items-center gap-1.5 px-2 py-0.5 rounded-[3px] bg-secondary/80 border border-border/80 text-[10px] sm:text-[10.5px] font-semibold tracking-wide uppercase shrink-0 text-muted-foreground"
        title={`Feed: ${streamState || 'CONNECTED'} • Session: ${marketSession || (isClosed ? 'Closed' : 'Open')}`}
      >
        {isClosed ? (
          <>
            <span className="w-1.5 h-1.5 rounded-full bg-ink-4" />
            <span className="font-mono">Closed</span>
          </>
        ) : isLive ? (
          <>
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-up opacity-75" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-up" />
            </span>
            <span className="text-up-strong font-mono">Live</span>
          </>
        ) : (
          <>
            <span className="w-1.5 h-1.5 rounded-full bg-warn animate-pulse" />
            <span className="text-warn-strong font-mono">Sync</span>
          </>
        )}
      </div>

      {/* Divider between status and items */}
      <div className="h-4 w-px bg-border/60 mx-1.5 sm:mx-2 shrink-0" aria-hidden="true" />

      {/* Stationary Fitted Indices Ribbon (NO SCROLLBAR, NEVER OVERFLOWS) */}
      <div className="flex items-center justify-start gap-1 sm:gap-1.5 md:gap-2 lg:gap-2.5 overflow-hidden w-full">
        {orderedCards.map((card, idx) => {
          const visClass = getItemVisibilityClass(idx);
          return (
            <div
              key={`${card.symbol || card.display_name}-${idx}`}
              className={`items-center gap-1 sm:gap-1.5 md:gap-2 shrink-0 ${visClass}`}
            >
              <IndexCardItem
                card={card}
                onSelect={onSelectSymbol}
              />
              {idx < orderedCards.length - 1 && (
                <div
                  className={`h-3.5 w-px bg-border/40 shrink-0 ${
                    idx < 3
                      ? 'block'
                      : idx === 3
                        ? 'hidden xl:block'
                        : 'hidden 2xl:block'
                  }`}
                  aria-hidden="true"
                />
              )}
            </div>
          );
        })}
      </div>
    </nav>
  );
}

export const MarketTicker = memo(MarketTickerInner);
export default MarketTicker;
