'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { MarketRegimeOverview, MarketBreadthData, FIIDIIOverviewResponse } from '@/lib/types';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import { RegimeBanner } from '@/components/markets/RegimeBanner';
import { KeyLevelsTable } from '@/components/markets/KeyLevelsTable';
import { IndicatorsGrid } from '@/components/markets/IndicatorsGrid';
import { VixRegimeCard } from '@/components/markets/VixRegimeCard';
import { ErrorCard } from '@/components/ui/ErrorCard';
import { Card, EmptyNote, Stat, fmtINR, fmtNum } from '@/components/ui/desk';

const SYMBOLS = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX'];

const FALLBACK_POLL_MS = 15 * 60 * 1000;

/**
 * Compact "Breadth & Flows" strip — stat-grid only.
 * Reuses the SAME data hooks as the dashboard cards (no component imports):
 * - MarketBreadth path: useOptionalMarketDataContext().breadth ?? api.getMarketBreadth()
 * - FIIPositioningCard path: useOptionalMarketDataContext().fiiDii ?? api.getFIIDIIOverview()
 */
function BreadthFlowsStrip() {
  const ctx = useOptionalMarketDataContext();
  const ctxBreadth = ctx?.breadth ?? null;
  const ctxFii = (ctx?.fiiDii as FIIDIIOverviewResponse | null) ?? null;
  const hasCtxBreadth = ctxBreadth ? 'ctx' : 'noctx';
  const hasCtxFii = ctxFii ? 'ctx' : 'noctx';
  const [fbBreadth, setFbBreadth] = useState<MarketBreadthData | null>(null);
  const [fbFii, setFbFii] = useState<FIIDIIOverviewResponse | null>(null);

  const breadth: MarketBreadthData | null = ctxBreadth ?? fbBreadth;
  const fii: FIIDIIOverviewResponse | null = ctxFii ?? fbFii;

  useEffect(() => {
    if (ctxBreadth && ctxFii) return;
    let isMounted = true;
    const load = async () => {
      if (typeof document !== 'undefined' && document.hidden) return;
      try {
        if (!ctxBreadth) {
          const b = await api.getMarketBreadth();
          if (isMounted && b.data) setFbBreadth(b.data);
        }
        if (!ctxFii) {
          const f = await api.getFIIDIIOverview();
          if (isMounted && f.data) setFbFii(f.data);
        }
      } catch {
        // Keep strip silent — shows placeholder text below.
      }
    };
    void load();
    let timeout: ReturnType<typeof setTimeout> | null = null;
    const schedule = () => {
      timeout = setTimeout(() => {
        if (!document.hidden) void load();
        schedule();
      }, FALLBACK_POLL_MS * (0.8 + Math.random() * 0.4));
    };
    schedule();
    const onVis = () => { if (!document.hidden) void load(); };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      isMounted = false;
      if (timeout) clearTimeout(timeout);
      document.removeEventListener('visibilitychange', onVis);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasCtxBreadth, hasCtxFii]);

  if (!breadth && !fii) {
    return (
      <Card title="Breadth & Flows" meta="loading…">
        <EmptyNote>Loading breadth &amp; flows…</EmptyNote>
      </Card>
    );
  }

  const sentiment = breadth?.sentiment ? String(breadth.sentiment).replace(/_/g, ' ') : '—';
  const fiiLS =
    fii && Number.isFinite(Number(fii.fii_long_short_ratio))
      ? `${fmtNum(fii.fii_long_short_ratio, 2)}x`
      : '—';

  return (
    <Card title="Breadth & Flows" meta={sentiment !== '—' ? sentiment : undefined}>
      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))' }}>
        <Stat label="Advances" value={breadth ? fmtNum(breadth.advancing, 0) : '—'} />
        <Stat label="Declines" value={breadth ? fmtNum(breadth.declining, 0) : '—'} />
        <Stat label="A/D ratio" value={breadth ? fmtNum(breadth.advance_decline_ratio, 2) : '—'} />
        <Stat label="Sentiment" value={sentiment} />
        <Stat label="FII long/short" value={fiiLS} />
      </div>
    </Card>
  );
}

export default function MarketsPage() {
  const [selectedSymbol, setSelectedSymbol] = useState<string>('NIFTY');
  const [overview, setOverview] = useState<MarketRegimeOverview | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRegime = async () => {
    if (typeof document !== 'undefined' && document.hidden) return;
    try {
      const res = await api.getRegimeOverview(selectedSymbol);
      setOverview(res.data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch market regime data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let isMounted = true;
    let timeout: ReturnType<typeof setTimeout> | null = null;

    setLoading(true);
    void fetchRegime();

    const schedule = () => {
      const jittered = 30000 * (0.8 + Math.random() * 0.4);
      timeout = setTimeout(async () => {
        if (!isMounted) return;
        await fetchRegime();
        schedule();
      }, jittered);
    };
    schedule();
    const onVis = () => { if (!document.hidden) void fetchRegime(); };
    document.addEventListener('visibilitychange', onVis);

    return () => {
      isMounted = false;
      if (timeout) clearTimeout(timeout);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [selectedSymbol]);

  const spotPrice = overview?.spot_price || 0;
  const regimeLine = overview?.regime_state
    ? overview.regime_state.replace(/_/g, ' ')
    : 'Computing regime';

  return (
    <div className="ds-page">
      {/* header */}
      <header className="page-hero">
        <div className="toolbar">
          <div>
            <div className="flex items-center gap-2.5">
              <h1>Market Context</h1>
              <span className="badge b-info" style={{ fontSize: 11 }}>{selectedSymbol}</span>
            </div>
            <p className="muted num">
              {overview ? `Spot ${fmtINR(spotPrice)} · ${regimeLine}` : loading ? 'Loading regime…' : ''}
            </p>
          </div>
          <span className="spacer" />
          <div className="seg" role="group" aria-label="Symbol">
            {SYMBOLS.map((sym) => (
              <button
                key={sym}
                type="button"
                className="seg-btn"
                data-active={selectedSymbol === sym}
                aria-pressed={selectedSymbol === sym}
                onClick={() => setSelectedSymbol(sym)}
              >
                {sym}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setLoading(true);
              void fetchRegime();
            }}
            disabled={loading}
          >
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      <RegimeBanner
        overview={overview}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={(sym) => setSelectedSymbol(sym)}
      />

      {error ? (
        <ErrorCard
          title="Error loading market regime intelligence"
          message={error}
          mode="full-page"
          onRetry={() => {
            setLoading(true);
            void fetchRegime();
          }}
          isRetrying={loading}
        />
      ) : loading && !overview ? (
        <Card title="Market Context" meta="loading…">
          <div style={{ display: 'grid', gap: 8 }}>
            <div className="skel" style={{ height: 30, width: '40%' }}>.</div>
            <div className="skel" style={{ height: 14, width: '75%' }}>.</div>
            <div className="skel" style={{ height: 14, width: '60%' }}>.</div>
          </div>
        </Card>
      ) : (
        <>
          <section aria-label="Technical indicators">
            <IndicatorsGrid indicators={overview?.indicators || null} spotPrice={spotPrice} />
          </section>
          <section aria-label="Support and resistance">
            <KeyLevelsTable keyLevels={overview?.key_levels || null} spotPrice={spotPrice} />
          </section>
          <section aria-label="Volatility regime">
            <VixRegimeCard vixInfo={overview?.vix_regime || null} />
          </section>
        </>
      )}
      <section aria-label="Breadth and flows">
        <BreadthFlowsStrip />
      </section>
    </div>
  );
}
