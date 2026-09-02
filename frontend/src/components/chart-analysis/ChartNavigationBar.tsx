'use client';

import { Clock3, Activity, Wifi, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';

const TIMEFRAMES = [
  { id: '1m', label: '1M' },
  { id: '5m', label: '5M' },
  { id: '15m', label: '15M' },
  { id: '1h', label: '1H' },
  { id: '4h', label: '4H' },
  { id: '1D', label: '1D' },
] as const;

type ChartNavigationBarProps = {
  activeTf: string;
  onTfChange: (tf: string) => void;
  data?: any;
  symbol?: string;
  loading?: boolean;
};

function FreshnessDot({ freshness }: { freshness?: string }) {
  const cfg =
    freshness === 'LIVE'
      ? { dot: 'bg-emerald-500', label: 'LIVE', cls: 'bg-emerald-500/10 text-emerald-700 border-emerald-500/20' }
      : freshness === 'STALE' || freshness === 'DELAYED'
        ? { dot: 'bg-amber-500', label: freshness, cls: 'bg-amber-500/10 text-amber-700 border-amber-500/20' }
        : freshness === 'DATA_UNAVAILABLE'
          ? { dot: 'bg-slate-400', label: 'OFFLINE', cls: 'bg-slate-100 text-slate-600 border-slate-200' }
          : { dot: 'bg-slate-400', label: '—', cls: 'bg-muted text-muted-foreground border-border' };
  return (
    <span className={cn('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold tracking-wide border', cfg.cls)}>
      <span className={cn('w-1.5 h-1.5 rounded-full', cfg.dot, freshness === 'LIVE' && 'animate-pulse')} />
      {cfg.label}
    </span>
  );
}

export function ChartNavigationBar({ activeTf, onTfChange, data, symbol, loading }: ChartNavigationBarProps) {
  const freshness: string | undefined = data?.freshness;
  const marketStatus: string | undefined = data?.market_status;
  const age: number | undefined = data?.data_age_seconds;
  const exchange: string | undefined = data?.exchange;
  const assetClass: string | undefined = data?.asset_class;

  const hasData = !!data && !loading;
  const isLive = freshness === 'LIVE';

  return (
    <div className="w-full rounded-xl border border-border bg-card/90 backdrop-blur supports-[backdrop-filter]:bg-card/70 shadow-sm overflow-hidden">
      {/* Top strip — subtle accent */}
      <div className="h-[2px] w-full bg-gradient-to-r from-primary/60 via-primary/20 to-transparent" aria-hidden />

      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 px-3 sm:px-4 py-3">
        {/* Left: context */}
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="hidden sm:flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 border border-primary/15 shrink-0">
            <TrendingUp className="w-4 h-4 text-primary" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-bold tracking-tight truncate">
                {symbol || data?.symbol || 'Select instrument'}
              </span>
              {hasData && (
                <>
                  <span className="h-3 w-px bg-border hidden sm:inline-block" />
                  <span className="text-xs text-muted-foreground truncate">
                    {data?.display_name ? `${data.display_name} • ${exchange || ''}`.trim() : exchange || assetClass || ''}
                  </span>
                  <span
                    className={cn(
                      'inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border',
                      marketStatus === 'OPEN'
                        ? 'bg-emerald-500/10 text-emerald-700 border-emerald-500/20'
                        : 'bg-muted text-muted-foreground border-border'
                    )}
                  >
                    {marketStatus || '—'}
                  </span>
                </>
              )}
              {loading && <span className="text-xs text-muted-foreground animate-pulse">Loading…</span>}
            </div>
            {hasData && (
              <div className="flex items-center gap-1.5 mt-1 text-[11px] text-muted-foreground">
                <Clock3 className="w-3 h-3 opacity-60" />
                <span className="tabular-nums">
                  {data?.data_timestamp ? new Date(data.data_timestamp).toLocaleTimeString() : '—'}
                </span>
                {typeof age === 'number' && age >= 0 && (
                  <>
                    <span className="opacity-40">•</span>
                    <span className={cn('tabular-nums', age > 120 && 'text-amber-600')}>
                      {age}s ago
                    </span>
                  </>
                )}
                {exchange && (
                  <>
                    <span className="opacity-40">•</span>
                    <span>{exchange}</span>
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Center: timeframe pills */}
        <div className="flex items-center gap-1 p-1 rounded-full bg-muted/60 border border-border/60 self-start lg:self-center overflow-x-auto scrollbar-none max-w-full">
          {TIMEFRAMES.map((tf) => {
            const active = activeTf === tf.id;
            const isUnavailable = hasData && data?.unavailable_timeframes?.includes(tf.id);
            return (
              <button
                key={tf.id}
                type="button"
                onClick={() => !isUnavailable && onTfChange(tf.id)}
                disabled={isUnavailable}
                aria-pressed={active}
                title={isUnavailable ? 'Data unavailable' : tf.label}
                className={cn(
                  'relative inline-flex items-center justify-center px-3.5 py-1.5 rounded-full text-xs font-semibold tracking-wide transition-all duration-150 shrink-0',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-0',
                  active
                    ? 'bg-primary text-primary-foreground shadow-sm ring-1 ring-primary/20'
                    : isUnavailable
                      ? 'bg-transparent text-muted-foreground/40 cursor-not-allowed line-through decoration-dashed'
                      : 'bg-card text-muted-foreground hover:bg-accent hover:text-foreground border border-transparent hover:border-border'
                )}
              >
                {tf.label}
                {isUnavailable && <span className="absolute -top-1 -right-1 w-1.5 h-1.5 rounded-full bg-amber-500" aria-hidden />}
              </button>
            );
          })}
        </div>

        {/* Right: status */}
        <div className="flex items-center gap-2 self-start lg:self-center shrink-0">
          <FreshnessDot freshness={freshness} />
          <span className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-muted/60 border border-border/60 text-[11px] font-medium text-muted-foreground">
            <Wifi className={cn('w-3 h-3', isLive ? 'text-emerald-500' : 'text-muted-foreground/40')} />
            <span className="hidden xl:inline">Fyers • Binance</span>
            <span className="xl:hidden">Feed 1s</span>
          </span>
          <span className="hidden md:inline-flex items-center gap-1 px-2 py-1 rounded-full bg-secondary/60 border border-border text-[11px] font-medium text-muted-foreground">
            <Activity className="w-3 h-3 opacity-60" />
            {hasData ? `${Object.keys(data?.timeframes || {}).length} TF` : '— TF'}
          </span>
        </div>
      </div>

      {/* Bottom meta — only when data */}
      {hasData && (
        <div className="flex flex-wrap items-center gap-2 px-3 sm:px-4 py-2 bg-muted/30 border-t border-border/60 text-[11px] leading-none text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <span className="w-1 h-1 rounded-full bg-primary/60" aria-hidden />
            Universe: NIFTY • BANKNIFTY • FINNIFTY • SENSEX • BTC • ETH • SOL
          </span>
          <span className="hidden sm:inline opacity-30">•</span>
          <span className="tabular-nums">Generated {data?.generated_at ? new Date(data.generated_at).toLocaleTimeString() : '—'}</span>
          {data?.unavailable_timeframes?.length > 0 && (
            <>
              <span className="opacity-30">•</span>
              <span className="text-amber-700 font-medium">
                Unavailable: {data.unavailable_timeframes.join(', ')}
              </span>
            </>
          )}
        </div>
      )}
    </div>
  );
}
