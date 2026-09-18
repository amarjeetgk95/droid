'use client';

import React from 'react';
import {
  MarketPulseBar,
  ActiveSignalsRibbon,
  PaperPnLWidget,
  SystemHealthStrip,
  MLPredictionBadges,
  CommandDesk,
} from '@/components/command-center';
import { useInstrument, type SupportedInstrument } from '@/context/InstrumentContext';
import { PaperTradingProvider } from '@/context/PaperTradingContext';
import { WhyStrip } from '@/components/dashboard/WhyStrip';
import { ForecastOutcomes } from '@/components/dashboard/ForecastOutcomes';
import { isMinimalUi } from '@/lib/featureFlags';

/** Research endpoints key off the index symbol names used by the prediction store. */
const RESEARCH_SYMBOL: Record<SupportedInstrument, string> = {
  NIFTY: 'NIFTY 50',
  BANKNIFTY: 'BANKNIFTY',
  SENSEX: 'SENSEX',
};

export default function CommandCenterPage() {
  const { instrument, timeframe } = useInstrument();
  const researchSymbol = RESEARCH_SYMBOL[instrument];

  if (isMinimalUi()) {
    return <CommandDesk />;
  }

  return (
    <div className="space-y-5">
      {/* Top Operations Telemetry Strip */}
      <SystemHealthStrip />

      {/* Primary Market Pulse Bar: NIFTY / BANKNIFTY / SENSEX */}
      <MarketPulseBar />

      {/* Main Signal Command Ribbon */}
      <ActiveSignalsRibbon />

      {/* Real-Time Quantitative Engine & Paper Accounting */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <MLPredictionBadges />
        <PaperTradingProvider pollIntervalMs={4000}>
          <PaperPnLWidget />
        </PaperTradingProvider>
      </div>

      {/* Market context telemetry for the selected index */}
      <WhyStrip instrument={researchSymbol} />

      {/* Recorded forecast track record for the selected horizon */}
      <ForecastOutcomes instrument={researchSymbol} horizon={timeframe} />
    </div>
  );
}
