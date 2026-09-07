'use client';
import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ErrorCard } from '@/components/ui/ErrorCard';
import { Skeleton } from '@/components/ui/skeleton';
import {
  FeedHealthBadge,
  ScoreMeter,
  SignalStatusBadge,
  timeAgo,
} from '@/components/institutional/mi-ui';

type MiPanelProps = { instrument?: string };

interface MiData {
  instrument: string;
  regime: string;
  price_action: { structure: string; trend: string; momentum: string; location: string };
  bullish_score: number;
  bearish_score: number;
  breakout_pressure: number;
  breakdown_pressure?: number;
  false_breakout_risk: number;
  short_horizon: { direction: string; status: string; confidence: number };
  continuation: { direction: string; status: string; confidence: number; max_holding_minutes: number };
  max_holding: string;
  spot_price?: number | null;
  last_update_ms?: number | null;
  data_health?: string;
  feed_health?: { health?: string; staleness_ms?: number; is_stale?: boolean } | string;
  spot_source?: string;
  used_cache?: boolean;
}

const INSTRUMENTS = ['NIFTY', 'BANKNIFTY', 'SENSEX', 'BTCUSD'] as const;

export function MarketIntelligencePanel({ instrument = 'NIFTY', refreshKey }: MiPanelProps & { refreshKey?: number }) {
  const [data, setData] = useState<MiData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState(instrument);

  useEffect(() => { setSelected(instrument); }, [instrument]);

  useEffect(() => {
    let cancelled = false;
    let failures = 0;
    async function fetchMi(isManual = false) {
      if (isManual) setRefreshing(true);
      try {
        const res = await api.getInstitutionalMIDashboard(selected);
        const payload = (res?.data ?? res) as MiData | null;
        if (!cancelled && payload) {
          setData(payload);
          setError(null);
          failures = 0;
        }
      } catch (e) {
        failures += 1;
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Failed to load Market Intelligence');
          // Keep last-good data on transient failure; only clear when we never had data.
          setData(prev => prev);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    }
    setLoading(true);
    setError(null);
    void fetchMi();
    // Relaxed 30s poll with jitter for deep quant analytics — paused when hidden.
    // Back off on repeated failures so a down backend isn't hammered.
    let timeout: ReturnType<typeof setTimeout> | null = null;
    const schedule = () => {
      const base = failures > 0 ? Math.min(120000, 30000 * Math.pow(1.5, Math.min(failures, 4))) : 30000;
      const jittered = base * (0.8 + Math.random() * 0.4);
      timeout = setTimeout(() => {
        if (!document.hidden && !cancelled) void fetchMi().finally(schedule);
        else schedule();
      }, jittered);
    };
    schedule();
    const onVis = () => { if (!document.hidden && !cancelled) void fetchMi(); };
    document.addEventListener('visibilitychange', onVis);
    return () => { cancelled = true; if (timeout) clearTimeout(timeout); document.removeEventListener('visibilitychange', onVis); };
  }, [selected, refreshKey]);

  if (loading && !data) {
    return (
      <Card className="gap-3 py-4" data-testid="mi-panel-loading">
        <CardContent className="px-4 space-y-2">
          <Skeleton className="h-4 w-36" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-2/3" />
        </CardContent>
      </Card>
    );
  }
  if (!data && error) {
    return <ErrorCard title="Market Intelligence unavailable" message={error} onRetry={() => window.location.reload()} data-testid="mi-panel-error" />;
  }
  if (!data) return <ErrorCard title="Market Intelligence unavailable" />;

  const feed = typeof data.feed_health === 'string' ? data.feed_health : (data.feed_health?.health ?? data.data_health ?? 'UNKNOWN');
  const ageMs = typeof data.feed_health === 'object' && data.feed_health?.staleness_ms != null ? data.feed_health.staleness_ms : null;

  return (
    <Card className="gap-4 py-4" data-testid="mi-panel">
      <CardHeader className="px-4 flex-row items-center justify-between gap-2">
        <CardTitle className="text-sm tracking-widest uppercase">Market Intelligence</CardTitle>
        <div className="flex items-center gap-1.5">
          <select
            value={selected}
            onChange={e => setSelected(e.target.value)}
            aria-label="Instrument"
            className="text-xs bg-secondary text-secondary-foreground rounded-md px-2 py-1 border border-border cursor-pointer"
          >
            {INSTRUMENTS.map(i => <option key={i} value={i}>{i}</option>)}
          </select>
          <Button variant="ghost" size="icon-xs" onClick={() => { setLoading(true); setError(null); api.getInstitutionalMIDashboard(selected).then(r => setData(r?.data ?? r)).catch((e: unknown) => setError(e instanceof Error ? e.message : 'Refresh failed')).finally(() => setLoading(false)); }} disabled={refreshing} aria-label="Refresh">
            <RefreshCw className={refreshing ? 'animate-spin' : ''} />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="px-4 space-y-3">
        <div className="flex items-center gap-2 text-[11px] flex-wrap">
          <FeedHealthBadge feed={feed} quality={data.data_health} />
          {data.spot_price != null && (
            <span className="font-mono tabular-nums text-muted-foreground">
              {Number(data.spot_price).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
            </span>
          )}
          {data.last_update_ms != null && (
            <span className="text-muted-foreground" title={new Date(data.last_update_ms).toLocaleString()}>{timeAgo(data.last_update_ms)}</span>
          )}
          {data.used_cache && <span className="text-amber-600 font-medium">cached</span>}
          {error && <span className="text-destructive truncate" title={error}>refresh failed — showing last good</span>}
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div><div className="text-muted-foreground text-[11px]">Regime</div><div className="font-bold">{data.regime || '—'}</div></div>
          <div><div className="text-muted-foreground text-[11px]">Trend</div><div className="font-bold">{data.price_action?.trend || '—'}</div></div>
        </div>

        <div className="space-y-2.5">
          <ScoreMeter label="Bullish" value={data.bullish_score} tone="emerald" />
          <ScoreMeter label="Bearish" value={data.bearish_score} tone="red" />
          <ScoreMeter label="Breakout pressure" value={data.breakout_pressure} tone="sky" />
          <ScoreMeter label="False-breakout risk" value={data.false_breakout_risk} tone="amber" />
        </div>

        <div className="border-t border-border pt-3 space-y-2.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold">10-Minute Setup</span>
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="font-bold text-foreground">{data.short_horizon?.direction || 'NEUTRAL'}</span>
              <SignalStatusBadge status={data.short_horizon?.status} />
            </span>
          </div>
          <div className="text-xs text-muted-foreground tabular-nums">Confidence: {data.short_horizon?.confidence ?? 0}%</div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold">Intraday Continuation</span>
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="font-bold text-foreground">{data.continuation?.direction || 'NEUTRAL'}</span>
              <SignalStatusBadge status={data.continuation?.status} />
            </span>
          </div>
          <div className="text-xs text-muted-foreground tabular-nums">Confidence: {data.continuation?.confidence ?? 0}%</div>
          <div className="text-[11px] text-muted-foreground">
            Max holding: {data.continuation?.max_holding_minutes ? `${data.continuation.max_holding_minutes} min` : (data.max_holding || '< 2 Hours')}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
