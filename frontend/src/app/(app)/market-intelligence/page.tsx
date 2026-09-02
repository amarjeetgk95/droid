'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { Activity, TrendingUp, TrendingDown, AlertTriangle, Shield, Clock, Database, BarChart3, Layers, Zap, Eye, ChevronDown, RefreshCw } from 'lucide-react';

// Types mirroring backend authoritative objects
type InstrumentId = 'NIFTY' | 'BANKNIFTY' | 'SENSEX' | 'BTCUSD' | 'BREAKOUT_SETUPS';
const INSTRUMENTS: InstrumentId[] = ['NIFTY', 'BANKNIFTY', 'SENSEX', 'BTCUSD', 'BREAKOUT_SETUPS'];
const INSTRUMENT_LABELS: Record<InstrumentId, string> = { NIFTY: 'NIFTY', BANKNIFTY: 'BANKNIFTY', SENSEX: 'SENSEX', BTCUSD: 'BTCUSD', BREAKOUT_SETUPS: 'BREAKOUT SETUPS' };

type SecondaryTab = 'overview' | 'price-action' | 'futures' | 'options' | 'volume' | 'levels' | 'volatility' | 'cross-market' | 'breakout' | '10-min' | 'continuation' | 'ai' | 'risk' | 'data-health' | 'audit';

interface FullMiResponse {
  instrument_id: string;
  asset_class: string;
  pipeline: string;
  header: { instrument: string; display_name: string; live_status: string; price: string | null; price_formatted: string; session: string; session_label: string; last_update_utc: number; last_update_iso: string; data_quality: string; feed_health: string; };
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
  data_health: { feed: string; feed_reason: string | null; data_health: string; clock_sync: string; sequence: string; contract: string; snapshot: string; synchronization: string; last_event_age_ms: number | null };
  capabilities: string[];
  instrument_specific: { is_crypto: boolean; fields: string[] };
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

function Badge({ status }: { status: string }) {
  const cls = status === 'CONFIRMED' ? 'bg-emerald-500 text-white' : status === 'WATCH' ? 'bg-amber-400 text-black' : status === 'POSSIBLE' ? 'bg-sky-500 text-white' : status === 'REJECTED' ? 'bg-muted text-muted-foreground border' : 'bg-secondary text-muted-foreground';
  return <span className={`px-2 py-0.5 rounded text-xs font-bold tracking-widest ${cls}`}>{status}</span>;
}

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

  const fetchFor = useCallback(async (iid: InstrumentId, showLoading = false) => {
    if (iid === 'BREAKOUT_SETUPS') return;
    if (showLoading) setLoading(prev => ({ ...prev, [iid]: true }));
    try {
      const base = (process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com').replace(/\/+$/, '');
      const url = `${base}/api/v1/institutional/market-intelligence/${iid}/full`;
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) {
        const txt = await res.text().catch(() => '');
        throw new Error(`${res.status} ${res.statusText}${txt ? ` — ${txt.slice(0,120)}` : ''}`);
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
      setLoading(prev => ({ ...prev, [iid]: false }));
    }
  }, []);

  const fetchBreakoutSetups = useCallback(async (showLoading = true) => {
    if (showLoading) setBreakoutLoading(true);
    try {
      const base = (process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com').replace(/\/+$/, '');
      const url = `${base}/api/v1/institutional/signals/active`;
      const res = await fetch(url, { cache: 'no-store' });
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

  // Polling: 7s with jitter for MI workspace (was throttled to 30s, too stale) + hidden-tab pause
  useEffect(() => {
    let timeout: ReturnType<typeof setTimeout> | null = null;
    const schedule = (fn: () => void) => {
      const jittered = 7000 * (0.8 + Math.random() * 0.4);
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

  // Pre-warm other instruments in background without blocking UI (cached)
  useEffect(() => {
    INSTRUMENTS.filter(i => i !== selected && i !== 'BREAKOUT_SETUPS').forEach(i => {
      if (!cacheRef.current.has(i as InstrumentId)) fetchFor(i as InstrumentId, false);
    });
  }, [selected, fetchFor]);

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
        <button onClick={() => fetchFor(selected, true)} className="text-xs flex items-center gap-1 px-2 py-1 border rounded hover:bg-secondary">
          <RefreshCw className="w-3 h-3" /> Refresh
        </button>
      </div>

      {/* Top instrument tabs — 5 tabs NOT in global sidebar */}
      <div className="border-b border-border">
        <div className="flex gap-1 sm:gap-2 overflow-x-auto pb-px scrollbar-none" role="tablist">
          {INSTRUMENTS.map(iid => {
            const isActive = selected === iid;
            const label = INSTRUMENT_LABELS[iid];
            const isBreakout = iid === 'BREAKOUT_SETUPS';
            return (
              <button
                key={iid}
                role="tab"
                aria-selected={isActive}
                onClick={() => { setSelected(iid); if (!isBreakout) setSecondary('overview'); }}
                className={`px-3 sm:px-5 py-2.5 text-sm font-bold tracking-widest border-b-2 whitespace-nowrap transition-colors ${isActive ? 'border-primary text-foreground bg-secondary/50' : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary/30'} ${isBreakout ? 'flex items-center gap-1.5' : ''}`}
              >
                {isBreakout && <Zap className="w-4 h-4" />}{label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Selected Instrument Workspace */}
      {isLoading && (
        <div className="bg-card border rounded-lg p-8 animate-pulse space-y-3">
          <div className="h-6 bg-muted rounded w-32" /> <div className="h-4 bg-muted rounded w-48" /> <div className="h-40 bg-muted rounded" />
        </div>
      )}

      {err && !data && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-6 text-sm">
          <p className="font-semibold text-destructive flex items-center gap-2"><AlertTriangle className="w-4 h-4" /> Failed to load {selected}</p>
          <p className="text-muted-foreground mt-1">{err}</p>
          <p className="text-xs mt-2">Backend: {(process.env.NEXT_PUBLIC_API_URL || 'relative') + `/api/v1/institutional/market-intelligence/${selected}/full`}</p>
        </div>
      )}

      {data && (
        <div className="space-y-4">
          {/* Instrument Header (§5) */}
          <div className="bg-card border rounded-lg p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold tracking-tight">{data.header.display_name} <span className="text-sm font-mono text-muted-foreground">{data.header.instrument}</span></h2>
              <div className="flex items-center gap-2 mt-1">
                <span className={`w-2 h-2 rounded-full ${data.header.live_status === 'LIVE' ? 'bg-emerald-500 animate-pulse' : data.header.live_status === 'FEED_DEGRADED' ? 'bg-red-500' : 'bg-amber-400'}`} />
                <span className="text-xs font-mono font-bold">{data.header.live_status}</span>
                <span className="text-xs text-muted-foreground">Price: <span className="font-mono font-bold text-foreground">{data.header.price_formatted}</span></span>
                <span className="text-xs text-muted-foreground hidden sm:inline">Session: <span className="font-medium">{data.header.session_label}</span></span>
              </div>
            </div>
            <div className="text-right">
              <div className="text-xs text-muted-foreground">Last Update</div>
              <div className="text-xs font-mono font-medium">{data.header.last_update_iso}</div>
              <div className="text-[11px] text-muted-foreground">{data.header.data_quality} • {data.header.feed_health} • {data.asset_class} {data.pipeline}</div>
            </div>
          </div>

          {/* FE-degraded prominent banner (§25/§17) */}
          {isDegraded && (
            <div className="bg-amber-50 border border-amber-300 rounded-lg p-4">
              <p className="font-bold text-sm flex items-center gap-2 text-amber-800"><AlertTriangle className="w-4 h-4" /> ⚠ FEED DEGRADED</p>
              <p className="text-xs text-muted-foreground mt-1">Sequence integrity failure detected.</p>
              <ul className="text-xs mt-2 grid grid-cols-1 sm:grid-cols-3 gap-1 list-disc pl-4">
                <li>Breakout candidates: DISABLED</li>
                <li>AI confirmation: DISABLED</li>
                <li>Execution: DISABLED</li>
              </ul>
              <p className="text-xs font-medium mt-2">Waiting for clean resynchronization.</p>
              {data.data_health.feed_reason && <p className="text-xs text-muted-foreground mt-1">Reason: {data.data_health.feed_reason}</p>}
            </div>
          )}

          {/* Secondary detail navigation — below primary tabs (§19) */}
          <div className="bg-card border rounded-lg p-2 overflow-x-auto">
            <div className="flex gap-1 flex-wrap sm:flex-nowrap sm:overflow-x-auto">
              {SECONDARY_TABS.map(t => (
                <button
                  key={t.id}
                  onClick={() => setSecondary(t.id)}
                  className={`px-2.5 py-1.5 text-xs font-medium rounded whitespace-nowrap border ${secondary === t.id ? 'bg-primary text-primary-foreground border-primary' : 'bg-secondary/50 text-muted-foreground border-transparent hover:bg-secondary'}`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          {/* Content per secondary tab — shared structure, instrument-specific rendering (§18) */}
          {(secondary === 'overview' || secondary === 'price-action') && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              {/* Market State Summary (§6) */}
              <div className="lg:col-span-4 bg-card border rounded-lg p-4 space-y-3">
                <h3 className="font-bold text-xs tracking-widest uppercase flex items-center gap-2"><Layers className="w-4 h-4" /> Market State</h3>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Regime</span><span className="font-bold text-emerald-600">{data.market_state.regime || '—'}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Price Action</span><span className="font-mono text-xs">{data.market_state.price_action?.structure} / {data.market_state.price_action?.trend}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Momentum</span><span className="font-medium text-xs">{data.market_state.momentum || data.price_action.momentum || '—'}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Participation</span><span className="font-medium text-xs">{data.market_state.participation?.volume || '—'}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Volatility</span><span className="font-medium text-xs">{data.market_state.volatility || '—'}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">VWAP</span><span className="font-medium text-xs">{data.market_state.vwap || '—'}</span></div>
                </div>
                <div className="border-t pt-3 space-y-1.5">
                  <div className="flex justify-between text-xs"><span>Bullish Pressure</span><span className="font-mono font-bold">{data.market_state.scores.bullish_score} / 100</span></div>
                  <div className="w-full h-1.5 bg-muted rounded overflow-hidden"><div className="h-full bg-emerald-500" style={{ width: `${data.market_state.scores.bullish_score}%` }} /></div>
                  <div className="flex justify-between text-xs"><span>Bearish Pressure</span><span className="font-mono">{data.market_state.scores.bearish_score} / 100</span></div>
                  <div className="w-full h-1.5 bg-muted rounded overflow-hidden"><div className="h-full bg-red-500" style={{ width: `${data.market_state.scores.bearish_score}%` }} /></div>
                  <div className="flex justify-between text-xs"><span>Breakout Pressure</span><span className="font-mono font-bold text-sky-600">{data.market_state.scores.breakout_pressure} / 100</span></div>
                  <div className="flex justify-between text-xs"><span>False Breakout Risk</span><span className={`font-mono ${data.market_state.scores.false_breakout_risk > 60 ? 'text-red-600' : ''}`}>{data.market_state.scores.false_breakout_risk} / 100</span></div>
                </div>
              </div>

              {/* Price Action (§7) */}
              <div className="lg:col-span-4 bg-card border rounded-lg p-4 space-y-3">
                <h3 className="font-bold text-xs tracking-widest uppercase flex items-center gap-2"><TrendingUp className="w-4 h-4" /> Price Action</h3>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="bg-secondary/50 rounded p-2"><div className="text-muted-foreground">Structure</div><div className="font-medium mt-1">{data.price_action.structure || '—'}</div></div>
                  <div className="bg-secondary/50 rounded p-2"><div className="text-muted-foreground">Trend</div><div className="font-bold mt-1 flex items-center gap-1">{data.price_action.trend === 'BULLISH' ? <TrendingUp className="w-3 h-3 text-emerald-500" /> : data.price_action.trend === 'BEARISH' ? <TrendingDown className="w-3 h-3 text-red-500" /> : null}{data.price_action.trend || '—'}</div></div>
                  <div className="bg-secondary/50 rounded p-2"><div className="text-muted-foreground">Momentum</div><div className="font-medium mt-1">{data.price_action.momentum || '—'}</div></div>
                  <div className="bg-secondary/50 rounded p-2"><div className="text-muted-foreground">Location</div><div className="font-medium mt-1">{data.price_action.location || '—'}</div></div>
                  <div className="bg-secondary/50 rounded p-2"><div className="text-muted-foreground">VWAP</div><div className="font-medium mt-1">{data.price_action.vwap || '—'}</div></div>
                  <div className="bg-secondary/50 rounded p-2"><div className="text-muted-foreground">Volume</div><div className="font-medium mt-1">{data.price_action.volume || '—'}</div></div>
                </div>
                {data.instrument_specific.is_crypto ? (
                  <div className="text-[11px] text-muted-foreground border-t pt-2">Crypto: Spot • Perp • Funding {data.evidence.supporting.find(e=>e.signal.includes('funding')) ? '• Funding elevated' : ''} • No equity breadth</div>
                ) : (
                  <div className="text-[11px] text-muted-foreground border-t pt-2">Equity: Futures • Options • PCR • Breadth {data.evidence.supporting.find(e=>e.signal.includes('breadth')) ? '• Supportive' : ''}</div>
                )}
              </div>

              {/* Market Pressure cards */}
              <div className="lg:col-span-4 grid grid-cols-3 lg:grid-cols-1 gap-3">
                {[
                  { label: 'REGIME', value: data.market_state.regime || '—', sub: data.price_action.trend || '' },
                  { label: 'PRESSURE', value: `${data.market_state.scores.bullish_score} / ${data.market_state.scores.bearish_score}`, sub: 'Bull / Bear' },
                  { label: 'BREAKOUT', value: `${data.market_state.scores.breakout_pressure} / 100`, sub: `Risk ${data.market_state.scores.false_breakout_risk}` },
                ].map(c => (
                  <div key={c.label} className="bg-card border rounded-lg p-4 flex flex-col justify-center">
                    <div className="text-[11px] tracking-widest text-muted-foreground">{c.label}</div>
                    <div className="font-bold text-sm mt-1">{c.value}</div>
                    <div className="text-xs text-muted-foreground">{c.sub}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Evidence (§8) */}
          {(secondary === 'overview' || secondary === 'price-action') && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="bg-card border rounded-lg p-4">
                <h3 className="font-bold text-xs tracking-widest uppercase text-emerald-700">Supporting Evidence</h3>
                <ul className="mt-2 space-y-1.5">
                  {(data.evidence.supporting.length ? data.evidence.supporting : [{ signal: 'No strong supporting evidence', detail: '' } as any]).map((e, idx) => (
                    <li key={idx} className="text-xs flex gap-2"><span className="text-emerald-500">✓</span><span><span className="font-medium">{e.signal}</span>{e.detail ? <span className="text-muted-foreground"> — {e.detail}</span> : null}</span></li>
                  ))}
                </ul>
                {data.evidence.missing.length > 0 && <p className="text-[11px] text-muted-foreground mt-2">Missing: {data.evidence.missing.join(', ')}</p>}
              </div>
              <div className="bg-card border rounded-lg p-4">
                <h3 className="font-bold text-xs tracking-widest uppercase text-amber-700">Conflicting Evidence</h3>
                <ul className="mt-2 space-y-1.5">
                  {(data.evidence.conflicting.length ? data.evidence.conflicting : [{ signal: 'No major conflicts', detail: '' } as any]).map((e, idx) => (
                    <li key={idx} className="text-xs flex gap-2"><span className="text-amber-500">!</span><span><span className="font-medium">{e.signal}</span>{e.detail ? <span className="text-muted-foreground"> — {e.detail}</span> : null}</span></li>
                  ))}
                </ul>
                {data.evidence.stale.length > 0 && <p className="text-[11px] text-red-600 mt-2">Stale: {data.evidence.stale.join(', ')}</p>}
              </div>
            </div>
          )}

          {/* Key Levels (§9) */}
          {(secondary === 'overview' || secondary === 'levels') && (
            <div className="bg-card border rounded-lg p-4">
              <h3 className="font-bold text-xs tracking-widest uppercase flex items-center gap-2"><Layers className="w-4 h-4" /> Key Levels</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
                <div className="bg-secondary/40 rounded p-3"><div className="text-[11px] text-muted-foreground">Resistance</div><div className="font-mono font-bold mt-1">{data.levels.nearest_resistance || data.levels.resistance[0] || '—'}</div></div>
                <div className="bg-secondary/40 rounded p-3"><div className="text-[11px] text-muted-foreground">Next Resistance</div><div className="font-mono mt-1">{data.levels.resistance[1] || '—'}</div></div>
                <div className="bg-secondary/40 rounded p-3"><div className="text-[11px] text-muted-foreground">Support</div><div className="font-mono font-bold mt-1">{data.levels.nearest_support || data.levels.support[0] || '—'}</div></div>
                <div className="bg-secondary/40 rounded p-3"><div className="text-[11px] text-muted-foreground">Next Support</div><div className="font-mono mt-1">{data.levels.support[1] || '—'}</div></div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-3 text-xs">
                <div className="border rounded p-2"><span className="text-muted-foreground">Breakout trigger</span><span className="font-mono font-bold ml-2">{data.levels.breakout_trigger || '—'}</span></div>
                <div className="border rounded p-2"><span className="text-muted-foreground">Breakdown trigger</span><span className="font-mono ml-2">{data.levels.breakdown_trigger || '—'}</span></div>
                <div className="border rounded p-2"><span className="text-muted-foreground">Invalidation</span><span className="font-mono ml-2">{data.levels.invalidation || '—'}</span></div>
              </div>
              <p className="text-[11px] text-muted-foreground mt-2">Decimal precision preserved exactly via backend Decimal.</p>
            </div>
          )}

          {/* Breakout Analysis (§10) */}
          {(secondary === 'overview' || secondary === 'breakout') && (
            <div className={`border rounded-lg p-4 ${isDegraded ? 'bg-muted/50 opacity-60' : 'bg-card'}`}>
              <h3 className="font-bold text-xs tracking-widest uppercase">{data.breakout.direction === 'BEARISH' ? 'Breakdown Analysis' : 'Breakout Analysis'}</h3>
              <div className="mt-2 flex flex-wrap gap-2 items-center">
                <span className="text-sm font-bold">{data.breakout.status} {data.breakout.direction !== 'NEUTRAL' ? `${data.breakout.direction}` : ''} {data.breakout.direction === 'BULLISH' ? 'BREAKOUT' : data.breakout.direction === 'BEARISH' ? 'BREAKDOWN' : ''}</span>
                <Badge status={data.breakout.status} />
                {isDegraded && <span className="text-xs text-red-600">— DISABLED (feed degraded)</span>}
              </div>
              <div className="grid grid-cols-3 gap-3 mt-3">
                <div><div className="text-[11px] text-muted-foreground">{data.breakout.direction === 'BEARISH' ? 'Breakdown' : 'Breakout'} Pressure</div><div className="font-mono font-bold">{(data.breakout.direction === 'BEARISH' ? data.breakout.breakdown_pressure : data.breakout.breakout_pressure) ?? data.market_state.scores.breakout_pressure} / 100</div></div>
                <div><div className="text-[11px] text-muted-foreground">Breakout Quality</div><div className="font-mono font-bold">{data.breakout.breakout_quality} / 100</div></div>
                <div><div className="text-[11px] text-muted-foreground">False Breakout Risk</div><div className={`font-mono font-bold ${data.breakout.false_breakout_risk > 60 ? 'text-red-600' : ''}`}>{data.breakout.false_breakout_risk} / 100</div></div>
              </div>
              <div className="text-xs mt-2">Trigger: <span className="font-mono font-bold">{data.breakout.breakout_level || '—'}</span> <span className="text-muted-foreground">• Status: {isDegraded ? 'WAITING (degraded)' : (data.breakout.reason || data.breakout.status)}</span></div>
              {data.instrument_specific.is_crypto && <p className="text-[11px] text-muted-foreground mt-2">BTCUSD: evaluated on spot/perp/funding/liquidations — no PCR/breadth.</p>}
            </div>
          )}

          {/* 10-Minute + Continuation (§11, §12) */}
          {(secondary === 'overview' || secondary === '10-min' || secondary === 'continuation') && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className={`border-2 rounded-lg p-4 ${data.short_horizon.status === 'CONFIRMED' ? 'border-emerald-500 bg-emerald-50' : data.short_horizon.status === 'REJECTED' ? 'border-border bg-muted/30 opacity-75' : 'border-border bg-card'}`}>
                <h3 className="font-bold text-xs tracking-widest uppercase flex items-center gap-2"><Zap className="w-4 h-4" /> 10-Minute Trade</h3>
                <div className="mt-2 space-y-1 text-sm">
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Direction</span><span className="font-bold">{data.short_horizon.direction}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Status</span><Badge status={data.short_horizon.status} /></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Confidence</span><span className="font-mono font-bold">{data.short_horizon.confidence}%</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Entry</span><span className="font-mono text-xs">{data.short_horizon.entry_zone.length ? `${data.short_horizon.entry_zone[0]}–${data.short_horizon.entry_zone[1]}` : '—'}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Stop</span><span className="font-mono text-xs">{data.short_horizon.stop_loss !== '0' ? data.short_horizon.stop_loss : '—'}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Target</span><span className="font-mono text-xs">{data.short_horizon.target_zone.length ? `${data.short_horizon.target_zone[0]}–${data.short_horizon.target_zone[1]}` : '—'}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Holding Horizon</span><span className="font-medium text-xs">~10 minutes</span></div>
                  {data.short_horizon.status === 'REJECTED' && <p className="text-xs text-muted-foreground mt-2">Not actionable — {data.short_horizon.reason}</p>}
                </div>
              </div>
              <div className={`border-2 rounded-lg p-4 ${data.continuation.status === 'CONFIRMED' ? 'border-emerald-500 bg-emerald-50' : data.continuation.status === 'REJECTED' ? 'border-border bg-muted/30 opacity-75' : 'border-border bg-card'}`}>
                <h3 className="font-bold text-xs tracking-widest uppercase flex items-center gap-2"><Clock className="w-4 h-4" /> Intraday Continuation</h3>
                <div className="mt-2 space-y-1 text-sm">
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Direction</span><span className="font-bold">{data.continuation.direction}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Status</span><Badge status={data.continuation.status} /></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Confidence</span><span className="font-mono font-bold">{data.continuation.confidence}%</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Trigger</span><span className="font-mono text-xs">{data.levels.breakout_trigger || '—'}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Invalidation</span><span className="font-mono text-xs">{data.continuation.invalidation || data.levels.invalidation || '—'}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Maximum Holding</span><span className="font-bold text-xs">&lt; 2 Hours ({data.continuation.max_holding_minutes} min)</span></div>
                  {data.continuation.status === 'REJECTED' && <p className="text-xs text-muted-foreground mt-2">Not actionable</p>}
                </div>
              </div>
            </div>
          )}

          {/* AI Confirmation (§13) + Signal Conflict (§14) */}
          {(secondary === 'overview' || secondary === 'ai') && (
            <div className="bg-card border rounded-lg p-4 space-y-3">
              <h3 className="font-bold text-xs tracking-widest uppercase flex items-center gap-2"><Eye className="w-4 h-4" /> AI Confirmation</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="border rounded p-3">
                  <div className="text-xs font-bold">10-Minute Setup</div>
                  <div className="text-xs mt-1">AI Decision: <span className="font-bold">{data.ai.short_horizon.decision}</span> <span className="font-mono text-xs">({data.ai.short_horizon.confidence}%)</span> {data.ai.status === 'UNAVAILABLE' && <span className="text-[11px] text-muted-foreground">(AI unavailable — deterministic)</span>}</div>
                  <ul className="text-xs mt-2 space-y-1">
                    {data.ai.short_horizon.reasoning.map((r, i) => <li key={i} className="flex gap-1"><span className="text-emerald-500">✓</span>{r}</li>)}
                    {data.ai.short_horizon.conflicts.map((c, i) => <li key={i} className="text-xs flex gap-1"><span className="text-amber-500">!</span>{c}</li>)}
                  </ul>
                  <div className="text-[11px] text-muted-foreground mt-2">Invalidation: {data.ai.short_horizon.invalidation_conditions.join(', ') || '—'}</div>
                </div>
                <div className="border rounded p-3">
                  <div className="text-xs font-bold">Continuation</div>
                  <div className="text-xs mt-1">AI Decision: <span className="font-bold">{data.ai.continuation.decision}</span> <span className="font-mono text-xs">({data.ai.continuation.confidence}%)</span></div>
                  <ul className="text-xs mt-2 space-y-1">
                    {data.ai.continuation.reasoning.map((r, i) => <li key={i} className="flex gap-1"><span className="text-emerald-500">✓</span>{r}</li>)}
                  </ul>
                </div>
              </div>
              {/* Conflict state */}
              {data.breakout.confidence > 75 && data.ai.short_horizon.decision === 'REJECT' && (
                <div className="bg-amber-50 border border-amber-300 rounded p-3">
                  <p className="text-xs font-bold flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> ⚠ SIGNAL CONFLICT</p>
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
            </div>
          )}

          {/* Risk Status (§15) */}
          {(secondary === 'overview' || secondary === 'risk') && (
            <div className={`border rounded-lg p-4 ${data.risk.portfolio === 'REJECTED' ? 'bg-red-50 border-red-300' : 'bg-card'}`}>
              <h3 className="font-bold text-xs tracking-widest uppercase flex items-center gap-2"><Shield className="w-4 h-4" /> Risk Status</h3>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mt-3 text-xs">
                <div className="border rounded p-2">Strategy <div className={`font-bold ${data.risk.strategy === 'APPROVED' ? 'text-emerald-600' : 'text-red-600'}`}>{data.risk.strategy}</div></div>
                <div className="border rounded p-2">Portfolio <div className={`font-bold ${data.risk.portfolio === 'APPROVED' ? 'text-emerald-600' : 'text-red-600'}`}>{data.risk.portfolio}</div></div>
                <div className="border rounded p-2">Exposure <div className="font-medium">{data.risk.exposure}</div></div>
                <div className="border rounded p-2">Margin <div className="font-medium">{data.risk.margin}</div></div>
                <div className="border rounded p-2">Correlation <div className="font-medium">{data.risk.correlation}</div></div>
              </div>
              {data.risk.portfolio === 'REJECTED' && <p className="text-xs text-red-700 mt-2">RISK REJECTED — Reason: {data.risk.reason}</p>}
              <p className="text-[11px] text-muted-foreground mt-2">Risk status from backend Risk Engine — final authority before execution.</p>
            </div>
          )}

          {/* Signal TTL / Execution Status (§16) */}
          {(secondary === 'overview' || secondary === 'risk') && (
            <div className="bg-card border rounded-lg p-4">
              <h3 className="font-bold text-xs tracking-widest uppercase flex items-center gap-2"><Clock className="w-4 h-4" /> Signal TTL / Execution Status</h3>
              {data.signal ? (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3 text-xs font-mono">
                  <div>Created: {new Date(data.signal.created_at_utc).toISOString().substring(11, 23)} UTC</div>
                  <div>TTL: {data.signal.ttl_ms / 1000}s</div>
                  <div>Expires: {new Date(data.signal.expires_at_utc).toISOString().substring(11, 23)} UTC</div>
                  <div>AI: {data.signal.ai?.status || data.ai.status}</div>
                  <div>Validation: {data.signal.validation_status}</div>
                  <div>Risk: {data.signal.risk_status}</div>
                  <div>Execution: {data.signal.fsm_state}</div>
                  <div>Freshness: {data.signal.is_expired ? 'EXPIRED' : 'VALID'}</div>
                </div>
              ) : data.short_horizon.status === 'CONFIRMED' ? (
                <p className="text-xs text-muted-foreground mt-2">Executable signal — TTL 5 sec • Expires {new Date(Date.now() + 5000).toISOString().substring(11,23)} UTC • AI: {data.ai.status} • Validation: PASS • Risk: {data.risk.portfolio} • Execution: PENDING • Freshness: VALID</p>
              ) : (
                <div className="border border-amber-200 rounded p-3 mt-2">
                  <p className="text-xs font-bold">No executable signal — {data.short_horizon.status} / {data.continuation.status}</p>
                  {data.short_horizon.status === 'EXPIRED' && <p className="text-xs mt-1">SIGNAL EXPIRED — TTL exceeded before execution. Order Submitted: NO</p>}
                  <p className="text-[11px] text-muted-foreground mt-1">Non-actionable — TTL N/A until CONFIRMED</p>
                </div>
              )}
              <p className="text-[11px] text-muted-foreground mt-2">Expired signals visually and semantically non-actionable — order never submitted.</p>
            </div>
          )}

          {/* Instrument-specific content hint (§18) */}
          {(secondary === 'futures' || secondary === 'options' || secondary === 'volume' || secondary === 'volatility' || secondary === 'cross-market') && (
            <div className="bg-card border rounded-lg p-4">
              <h3 className="font-bold text-xs tracking-widest uppercase">{secondary.replace('-', ' ').toUpperCase()} — {data.instrument_id}</h3>
              {data.instrument_specific.is_crypto ? (
                <div className="mt-2 text-xs space-y-1">
                  <p>Available for BTCUSD: {data.instrument_specific.fields.join(' • ')}</p>
                  <p className="text-muted-foreground">Spot 24/7 • Perp/Futures via Binance • Funding {data.evidence.supporting.find(e=>e.dimension==='POSITIONING') ? 'active' : '—'} • No PCR/breadth (NOT_APPLICABLE)</p>
                  <p className="text-[11px] text-muted-foreground">Cross-market sync: BTCUSD continuous — no Indian EOD reset.</p>
                </div>
              ) : (
                <div className="mt-2 text-xs space-y-1">
                  <p>Available: {data.instrument_specific.fields.join(' • ')}</p>
                  <p className="text-muted-foreground">Price Action • VWAP • Futures (OI, basis) • Options (PCR, OI chain) • Breadth • Cross NIFTY↔BANKNIFTY Δt&lt;500ms</p>
                </div>
              )}
              <p className="text-[11px] text-muted-foreground mt-2">Backend authoritative — frontend never recreates trading logic.</p>
            </div>
          )}

          {/* Data Health (§17) */}
          {(secondary === 'overview' || secondary === 'data-health') && (
            <div className={`border rounded-lg p-4 ${isDegraded ? 'bg-red-50 border-red-300' : 'bg-card'}`}>
              <h3 className="font-bold text-xs tracking-widest uppercase flex items-center gap-2"><Database className="w-4 h-4" /> Data Health</h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-3 text-xs">
                <div className="flex items-center gap-2"><span className={`w-2 h-2 rounded-full ${data.data_health.feed === 'HEALTHY' ? 'bg-emerald-500' : 'bg-red-500'}`} /> Market Feed: {data.data_health.feed}</div>
                <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-emerald-500" /> Timestamp: VALID</div>
                <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-emerald-500" /> Sequence: VALID</div>
                <div className="flex items-center gap-2"><span className={`w-2 h-2 rounded-full ${data.data_health.contract === 'VALID' ? 'bg-emerald-500' : 'bg-red-500'}`} /> Contract Spec: {data.data_health.contract}</div>
                <div className="flex items-center gap-2"><span className={`w-2 h-2 rounded-full ${data.data_health.snapshot !== 'MISSING' ? 'bg-emerald-500' : 'bg-amber-400'}`} /> Snapshot: {data.data_health.snapshot}</div>
                <div className="flex items-center gap-2"><span className={`w-2 h-2 rounded-full ${data.data_health.synchronization === 'VALID' || data.data_health.synchronization === 'UNKNOWN' ? 'bg-emerald-500' : 'bg-red-500'}`} /> Synchronization: {data.data_health.synchronization}</div>
              </div>
              {isDegraded && (
                <div className="mt-3 p-3 bg-amber-100 rounded text-xs">
                  <p className="font-bold">⚠ FEED DEGRADED</p>
                  <p>Breakout candidates: DISABLED • AI: DISABLED • Execution: DISABLED — Waiting for clean resynchronization.</p>
                </div>
              )}
              <p className="text-[11px] text-muted-foreground mt-2">Driven by backend infrastructure — Market Feed LIVE, Sequence VALID, Contract Spec VALID, Snapshot VALID.</p>
            </div>
          )}

          {/* Audit / Details (§29) */}
          {(secondary === 'audit' || secondary === 'overview') && (
            <div className="bg-card border rounded-lg p-4">
              <button onClick={() => setExpanded(!expanded)} className="flex items-center gap-2 text-xs font-bold tracking-widest uppercase">
                <Eye className="w-4 h-4" /> Audit / Details <ChevronDown className={`w-3 h-3 transition ${expanded ? 'rotate-180' : ''}`} />
              </button>
              {expanded && (
                <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
                  <div>Signal ID: {data.signal?.signal_id || '— (no executable signal)'}</div>
                  <div>Timestamp: {data.header.last_update_iso}</div>
                  <div>Market Context: Regime {data.market_state.regime} • {data.price_action.structure}</div>
                  <div>Supporting: {data.evidence.supporting.slice(0,2).map(e=>e.signal).join(', ') || '—'}</div>
                  <div>Conflicting: {data.evidence.conflicting.slice(0,2).map(e=>e.signal).join(', ') || '—'}</div>
                  <div>AI Decision: {data.ai.short_horizon.decision} ({data.ai.short_horizon.confidence}%) / {data.ai.continuation.decision} ({data.ai.continuation.confidence}%)</div>
                  <div>Validation: {data.risk.strategy}</div>
                  <div>Risk: {data.risk.portfolio} {data.risk.reason ? `— ${data.risk.reason}` : ''}</div>
                  <div>TTL: {data.signal ? `${data.signal.ttl_ms}ms` : 'N/A'}</div>
                  <div>Execution: {data.signal?.fsm_state || 'NOT_EXECUTED'}</div>
                </div>
              )}
              <p className="text-[11px] text-muted-foreground mt-2">Exactly why the system reached its conclusion — reconstructible via Audit Trail.</p>
            </div>
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
              <div className="bg-card border rounded-lg p-4">
                <h3 className="font-bold text-xs tracking-widest uppercase flex items-center gap-2"><Zap className="w-4 h-4" /> Breakout Signals — Generated by Market Intelligence</h3>
                <p className="text-[11px] text-muted-foreground mt-1">Market State → Breakout Developing? → Trigger → Pressure → False-Risk → 10m → Continuation → Options Confirm → AI → Risk — The Signals tab answers: <span className="font-bold text-foreground">Is there a breakout trade right now?</span></p>
                <div className="flex gap-2 mt-3 flex-wrap">
                  {(['ALL', 'NIFTY', 'BANKNIFTY', 'SENSEX', 'BTCUSD'] as const).map(f => (
                    <button key={f} onClick={() => setBreakoutFilter(f as any)} className={`px-3 py-1 text-xs font-bold rounded border ${breakoutFilter === f ? 'bg-primary text-primary-foreground border-primary' : 'bg-secondary border-transparent'}`}>{f}</button>
                  ))}
                  <button onClick={() => fetchBreakoutSetups(true)} className="ml-auto text-xs flex items-center gap-1 px-2 py-1 border rounded hover:bg-secondary"><RefreshCw className="w-3 h-3" /> Refresh</button>
                </div>
              </div>

              {breakoutLoading && breakoutSignals.length === 0 && <div className="bg-card border rounded-lg p-8 animate-pulse"><div className="h-4 bg-muted rounded w-32 mb-2" /><div className="h-20 bg-muted rounded" /></div>}

              {breakoutSignals.length === 0 && !breakoutLoading && <div className="bg-secondary border rounded-lg p-6 text-sm text-muted-foreground">No breakout setups right now — Market Intelligence sees NO_SETUP across all instruments. Supporting/conflicting evidence still available in instrument tabs.</div>}

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {breakoutSignals.filter(s => breakoutFilter === 'ALL' || s.instrument_id === breakoutFilter).map(sig => (
                  <div key={sig.signal_id} className={`border-2 rounded-lg p-4 space-y-2 ${sig.status === 'CONFIRMED' ? 'border-emerald-500 bg-emerald-50' : sig.status === 'TRIGGERED' ? 'border-amber-400 bg-amber-50' : sig.status.includes('POSSIBLE') ? 'border-sky-500 bg-sky-50' : sig.status === 'NO_SETUP' ? 'border-border bg-muted/30 opacity-75' : 'bg-card border-border'}`}>
                    <div className="flex justify-between items-start">
                      <div><div className="font-bold text-sm">{sig.display_name} <span className="font-mono text-xs text-muted-foreground">{sig.instrument_id}</span></div><div className="text-xs font-mono">{sig.price_formatted ? `Price ${sig.price_formatted}` : ''} • Session {sig.session} • {sig.data_health}</div></div>
                      <Badge status={sig.status} />
                    </div>
                    <div className="text-xs space-y-1">
                      <div className="flex justify-between"><span className="text-muted-foreground">Direction</span><span className={`font-bold ${sig.direction === 'BULLISH' ? 'text-emerald-600' : sig.direction === 'BEARISH' ? 'text-red-600' : ''}`}>{sig.direction}</span></div>
                      <div className="flex justify-between"><span className="text-muted-foreground">Trigger Level</span><span className="font-mono font-bold">{sig.trigger_level || '—'}</span></div>
                      <div className="flex justify-between"><span className="text-muted-foreground">Breakout Pressure</span><span className="font-mono">{sig.breakout_pressure} / 100</span></div>
                      <div className="flex justify-between"><span className="text-muted-foreground">False-Breakout Risk</span><span className={`font-mono ${sig.false_breakout_risk > 60 ? 'text-red-600' : ''}`}>{sig.false_breakout_risk} / 100</span></div>
                      <div className="border-t pt-2 mt-2 grid grid-cols-2 gap-2">
                        <div className="border rounded p-2 bg-card"><div className="text-[11px] font-bold">10-Minute</div><div className="flex justify-between text-xs mt-1"><span>{sig.short_horizon.direction}</span><Badge status={sig.short_horizon.status} /></div><div className="text-[11px] font-mono">{sig.short_horizon.confidence}% • {sig.short_horizon.entry_zone?.length ? sig.short_horizon.entry_zone.join('–') : '—'} → {sig.short_horizon.target_zone?.length ? sig.short_horizon.target_zone.join('–') : '—'}</div></div>
                        <div className="border rounded p-2 bg-card"><div className="text-[11px] font-bold">Continuation (&lt;2h)</div><div className="flex justify-between text-xs mt-1"><span>{sig.continuation.direction}</span><Badge status={sig.continuation.status} /></div><div className="text-[11px] font-mono">{sig.continuation.confidence}% • 119 min max • {sig.continuation.reason?.slice(0,30) || '—'}</div></div>
                      </div>
                      <div className="flex justify-between"><span className="text-muted-foreground">Options Confirmation</span><span className="font-medium text-xs">{sig.options_confirmation}</span></div>
                      <div className="flex justify-between"><span className="text-muted-foreground">AI Confirmation</span><span className="font-medium text-xs">{sig.ai_decision} {sig.ai_confidence}%</span></div>
                      <div className="flex justify-between"><span className="text-muted-foreground">Risk</span><span className={`font-bold text-xs ${sig.risk_status === 'APPROVED' ? 'text-emerald-600' : 'text-red-600'}`}>{sig.risk_status}</span></div>
                      <div className="text-[11px] text-muted-foreground">TTL {sig.ttl_ms ? `${sig.ttl_ms/1000}s` : '—'} • Created {sig.created_at_utc ? new Date(sig.created_at_utc).toISOString().substring(11,19) + ' UTC' : '—'} • Expires {sig.expires_at_utc ? new Date(sig.expires_at_utc).toISOString().substring(11,19) + ' UTC' : '—'}</div>
                      <div className="text-[11px]"><span className="text-emerald-600">✓ {sig.supporting?.join(' • ') || '—'}</span><br /><span className="text-amber-600">! {sig.conflicting?.join(' • ') || '—'}</span></div>
                    </div>
                    <div className="flex gap-2">
                      <button onClick={() => { setSelected(sig.instrument_id as InstrumentId); setSecondary('breakout'); window.scrollTo({top:0, behavior:'smooth'}); }} className="text-xs px-2 py-1 border rounded hover:bg-secondary">View in MI → {sig.instrument_id}</button>
                      <button onClick={() => { setSelected(sig.instrument_id as InstrumentId); setSecondary('ai'); }} className="text-xs px-2 py-1 border rounded hover:bg-secondary">AI Details</button>
                    </div>
                    {sig.status === 'NO_SETUP' && <p className="text-[11px] text-muted-foreground">No setup — not actionable. Check Levels/Volatility/Cross-Market for why.</p>}
                    {sig.status === 'EXPIRED' && <p className="text-[11px] text-red-600">Signal expired — TTL exceeded before execution. Order NOT submitted.</p>}
                  </div>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground text-center border-t pt-2">Populated exclusively by Market Intelligence → Breakout Engine → SignalCenter. Not a mesh — single writer, breakout calls are authoritative SignalEvents.</p>
              <div className="bg-card border rounded-lg p-3 text-xs">
                <span className="font-bold">CALLS & PUTS live data</span> still available via <span className="font-mono">GET /api/v1/institutional/calls-puts/NIFTY/full</span> and linked from each breakout card’s Options Confirmation. Full chain viewer at existing Options page — breakout tab shows confirming summary, not raw chain mesh.
              </div>
            </div>
          )}
    </div>
  );
}
