// @vitest-environment happy-dom
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

vi.mock('@/components/execution-cockpit', () => ({
  KillSwitchButton: () => <div data-testid="kill-switch" />,
  ExecutionModeSwitcher: () => <div data-testid="execution-mode-switcher" />,
  PaperPortfolioCard: () => <div data-testid="paper-portfolio-card" />,
  PositionsTable: () => <div data-testid="positions-table" />,
  OrderBook: () => <div data-testid="order-book" />,
  BasketOrderBuilder: () => <div data-testid="basket-order-builder" />,
  SizingPreview: () => <div data-testid="sizing-preview" />,
  ExposureGauge: () => <div data-testid="exposure-gauge" />,
  ReconciliationPanel: () => <div data-testid="reconciliation-panel" />,
  CapitalLimitsEditor: () => <div data-testid="capital-limits-editor" />,
}));

vi.mock('@/components/risk-matrix', () => ({
  PerformanceCards: () => <div data-testid="performance-cards" />,
  PerformanceChart: () => <div data-testid="performance-chart" />,
  AuditLedger: () => <div data-testid="audit-ledger" />,
  PortfolioGreeksDisplay: () => <div data-testid="portfolio-greeks" />,
  PortfolioRiskPanel: () => <div data-testid="portfolio-risk-panel" />,
  BulkOperationsBar: () => <div data-testid="bulk-operations-bar" />,
}));

vi.mock('@/components/swing/SwingDesk', () => ({
  SwingDesk: () => <div data-testid="swing-desk" />,
}));

vi.mock('@/context/PaperTradingContext', () => ({
  PaperTradingProvider: ({
    children,
    pollIntervalMs,
  }: {
    children: React.ReactNode;
    pollIntervalMs?: number;
  }) => (
    <div data-testid="paper-provider" data-poll-interval={pollIntervalMs}>
      {children}
    </div>
  ),
}));

vi.mock('@/context/RiskDataContext', () => ({
  RiskDataProvider: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="risk-provider">{children}</div>
  ),
}));

import { PositionsDesk } from './PositionsDesk';

const ORDER_TAB_IDS = [
  'order-book',
  'basket-order-builder',
  'sizing-preview',
  'capital-limits-editor',
  'reconciliation-panel',
];

const RISK_TAB_IDS = [
  'performance-cards',
  'performance-chart',
  'portfolio-greeks',
  'portfolio-risk-panel',
  'audit-ledger',
  'bulk-operations-bar',
];

afterEach(cleanup);

describe('PositionsDesk', () => {
  it('renders the header controls and the four section tabs', () => {
    render(<PositionsDesk />);

    expect(screen.getByTestId('kill-switch')).toBeTruthy();
    expect(screen.getByTestId('execution-mode-switcher')).toBeTruthy();
    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'Positions',
      'Orders',
      'Risk',
      'Swing',
    ]);
  });

  it('mounts only the Positions tab by default', () => {
    render(<PositionsDesk />);

    expect(screen.getByRole('tab', { name: 'Positions' }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByTestId('paper-provider').getAttribute('data-poll-interval')).toBe('4000');
    expect(screen.getByTestId('paper-portfolio-card')).toBeTruthy();
    expect(screen.getByTestId('exposure-gauge')).toBeTruthy();
    expect(screen.getByTestId('positions-table')).toBeTruthy();

    for (const id of ORDER_TAB_IDS) expect(screen.queryByTestId(id)).toBeNull();
    expect(screen.queryByTestId('risk-provider')).toBeNull();
    expect(screen.queryByTestId('swing-desk')).toBeNull();
  });

  it('switches to Orders and unmounts the positions provider', () => {
    render(<PositionsDesk />);

    fireEvent.click(screen.getByRole('tab', { name: 'Orders' }));

    expect(screen.getByRole('tab', { name: 'Orders' }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tab', { name: 'Positions' }).getAttribute('aria-selected')).toBe('false');
    for (const id of ORDER_TAB_IDS) expect(screen.getByTestId(id)).toBeTruthy();

    expect(screen.queryByTestId('paper-provider')).toBeNull();
    expect(screen.queryByTestId('positions-table')).toBeNull();
    expect(screen.queryByTestId('risk-provider')).toBeNull();
    expect(screen.queryByTestId('swing-desk')).toBeNull();
  });

  it('switches to Risk, wrapping every panel in the RiskDataProvider', () => {
    render(<PositionsDesk />);

    fireEvent.click(screen.getByRole('tab', { name: 'Risk' }));

    const provider = screen.getByTestId('risk-provider');
    for (const id of RISK_TAB_IDS) {
      expect(provider.contains(screen.getByTestId(id))).toBe(true);
    }

    expect(screen.queryByTestId('paper-provider')).toBeNull();
    expect(screen.queryByTestId('order-book')).toBeNull();
    expect(screen.queryByTestId('swing-desk')).toBeNull();
  });

  it('switches to Swing and mounts only the existing swing desk', () => {
    render(<PositionsDesk />);

    fireEvent.click(screen.getByRole('tab', { name: 'Swing' }));

    expect(screen.getByTestId('swing-desk')).toBeTruthy();
    expect(screen.queryByTestId('paper-provider')).toBeNull();
    expect(screen.queryByTestId('risk-provider')).toBeNull();
    expect(screen.queryByTestId('order-book')).toBeNull();
  });
});
