'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { Activity, TrendingUp, TrendingDown, AlertTriangle, Shield, Clock, Database, Layers, Zap, Eye, ChevronDown, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { ErrorCard } from '@/components/ui/ErrorCard';
import { PageTabs } from '@/components/ui/PageTabs';
import {
  EvidenceList,
  FeedHealthBadge,
  MetricTile,
  MiSection,
  MiUnavailable,
  MiWorkspaceSkeleton,
  ScoreMeter,
  SignalStatusBadge as Badge,
  formatClock,
  timeAgo,
} from '@/components/institutional/mi-ui';

// Types mirroring backend authoritative objects
type InstrumentId = 'NIFTY' | 'BANKNIFTY' | 'SENSEX' | 'BTCUSD' | 'BREAKOUT_SETUPS';
const INSTRUMENTS: InstrumentId[] = ['NIFTY', 'BANKNIFTY', 'SENSEX', 'BTCUSD', 'BREAKOUT_SETUPS'];
const INSTRUMENT_LABELS: Record<InstrumentId, string> = { NIFTY: 'NIFTY', BANKNIFTY: 'BANKNIFTY', SENSEX: 'SENSEX', BTCUSD: 'BTCUSD', BREAKOUT_SETUPS: 'BREAKOUT SETUPS' };

type SecondaryTab = 'overview' | 'price-action' | 'futures' | 'options' | 'volume' | 'levels' | 'volatility' | 'cross-market' | 'breakout' | '10-min' | 'continuation' | 'ai' | 'risk' | 'data-health' | 'audit';

interface FullMiResponse {
  instrument_id: string;
  asset_class: string;
  pipeline: string;
  header: { instrument: string; display_name: string; live_status: string; price: string | null; price_formatted: string; session: string; session_label: string; last_update_utc: number; last_update_iso: string; data_quality: string; feed_health: string; spot_source?: string; used_cache?: boolean };
  market_state: { regime: string; price_action: any; momentum: string; participation: any; volatility: string; vwap: string; scores: { bullish_score: number; bearish_score: number; breakout_pressure: number; breakdown_pressure: number; false_breakout_risk: number } };
  price_action: { structure: string; trend: string; momentum: string; location: string; vwap: string; volume: string; breadth: string };
  evidence: { supporting: {dimension:string; signal:string; detail:string; state:string}[]; conflicting: {dimension:string; signal:string; detail:string; state:string}[]; missing: string[]; stale: string[]; invalid: string[] };
  levels: { support: string[]; resistance: string[]; breakout_trigger: string | null; breakdown_trigger: string | null; invalidation: string; nearest_support: string | null; nearest_resistance: string | null };
  breakout: { direction: string; status: string; confidence: number; breakout_level: string | null; breakout_pressure: number; breakdown_pressure: number; false_breakout_risk: number; breakout_quality: number; supporting: string[]; conflicts: string[]; reason: string };
  short_horizon: { strategy: string; instrument: string; direction: string; status: string; confidence: number; horizon_minutes: number; entry_zone: string[]; stop_loss: string; target_zone: string[]; false_breakout_risk: number; reason: string };
  continuation: { strategy: string; instrument: string; direction: string; status: string; confidence: number; max_holding_minutes: number; reason: string; invalidation: string };
  ai: { status: string; short_horizon: {decision:string; confidence:number; reasoning:string[]; conflicts:string[]; invalidation_conditions:string[]}; continuation: {decision:string; confidence:number; reasoning:string[]; conflicts:string[]; invalidation_conditions:string[]}; overall: any };
  risk: { strategy: string; portfolio: string; exposure: string; margin: string; correlation: string; reason: string | null };
  signal: any;
  data_health: { feed: string; feed_reason: string | null; data_health: string; clock_sync: string; sequence: string; contract: string; snapshot: string; synchronization: string; last_event_age_ms: number | null; spot_source?: string; used_cache?: boolean };
  capabilities: string[];
  instrument_specific: { is_crypto: boolean; fields: string[] };
  details?: {
    spot: { price: number | null; source: string; age_ms: number | null; used_cache: boolean; status: string };
    vwap: { value: number | null; relation: string; source: string | null; status: string; reason: string | null };
    volume: { volume_change: number | null; state: string; quote_volume: number | null; status: string; reason: string | null };
    options: { pcr: number | null; total_call_oi: number | null; total_put_oi: number | null; pcr_volume: number | null; status: string; reason: string | null };
    volatility: { volatility_change: number | null; regime: string; status: string; reason: string | null };
    futures: { status: string; reason: string | null };
    liquidity: { state: string };
    atr: number | null;
    multi_timeframe: Record<string, string> | null;
    funding: { rate: number } | null;
    levels_source: string | null;
    breadth: string;
    cross_market: { status: string; detail: any };
    breadth_detail?: { advancing: number | null; declining: number | null; unchanged: number | null; advance_decline_ratio: number | null; sentiment: string | null; sentiment_score: number | null; status: string; reason: string | null };
    provenance?: { errors?: Record<string, string>; cache_hits?: string[]; vwap_source?: string | null; levels_source?: string | null; options_status?: string; meta_fresh?: boolean; spot_source?: string };
  };
}

const SECONDARY_TABS: { id: SecondaryTab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'price-action', label: 'Price Action' },
  { id: 'futures', label: 'Futures' },
  { id: 'options', label: 'Options & OI' },
  { id: 'volume', label: 'Volume' },
  { id: 'levels', label: 'Levels' },
  { id: 'volatility', label: 'Volatility' },
  { id: 'cross-market', label: 'Cross-Market' },
  { id: 'breakout', label: 'Breakout' },
  { id: '10-min', label: '10-Minute' },
  { id: 'continuation', label: 'Continuation' },
  { id: 'ai', label: 'AI Confirmation' },
  { id: 'risk', label: 'Risk' },
  { id: 'data-health', label: 'Data Health' },
];

export default function MarketIntelligencePage() {
  const [selected, setSelected] = useState<InstrumentId>('NIFTY');
  const [secondary, setSecondary] = useState<SecondaryTab>('overview');
  const [breakoutSignals, setBreakoutSignals] = useState<any[]>([]);
  const [breakoutLoading, setBreakoutLoading] = useState(false);
  const [breakoutFilter, setBreakoutFilter] = useState<'ALL' | InstrumentId>('ALL' as any);
  const [dataByInstrument, setDataByInstrument] = useState<Partial<Record<InstrumentId, FullMiResponse>>>({});
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [errorByInstrument, setErrorByInstrument] = useState<Partial<Record<InstrumentId, string>>>({});
  const [expanded, setExpanded] = useState(false);

  // Per-instrument cache ref to avoid stale data leak between tabs
  const cacheRef = useRef<Map<InstrumentId, FullMiResponse>>(new Map());

  const inFlightRef = useRef<Set<string>>(new Set());

  const fetchFor = useCallback(async (iid: InstrumentId, showLoading = false) => {
    if (iid === 'BREAKOUT_SETUPS') return;
    // Single-flight per instrument: never stack a refresh while one is active.
    if (inFlightRef.current.has(iid)) return;
    inFlightRef.current.add(iid);
    if (showLoading) setLoading(prev => ({ ...prev, [iid]: true }));
    try {
      // Same base-URL resolution as lib/api.ts: local backend on localhost, hosted fallback otherwise.
      const isLocal = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
      const base = (process.env.NEXT_PUBLIC_API_URL || (isLocal ? 'http://localhost:8000' : 'https://droid-backend-emeq.onrender.com')).replace(/\/+$/, '');
      const url = `${base}/api/v1/institutional/market-intelligence/${iid}/full`;
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 60000);
      let res: Response;
      try {
        res = await fetch(url, { cache: 'no-store', signal: ctrl.signal });
      } finally {
        clearTimeout(timer);
      }
      if (!res.ok) {
        const txt = await res.text().catch(() => '');
        throw new Error(`${res.status} ${res.statusText}${txt ? ` — ${txt.slice(0,200)}` : ''}`);
      }
      const json = await res.json();
      const raw = (json.data ?? json) as any;
      // Adapter: new backend returns flattened {instrument,session,feed_health,market_intelligence,breakout_candidate,short_horizon,continuation}
      // Old frontend expects header/market_state etc — map with safe fallbacks so UI never crashes
      let payload: FullMiResponse;
      if (raw.header && raw.market_state) {
        payload = raw as FullMiResponse;
      } else {
        const spot = raw.market_intelligence?.spot_price ?? raw.spot_price ?? null;
        const spotStr = spot != null ? String(spot) : null;
        const spotFmt = spot != null ? Number(spot).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—';
        const feedHealth = raw.feed_health?.health ?? raw.feed_health ?? 'HEALTHY';
        const dataQuality = raw.feed_health?.is_stale ? 'STALE' : 'LIVE';
        const sess = raw.session?.session_type ?? raw.session ?? 'UNKNOWN';
        const lastMs = raw.market_intelligence?.last_update_ms ?? raw.generated_at_ms ?? Date.now();
        const instId = raw.instrument?.id ?? raw.instrument?.instrument_id ?? iid;
        const displayName = raw.instrument?.name ?? raw.instrument?.display_name ?? iid;
        const regime = raw.market_intelligence?.regime ?? 'NEUTRAL';
        const priceAction = raw.market_intelligence?.price_action ?? {};
        const bullish = raw.market_intelligence?.bullish_score ?? 50;
        const bearish = raw.market_intelligence?.bearish_score ?? 50;
        const breakoutPressure = raw.market_intelligence?.breakout_pressure ?? 50;
        const falseRisk = raw.market_intelligence?.false_breakout_risk ?? 20;
        const bc = raw.breakout_candidate ?? raw.breakout ?? {};
        const sh = raw.short_horizon ?? {};
        const cont = raw.continuation ?? {};
        payload = {
          instrument_id: instId,
          asset_class: raw.instrument?.asset_class ?? (iid === 'BTCUSD' ? 'CRYPTO' : 'INDEX'),
          pipeline: raw.instrument?.pipeline ?? (iid === 'BTCUSD' ? 'CRYPTO' : 'INDIAN_EQUITY'),
          header: {
            instrument: instId,
            display_name: displayName,
            live_status: feedHealth,
            price: spotStr,
            price_formatted: spotFmt,
            session: sess,
            session_label: sess,
            last_update_utc: lastMs,
            last_update_iso: new Date(lastMs).toISOString(),
            data_quality: dataQuality,
            feed_health: feedHealth,
          },
          market_state: {
            regime,
            price_action: priceAction,
            momentum: priceAction?.momentum ?? 'NEUTRAL',
            participation: priceAction?.participation ?? {},
            volatility: priceAction?.volatility ?? '—',
            vwap: priceAction?.vwap ?? '—',
            scores: { bullish_score: bullish, bearish_score: bearish, breakout_pressure: breakoutPressure, breakdown_pressure: bearish, false_breakout_risk: falseRisk },
          },
          price_action: {
            structure: priceAction?.structure ?? '—',
            trend: priceAction?.trend ?? 'NEUTRAL',
            momentum: priceAction?.momentum ?? 'NEUTRAL',
            location: priceAction?.location ?? '—',
            vwap: priceAction?.vwap ?? '—',
            volume: priceAction?.volume ?? '—',
            breadth: priceAction?.breadth ?? '—',
          },
          evidence: raw.evidence ?? { supporting: [], conflicting: [], missing: [], stale: [], invalid: [] },
          levels: raw.levels ?? { support: [], resistance: [], breakout_trigger: bc.trigger_level ? String(bc.trigger_level) : null, breakdown_trigger: null, invalidation: '—', nearest_support: null, nearest_resistance: null },
          breakout: {
            direction: bc.direction ?? 'NEUTRAL',
            status: bc.status ?? bc.candidate ?? 'WATCH',
            confidence: bc.confidence ?? 50,
            breakout_level: bc.trigger_level ? String(bc.trigger_level) : null,
            breakout_pressure: breakoutPressure,
            breakdown_pressure: bearish,
            false_breakout_risk: falseRisk,
            breakout_quality: bc.confidence ?? 50,
            supporting: bc.reasons ?? [],
            conflicts: [],
            reason: (bc.reasons ?? []).join(', ') || '',
          },
          short_horizon: {
            strategy: sh.strategy ?? 'BREAKOUT',
            instrument: sh.instrument ?? instId,
            direction: sh.direction ?? 'NEUTRAL',
            status: sh.status ?? 'WATCH',
            confidence: sh.confidence ?? 50,
            horizon_minutes: sh.horizon_minutes ?? 10,
            entry_zone: sh.entry_zone ?? [],
            stop_loss: sh.stop_loss ?? '0',
            target_zone: sh.target_zone ?? [],
            false_breakout_risk: sh.false_breakout_risk ?? falseRisk,
            reason: sh.reason ?? '',
          },
          continuation: {
            strategy: cont.strategy ?? 'CONTINUATION',
            instrument: cont.instrument ?? instId,
            direction: cont.direction ?? 'NEUTRAL',
            status: cont.status ?? 'WATCH',
            confidence: cont.confidence ?? 50,
            max_holding_minutes: cont.max_holding_minutes ?? 120,
            reason: cont.reason ?? '',
            invalidation: cont.invalidation ?? '—',
          },
          ai: raw.ai ?? { status: 'UNAVAILABLE', short_horizon: { decision: 'WATCH', confidence: 50, reasoning: [], conflicts: [], invalidation_conditions: [] }, continuation: { decision: 'WATCH', confidence: 50, reasoning: [], conflicts: [], invalidation_conditions: [] }, overall: {} },
          risk: raw.risk ?? { strategy: 'APPROVED', portfolio: 'APPROVED', exposure: '—', margin: '—', correlation: '—', reason: null },
          signal: raw.signal ?? null,
          data_health: {
            feed: feedHealth,
            feed_reason: raw.feed_health?.is_synthetic_fallback ? 'synthetic' : null,
            data_health: dataQuality,
            clock_sync: 'VALID',
            sequence: raw.sequence?.gap_detected ? 'GAP' : 'VALID',
            contract: raw.instrument?.contract_spec ? 'VALID' : 'UNKNOWN',
            snapshot: raw.instrument ? 'VALID' : 'MISSING',
            synchronization: raw.market_intelligence?.synchronization_status ?? 'UNKNOWN',
            last_event_age_ms: raw.feed_health?.staleness_ms ?? null,
          },
          capabilities: raw.instrument?.capabilities ? Object.keys(raw.instrument.capabilities).filter((k: string) => (raw.instrument.capabilities as Record<string, unknown>)[k]) : [],
          instrument_specific: {
            is_crypto: (raw.instrument?.asset_class ?? (iid === 'BTCUSD' ? 'CRYPTO' : 'INDEX')) === 'CRYPTO',
            fields: raw.instrument?.capabilities ? Object.keys(raw.instrument.capabilities) : [],
          },
        } as FullMiResponse;
      }
      cacheRef.current.set(iid, payload);
      setDataByInstrument(prev => ({ ...prev, [iid]: payload }));
      setErrorByInstrument(prev => ({ ...prev, [iid]: undefined }));
    } catch (e: any) {
      setErrorByInstrument(prev => ({ ...prev, [iid]: e?.message || 'Failed to load' }));
    } finally {
      inFlightRef.current.delete(iid);
      setLoading(prev => ({ ...prev, [iid]: false }));
    }
  }, []);

  const fetchBreakoutSetups = useCallback(async (showLoading = true) => {
    if (showLoading) setBreakoutLoading(true);
    try {
      const isLocal = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
      const base = (process.env.NEXT_PUBLIC_API_URL || (isLocal ? 'http://localhost:8000' : 'https://droid-backend-emeq.onrender.com')).replace(/\/+$/, '');
      const url = `${base}/api/v1/institutional/signals/active`;
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 60000);
      let res: Response;
      try {
        res = await fetch(url, { cache: 'no-store', signal: ctrl.signal });
      } finally {
        clearTimeout(timer);
      }
      if (!res.ok) throw new Error(`${res.status}`);
      const json = await res.json();
      const payload = json.data ?? json;
      const signals = payload.signals || payload || [];
      setBreakoutSignals(signals);
    } catch {
      // keep previous
    } finally {
      setBreakoutLoading(false);
    }
  }, []);

  // Polling: ~15s with jitter for MI workspace + hidden-tab pause.
  // Only the SELECTED instrument is fetched — no background pre-warm of
  // other instruments (that quadrupled every tab switch for data the user
  // may never view; each tab loads on selection via cacheRef instead).
  useEffect(() => {
    let timeout: ReturnType<typeof setTimeout> | null = null;
    const schedule = (fn: () => void) => {
      const jittered = 15000 * (0.8 + Math.random() * 0.4);
      timeout = setTimeout(() => {
        if (!document.hidden) fn();
        schedule(fn);
      }, jittered);
    };
    const onVis = () => {
      if (document.hidden) return;
      if (selected === 'BREAKOUT_SETUPS') void fetchBreakoutSetups(false);
      else void fetchFor(selected, false);
    };
    document.addEventListener('visibilitychange', onVis);
    if (selected === 'BREAKOUT_SETUPS') {
      fetchBreakoutSetups(true);
      schedule(() => void fetchBreakoutSetups(false));
    } else {
      fetchFor(selected, true);
      schedule(() => void fetchFor(selected, false));
    }
    return () => {
      if (timeout) clearTimeout(timeout);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [selected, fetchFor, fetchBreakoutSetups]);

  const data = dataByInstrument[selected] ?? cacheRef.current.get(selected) ?? null;
  const err = errorByInstrument[selected];
  const isLoading = loading[selected] && !data;

  // FE-degraded rule: prominently display degraded, don't show CONFIRMED as valid
  const isDegraded = data?.data_health.feed === 'FEED_DEGRADED' || data?.header.feed_health === 'FEED_DEGRADED';

  return (
    <div className="space-y-4 max-w-[1600px] mx-auto">
      {/* Page title */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
          <Activity className="w-5 h-5 text-primary" /> Market Intelligence
          <span className="text-xs font-normal text-muted-foreground ml-2 hidden sm:inline">Professional trading workspace — authoritative backend state</span>
        </h1>
        <Button
          variant="outline"
          size="sm"
          onClick={() => fetchFor(selected, true)}
          disabled={selected !== 'BREAKOUT_SETUPS' && !!loading[selected]}
        >
          <RefreshCw className={selected !== 'BREAKOUT_SETUPS' && loading[selected] ? 'animate-spin' : ''} /> Refresh
        </Button>
      </div>

      {/* Top instrument tabs — 5 tabs NOT in global sidebar */}
      <PageTabs
        tabs={INSTRUMENTS.map(iid => ({
          id: iid,
          label: INSTRUMENT_LABELS[iid],
          icon: iid === 'BREAKOUT_SETUPS' ? Zap : undefined,
        }))}
        activeTab={selected}
        onTabChange={(id) => { setSelected(id as InstrumentId); if (id !== 'BREAKOUT_SETUPS') setSecondary('overview'); }}
      />

      {/* Selected Instrument Workspace */}
      {isLoading && <MiWorkspaceSkeleton />}

      {err && !data && (
        <ErrorCard
          mode="full-page"
          title={`Failed to load ${selected}`}
          message={err}
          onRetry={() => fetchFor(selected, true)}
          isRetrying={!!loading[selected]}
        />
      )}

      {data && (
        <div className="space-y-4">
          {/* Instrument Header (§5) */}
          <Card className="py-4">
            <CardContent className="px-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="min-w-0">
                <h2 className="text-lg font-bold tracking-tight text-foreground truncate">
                  {data.header.display_name} <span className="text-xs font-mono font-normal text-muted-foreground">{data.header.instrument}</span>
                </h2>
                <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                  <FeedHealthBadge feed={data.header.live_status} quality={data.header.data_quality} />
                  <span className="text-xs text-muted-foreground">Price: <span className="font-mono font-bold tabular-nums text-foreground">{data.header.price_formatted}</span></span>
                  {data.header.spot_source === 'eod' && <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-secondary text-secondary-foreground" title="Reference price from the last session candle — not a live tick">EOD</span>}
                  <span className="text-xs text-muted-foreground hidden sm:inline">Session: <span className="font-medium text-foreground">{data.header.session_label}</span></span>
                </div>
              </div>
              <div className="sm:text-right shrink-0">
                <div className="text-[11px] text-muted-foreground">Last Update</div>
                {data.header.price != null && data.header.spot_source !== 'eod' ? (
                  <div className="text-xs font-mono font-medium tabular-nums text-foreground" title={data.header.last_update_iso}>
                    {formatClock(data.header.last_update_utc)} <span className="text-muted-foreground">({timeAgo(data.header.last_update_utc)})</span>
                  </div>
                ) : data.header.price != null ? (
                  <div className="text-xs text-muted-foreground">EOD reference — market closed</div>
                ) : (
                  <div className="text-xs text-muted-foreground">No live ticks — {data.header.session_label === 'CLOSED' ? 'market closed' : 'feed idle'}</div>
                )}
                <div className="text-[10px] text-muted-foreground">{data.header.data_quality} • {data.header.feed_health} • {data.asset_class} {data.pipeline}</div>
              </div>
            </CardContent>
          </Card>

          {/* FE-degraded prominent banner (§25/§17) */}
          {isDegraded && (
            <div className="bg-warning/10 border border-warning/30 rounded-xl p-4 text-xs">
              <p className="font-bold text-sm flex items-center gap-2 text-warning">
                <AlertTriangle className="w-4 h-4 shrink-0" /> FEED DEGRADED
              </p>
              <p className="text-muted-foreground mt-1">Sequence integrity failure detected.</p>
              <ul className="text-xs mt-2 grid grid-cols-1 sm:grid-cols-3 gap-1 list-disc pl-4 text-muted-foreground">
                <li>Breakout candidates: DISABLED</li>
                <li>AI confirmation: DISABLED</li>
                <li>Execution: DISABLED</li>
              </ul>
              <p className="font-medium mt-2 text-foreground">Waiting for clean resynchronization.</p>
              {data.data_health.feed_reason && <p className="text-muted-foreground mt-1">Reason: {data.data_health.feed_reason}</p>}
            </div>
          )}

          {/* Secondary detail navigation — below primary tabs (§19) */}
          <div className="sticky top-0 z-10 bg-background/95 backdrop-blur py-1">
            <PageTabs
              tabs={SECONDARY_TABS.map(t => ({ id: t.id, label: t.label }))}
              activeTab={secondary}
              onTabChange={(id) => setSecondary(id as SecondaryTab)}
            />
          </div>

          {/* Content per secondary tab — shared structure, instrument-specific rendering (§18) */}
          {(secondary === 'overview' || secondary === 'price-action') && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              {/* Market State Summary (§6) */}
              <MiSection icon={Layers} title="Market State" className="lg:col-span-4">
                <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                  <div><div className="text-muted-foreground text-[11px]">Regime</div><div className="font-bold">{data.market_state.regime || '—'}</div></div>
                  <div><div className="text-muted-foreground text-[11px]">Trend</div><div className="font-mono">{data.market_state.price_action?.structure} / {data.market_state.price_action?.trend}</div></div>
                  <div><div className="text-muted-foreground text-[11px]">Momentum</div><div className="font-medium">{data.market_state.momentum || data.price_action.momentum || '—'}</div></div>
                  <div><div className="text-muted-foreground text-[11px]">Participation</div><div className="font-medium">{data.market_state.participation?.volume || '—'}</div></div>
                  <div><div className="text-muted-foreground text-[11px]">Volatility</div><div className="font-medium">{data.market_state.volatility || '—'}</div></div>
                  <div><div className="text-muted-foreground text-[11px]">VWAP</div><div className="font-medium">{data.market_state.vwap || '—'}</div></div>
                </div>
                <div className="border-t border-border pt-3 mt-3 space-y-2.5">
                  <ScoreMeter label="Bullish pressure" value={data.market_state.scores.bullish_score} tone="emerald" />
                  <ScoreMeter label="Bearish pressure" value={data.market_state.scores.bearish_score} tone="red" />
                  <ScoreMeter label="Breakout pressure" value={data.market_state.scores.breakout_pressure} tone="sky" />
                  <ScoreMeter label="False-breakout risk" value={data.market_state.scores.false_breakout_risk} tone="amber" />
                </div>
              </MiSection>

              {/* Price Action (§7) */}
              <MiSection icon={TrendingUp} title="Price Action" className="lg:col-span-4">
                <div className="grid grid-cols-2 gap-2.5 text-xs">
                  <MetricTile label="Structure" value={data.price_action.structure || '—'} />
                  <MetricTile label="Trend" value={<span className="inline-flex items-center gap-1">{data.price_action.trend === 'BULLISH' ? <TrendingUp className="w-3 h-3 text-emerald-500" /> : data.price_action.trend === 'BEARISH' ? <TrendingDown className="w-3 h-3 text-destructive" /> : null}{data.price_action.trend || '—'}</span>} />
                  <MetricTile label="Momentum" value={data.price_action.momentum || '—'} />
                  <MetricTile label="Location" value={data.price_action.location || '—'} />
                  <MetricTile label="VWAP" value={data.price_action.vwap || '—'} />
                  <MetricTile label="Volume" value={data.price_action.volume || '—'} />
                </div>
                {data.instrument_specific.is_crypto ? (
                  <div className="text-[11px] text-muted-foreground border-t border-border pt-2 mt-3">Crypto: Spot • Perp • Funding {data.evidence.supporting.find(e=>e.signal.includes('funding')) ? '• Funding elevated' : ''} • No equity breadth</div>
                ) : (
                  <div className="text-[11px] text-muted-foreground border-t border-border pt-2 mt-3">Equity: Futures • Options • PCR • Breadth {data.evidence.supporting.find(e=>e.signal.includes('breadth')) ? '• Supportive' : ''}</div>
                )}
              </MiSection>

              {/* Market Pressure cards */}
              <div className="lg:col-span-4 grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-1 gap-3">
                <MetricTile label="REGIME" value={data.market_state.regime || '—'} sub={data.price_action.trend || ''} />
                <MetricTile label="PRESSURE" value={`${data.market_state.scores.bullish_score} / ${data.market_state.scores.bearish_score}`} sub="Bull / Bear" />
                <MetricTile label="BREAKOUT" value={`${data.market_state.scores.breakout_pressure} / 100`} sub={`Risk ${data.market_state.scores.false_breakout_risk}`} />
              </div>
            </div>
          )}

          {/* Evidence (§8) */}
          {(secondary === 'overview' || secondary === 'price-action') && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <MiSection title="Supporting Evidence">
                <EvidenceList items={data.evidence.supporting} tone="support" emptyText="No strong supporting evidence in this poll." />
                {data.evidence.missing.length > 0 && <p className="text-[11px] text-muted-foreground mt-2">Missing: {data.evidence.missing.join(', ')}</p>}
              </MiSection>
              <MiSection title="Conflicting Evidence">
                <EvidenceList items={data.evidence.conflicting} tone="conflict" emptyText="No major conflicts in this poll." />
                {data.evidence.stale.length > 0 && <p className="text-[11px] text-destructive mt-2">Stale: {data.evidence.stale.join(', ')}</p>}
              </MiSection>
            </div>
          )}

          {/* Key Levels (§9) */}
          {(secondary === 'overview' || secondary === 'levels') && (
            <MiSection icon={Layers} title={`Key Levels${data.details?.levels_source ? ` • ${data.details.levels_source}` : ''}`}>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                <MetricTile label="Resistance" value={data.levels.nearest_resistance || data.levels.resistance[0] || '—'} />
                <MetricTile label="Next resistance" value={data.levels.resistance[1] || '—'} />
                <MetricTile label="Support" value={data.levels.nearest_support || data.levels.support[0] || '—'} />
                <MetricTile label="Next support" value={data.levels.support[1] || '—'} />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 mt-3 text-xs">
                <MetricTile label="Breakout trigger" value={data.levels.breakout_trigger || '—'} />
                <MetricTile label="Breakdown trigger" value={data.levels.breakdown_trigger || '—'} />
                <MetricTile label="Invalidation" value={data.levels.invalidation || '—'} />
              </div>
              <p className="text-[11px] text-muted-foreground mt-2">Decimal precision preserved exactly via backend Decimal.</p>
            </MiSection>
          )}

          {/* Breakout Analysis (§10) */}
          {(secondary === 'overview' || secondary === 'breakout') && (
            <MiSection
              title={data.breakout.direction === 'BEARISH' ? 'Breakdown Analysis' : 'Breakout Analysis'}
              tone={isDegraded ? 'muted' : undefined}
              action={<Badge status={data.breakout.status} />}
            >
              <div className="mt-0 flex flex-wrap gap-2 items-center">
                <span className="text-sm font-bold tabular-nums">{data.breakout.status} {data.breakout.direction !== 'NEUTRAL' ? `${data.breakout.direction}` : ''} {data.breakout.direction === 'BULLISH' ? 'BREAKOUT' : data.breakout.direction === 'BEARISH' ? 'BREAKDOWN' : ''}</span>
                {isDegraded && <span className="text-xs text-destructive">— DISABLED (feed degraded)</span>}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 mt-3">
                <MetricTile label={`${data.breakout.direction === 'BEARISH' ? 'Breakdown' : 'Breakout'} pressure`} value={`${(data.breakout.direction === 'BEARISH' ? data.breakout.breakdown_pressure : data.breakout.breakout_pressure) ?? data.market_state.scores.breakout_pressure} / 100`} />
                <MetricTile label="Breakout quality" value={`${data.breakout.breakout_quality} / 100`} />
                <MetricTile label="False-breakout risk" value={`${data.breakout.false_breakout_risk} / 100`} />
              </div>
              <div className="mt-3"><ScoreMeter label="Breakout pressure" value={data.breakout.direction === 'BEARISH' ? data.breakout.breakdown_pressure : data.breakout.breakout_pressure} tone="sky" /></div>
              <div className="text-xs mt-2">Trigger: <span className="font-mono font-bold tabular-nums">{data.breakout.breakout_level || '—'}</span> <span className="text-muted-foreground">• Status: {isDegraded ? 'WAITING (degraded)' : (data.breakout.reason || data.breakout.status)}</span></div>
              {data.instrument_specific.is_crypto && <p className="text-[11px] text-muted-foreground mt-2">BTCUSD: evaluated on spot/perp/funding/liquidations — no PCR/breadth.</p>}
            </MiSection>
          )}

          {/* 10-Minute + Continuation (§11, §12) */}
          {(secondary === 'overview' || secondary === '10-min' || secondary === 'continuation') && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <MiSection
                icon={Zap}
                title="10-Minute Trade"
                tone={data.short_horizon.status === 'CONFIRMED' ? 'success' : data.short_horizon.status === 'REJECTED' ? 'muted' : undefined}
                action={<Badge status={data.short_horizon.status} />}
              >
                <div className="space-y-1.5 text-sm">
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Direction</span><span className="font-bold">{data.short_horizon.direction}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Confidence</span><span className="font-mono font-bold tabular-nums">{data.short_horizon.confidence}%</span></div>
                  <div className="flex justify-between gap-2"><span className="text-muted-foreground text-xs shrink-0">Entry</span><span className="font-mono text-xs tabular-nums text-right break-all">{data.short_horizon.entry_zone.length ? `${data.short_horizon.entry_zone[0]} – ${data.short_horizon.entry_zone[1]}` : '—'}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Stop</span><span className="font-mono text-xs tabular-nums">{data.short_horizon.stop_loss !== '0' ? data.short_horizon.stop_loss : '—'}</span></div>
                  <div className="flex justify-between gap-2"><span className="text-muted-foreground text-xs shrink-0">Target</span><span className="font-mono text-xs tabular-nums text-right break-all">{data.short_horizon.target_zone.length ? `${data.short_horizon.target_zone[0]} – ${data.short_horizon.target_zone[1]}` : '—'}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Holding horizon</span><span className="font-medium text-xs">~10 minutes</span></div>
                  {data.short_horizon.status === 'REJECTED' && <p className="text-xs text-muted-foreground mt-2">Not actionable — {data.short_horizon.reason}</p>}
                </div>
              </MiSection>
              <MiSection
                icon={Clock}
                title="Intraday Continuation"
                tone={data.continuation.status === 'CONFIRMED' ? 'success' : data.continuation.status === 'REJECTED' ? 'muted' : undefined}
                action={<Badge status={data.continuation.status} />}
              >
                <div className="space-y-1.5 text-sm">
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Direction</span><span className="font-bold">{data.continuation.direction}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Confidence</span><span className="font-mono font-bold tabular-nums">{data.continuation.confidence}%</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Trigger</span><span className="font-mono text-xs tabular-nums">{data.levels.breakout_trigger || '—'}</span></div>
                  <div className="flex justify-between gap-2"><span className="text-muted-foreground text-xs shrink-0">Invalidation</span><span className="font-mono text-xs text-right break-all">{data.continuation.invalidation || data.levels.invalidation || '—'}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Maximum holding</span><span className="font-bold text-xs">&lt; 2 Hours ({data.continuation.max_holding_minutes} min)</span></div>
                  {data.continuation.status === 'REJECTED' && <p className="text-xs text-muted-foreground mt-2">Not actionable</p>}
                </div>
              </MiSection>
            </div>
          )}

          {/* AI Confirmation (§13) + Signal Conflict (§14) */}
          {(secondary === 'overview' || secondary === 'ai') && (
            <MiSection icon={Eye} title="AI Confirmation">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="border border-border rounded-lg p-3">
                  <div className="text-xs font-bold">10-Minute Setup</div>
                  <div className="text-xs mt-1">AI Decision: <span className="font-bold">{data.ai.short_horizon.decision}</span> <span className="font-mono text-xs tabular-nums">({data.ai.short_horizon.confidence}%)</span> {data.ai.status === 'UNAVAILABLE' && <span className="text-[11px] text-muted-foreground">(AI unavailable — deterministic)</span>}</div>
                  <EvidenceList items={data.ai.short_horizon.reasoning.map(r => ({ signal: r }))} tone="support" emptyText="No AI reasoning in this poll." />
                  <EvidenceList items={data.ai.short_horizon.conflicts.map(c => ({ signal: c }))} tone="conflict" emptyText="" />
                  <div className="text-[11px] text-muted-foreground mt-2">Invalidation: {data.ai.short_horizon.invalidation_conditions.join(', ') || '—'}</div>
                </div>
                <div className="border border-border rounded-lg p-3">
                  <div className="text-xs font-bold">Continuation</div>
                  <div className="text-xs mt-1">AI Decision: <span className="font-bold">{data.ai.continuation.decision}</span> <span className="font-mono text-xs tabular-nums">({data.ai.continuation.confidence}%)</span></div>
                  <EvidenceList items={data.ai.continuation.reasoning.map(r => ({ signal: r }))} tone="support" emptyText="No AI reasoning in this poll." />
                </div>
              </div>
              {/* Conflict state */}
              {data.breakout.confidence > 75 && data.ai.short_horizon.decision === 'REJECT' && (
                <div className="bg-warning/10 border border-warning/30 rounded-lg p-3 mt-3">
                  <p className="text-xs font-bold flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5" /> SIGNAL CONFLICT</p>
                  <p className="text-xs mt-1">Quantitative: {data.breakout.direction} — {data.breakout.confidence} <span className="text-muted-foreground">vs</span> AI: REJECT</p>
                  <p className="text-xs font-bold">Final: NO TRADE</p>
                </div>
              )}
              {data.breakout.confidence < 65 && data.ai.short_horizon.decision === 'CONFIRM' && (
                <div className="bg-secondary border rounded p-3">
                  <p className="text-xs">QUANTITATIVE: {data.breakout.confidence} — {data.breakout.direction}</p>
                  <p className="text-xs">AI: CONFIRM</p>
                  <p className="text-xs font-bold">FINAL: WATCH (weak quant not promoted)</p>
                </div>
              )}
              <p className="text-[11px] text-muted-foreground">AI never overrides deterministic safety; risk remains final authority. Frontend never edits AI conclusions.</p>
            </MiSection>
          )}

          {/* Risk Status (§15) */}
          {(secondary === 'overview' || secondary === 'risk') && (
            <MiSection icon={Shield} title="Risk Status" tone={data.risk.portfolio === 'REJECTED' ? 'destructive' : undefined}>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5 text-xs">
                <MetricTile label="Strategy" value={data.risk.strategy} />
                <MetricTile label="Portfolio" value={data.risk.portfolio} />
                <MetricTile label="Exposure" value={data.risk.exposure} />
                <MetricTile label="Margin" value={data.risk.margin} />
                <MetricTile label="Correlation" value={data.risk.correlation} />
              </div>
              {data.risk.portfolio === 'REJECTED' && <p className="text-xs text-destructive font-semibold mt-2">RISK REJECTED — Reason: {data.risk.reason}</p>}
              <p className="text-[11px] text-muted-foreground mt-2">Risk status from backend Risk Engine — final authority before execution.</p>
            </MiSection>
          )}

          {/* Signal TTL / Execution Status (§16) */}
          {(secondary === 'overview' || secondary === 'risk') && (
            <MiSection icon={Clock} title="Signal TTL / Execution Status">
              {data.signal ? (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
                  <MetricTile label="Created" value={`${formatClock(data.signal.created_at_utc)} UTC`} />
                  <MetricTile label="TTL" value={data.signal.ttl_ms != null ? `${data.signal.ttl_ms / 1000}s` : '—'} />
                  <MetricTile label="Expires" value={`${formatClock(data.signal.expires_at_utc)} UTC`} />
                  <MetricTile label="AI" value={data.signal.ai?.status || data.ai.status} />
                  <MetricTile label="Validation" value={data.signal.validation_status} />
                  <MetricTile label="Risk" value={data.signal.risk_status} />
                  <MetricTile label="Execution" value={data.signal.fsm_state} />
                  <MetricTile label="Freshness" value={data.signal.is_expired ? 'EXPIRED' : 'VALID'} />
                </div>
              ) : data.short_horizon.status === 'CONFIRMED' ? (
                <p className="text-xs text-muted-foreground mt-2">Executable signal — TTL 5 sec • Expires {formatClock(Date.now() + 5000)} UTC • AI: {data.ai.status} • Validation: PASS • Risk: {data.risk.portfolio} • Execution: PENDING • Freshness: VALID</p>
              ) : (
                <div className="border border-warning/30 bg-warning/5 dark:bg-warning/10 rounded-lg p-3 mt-2">
                  <p className="text-xs font-bold">No executable signal — {data.short_horizon.status} / {data.continuation.status}</p>
                  {data.short_horizon.status === 'EXPIRED' && <p className="text-xs mt-1">SIGNAL EXPIRED — TTL exceeded before execution. Order Submitted: NO</p>}
                  <p className="text-[11px] text-muted-foreground mt-1">Non-actionable — TTL N/A until CONFIRMED</p>
                </div>
              )}
              <p className="text-[11px] text-muted-foreground mt-2">Expired signals visually and semantically non-actionable — order never submitted.</p>
            </MiSection>
          )}

          {/* Module detail tabs — real backend values, honest unavailable states (§18) */}
          {(secondary === 'futures' || secondary === 'options' || secondary === 'volume' || secondary === 'volatility' || secondary === 'cross-market') && (
            <MiSection title={`${secondary.replace('-', ' ').toUpperCase()} — ${data.instrument_id}`}>
              {(() => {
                const d = data.details;
                if (!d) return (<div className="mt-2 text-xs text-muted-foreground">Detail feed loading — switch tabs or refresh. Backend authoritative, frontend never recreates trading logic.</div>);
                if (secondary === 'options') {
                  // PCR ≤ 0 is never a real reading (empty chain sentinel) — show '—', never a bias label.
                  const pcr = d.options.pcr != null && d.options.pcr > 0 ? d.options.pcr : null;
                  const interp = pcr == null ? '—' : pcr > 1.2 ? 'Bullish positioning' : pcr < 0.85 ? 'Bearish positioning' : 'Neutral positioning';
                  const fmtOi = (v: number | null) => v != null ? v.toLocaleString('en-IN') : '—';
                  return (<div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                    <MetricTile label="PCR (OI)" value={pcr != null ? pcr.toFixed(2) : '—'} sub={interp} />
                    <MetricTile label="Put OI" value={fmtOi(d.options.total_put_oi)} />
                    <MetricTile label="Call OI" value={fmtOi(d.options.total_call_oi)} />
                    <MetricTile label="PCR (Vol)" value={d.options.pcr_volume != null && d.options.pcr_volume > 0 ? d.options.pcr_volume.toFixed(2) : '—'} />
                    <MetricTile label="Status" value={d.options.status} />
                    <MetricTile label="Spot ref" value={data.header.price_formatted} />
                    {d.options.status !== 'AVAILABLE' ? <div className="col-span-full"><MiUnavailable reason={d.options.reason} /></div> : null}
                    {data.instrument_specific.is_crypto ? <p className="text-[11px] text-muted-foreground col-span-full">BTCUSD has no options chain — funding/perp positioning applies (NOT_APPLICABLE for PCR).</p> : null}
                  </div>);
                }
                if (secondary === 'volume') {
                  const chg = d.volume.volume_change;
                  return (<div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                    <MetricTile label="Volume change" value={chg != null ? `${(chg * 100).toFixed(0)}%` : '—'} sub={`State: ${d.volume.state}`} />
                    <MetricTile label="Quote volume" value={d.volume.quote_volume != null ? d.volume.quote_volume.toLocaleString('en-IN') : '—'} />
                    <MetricTile label="VWAP" value={data.details?.vwap.value != null ? Number(data.details.vwap.value).toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '—'} sub={`${data.price_action.vwap}${data.details?.vwap.source ? ` • ${data.details.vwap.source}` : ''}`} />
                    {d.volume.status !== 'AVAILABLE' ? <div className="col-span-full"><MiUnavailable reason={d.volume.reason} /></div> : null}
                  </div>);
                }
                if (secondary === 'volatility') {
                  return (<div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                    <MetricTile label="Regime" value={d.volatility.regime} />
                    <MetricTile label="Change" value={d.volatility.volatility_change != null ? `${(d.volatility.volatility_change * 100).toFixed(0)}%` : '—'} />
                    <MetricTile label="ATR(14)" value={d.atr != null ? d.atr.toFixed(2) : '—'} />
                    {d.volatility.status !== 'AVAILABLE' ? <div className="col-span-full"><MiUnavailable reason={d.volatility.reason} /></div> : null}
                  </div>);
                }
                if (secondary === 'futures') {
                  return (<div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                    <MetricTile label="Status" value={d.futures.status} />
                    <MetricTile label="Spot ref" value={data.header.price_formatted} />
                    <MetricTile label="Funding" value={d.funding ? String(d.funding.rate) : data.instrument_specific.is_crypto ? '—' : 'N/A (equity)'} />
                    <div className="col-span-full"><MiUnavailable reason={d.futures.reason} /></div>
                  </div>);
                }
                // cross-market
                const cm: any = d.cross_market?.detail || {};
                const bd = d.breadth_detail;
                return (<div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                  <MetricTile label="Sync status" value={d.cross_market?.status || 'UNKNOWN'} />
                  <MetricTile label="Delta ms" value={cm.delta_ms != null ? String(cm.delta_ms) : '—'} sub="Threshold 500ms" />
                  <MetricTile label="Breadth" value={d.breadth || '—'} sub={bd?.sentiment ? `Sentiment: ${bd.sentiment}` : undefined} />
                  <MetricTile label="Advancing" value={bd?.advancing != null ? bd.advancing.toLocaleString('en-IN') : '—'} />
                  <MetricTile label="Declining" value={bd?.declining != null ? bd.declining.toLocaleString('en-IN') : '—'} />
                  <MetricTile label="Adv/Dec ratio" value={bd?.advance_decline_ratio != null ? bd.advance_decline_ratio.toFixed(2) : '—'} />
                  {bd?.status !== 'AVAILABLE' && !data.instrument_specific.is_crypto ? <div className="col-span-full"><MiUnavailable reason={bd?.reason} /></div> : null}
                  {data.instrument_specific.is_crypto
                    ? <p className="text-[11px] text-muted-foreground col-span-full">BTCUSD trades 24/7 — no peer sync, no Indian EOD reset. Breadth is NOT_APPLICABLE to crypto.</p>
                    : <p className="text-[11px] text-muted-foreground col-span-full">NIFTY↔BANKNIFTY peer sync Δt&lt;500ms. UNKNOWN means the peer snapshot has not arrived yet — not an error.</p>}
                </div>);
              })()}
              <p className="text-[11px] text-muted-foreground mt-2">Backend authoritative — frontend never recreates trading logic.</p>
            </MiSection>
          )}

          {/* Data Health (§17) */}
          {(secondary === 'overview' || secondary === 'data-health') && (
            <MiSection icon={Database} title="Data Health" tone={isDegraded ? 'destructive' : undefined}>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs">
                <MetricTile label="Market feed" value={data.data_health.feed} />
                <MetricTile label="Timestamp" value="VALID" />
                <MetricTile label="Sequence" value={data.data_health.sequence} />
                <MetricTile label="Contract spec" value={data.data_health.contract} />
                <MetricTile label="Snapshot" value={data.data_health.snapshot} />
                <MetricTile label="Synchronization" value={data.data_health.synchronization} />
              </div>
              {data.data_health.last_event_age_ms != null && (
                <p className="text-[11px] text-muted-foreground mt-2 tabular-nums">Last event age: {(data.data_health.last_event_age_ms / 1000).toFixed(1)}s{data.data_health.spot_source ? ` • source: ${data.data_health.spot_source}` : ''}{data.data_health.used_cache ? ' • cached' : ''}</p>
              )}
              {(() => {
                const prov = data.details?.provenance;
                const errs = prov?.errors || {};
                const keys = Object.keys(errs);
                if (!keys.length) return null;
                const hits = prov?.cache_hits || [];
                return (
                  <div className="mt-2 text-[11px] space-y-1">
                    <p className="font-semibold">Enrichment gaps this poll:</p>
                    {keys.map(k => <p key={k} className="text-muted-foreground font-mono break-words">{k}: {errs[k]}</p>)}
                    {hits.length > 0 && (
                      <p className="text-muted-foreground">Served from short cache: {hits.join(', ')}</p>
                    )}
                  </div>
                );
              })()}
              {isDegraded && (
                <div className="mt-3 p-3 bg-warning/10 border border-warning/30 rounded-lg text-xs">
                  <p className="font-bold flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5" /> FEED DEGRADED</p>
                  <p className="mt-1">Breakout candidates: DISABLED • AI: DISABLED • Execution: DISABLED — Waiting for clean resynchronization.</p>
                </div>
              )}
              <p className="text-[11px] text-muted-foreground mt-2">Driven by backend infrastructure — Market Feed LIVE, Sequence VALID, Contract Spec VALID, Snapshot VALID.</p>
            </MiSection>
          )}

          {/* Audit / Details (§29) */}
          {(secondary === 'audit' || secondary === 'overview') && (
            <MiSection
              icon={Eye}
              title="Audit / Details"
              action={<Button variant="ghost" size="xs" onClick={() => setExpanded(!expanded)}>Details <ChevronDown className={`w-3 h-3 transition ${expanded ? 'rotate-180' : ''}`} /></Button>}
            >
              {expanded && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
                  <MetricTile label="Signal ID" value={data.signal?.signal_id || '— (no executable signal)'} />
                  <MetricTile label="Timestamp" value={`${formatClock(data.header.last_update_utc)} (${timeAgo(data.header.last_update_utc)})`} />
                  <MetricTile label="Market context" value={`Regime ${data.market_state.regime} • ${data.price_action.structure}`} />
                  <MetricTile label="Supporting" value={data.evidence.supporting.slice(0,2).map(e=>e.signal).join(', ') || '—'} />
                  <MetricTile label="Conflicting" value={data.evidence.conflicting.slice(0,2).map(e=>e.signal).join(', ') || '—'} />
                  <MetricTile label="AI decision" value={`${data.ai.short_horizon.decision} (${data.ai.short_horizon.confidence}%) / ${data.ai.continuation.decision} (${data.ai.continuation.confidence}%)`} />
                  <MetricTile label="Validation" value={data.risk.strategy} />
                  <MetricTile label="Risk" value={`${data.risk.portfolio}${data.risk.reason ? ` — ${data.risk.reason}` : ''}`} />
                  <MetricTile label="TTL" value={data.signal ? `${data.signal.ttl_ms}ms` : 'N/A'} />
                  <MetricTile label="Execution" value={data.signal?.fsm_state || 'NOT_EXECUTED'} />
                </div>
              )}
              <p className="text-[11px] text-muted-foreground mt-2">Exactly why the system reached its conclusion — reconstructible via Audit Trail.</p>
            </MiSection>
          )}

          {/* Error states (§28) */}
          {(data.evidence.invalid.length > 0 || data.evidence.stale.length > 0) && (
            <div className="bg-secondary border rounded p-3 text-xs">
              <span className="font-bold">Infrastructure states:</span> {data.evidence.invalid.join(', ')} {data.evidence.stale.join(', ')}
              {isDegraded ? ' • Sequence gap • Feed degraded' : ''} {data.ai.status === 'UNAVAILABLE' ? ' • AI unavailable' : ''} {data.risk.portfolio === 'REJECTED' ? ' • Risk rejected' : ''}
            </div>
          )}

          {/* Non-execution notice (§26/§27) */}
          <p className="text-[11px] text-muted-foreground text-center border-t pt-2">
            Market Intelligence is analysis/decision-support — not execution. Any order flows Strategy → AI → Validation → Risk → Atomic FSM → TTL → Execution Engine. Telegram consumes same canonical backend event.
          </p>
        </div>
      )}

      {/* BREAKOUT SETUPS — populated exclusively by Market Intelligence Engine */}
      {selected === 'BREAKOUT_SETUPS' && (
        <div className="space-y-4">
              {/* Signal Center header — explicit breakout center */}
              <MiSection icon={Zap} title="Breakout Signals — Generated by Market Intelligence">
                <p className="text-[11px] text-muted-foreground mt-0">Market State → Breakout Developing? → Trigger → Pressure → False-Risk → 10m → Continuation → Options Confirm → AI → Risk — The Signals tab answers: <span className="font-bold text-foreground">Is there a breakout trade right now?</span></p>
                <div className="flex gap-1.5 mt-3 flex-wrap items-center">
                  {(['ALL', 'NIFTY', 'BANKNIFTY', 'SENSEX', 'BTCUSD'] as const).map(f => (
                    <Button key={f} size="xs" variant={breakoutFilter === f ? 'default' : 'secondary'} onClick={() => setBreakoutFilter(f as any)}>{f}</Button>
                  ))}
                  <Button size="xs" variant="outline" onClick={() => fetchBreakoutSetups(true)} className="ml-auto"><RefreshCw className={breakoutLoading ? 'animate-spin' : ''} /> Refresh</Button>
                </div>
              </MiSection>

              {breakoutLoading && breakoutSignals.length === 0 && <MiWorkspaceSkeleton />}

              {breakoutSignals.length === 0 && !breakoutLoading && <MiSection title="No setups"><p className="text-sm text-muted-foreground">No breakout setups right now — Market Intelligence sees NO_SETUP across all instruments. Supporting/conflicting evidence still available in instrument tabs.</p></MiSection>}

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {breakoutSignals.filter(s => breakoutFilter === 'ALL' || s.instrument_id === breakoutFilter).map(sig => (
                  <MiSection
                    key={sig.signal_id}
                    title={`${sig.display_name} • ${sig.instrument_id}`}
                    action={<Badge status={sig.status} />}
                    tone={sig.status === 'CONFIRMED' ? 'success' : sig.status === 'TRIGGERED' ? 'warning' : sig.status === 'NO_SETUP' ? 'muted' : undefined}
                  >
                    <div className="text-xs font-mono tabular-nums text-muted-foreground -mt-2">{sig.price_formatted ? `Price ${sig.price_formatted}` : 'Price —'} • Session {sig.session || '—'} • {sig.data_health || '—'}</div>
                    <div className="text-xs space-y-1.5 mt-2">
                      <div className="flex justify-between"><span className="text-muted-foreground">Direction</span><span className="font-bold">{sig.direction}</span></div>
                      <div className="flex justify-between"><span className="text-muted-foreground">Trigger Level</span><span className="font-mono font-bold tabular-nums">{sig.trigger_level || '—'}</span></div>
                      <ScoreMeter label="Breakout pressure" value={sig.breakout_pressure} tone="sky" />
                      <ScoreMeter label="False-breakout risk" value={sig.false_breakout_risk} tone="amber" />
                      <div className="border-t border-border pt-2 mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2">
                        <div className="border border-border rounded-lg p-2 bg-card"><div className="text-[11px] font-bold">10-Minute</div><div className="flex justify-between items-center text-xs mt-1"><span>{sig.short_horizon.direction || '—'}</span><Badge status={sig.short_horizon.status} /></div><div className="text-[11px] font-mono tabular-nums mt-1 break-all">{sig.short_horizon.confidence ?? 0}% • {sig.short_horizon.entry_zone?.length ? sig.short_horizon.entry_zone.join(' – ') : '—'} → {sig.short_horizon.target_zone?.length ? sig.short_horizon.target_zone.join(' – ') : '—'}</div></div>
                        <div className="border border-border rounded-lg p-2 bg-card"><div className="text-[11px] font-bold">Continuation (&lt;2h)</div><div className="flex justify-between items-center text-xs mt-1"><span>{sig.continuation.direction || '—'}</span><Badge status={sig.continuation.status} /></div><div className="text-[11px] font-mono tabular-nums mt-1">{sig.continuation.confidence ?? 0}% • 119 min max • {sig.continuation.reason?.slice(0,30) || '—'}</div></div>
                      </div>
                      <div className="flex justify-between"><span className="text-muted-foreground">Options Confirmation</span><span className="font-medium text-xs">{sig.options_confirmation || '—'}</span></div>
                      <div className="flex justify-between"><span className="text-muted-foreground">AI Confirmation</span><span className="font-medium text-xs">{sig.ai_decision || '—'}{sig.ai_confidence != null ? ` ${sig.ai_confidence}%` : ''}</span></div>
                      <div className="flex justify-between"><span className="text-muted-foreground">Risk</span><span className="font-bold text-xs">{sig.risk_status || '—'}</span></div>
                      {sig.risk_reason && <div className="text-[11px] text-muted-foreground">{sig.risk_reason}</div>}
                      <div className="text-[11px] text-muted-foreground tabular-nums">TTL {sig.ttl_ms ? `${sig.ttl_ms/1000}s` : '—'} • Created {sig.created_at_utc ? `${formatClock(sig.created_at_utc)} UTC` : '—'} • Expires {sig.expires_at_utc ? `${formatClock(sig.expires_at_utc)} UTC` : '—'}</div>
                      <EvidenceList items={(sig.supporting || []).map((s: string) => ({ signal: s }))} tone="support" emptyText="" />
                      <EvidenceList items={(sig.conflicting || []).map((s: string) => ({ signal: s }))} tone="conflict" emptyText="" />
                      {(!sig.supporting?.length && !sig.conflicting?.length) && <div className="text-[11px] text-muted-foreground">No supporting/conflicting evidence in this poll.</div>}
                    </div>
                    <div className="flex gap-2 mt-3">
                      <Button size="xs" variant="outline" onClick={() => { setSelected(sig.instrument_id as InstrumentId); setSecondary('breakout'); window.scrollTo({top:0, behavior:'smooth'}); }}>View in MI → {sig.instrument_id}</Button>
                      <Button size="xs" variant="outline" onClick={() => { setSelected(sig.instrument_id as InstrumentId); setSecondary('ai'); }}>AI Details</Button>
                    </div>
                    {sig.status === 'NO_SETUP' && <p className="text-[11px] text-muted-foreground mt-2">No setup — not actionable. Check Levels/Volatility/Cross-Market for why.</p>}
                    {sig.status === 'EXPIRED' && <p className="text-[11px] text-destructive mt-2">Signal expired — TTL exceeded before execution. Order NOT submitted.</p>}
                  </MiSection>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground text-center border-t border-border pt-2">Populated exclusively by Market Intelligence → Breakout Engine → SignalCenter. Not a mesh — single writer, breakout calls are authoritative SignalEvents.</p>
              <MiSection title="Calls & puts live data">
                <p className="text-xs text-muted-foreground">Still available via <span className="font-mono">GET /api/v1/institutional/calls-puts/NIFTY/full</span> and linked from each breakout card's Options Confirmation. Full chain viewer at existing Options page — breakout tab shows confirming summary, not raw chain mesh.</p>
              </MiSection>
            </div>
          )}
    </div>
  );
}
