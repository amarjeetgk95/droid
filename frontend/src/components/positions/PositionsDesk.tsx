'use client';

import React, { useState } from 'react';
import {
  BasketOrderBuilder,
  CapitalLimitsEditor,
  ExecutionModeSwitcher,
  ExposureGauge,
  KillSwitchButton,
  OrderBook,
  PaperPortfolioCard,
  PositionsTable,
  ReconciliationPanel,
  SizingPreview,
} from '@/components/execution-cockpit';
import {
  AuditLedger,
  BulkOperationsBar,
  PerformanceCards,
  PerformanceChart,
  PortfolioGreeksDisplay,
  PortfolioRiskPanel,
} from '@/components/risk-matrix';
import { SwingDesk } from '@/components/swing/SwingDesk';
import { PaperTradingProvider } from '@/context/PaperTradingContext';
import { RiskDataProvider } from '@/context/RiskDataContext';

type PositionsTabId = 'positions' | 'orders' | 'risk' | 'swing';

const TABS: ReadonlyArray<{ id: PositionsTabId; label: string }> = [
  { id: 'positions', label: 'Positions' },
  { id: 'orders', label: 'Orders' },
  { id: 'risk', label: 'Risk' },
  { id: 'swing', label: 'Swing' },
];

/**
 * Positions desk (P2-2): the consolidated execution + risk + swing
 * destination behind `isMinimalUi()`. Every child is the existing route
 * component with its existing props; only the active tab is mounted, so the
 * inactive providers (and their pollers) never run.
 */
export function PositionsDesk() {
  const [activeTab, setActiveTab] = useState<PositionsTabId>('positions');

  return (
    <div className="space-y-5">
      {/* Header row — emergency controls */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <KillSwitchButton />
        <ExecutionModeSwitcher />
      </div>

      {/* Section tabs */}
      <div className="seg" role="tablist" aria-label="Positions sections">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`positions-tab-${tab.id}`}
            aria-selected={activeTab === tab.id}
            aria-controls={`positions-panel-${tab.id}`}
            className="seg-btn"
            data-active={activeTab === tab.id}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'positions' ? (
        <div
          id="positions-panel-positions"
          role="tabpanel"
          aria-labelledby="positions-tab-positions"
        >
          <PaperTradingProvider pollIntervalMs={4000}>
            <div className="space-y-5">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <PaperPortfolioCard />
                <ExposureGauge />
              </div>
              <PositionsTable />
            </div>
          </PaperTradingProvider>
        </div>
      ) : null}

      {activeTab === 'orders' ? (
        <div id="positions-panel-orders" role="tabpanel" aria-labelledby="positions-tab-orders" className="space-y-5">
          <OrderBook />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <BasketOrderBuilder />
            <SizingPreview />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <CapitalLimitsEditor />
            <ReconciliationPanel />
          </div>
        </div>
      ) : null}

      {activeTab === 'risk' ? (
        <div id="positions-panel-risk" role="tabpanel" aria-labelledby="positions-tab-risk">
          <RiskDataProvider>
            <div className="space-y-5">
              <PerformanceCards />
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <PerformanceChart />
                <PortfolioGreeksDisplay />
              </div>
              <PortfolioRiskPanel />
              <AuditLedger />
              <BulkOperationsBar />
            </div>
          </RiskDataProvider>
        </div>
      ) : null}

      {activeTab === 'swing' ? (
        <div id="positions-panel-swing" role="tabpanel" aria-labelledby="positions-tab-swing">
          <SwingDesk />
        </div>
      ) : null}
    </div>
  );
}
