'use client';

import React from 'react';
import {
  AuditLedger,
  PerformanceCards,
  PerformanceChart,
  PortfolioRiskPanel,
  PortfolioGreeksDisplay,
  BulkOperationsBar,
} from '@/components/risk-matrix';
import { RiskDataProvider } from '@/context/RiskDataContext';

export default function RiskMatrixPage() {
  return (
    <RiskDataProvider>
      <div className="space-y-5">
        {/* Top Performance Analytics KPI Row */}
        <PerformanceCards />

        {/* Equity Growth & Greeks Sensitivity */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <PerformanceChart />
          <PortfolioGreeksDisplay />
        </div>

        {/* Portfolio Risk — explicit order evaluation (no cached figures) */}
        <PortfolioRiskPanel />

        {/* Full Audit Ledger & Database Operations */}
        <AuditLedger />
        <BulkOperationsBar />
      </div>
    </RiskDataProvider>
  );
}
