'use client';

import React from 'react';
import {
  ExecutionModeSwitcher,
  KillSwitchButton,
  PaperPortfolioCard,
  PositionsTable,
  OrderBook,
  BasketOrderBuilder,
  SizingPreview,
  ExposureGauge,
  ReconciliationPanel,
  CapitalLimitsEditor,
} from '@/components/execution-cockpit';
import { PaperTradingProvider } from '@/context/PaperTradingContext';

export default function ExecutionCockpitPage() {
  return (
    <PaperTradingProvider pollIntervalMs={4000}>
      <div className="space-y-5">
        {/* Big Emergency Kill Switch */}
        <KillSwitchButton />

        {/* Execution Mode Switcher */}
        <ExecutionModeSwitcher />

        {/* Capital Portfolio & Exposure Gauges */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <PaperPortfolioCard />
          <ExposureGauge />
        </div>

        {/* Open Positions & Order Book */}
        <PositionsTable />
        <OrderBook />

        {/* Multi-Leg Basket Order Builder & Sizing Preview */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <BasketOrderBuilder />
          <SizingPreview />
        </div>

        {/* Capital Limits & Reconciliation */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <CapitalLimitsEditor />
          <ReconciliationPanel />
        </div>
      </div>
    </PaperTradingProvider>
  );
}
