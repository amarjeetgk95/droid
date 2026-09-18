'use client';

import React, { useState } from 'react';
import { SystemHealthStrip } from './SystemHealthStrip';
import { MarketPulseBar } from './MarketPulseBar';
import { MLPredictionBadges } from './MLPredictionBadges';
import { ActiveSignalsRibbon } from './ActiveSignalsRibbon';
import { PaperPnLWidget } from './PaperPnLWidget';
import { WhyStrip } from '@/components/dashboard/WhyStrip';
import { ForecastOutcomes } from '@/components/dashboard/ForecastOutcomes';
import { PaperTradingProvider } from '@/context/PaperTradingContext';
import { useInstrument, type SupportedInstrument } from '@/context/InstrumentContext';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import { regimeFromSummary } from '@/lib/regime';
import { confidencePct, isUsableRegimeOverview, posNum } from '@/components/markets/truthful';
import { Card, DirectionBadge, fmtNum } from '@/components/ui/desk';

/** Research endpoints key off the index symbol names used by the prediction store. */
const RESEARCH_SYMBOL: Record<SupportedInstrument, string> = {
  NIFTY: 'NIFTY 50',
  BANKNIFTY: 'BANKNIFTY',
  SENSEX: 'SENSEX',
};

function directionForRegime(state: string): 'BULLISH' | 'BEARISH' | 'NEUTRAL' {
  const s = state.toUpperCase();
  if (s.includes('BULLISH')) return 'BULLISH';
  if (s.includes('BEARISH')) return 'BEARISH';
  return 'NEUTRAL';
}

/**
 * Compact bias summary built entirely from the shared MarketDataContext
 * regime leg (summary regime is always the NIFTY diagnosis — see
 * `regimeFromSummary`). Renders nothing when the leg is absent/unusable rather
 * than opening a fetch of its own.
 */
function BiasSummaryBlock({ researchSymbol }: { researchSymbol: string }) {
  const market = useOptionalMarketDataContext();
  const regime = regimeFromSummary(market?.regimeOverview, researchSymbol);
  if (!regime || !isUsableRegimeOverview(regime, researchSymbol)) return null;

  const conf = confidencePct(regime.confidence_score);
  const vix = posNum(regime.vix_regime?.vix_value);

  return (
    <Card title="Bias summary" meta={regime.symbol}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <DirectionBadge direction={directionForRegime(regime.regime_state)} />
        <span style={{ fontWeight: 600, fontSize: 12.5 }}>
          {regime.regime_state.replace(/_/g, ' ')}
        </span>
        {conf !== null ? (
          <span className="muted num" style={{ marginLeft: 'auto', fontSize: 12 }}>
            {conf}% conf
          </span>
        ) : null}
      </div>
      <p className="muted" style={{ margin: '8px 0 0', fontSize: 12 }}>
        {regime.summary_headline}
      </p>
      {vix !== null ? (
        <div className="muted num" style={{ marginTop: 8, fontSize: 11.5 }}>
          VIX {fmtNum(vix, 1)}
          {regime.vix_regime?.regime_category
            ? ` · ${regime.vix_regime.regime_category.replace(/_/g, ' ')}`
            : ''}
        </div>
      ) : null}
    </Card>
  );
}

/**
 * Command desk (P2-1): the consolidated default screen behind
 * `isMinimalUi()`. Three columns at ≥1440 px — market/bias, signals/forecast,
 * collapsible context rail — collapsing to one column below that. Every child
 * is the existing route component, mounted with its existing props; no new
 * API calls are introduced here.
 */
export function CommandDesk() {
  const { instrument, timeframe } = useInstrument();
  const researchSymbol = RESEARCH_SYMBOL[instrument];
  const [railOpen, setRailOpen] = useState(true);

  return (
    <div className="space-y-5">
      {/* Top Operations Telemetry Strip — the single status ribbon */}
      <SystemHealthStrip />

      <div className="flex justify-end">
        <button
          type="button"
          className="btn"
          onClick={() => setRailOpen((prev) => !prev)}
          aria-expanded={railOpen}
          aria-controls="command-context-rail"
        >
          {railOpen ? 'Hide context rail' : 'Show context rail'}
        </button>
      </div>

      <div
        className={`grid grid-cols-1 gap-5 ${
          railOpen
            ? 'min-[1440px]:grid-cols-[minmax(280px,320px)_minmax(0,1fr)_minmax(360px,400px)]'
            : 'min-[1440px]:grid-cols-[minmax(280px,320px)_minmax(0,1fr)]'
        }`}
      >
        <section aria-label="Market and bias" className="flex min-w-0 flex-col gap-5">
          <BiasSummaryBlock researchSymbol={researchSymbol} />
          <MarketPulseBar />
          <MLPredictionBadges />
        </section>

        <section aria-label="Signals and forecast" className="flex min-w-0 flex-col gap-5">
          <ActiveSignalsRibbon />
          <ForecastOutcomes instrument={researchSymbol} horizon={timeframe} />
        </section>

        {railOpen ? (
          <aside
            id="command-context-rail"
            aria-label="Context rail"
            className="flex min-w-0 flex-col gap-5"
          >
            <WhyStrip instrument={researchSymbol} />
            <PaperTradingProvider pollIntervalMs={4000}>
              <PaperPnLWidget />
            </PaperTradingProvider>
          </aside>
        ) : null}
      </div>
    </div>
  );
}
