'use client';

import { memo, useMemo, useEffect, useRef, useState, useCallback } from 'react';
import { IndexCard } from '@/lib/types';
import { safeInt } from '@/lib/utils';
import { useOptionalLiveMarketContext } from '@/context/LiveMarketContext';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import { TrendingUp, TrendingDown, RefreshCw } from 'lucide-react';
import { resolveCardSymbol } from '@/lib/symbols';

export interface MarketTickerProps {
  cards?: IndexCard[];
  loading?: boolean;
  onSelectSymbol?: (symbol: string) => void;
}

const PRIMARY_BENCHMARKS = [
  'NIFTY 50',
  'BANKNIFTY',
  'SENSEX',
  'FINNIFTY',
  'INDIA VIX',
  'MIDCPNIFTY',
] as const;

/** Fallback placeholders ensuring zero CLS and stable structure even on cold starts or network loss */
const FALLBACK_BENCHMARKS: Array<Pick<IndexCard, 'symbol' | 'display_name' | 'ltp' | 'change' | 'change_percent'>> = [
  { symbol: 'NIFTY 50', display_name: 'NIFTY 50', ltp: 0, change: 0, change_percent: 0 },
  { symbol: 'BANKNIFTY', display_name: 'BANKNIFTY', ltp: 0, change: 0, change_percent: 0 },
  { symbol: 'SENSEX', display_name: 'SENSEX', ltp: 0, change: 0, change_percent: 0 },
];

/** Robust number parser */
function safeNum(val: unknown, fallback = 0): number {
  if (typeof val === 'number') return Number.isFinite(val) ? val : fallback;
  if (typeof val === 'string') {
    const parsed = parseFloat(val.replace(/,/g, ''));
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
}

/** Formats price using Indian Numbering System (e.g. 23,259.30) */
export function formatIndianPrice(val: number | null | undefined): string {
  const n = safeNum(val, NaN);
  if (Number.isNaN(n) || n <= 0) return '—';
  return n.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Formats signed points change (e.g. +142.50 or -218.50) */
export function formatPointsChange(change: number | null | undefined): string {
  const n = safeNum(change, NaN);
  if (Number.isNaN(n)) return '—';
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

function isCryptoCard(card: Pick<IndexCard, 'symbol' | 'provider'>): boolean {
  const sym = (card.symbol || '').toUpperCase();
  const prov = (card.provider || '').toLowerCase();
  return prov.includes('binance') || sym.endsWith('USDT') || sym.endsWith('BTC');
}

/** Mini SVG Sparkline for intraday trajectory */
function MicroSparkline({
  points,
  isPositive,
}: {
  points: number[];
  isPositive: boolean;
}) {
  if (!points || points.length < 2) return null;

  const valid = points.filter((p) => typeof p === 'number' && Number.isFinite(p));
  if (valid.length < 2) return null;

  const min = Math.min(...valid);
  const max = Math.max(...valid);
  const range = max - min || 1;

  const width = 34;
  const height = 13;
  const padding = 1;

  const pathCoords = valid.map((val, idx) => {
    const x = (idx / (valid.length - 1)) * (width - 2 * padding) + padding;
    const y = height - padding - ((val - min) / range) * (height - 2 * padding);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const pathD = `M ${pathCoords.join(' L ')}`;
  const strokeColor = isPositive ? 'var(--ds-bull, #12934f)' : 'var(--ds-bear, #d92d20)';

  return (
    <svg
      width={width}
      height={height}
      className="shrink-0 opacity-80 group-hover/item:opacity-100 transition-opacity"
      aria-hidden="true"
    >
      <path
        d={pathD}
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Micro Day Range Indicator showing current position between Day Low & Day High */
function DayRangeBar({
  ltp,
  low,
  high,
}: {
  ltp: number;
  low: number;
  high: number;
}) {
  if (!Number.isFinite(ltp) || !Number.isFinite(low) || !Number.isFinite(high) || high <= low || ltp <= 0) {
    return null;
  }

  const clampedLtp = Math.min(Math.max(ltp, low), high);
  const positionPct = ((clampedLtp - low) / (high - low)) * 100;

  return (
    <div
      className="hidden 2xl:flex items-center gap-1.5 pl-1.5 border-l border-border/50 text-[10px] text-muted-foreground font-mono select-none"
      title={`Day Range • Low: ₹${formatIndianPrice(low)} | High: ₹${formatIndianPrice(high)}`}
    >
      <span className="text-[9px] opacity-70">L</span>
      <div className="relative w-10 h-1 bg-secondary rounded-full overflow-hidden border border-border/60">
        <div
          className="absolute top-0 bottom-0 left-0 bg-primary/70 rounded-full transition-all duration-300"
          style={{ width: `${Math.min(Math.max(positionPct, 6), 100)}%` }}
        />
      </div>
      <span className="text-[9px] opacity-70">H</span>
    </div>
  );
}

/** Single Interactive Index Card Item */
function IndexCardItem({
  card,
  onSelect,
  isPriority,
}: {
  card: IndexCard;
  onSelect?: (symbol: string) => void;
  isPriority?: boolean;
}) {
  const ltp = safeNum(card.ltp, 0);
  const prevClose = safeNum(card.previous_close, 0);

  // Defensive calculation: compute change & pct if missing or inconsistent
  let change = safeNum(card.change, NaN);
  let changePct = safeNum(card.change_percent, NaN);

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

  const handleClick = useCallback(() => {
    const symbolFocus = resolveCardSymbol(displayName);
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('droid:select-instrument', {
          detail: { symbol: symbolFocus, rawSymbol: card.symbol, displayName },
        })
      );
    }
    onSelect?.(symbolFocus);
  }, [card.symbol, displayName, onSelect]);

  const formattedLtp = formatIndianPrice(ltp);
  const formattedChange = formatPointsChange(change);
  const safeVol = card.volume ? safeInt(card.volume) : '—';
  const safeOi = card.open_interest != null ? safeInt(card.open_interest) : '—';

  return (
    <button
      type="button"
      onClick={handleClick}
      className={`group/item flex items-center gap-1.5 sm:gap-2 px-1.5 sm:px-2 py-0.5 rounded-[3px] border border-transparent hover:border-border hover:bg-[#f7f7f7] transition-colors cursor-pointer shrink-0 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary ${
        closed ? 'opacity-80' : ''
      }`}
      title={`${displayName} • LTP: ₹${formattedLtp} (${formattedChange}) • Session: ${sessionLabel} • Vol: ${safeVol} • OI: ${safeOi} • Click to focus forecast`}
      aria-label={`${displayName} index at ${formattedLtp}, ${isPos ? 'up' : isNeg ? 'down' : 'unchanged'} by ${Math.abs(changePct || 0).toFixed(2)}%`}
    >
      {/* Symbol Name */}
      <span className="font-bold text-foreground tracking-tight text-[11.5px] sm:text-[12px] whitespace-nowrap group-hover/item:text-primary transition-colors">
        {displayName}
      </span>

      {/* Live LTP with directional micro-flash */}
      <span
        className={`tabular-nums font-mono font-bold text-[12px] sm:text-[12.5px] px-1 py-0.5 rounded-[2px] transition-colors duration-200 ${
          flash === 'up'
            ? 'bg-emerald-500/15 text-emerald-700'
            : flash === 'down'
              ? 'bg-rose-500/15 text-rose-700'
              : 'text-foreground'
        }`}
      >
        {formattedLtp}
      </span>

      {/* Badge for Percentage Change */}
      <span
        className={`tabular-nums inline-flex items-center gap-0.5 sm:gap-1 font-semibold px-1 sm:px-1.5 py-0.5 rounded-[2px] text-[10px] sm:text-[10.5px] leading-tight border transition-colors ${
          isNeutral
            ? 'text-muted-foreground bg-secondary border-border'
            : isPos
              ? 'text-emerald-700 bg-emerald-500/10 border-emerald-500/25'
              : 'text-rose-700 bg-rose-500/10 border-rose-500/25'
        }`}
      >
        {isNeutral ? (
          <span className="text-[8px] leading-none opacity-60">—</span>
        ) : isPos ? (
          <TrendingUp className="w-2.5 h-2.5 shrink-0" aria-hidden="true" />
        ) : (
          <TrendingDown className="w-2.5 h-2.5 shrink-0" aria-hidden="true" />
        )}
        {Math.abs(changePct || 0).toFixed(2)}%
      </span>

      {/* Points Change (hidden on mobile, visible on tablet/desktop) */}
      <span
        className={`hidden md:inline tabular-nums font-mono text-[11px] sm:text-[11.5px] font-medium ${
          isPos
            ? 'text-emerald-700/80 dark:text-emerald-400/90'
            : isNeg
              ? 'text-rose-700/80 dark:text-rose-400/90'
              : 'text-muted-foreground'
        }`}
      >
        {formattedChange}
      </span>

      {/* Micro Sparkline when tick points exist and screen is wide */}
      {isPriority && card.sparkline && card.sparkline.length > 2 && (
        <div className="hidden lg:block pl-0.5">
          <MicroSparkline points={card.sparkline} isPositive={!isNeg} />
        </div>
      )}

      {/* Intraday High/Low Range Gauge */}
      {card.high > 0 && card.low > 0 && (
        <DayRangeBar ltp={ltp} low={card.low} high={card.high} />
      )}
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
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
          Offline
        </span>

        <div className="h-4 w-px bg-border/60 shrink-0" />

        {/* Static Fallback Placeholders */}
        <div className="flex items-center gap-4 sm:gap-6 text-[12px] sm:text-[12.5px] text-muted-foreground overflow-hidden">
          {FALLBACK_BENCHMARKS.map((f, i) => (
            <div
              key={f.symbol}
              className={`flex items-center gap-1.5 shrink-0 ${
                i === 2 ? 'hidden sm:flex' : ''
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
  // Live market ticks + status from LiveMarketContext
  let contextCards: IndexCard[] | undefined;
  let contextLoading: boolean | undefined;
  let contextRefetch: (() => Promise<void>) | undefined;
  let streamState: string | undefined;
  let ticksFresh: boolean | undefined;

  try {
    const live = useOptionalLiveMarketContext();
    contextCards = live?.cards;
    contextLoading = live?.loading;
    contextRefetch = live?.refetchCards;
    streamState = live?.streamState;
    ticksFresh = live?.ticksFresh;
  } catch {
    // Isolated usage / stories
  }

  // Market session overview
  let marketSession: string | undefined;
  try {
    const market = useOptionalMarketDataContext();
    marketSession = market?.marketStatus?.session;
  } catch {}

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
  // - On mobile (<sm): Show NIFTY 50 and BANKNIFTY cleanly
  // - On small screens (sm): Show NIFTY 50, BANKNIFTY, SENSEX
  // - On large screens (lg): Show 4th benchmark (e.g. FINNIFTY)
  // - On xl screens (xl+): Show 5th benchmark (e.g. INDIA VIX)
  const getItemVisibilityClass = (idx: number) => {
    if (idx < 2) return 'flex';
    if (idx === 2) return 'hidden sm:flex';
    if (idx === 3) return 'hidden lg:flex';
    return 'hidden xl:flex';
  };

  return (
    <nav
      role="region"
      aria-label="Live Market Indices Ribbon"
      className="relative h-10 border-b border-border bg-card flex items-center px-3 sm:px-4 md:px-6 select-none text-[12.5px] z-20 overflow-hidden"
    >
      {/* Stream Status Chip */}
      <div
        className="flex items-center gap-1.5 px-1.5 sm:px-2 py-0.5 rounded-[2px] bg-secondary border border-border text-[10px] sm:text-[10.5px] font-semibold tracking-wide uppercase shrink-0 text-muted-foreground"
        title={`Feed: ${streamState || 'CONNECTED'} • Session: ${marketSession || (isClosed ? 'Closed' : 'Open')}`}
      >
        {isClosed ? (
          <>
            <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
            <span className="hidden xs:inline">Closed</span>
          </>
        ) : isLive ? (
          <>
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-emerald-700 dark:text-emerald-400 hidden xs:inline">Live</span>
          </>
        ) : (
          <>
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
            <span className="text-amber-700 dark:text-amber-400 hidden xs:inline">Sync</span>
          </>
        )}
      </div>

      {/* Divider between status and items */}
      <div className="h-4 w-px bg-border/60 mx-2 sm:mx-3 shrink-0" aria-hidden="true" />

      {/* Stationary Fitted Indices Ribbon (NO SCROLLBAR, NEVER OVERFLOWS) */}
      <div className="flex items-center justify-start gap-1 sm:gap-2.5 md:gap-3.5 lg:gap-5 overflow-hidden w-full">
        {orderedCards.map((card, idx) => {
          const visClass = getItemVisibilityClass(idx);
          return (
            <div
              key={`${card.symbol || card.display_name}-${idx}`}
              className={`items-center gap-1 sm:gap-2.5 md:gap-3.5 lg:gap-5 shrink-0 ${visClass}`}
            >
              <IndexCardItem
                card={card}
                onSelect={onSelectSymbol}
                isPriority={idx < 2}
              />
              {idx < orderedCards.length - 1 && (
                <div
                  className={`h-3.5 w-px bg-border/40 shrink-0 ${
                    idx === 1 ? 'hidden sm:block' : idx === 2 ? 'hidden lg:block' : idx === 3 ? 'hidden xl:block' : ''
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
