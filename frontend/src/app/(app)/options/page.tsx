'use client';

import { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { api } from '@/lib/api';
import { OptionChainResponse, MaxPainResult } from '@/lib/types';
import { Card, Stat, fmtINR, fmtNum } from '@/components/ui/desk';
import { OptionsHeader } from '@/components/options/OptionsHeader';
import { OptionChainTable } from '@/components/options/OptionChainTable';
import { PayoffChart } from '@/components/options/PayoffChart';
import { IVSmileChart } from '@/components/options/IVSmileChart';
import { ExpectedMoveCard, ExpectedMoveData } from '@/components/options/ExpectedMoveCard';
import { GreeksSummaryCard, GreeksSummaryData } from '@/components/options/GreeksSummaryCard';
import { ErrorCard } from '@/components/ui/ErrorCard';
import { AIAnalysisCard, AIStrategyPanel, AITradeValidator } from '@/components/ai';
import { deskCache } from '@/lib/useDeskCache';
import { OptionChainSkeleton } from '@/components/options/OptionChainSkeleton';

// Flow ladder loads lazily; it owns its own polling hook.
const InstitutionalFlowTracker = dynamic(
  () => import('@/components/options/InstitutionalFlowTracker').then((m) => m.InstitutionalFlowTracker),
  {
    ssr: false,
    loading: () => (
      <div className="card card-pad">
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>Loading institutional flow…</p>
      </div>
    ),
  },
);

/** Slim AI-research verdict: 3 plain lines folded from the old AiResearchTab. */
interface ResearchVerdict {
  research_assessment?: string;
  uncertainty_level?: string;
  bull_case_summary?: string;
  bear_case_summary?: string;
  ai_impact?: string;
  impact_rationale?: string[];
  contradiction_analysis?: {
    strongest_counter_argument?: string;
    counter_weight_score?: number;
    invalidation_conditions?: string[];
  };
}

/** Intelligence endpoints return models directly; options endpoints wrap in {data,meta}. */
function unwrapModel<T>(raw: unknown): T {
  if (raw && typeof raw === 'object' && 'data' in raw && 'meta' in raw) {
    return (raw as { data: T }).data;
  }
  return raw as T;
}

export default function OptionsPage() {
  // Single shared symbol/expiry state for every section below — no forks.
  const [selectedSymbol, setSelectedSymbol] = useState<string>('NIFTY');
  const [selectedExpiry, setSelectedExpiry] = useState<string>('');
  const [viewMode, setViewMode] = useState<'standard' | 'greeks'>('standard');
  const [forecastDirection, setForecastDirection] = useState<'BULLISH' | 'BEARISH'>('BULLISH');

  const [chainData, setChainData] = useState<OptionChainResponse | null>(null);
  const [maxPainData, setMaxPainData] = useState<MaxPainResult | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState<number>(0);

  // 1h (INTRADAY) forecast state, derived from the same symbol + chain spot.
  const [expectedMove, setExpectedMove] = useState<ExpectedMoveData | null>(null);
  const [greeks, setGreeks] = useState<GreeksSummaryData | null>(null);
  const [research, setResearch] = useState<ResearchVerdict | null>(null);
  const [forecastLoading, setForecastLoading] = useState<boolean>(false);
  const [forecastError, setForecastError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const cacheKey = `options:${selectedSymbol}:${selectedExpiry || 'default'}`;
    const cached = deskCache.get<{ chainData: unknown; maxPainData: unknown }>(cacheKey);

    if (cached) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setChainData(cached.data.chainData as OptionChainResponse);
      setMaxPainData(cached.data.maxPainData as MaxPainResult);
      setLoading(false);
      if (!cached.isStale) return;
    } else {
      setLoading(true);
    }

    const run = async () => {
      try {
        if (!selectedExpiry) {
          const [chainRes, mpRes] = await Promise.all([
            api.getOptionChain(selectedSymbol, undefined),
            api.getMaxPain(selectedSymbol, undefined),
          ]);
          if (!isMounted) return;
          setChainData(chainRes.data);
          setMaxPainData(mpRes.data);

          if (chainRes.data.expiry) {
            setSelectedExpiry(chainRes.data.expiry);
          }

          deskCache.set(cacheKey, { chainData: chainRes.data, maxPainData: mpRes.data });
          setError(null);
          return;
        }

        const [chainRes, mpRes] = await Promise.all([
          api.getOptionChain(selectedSymbol, selectedExpiry),
          api.getMaxPain(selectedSymbol, selectedExpiry),
        ]);
        if (!isMounted) return;
        setChainData(chainRes.data);
        setMaxPainData(mpRes.data);
        deskCache.set(cacheKey, { chainData: chainRes.data, maxPainData: mpRes.data });
        setError(null);
      } catch (err) {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : 'Failed to fetch options data');
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    void run();

    return () => {
      isMounted = false;
    };
  }, [selectedSymbol, selectedExpiry, reloadToken]);

  const spotPrice = chainData?.spot_price || 0;
  const atmIv = chainData?.analytics?.atm_iv;
  const currentIv = (() => {
    if (atmIv !== null && atmIv !== undefined && atmIv > 0) return atmIv / 100;
    return null;
  })();

  // 1h forecast fetch: same symbol + chain spot, fixed INTRADAY horizon.
  useEffect(() => {
    if (!spotPrice || spotPrice <= 0 || currentIv === null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setExpectedMove(null);
      setGreeks(null);
      setResearch(null);
      return;
    }
    let mounted = true;
    setForecastLoading(true);
    const run = async () => {
      try {
        const [emRaw, gkRaw, rsRaw] = await Promise.all([
          api.projectExpectedMove({
            underlying: selectedSymbol,
            spot: spotPrice,
            direction: forecastDirection,
            horizon: 'INTRADAY',
            current_iv: currentIv,
          }),
          api.getPortfolioGreeksSummary(),
          api.getFinancialResearch(selectedSymbol, 'INTRADAY', forecastDirection),
        ]);
        if (!mounted) return;
        setExpectedMove(unwrapModel<ExpectedMoveData>(emRaw));
        setGreeks(unwrapModel<GreeksSummaryData>(gkRaw));
        setResearch(unwrapModel<ResearchVerdict>(rsRaw));
        setForecastError(null);
      } catch (err) {
        if (!mounted) return;
        setForecastError(err instanceof Error ? err.message : 'Failed to fetch 1h forecast');
      } finally {
        if (mounted) setForecastLoading(false);
      }
    };
    void run();
    return () => {
      mounted = false;
    };
  }, [selectedSymbol, spotPrice, currentIv, forecastDirection]);

  // Positioning strip: walls = strikes with highest call / put OI in this expiry.
  let callWall: number | null = null;
  let putWall: number | null = null;
  if (chainData?.strikes?.length) {
    let maxCallOi = -1;
    let maxPutOi = -1;
    for (const row of chainData.strikes) {
      const cOi = row.call?.open_interest ?? 0;
      const pOi = row.put?.open_interest ?? 0;
      if (cOi > maxCallOi) {
        maxCallOi = cOi;
        callWall = row.strike;
      }
      if (pOi > maxPutOi) {
        maxPutOi = pOi;
        putWall = row.strike;
      }
    }
    if (maxCallOi <= 0) callWall = null;
    if (maxPutOi <= 0) putWall = null;
  }

  const analytics = chainData?.analytics;
  const maxPainStrike = analytics?.max_pain_strike ?? maxPainData?.max_pain_strike ?? null;
  const pcrOi = analytics?.pcr_oi;
  const pcrVol = analytics?.pcr_volume;

  const verdictLine1 = research
    ? `${(research.research_assessment || 'MIXED').replace(/_/g, ' ')} · uncertainty ${research.uncertainty_level || 'MODERATE'} · AI impact ${research.ai_impact || 'NO_CHANGE'}`
    : null;
  const verdictLine2 = research
    ? `Bull: ${research.bull_case_summary || 'Not stated.'} Bear: ${research.bear_case_summary || 'Not stated.'}`
    : null;
  const verdictLine3 = research
    ? `Invalidation: ${(research.contradiction_analysis?.invalidation_conditions?.[0] || research.contradiction_analysis?.strongest_counter_argument || 'Local structural stop breach.')}`
    : null;

  return (
    <div className="ds-page">
      <header className="page-hero">
        <div className="toolbar">
          <div>
            <div className="flex items-center gap-2.5">
              <h1>Derivatives — Options</h1>
              <span className="badge b-info" style={{ fontSize: 11 }}>{selectedSymbol}</span>
            </div>
            <p className="muted num">
              {selectedExpiry || chainData?.expiry ? `Expiry ${selectedExpiry || chainData?.expiry}` : 'Loading chain…'} · 1h INTRADAY forecast
            </p>
          </div>
          <span className="spacer" />
          <div className="seg" role="group" aria-label="Forecast direction">
            {(['BULLISH', 'BEARISH'] as const).map((d) => (
              <button
                key={d}
                type="button"
                className="seg-btn"
                data-active={forecastDirection === d}
                aria-pressed={forecastDirection === d}
                onClick={() => setForecastDirection(d)}
              >
                {d === 'BULLISH' ? 'Call · Bullish' : 'Put · Bearish'}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* 1. Header: underlying + expiry selects */}
      <OptionsHeader
        analytics={chainData?.analytics || null}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={(sym) => {
          setSelectedSymbol(sym);
          setSelectedExpiry('');
        }}
        selectedExpiry={selectedExpiry || chainData?.expiry || ''}
        expiries={chainData?.expiries || []}
        onSelectExpiry={(exp) => setSelectedExpiry(exp)}
        viewMode={viewMode}
        onToggleViewMode={setViewMode}
      />

      {error ? (
        <ErrorCard
          title="Error loading option chain"
          message={error}
          mode="full-page"
          onRetry={() => {
            setError(null);
            setReloadToken(v => v + 1);
          }}
          isRetrying={loading}
        />
      ) : loading && !chainData ? (
        <OptionChainSkeleton rows={12} />
      ) : (
        <>
          {/* 2. Positioning strip: the numbers the 1h forecast consumes */}
          <Card
            title="Positioning"
            meta="PCR · max pain · OI walls"
          >
            <p className="muted" style={{ margin: '0 0 12px', fontSize: 12.5 }}>
              PCR, max pain and OI walls feeding the 1h forecast.
            </p>
            <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
              <Stat
                label="PCR (OI)"
                value={pcrOi !== undefined && pcrOi !== null ? fmtNum(Number(pcrOi)) : '—'}
                sub={`Vol PCR ${pcrVol ?? '—'}`}
              />
              <Stat
                label="Max pain"
                value={maxPainStrike ? Number(maxPainStrike).toLocaleString('en-IN') : '—'}
                sub={maxPainStrike && spotPrice ? `${fmtNum(Math.abs(spotPrice - maxPainStrike), 1)} pts from spot` : 'Least option payout'}
              />
              <Stat
                label="Call wall"
                value={callWall ? `${callWall.toLocaleString('en-IN')} CE` : '—'}
                sub="Highest call OI"
                tone="bear"
              />
              <Stat
                label="Put wall"
                value={putWall ? `${putWall.toLocaleString('en-IN')} PE` : '—'}
                sub="Highest put OI"
                tone="bull"
              />
              <Stat
                label="ATM IV"
                value={atmIv ? `${fmtNum(atmIv, 1)}%` : currentIv != null ? `${fmtNum(currentIv * 100, 1)}%` : '—'}
                sub={`ATM ${analytics?.atm_strike?.toLocaleString('en-IN') ?? '—'}`}
              />
              <Stat
                label="Spot"
                value={spotPrice ? fmtINR(spotPrice) : '—'}
                sub={analytics?.futures_price ? `Fut ${fmtINR(analytics.futures_price)}` : 'Fut —'}
              />
            </div>
          </Card>

          {/* 3. Option chain dense table */}
          <OptionChainTable
            strikes={chainData?.strikes || []}
            viewMode={viewMode}
            spotPrice={spotPrice}
          />

          {/* 4. Expected move + greeks summary (+ 3-line research verdict) */}
          <Card
            title="1h forecast"
            meta="INTRADAY · chain spot + IV"
          >
            <p className="muted" style={{ margin: '0 0 12px', fontSize: 12.5 }}>
              INTRADAY expected move from chain spot and IV, plus portfolio greeks. Research verdict folded to 3 lines.
            </p>

            <div className="stat" style={{ marginBottom: 10 }}>
              <div className="stat-l">Research verdict</div>
              {forecastLoading && !research ? (
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Loading research verdict…</div>
              ) : verdictLine1 ? (
                <div style={{ display: 'grid', gap: 2, fontSize: 12, marginTop: 4 }}>
                  <div>{verdictLine1}</div>
                  <div className="muted">{verdictLine2}</div>
                  <div className="muted">{verdictLine3}</div>
                </div>
              ) : (
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  No AI research — quant baseline (neutral).{forecastError ? ` Forecast note: ${forecastError}` : ''}
                </div>
              )}
            </div>

            {forecastLoading && !expectedMove ? (
              <p className="muted" style={{ margin: 0, fontSize: 12 }}>Loading 1h forecast…</p>
            ) : (
              <div style={{ display: 'grid', gap: 12 }}>
                <ExpectedMoveCard data={expectedMove} />
                <GreeksSummaryCard summary={greeks} />
                {forecastError && (expectedMove || greeks) ? (
                  <p className="muted" style={{ margin: 0, fontSize: 12 }}>Forecast note: {forecastError}</p>
                ) : null}
              </div>
            )}
          </Card>

          {/* 5. AI: analysis + strategy architect + trade auditor */}
          <AIAnalysisCard symbol={selectedSymbol} contextPage="options" />
          <AIStrategyPanel symbol={selectedSymbol} />
          <AITradeValidator symbol={selectedSymbol} spotPrice={spotPrice} />

          {/* 6. Payoff / IV plain cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 12 }}>
            <PayoffChart
              data={maxPainData}
              spotPrice={spotPrice}
            />
            <IVSmileChart
              strikes={chainData?.strikes || []}
              atmStrike={chainData?.analytics?.atm_strike || 0}
            />
          </div>

          {/* 6. Flow table slim */}
          <InstitutionalFlowTracker
            symbol={selectedSymbol}
            expiry={selectedExpiry || chainData?.expiry}
          />
        </>
      )}
    </div>
  );
}
