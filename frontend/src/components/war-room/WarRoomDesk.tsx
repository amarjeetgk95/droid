'use client';

import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import { useOptionalLiveMarketContext } from '@/context/LiveMarketContext';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import type { HourForecast } from '@/components/research/ForecastCard';
import { VerdictPanel } from './VerdictPanel';
import { SignalFeedPanel } from './SignalFeedPanel';
import { AlgoControlWidget } from './AlgoControlWidget';
import { OptionsChainDrawer } from './OptionsChainDrawer';
import { Layers, RefreshCw } from 'lucide-react';

const INSTRUMENTS = ['NIFTY 50', 'BANKNIFTY', 'SENSEX'] as const;
type Instrument = (typeof INSTRUMENTS)[number];

const TIMEFRAMES = [
  { id: '1m', label: '1M' },
  { id: '5m', label: '5M' },
  { id: '15m', label: '15M' },
  { id: '1h', label: '1H' },
] as const;
type Timeframe = (typeof TIMEFRAMES)[number]['id'];

/**
 * War Room — Mock A (Kite-minimal) live desk.
 * One calm column: header, controls, verdict, signals, levels+algo.
 * No section tabs, no ticker bar — single scroll, generous whitespace.
 */
export function WarRoomDesk() {
  const [instrument, setInstrument] = useState<Instrument>('NIFTY 50');
  const [timeframe, setTimeframe] = useState<Timeframe>('5m');
  const [forecast, setForecast] = useState<HourForecast | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summaryData, setSummaryData] = useState<any>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [optionsDrawerOpen, setOptionsDrawerOpen] = useState(false);

  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 10000);
    return () => clearInterval(id);
  }, []);

  const loadData = useCallback(async (opts?: { initial?: boolean; manual?: boolean }) => {
    const isInitial = opts?.initial ?? false;
    const isManual = opts?.manual ?? false;
    if (typeof document !== 'undefined' && document.hidden && !isManual) return;
    if (isInitial) setInitialLoading(true);
    else if (isManual) setRefreshing(true);
    if (isInitial || isManual) setError(null);

    try {
      const [biasRes, sumRes] = await Promise.allSettled([
        api.getTacticalBias(instrument, timeframe, true),
        api.getDashboardSummary(),
      ]);

      if (biasRes.status === 'fulfilled') {
        setForecast(biasRes.value as HourForecast);
        setLastUpdated(new Date());
      } else {
        const reason = biasRes.reason;
        setError(reason instanceof Error ? reason.message : 'tactical bias unavailable');
      }

      if (sumRes.status === 'fulfilled' && sumRes.value?.data) {
        setSummaryData(sumRes.value.data);
      }
    } catch (err) {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [instrument, timeframe]);

  useEffect(() => {
    const interval = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void loadData();
    }, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

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
      if (optionsDrawerOpen) return;

      if (e.key === '1') setInstrument('NIFTY 50');
      else if (e.key === '2') setInstrument('BANKNIFTY');
      else if (e.key === '3') setInstrument('SENSEX');
      else if (key === 'r') void loadData({ manual: true });
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [loadData, optionsDrawerOpen]);

  const live = useOptionalLiveMarketContext();
  const market = useOptionalMarketDataContext();
  const cards = live?.cards && live.cards.length > 0 ? live.cards : market?.cards ?? [];
  const currentCard = cards.find((c) => {
    const s = (c.symbol ?? '').replace(/^(NSE|BSE):/i, '').trim().toUpperCase();
    if (instrument === 'BANKNIFTY') return s.includes('BANKNIFTY');
    if (instrument === 'SENSEX') return s.includes('SENSEX');
    return (s === 'NIFTY 50' || s === 'NIFTY') && !s.includes('BANKNIFTY');
  });
  const liveSpot = currentCard?.ltp ?? null;

  const fiiDii = summaryData?.fii_dii ?? null;
  const regimeOverview = summaryData?.regime_overview ?? null;
  const optionsAnalytics =
    summaryData?.options_analytics ?? summaryData?.options?.analytics ?? summaryData?.regime?.analytics ?? null;
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

  const classicPivots = regimeOverview?.key_levels?.classic_pivots ?? null;
  const keyLevels =
    classicPivots != null
      ? {
          r2: classicPivots.r2 ?? null,
          r1: classicPivots.r1 ?? null,
          pivot: classicPivots.pivot ?? null,
          s1: classicPivots.s1 ?? null,
          s2: classicPivots.s2 ?? null,
        }
      : null;

  const busy = initialLoading || refreshing;
  const ageSecs = lastUpdated ? Math.max(0, Math.round((nowMs - lastUpdated.getTime()) / 1000)) : null;
  const stale = ageSecs == null || ageSecs > 90;
  const ageLabel = ageSecs == null ? '' : ageSecs < 5 ? 'just now' : `${ageSecs}s ago`;
  const feedText = busy && !lastUpdated ? 'Connecting…' : ageSecs == null ? 'Feed live' : stale ? `Feed stale · ${ageLabel}` : `Feed live · ${ageLabel}`;

  const spot = forecast?.current_price ?? liveSpot ?? null;
  const levelRows: [string, number | null][] = [
    ['R2', keyLevels?.r2 ?? (spot != null ? spot + 160 : null)],
    ['R1', keyLevels?.r1 ?? (spot != null ? spot + 80 : null)],
    ['Spot', spot],
    ['S1', keyLevels?.s1 ?? (spot != null ? spot - 80 : null)],
    ['S2', keyLevels?.s2 ?? (spot != null ? spot - 160 : null)],
  ];

  return (
    <div style={{ background: 'var(--ds-page)', color: 'var(--ds-ink)', minHeight: '100vh' }}>
      <div style={{ maxWidth: 1120, margin: '0 auto', padding: '28px 20px 60px', display: 'flex', flexDirection: 'column', gap: 28 }}>
        <header style={{ display: 'flex', alignItems: 'baseline', gap: 16, flexWrap: 'wrap' }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em' }}>War Room</h1>
          <span style={{ fontSize: 13, color: 'var(--ds-text-secondary)' }}>
            {instrument} · {timeframe} · {feedText}
          </span>
          <span style={{ flex: 1 }} />
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
        </header>

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
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
          <span style={{ flex: 1 }} />
          <span className="faint" style={{ fontSize: 11 }}>1/2/3 instruments · R refresh · O chain</span>
        </div>

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
          keyLevels={keyLevels}
          updatedAt={lastUpdated}
        />

        <SignalFeedPanel instrument={instrument} />

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 20 }}>
          <section className="card" aria-label="Key levels">
            <div className="card-bd" style={{ padding: '16px 20px' }}>
              <h3 style={{ fontSize: 13, fontWeight: 700, margin: '0 0 8px' }}>Key levels</h3>
              {levelRows.map(([l, v]) => (
                <div
                  key={l}
                  style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderBottom: '1px solid var(--ds-border-subtle)', fontSize: 13 }}
                >
                  <span style={{ color: 'var(--ds-text-secondary)' }}>{l}</span>
                  <span className="num" style={{ fontWeight: 600 }}>
                    {v != null ? Math.round(v).toLocaleString('en-IN') : '—'}
                  </span>
                </div>
              ))}
            </div>
          </section>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <AlgoControlWidget />
            <button type="button" className="btn w-full" onClick={() => setOptionsDrawerOpen(true)}>
              Open full option chain
            </button>
          </div>
        </div>
      </div>

      <OptionsChainDrawer
        isOpen={optionsDrawerOpen}
        onClose={() => setOptionsDrawerOpen(false)}
        instrument={instrument}
      />
    </div>
  );
}
