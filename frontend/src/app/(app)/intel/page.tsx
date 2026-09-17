'use client';

import React from 'react';
import {
  IntelHubProvider,
  InstrumentSelector,
  RegimePanel,
  EvidenceGrid,
  BreakoutMeter,
  OptionsFlowPanel,
  DataHealthMatrix,
  InstitutionalFlowTicker,
  ShortHorizonCard,
  ContinuationCard,
} from '@/components/intel-hub';

export default function IntelHubPage() {
  return (
    <IntelHubProvider>
      <div className="space-y-5">
        {/* Top Selector Strip */}
        <InstrumentSelector />

        {/* Primary Regime and Breakout Matrix */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <RegimePanel />
          <BreakoutMeter />
        </div>

        {/* Time-Boxed Setups Strip */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <ShortHorizonCard />
          <ContinuationCard />
        </div>

        {/* Derivatives Flow and Evidence Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <OptionsFlowPanel />
          <EvidenceGrid />
        </div>

        {/* Institutional Flow & Data Integrity */}
        <InstitutionalFlowTicker />
        <DataHealthMatrix />
      </div>
    </IntelHubProvider>
  );
}
