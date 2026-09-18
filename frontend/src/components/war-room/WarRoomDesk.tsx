'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '@/lib/api';
import { useOptionalLiveMarketContext } from '@/context/LiveMarketContext';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import type { HourForecast } from '@/lib/types';
import { VerdictPanel } from './VerdictPanel';
import { AlgoSafetyStrip } from './AlgoSafetyStrip';
import { OptionsChainDrawer } from './OptionsChainDrawer';
import { SignalFeedPanel, shouldRefreshVerdictOnSignalEvent, type WarRoomSignal } from './SignalFeedPanel';
import { SignalDetailDrawer } from '@/components/signals/SignalDetailDrawer';
import { BiasLayersCard } from './BiasLayersCard';
import { LevelsCard } from './LevelsCard';
import { PaperCard } from './PaperCard';
import { SessionStrip } from './SessionStrip';
import { AccountabilityStrip } from './AccountabilityStrip';
import { normalizeDirection } from '@/components/ui/desk';
import { DeskShell, DeskHeader, DeskToolbar, DeskFooter } from '@/components/layout/DeskShell';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import { Layers, RefreshCw, Sparkles, X } from 'lucide-react';
import { fmtNum } from '@/components/ui/desk';

const INSTRUMENTS = ['NIFTY 50', 'BANKNIFTY', 'SENSEX'] as const;
type Instrument = (typeof INSTRUMENTS)[number];

const TIMEFRAMES = [
  { id: '1m', label: '1M' },
  { id: '5m', label: '5M' },
  { id: '15m', label: '15M' },
  { id: '1h', label: '1H' },
] as const;
type Timeframe = (typeof TIMEFRAMES)[number]['id'];

export interface DashboardSummaryData {
  fii_dii?: {
    fii_net_crores?: number;
    dii_net_crores?: number;
    [key: string]: unknown;
  } | null;
  regime_overview?: {
    pcr?: number;
    pcr_oi?: number;
    max_pain?: number;
    max_pain_strike?: number;
    [key: string]: unknown;
  } | null;
  options_analytics?: {
    pcr_oi?: number;
    pcr?: number;
    max_pain_strike?: number;
    maxPain?: number;
    [key: string]: unknown;
  } | null;
  options?: {
    analytics?: {
      pcr_oi?: number;
      pcr?: number;
      max_pain_strike?: number;
      maxPain?: number;
      [key: string]: unknown;
    };
  };
  regime?: {
    analytics?: {
      pcr_oi?: number;
      pcr?: number;
      max_pain_strike?: number;
      maxPain?: number;
      [key: string]: unknown;
    };
  };
  degraded?: boolean;
  errors?: Record<string, string> | null;
  generated_at?: string | null;
  [key: string]: unknown;
}

/**
 * War Room — verdict terminal.
 * One grid: verdict hero (left) + setup rail (right). No duplicate ticker
 * (the global header already shows indices), no signal feed, no algo dock —
 * automation safety survives as a compact strip that appears only while the
 * engine is active. Feed truth renders via FreshnessClock, never bare text.
 */
export function WarRoomDesk() {
  const live = useOptionalLiveMarketContext();
  const market = useOptionalMarketDataContext();

  const [instrument, setInstrument] = useState<Instrument>('NIFTY 50');
  const [timeframe, setTimeframe] = useState<Timeframe>('5m');
  const [forecast, setForecast] = useState<HourForecast | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summaryData, setSummaryData] = useState<DashboardSummaryData | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [optionsDrawerOpen, setOptionsDrawerOpen] = useState(false);
  const [dossierSignal, setDossierSignal] = useState<WarRoomSignal | null>(null);
  const [dossierOpen, setDossierOpen] = useState(false);
  const [fillsNote, setFillsNote] = useState<string | null>(null);

  // On-demand Pre-Market Briefing state
  const [briefingOpen, setBriefingOpen] = useState(false);
  const [briefingLoading, setBriefingLoading] = useState(false);
  const [briefingData, setBriefingData] = useState<any | null>(null);
  const [briefingError, setBriefingError] = useState<string | null>(null);

  const handleOpenBriefing = useCallback(async () => {
    setBriefingOpen(true);
    setBriefingLoading(true);
    setBriefingError(null);
    try {
      const res = await api.getMarketBriefing(instrument);
      setBriefingData(res?.data ?? res);
    } catch (err) {
      setBriefingData(null);
      setBriefingError(err instanceof Error ? err.message : 'market briefing unavailable');
    } finally {
      setBriefingLoading(false);
    }
  }, [instrument]);

  // Summary presence is read via ref: a context summary arriving must not
  // re-identify `loadData` and re-trigger the initial load effect.
  const summaryRef = useRef(market?.summaryData ?? null);
  useEffect(() => {
    summaryRef.current = market?.summaryData ?? null;
  }, [market?.summaryData]);

  // Monotonic sequence: a late response for a previous instrument/timeframe
  // must never overwrite the current one.
  const requestSeqRef = useRef(0);

  const loadData = useCallback(async (opts?: { initial?: boolean; manual?: boolean }) => {
    const isInitial = opts?.initial ?? false;
    const isManual = opts?.manual ?? false;
    if (typeof document !== 'undefined' && document.hidden && !isManual) return;
    const seq = ++requestSeqRef.current;
    if (isInitial) setInitialLoading(true);
    else if (isManual) setRefreshing(true);
    if (isInitial || isManual) setError(null);

    try {
      // Avoid duplicate summary fetch: MarketDataContext already fetches /summary.
      // Only fetch summary explicitly if context has none or user clicked manual refresh.
      const shouldFetchSummary = isManual || !summaryRef.current;
      const promises: [Promise<any>, Promise<any>?] = [
        api.getTacticalBias(instrument, timeframe, true),
      ];
      if (shouldFetchSummary) {
        promises.push(api.getDashboardSummary());
      }

      const results = await Promise.allSettled(promises);
      if (seq !== requestSeqRef.current) return;
      const biasRes = results[0];
      const sumRes = results[1];

      if (biasRes.status === 'fulfilled') {
        setForecast(biasRes.value as HourForecast);
        setLastUpdated(new Date());
        // Every success clears the banner — a transient poll failure must not
        // leave a permanent stale error once data is flowing again.
        setError(null);
      } else {
        const reason = biasRes.reason;
        setError(reason instanceof Error ? reason.message : 'tactical bias unavailable');
      }

      if (sumRes && sumRes.status === 'fulfilled' && sumRes.value?.data) {
        setSummaryData(sumRes.value.data);
      }
    } catch (err) {
      if (seq !== requestSeqRef.current) return;
      setError(err instanceof Error ? err.message : 'Error loading War Room data');
    } finally {
      if (isInitial) setInitialLoading(false);
      else if (isManual) setRefreshing(false);
    }
  }, [instrument, timeframe]);

  useEffect(() => {
    void loadData({ initial: true });
  }, [loadData]);

  useEffect(() => {
    setForecast(null);
    setError(null);
    setLastUpdated(null);
  }, [instrument, timeframe]);

  useEffect(() => {
    const interval = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void loadData();
    }, 15000);
    return () => clearInterval(interval);
  }, [loadData]);

  // SSE verdict nudge (single EventSource lives in SignalFeedPanel): P0 signal
  // lifecycle events refresh the bias immediately instead of waiting for the
  // 30s poll. Throttled to max 1 / 10s — tactical_bias is expensive and
  // record=true persists a prediction per call.
  const loadDataRef = useRef(loadData);
  useEffect(() => {
    loadDataRef.current = loadData;
  }, [loadData]);
  const lastVerdictSseRef = useRef(0);
  const handleSignalStreamEvent = useCallback((evt: string) => {
    if (!shouldRefreshVerdictOnSignalEvent(evt)) return;
    if (typeof document !== 'undefined' && document.hidden) return;
    const nowMs = Date.now();
    if (nowMs - lastVerdictSseRef.current < 10000) return;
    lastVerdictSseRef.current = nowMs;
    void loadDataRef.current();
  }, []);

  // Paper fills audit line (typed client exists; omitted when unreachable, never faked).
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        if (typeof api.getPaperOrders !== 'function') return;
        const res = await api.getPaperOrders();
        if (cancelled) return;
        const fills = (res.data ?? []).filter((o) => o.status === 'FILLED');
        const last = fills[fills.length - 1];
        setFillsNote(
          fills.length === 0
            ? 'no paper fills yet'
            : last
              ? `${fills.length} paper fills · last ${last.symbol} ${last.side} ${last.quantity} @ ${last.fill_price ?? last.price}`
              : `${fills.length} paper fills`,
        );
      } catch {
        if (!cancelled) setFillsNote(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.repeat) return;
      const target = e.target as HTMLElement | null;
      if (target == null) return;
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;
      if (target.isContentEditable) return;

      const key = e.key.toLowerCase();
      if (key === 'o') {
        setOptionsDrawerOpen((prev) => !prev);
        return;
      }
      // A modal drawer owns the keyboard: instrument + refresh hotkeys must not
      // fire while the options chain or the dossier is open.
      if (optionsDrawerOpen || dossierOpen) return;

      if (e.key === '1') setInstrument('NIFTY 50');
      else if (e.key === '2') setInstrument('BANKNIFTY');
      else if (e.key === '3') setInstrument('SENSEX');
      else if (key === 'r') void loadData({ manual: true });
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [loadData, optionsDrawerOpen, dossierOpen]);

  const cards = live?.cards && live.cards.length > 0 ? live.cards : market?.cards ?? [];
  const currentCard = cards.find((c) => {
    const s = (c.symbol ?? '').replace(/^(NSE|BSE):/i, '').trim().toUpperCase();
    if (instrument === 'BANKNIFTY') return s.includes('BANKNIFTY');
    if (instrument === 'SENSEX') return s.includes('SENSEX');
    return (s === 'NIFTY 50' || s === 'NIFTY') && !s.includes('BANKNIFTY');
  });
  const liveSpot = currentCard?.ltp ?? null;

  const marketStatus = market?.marketStatus ?? null;
  const streamState = live?.streamState ?? market?.streamState ?? 'CONNECTING';
  const ticksFresh = live?.ticksFresh ?? market?.ticksFresh ?? false;
  const isMarketClosed = marketStatus?.session === 'CLOSED' || marketStatus?.is_trading_day === false;

  const effectiveSummary = summaryData ?? market?.summaryData ?? null;
  const fiiDii = effectiveSummary?.fii_dii ?? null;
  const regimeOverview = effectiveSummary?.regime_overview ?? null;
  const optionsAnalytics =
    effectiveSummary?.options_analytics ?? effectiveSummary?.options?.analytics ?? effectiveSummary?.regime?.analytics ?? null;
  const pcrRaw =
    regimeOverview?.pcr ??
    regimeOverview?.pcr_oi ??
    optionsAnalytics?.pcr_oi ??
    optionsAnalytics?.pcr ??
    null;
  const pcr: number | null =
    typeof pcrRaw === 'number' && Number.isFinite(pcrRaw) ? pcrRaw : null;
  const maxPainRaw =
    regimeOverview?.max_pain ??
    regimeOverview?.max_pain_strike ??
    optionsAnalytics?.max_pain_strike ??
    optionsAnalytics?.maxPain ??
    null;
  const maxPain: number | null =
    typeof maxPainRaw === 'number' && Number.isFinite(maxPainRaw) ? maxPainRaw : null;

  const busy = initialLoading || refreshing;
  // Live-first entry: executable WS price when available, bias snapshot as fallback.
  // VerdictPanel keeps the stable bias price + a separate drift line so the hero
  // number never flickers at tick cadence.
  const spot = liveSpot ?? forecast?.current_price ?? null;
  const dossierFeedState = isMarketClosed ? 'CLOSED' : ticksFresh ? 'LIVE' : 'SYNCING';

  const sessionLabel = marketStatus?.session
    ? marketStatus.session.replace(/_/g, ' ').toLowerCase()
    : 'session —';

  // Quiet backend-truth note: summary-level degradation, never a bare number.
  const summaryDegraded = effectiveSummary?.degraded === true;
  const summaryErrors = effectiveSummary?.errors && typeof effectiveSummary.errors === 'object'
    ? Object.values(effectiveSummary.errors).filter((m): m is string => typeof m === 'string' && m.length > 0)
    : [];
  const summaryGeneratedAt = typeof effectiveSummary?.generated_at === 'string' && effectiveSummary.generated_at
    ? new Date(effectiveSummary.generated_at)
    : null;
  const summaryGeneratedLabel = summaryGeneratedAt && !Number.isNaN(summaryGeneratedAt.getTime())
    ? summaryGeneratedAt.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : null;

  return (
    <DeskShell>
      <DeskHeader
        title="War Room"
        meta={<span>{instrument} · {timeframe} · {sessionLabel}</span>}
        feed={
          <FreshnessClock
            lastAt={lastUpdated}
            streamState={streamState}
            ticksFresh={ticksFresh}
            fetching={refreshing}
            marketClosed={isMarketClosed}
            dataQuality={forecast?.data_quality ?? null}
          />
        }
        actions={
          <>
            <button
              type="button"
              onClick={handleOpenBriefing}
              className="btn"
              style={{ fontSize: 12 }}
              title="Pre-Market Institutional Briefing"
            >
              <span className="btn-ic">
                <Sparkles className="w-3.5 h-3.5 text-accent-strong" />
                Briefing
              </span>
            </button>
            <button
              type="button"
              onClick={() => setOptionsDrawerOpen(true)}
              className="btn"
              style={{ fontSize: 12 }}
              title="Options chain (O)"
            >
              <span className="btn-ic">
                <Layers className="w-3.5 h-3.5" />
                Option chain
              </span>
            </button>
            <button
              type="button"
              onClick={() => void loadData({ manual: true })}
              disabled={busy}
              title="Refresh all (R)"
              className="btn icon-btn"
              aria-label="Refresh War Room"
            >
              <RefreshCw className={`w-4 h-4 ${busy ? 'animate-spin' : ''}`} />
            </button>
          </>
        }
      />

      {/* Command zone: controls + session context as one bordered unit */}
      <section className="card war-command" aria-label="War Room controls">
        <DeskToolbar
          label="War Room context"
          style={{ border: 0, borderRadius: 0, background: 'transparent' }}
        >
          <div className="seg" role="group" aria-label="Instrument">
            {INSTRUMENTS.map((inst, idx) => (
              <button
                key={inst}
                type="button"
                className="seg-btn"
                data-active={instrument === inst}
                aria-pressed={instrument === inst}
                onClick={() => setInstrument(inst)}
                title={`Switch to ${inst} (${idx + 1})`}
              >
                {inst.replace(' 50', '')}
              </button>
            ))}
          </div>
          <div className="seg" role="group" aria-label="Timeframe">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf.id}
                type="button"
                className="seg-btn"
                data-active={timeframe === tf.id}
                aria-pressed={timeframe === tf.id}
                onClick={() => setTimeframe(tf.id)}
              >
                {tf.label}
              </button>
            ))}
          </div>
        </DeskToolbar>
        <div className="war-command__div" aria-hidden="true" />
        <SessionStrip bare />
      </section>

      <div className="war-grid">
        <div className="war-main">
          {summaryDegraded || summaryErrors.length > 0 ? (
            <div role="note" className="notice notice--warn" style={{ fontSize: 11.5 }}>
              <span>
                Summary snapshot degraded{summaryGeneratedLabel ? ` · generated ${summaryGeneratedLabel}` : ''}
                {summaryErrors.length > 0 ? ` — ${summaryErrors.slice(0, 2).join(' · ')}` : ''}.
                Figures below ride their own freshness state.
              </span>
            </div>
          ) : null}
          <VerdictPanel
            forecast={forecast}
            loading={busy}
            error={error}
            instrument={instrument}
            timeframe={timeframe}
            onRefresh={() => void loadData({ manual: true })}
            fiiDii={fiiDii}
            pcr={pcr}
            maxPain={maxPain}
            liveSpot={liveSpot}
            updatedAt={lastUpdated}
          />
          <BiasLayersCard forecast={forecast} loading={busy} />
          <SignalFeedPanel
            instrument={instrument}
            onSelect={(sig) => {
              setDossierSignal(sig);
              setDossierOpen(true);
            }}
            onSignalEvent={handleSignalStreamEvent}
          />
        </div>
        <div className="war-rail">
          <SetupMathCard forecast={forecast} spot={spot} />
          <LevelsCard
            instrument={instrument}
            spot={spot}
            target={forecast?.target_price ?? null}
            stop={forecast?.invalidation_price ?? null}
            loading={busy}
          />
          <PaperCard />
          <AlgoSafetyStrip />
        </div>
      </div>

      <SignalDetailDrawer
        signal={dossierSignal}
        isOpen={dossierOpen && dossierSignal !== null}
        onClose={() => setDossierOpen(false)}
        feedState={dossierFeedState}
      />

      <OptionsChainDrawer
        isOpen={optionsDrawerOpen}
        onClose={() => setOptionsDrawerOpen(false)}
        instrument={instrument}
        direction={forecast ? normalizeDirection(forecast.direction) : undefined}
      />

      {briefingOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="briefing-title"
          className="fixed inset-0 z-[60] flex items-center justify-center bg-scrim p-4"
          onClick={() => setBriefingOpen(false)}
        >
          <div
            className="card max-w-xl w-full max-h-[85vh] flex flex-col bg-card border border-border shadow-2xl"
            onClick={(e) => e.stopPropagation()}
            style={{ borderRadius: 8, overflow: 'hidden' }}
          >
            <div className="card-hd flex justify-between items-center p-3 border-b border-border bg-surface-subtle" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px' }}>
              <div>
                <h2 id="briefing-title" className="card-title text-sm m-0" style={{ fontSize: 13, margin: 0 }}>
                  Pre-Market Institutional Briefing · {instrument}
                </h2>
                <span className="card-meta text-2xs num text-ink-3" style={{ fontSize: 10.5 }}>
                  {briefingData?.timestamp ? new Date(briefingData.timestamp).toLocaleTimeString('en-IN') : 'on-demand'}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setBriefingOpen(false)}
                className="p-1 rounded text-ink-3 hover:text-foreground cursor-pointer"
                aria-label="Close briefing"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="card-bd p-4 overflow-y-auto space-y-3 font-mono text-xs" style={{ padding: 14, overflowY: 'auto' }}>
              {briefingLoading ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div className="skel" style={{ height: 14, width: '70%' }} />
                  <div className="skel" style={{ height: 40, width: '100%' }} />
                  <div className="skel" style={{ height: 60, width: '100%' }} />
                </div>
              ) : briefingData ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ padding: 10, borderRadius: 6, background: 'var(--ds-surface-subtle)', border: '1px solid var(--ds-border)' }}>
                    <span className="micro-label" style={{ display: 'block', marginBottom: 4 }}>Executive Summary</span>
                    <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5, color: 'var(--ds-ink)' }}>
                      {briefingData.executive_summary}
                    </p>
                  </div>

                  {briefingData.key_levels_to_watch && (
                    <div style={{ padding: 10, borderRadius: 6, background: 'var(--ds-surface-subtle)', border: '1px solid var(--ds-border)' }}>
                      <span className="micro-label" style={{ display: 'block', marginBottom: 6 }}>Key Levels &amp; Pivots</span>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(80px, 1fr))', gap: 6 }}>
                        {Object.entries(briefingData.key_levels_to_watch).map(([k, v]) => (
                          <div key={k} style={{ padding: '4px 6px', borderRadius: 4, background: 'var(--ds-card)', border: '1px solid var(--ds-border)' }}>
                            <span style={{ fontSize: 9.5, color: 'var(--ds-text-secondary)', textTransform: 'uppercase', display: 'block' }}>{k}</span>
                            <span className="num" style={{ fontWeight: 600, fontSize: 11.5 }}>{typeof v === 'number' ? fmtNum(v, 1) : String(v)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {briefingData.options_pin_and_pivots && (
                    <div style={{ padding: 10, borderRadius: 6, background: 'var(--ds-surface-subtle)', border: '1px solid var(--ds-border)' }}>
                      <span className="micro-label" style={{ display: 'block', marginBottom: 4 }}>Options Gravity &amp; Pin</span>
                      <p style={{ margin: 0, fontSize: 12, color: 'var(--ds-text-secondary)' }}>{briefingData.options_pin_and_pivots}</p>
                    </div>
                  )}

                  {briefingData.actionable_playbook && Array.isArray(briefingData.actionable_playbook) && (
                    <div style={{ padding: 10, borderRadius: 6, background: 'var(--ds-surface-subtle)', border: '1px solid var(--ds-border)' }}>
                      <span className="micro-label" style={{ display: 'block', marginBottom: 4 }}>Actionable Playbook</span>
                      <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: 'var(--ds-text-secondary)', display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {briefingData.actionable_playbook.map((step: string, i: number) => (
                          <li key={i}>{step}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <p role="alert" style={{ margin: 0, color: 'var(--ds-bear-strong)' }}>
                  Briefing unavailable{briefingError ? ` — ${briefingError}` : '.'}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      <DeskFooter>
        <AccountabilityStrip />
        {fillsNote ? <span>{fillsNote}</span> : null}
        <span>
          {forecast?.forecast_version ? `Forecast ${forecast.forecast_version}` : 'Forecast —'}
          {forecast?.model_version ? ` · model ${forecast.model_version}` : ''}
          {forecast?.snapshot_id ? ` · snap ${String(forecast.snapshot_id).slice(0, 8)}` : ''}
          {typeof forecast?.latency_ms === 'number' ? ` · ${Math.round(forecast.latency_ms)}ms` : ''}
          {summaryGeneratedLabel ? ` · summary ${summaryGeneratedLabel}` : ''}
        </span>
      </DeskFooter>
    </DeskShell>
  );
}

/** Trade math derived from the verdict's own levels — never invented. */
function SetupMathCard({ forecast, spot }: { forecast: HourForecast | null; spot: number | null }) {
  const target = typeof forecast?.target_price === 'number' && Number.isFinite(forecast.target_price)
    ? forecast.target_price
    : null;
  const stop = typeof forecast?.invalidation_price === 'number' && Number.isFinite(forecast.invalidation_price)
    ? forecast.invalidation_price
    : null;
  const confRaw = typeof forecast?.confidence === 'number' && Number.isFinite(forecast.confidence)
    ? forecast.confidence
    : null;
  const confPct = confRaw === null ? null : Math.round(confRaw > 1 ? confRaw : confRaw * 100);

  const risk = spot !== null && stop !== null ? Math.abs(spot - stop) : null;
  const reward = spot !== null && target !== null ? Math.abs(target - spot) : null;
  const rr = risk !== null && reward !== null && risk > 0 ? reward / risk : null;

  const fmt = (v: number | null, digits = 1) =>
    v === null ? '—' : v.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits });

  const rows: [string, string, string?][] = [
    ['Entry', fmt(spot)],
    ['Target', fmt(target)],
    ['Stop', fmt(stop)],
    ['Risk', risk === null ? '—' : `−${fmt(risk)} pts`],
    ['Reward', reward === null ? '—' : `+${fmt(reward)} pts`],
    ['R:R', rr === null ? '—' : `1 : ${rr.toFixed(1)}`],
    ['Confidence', confPct === null ? '—' : `${confPct}%`],
  ];

  return (
    <section className="card" aria-label="Setup math">
      <div className="card-hd">
        <h2 className="card-title">Setup math</h2>
      </div>
      <div className="card-bd" style={{ padding: '4px 12px 8px' }}>
        {rows.map(([l, v]) => (
          <div key={l} className="sg-kv">
            <span className="l">{l}</span>
            <span className="v num">{v}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
