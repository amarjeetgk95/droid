// @vitest-environment happy-dom
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  getSignalsAudit: vi.fn(),
  getSignalsPerformance: vi.fn(),
  getPortfolioGreeksSummary: vi.fn(),
  evaluatePortfolioRisk: vi.fn(),
  getSignalsStatus: vi.fn(),
  bulkDeleteSignals: vi.fn(),
  voidAuditTrades: vi.fn(),
  sanitizeSignalsAudit: vi.fn(),
}));

vi.mock('@/lib/api', () => ({ api: apiMocks }));

import { AuditLedger } from './AuditLedger';
import { BulkOperationsBar } from './BulkOperationsBar';
import { PerformanceCards } from './PerformanceCards';
import { PerformanceChart } from './PerformanceChart';
import { PortfolioGreeksDisplay } from './PortfolioGreeksDisplay';
import { PortfolioRiskPanel } from './PortfolioRiskPanel';
import { RiskDataProvider } from '@/context/RiskDataContext';

beforeEach(() => {
  Object.values(apiMocks).forEach((m) => m.mockReset());
});

afterEach(() => cleanup());

describe('AuditLedger', () => {
  it('renders real audit fields and never paints a missing P&L as profit', async () => {
    apiMocks.getSignalsAudit.mockResolvedValue({
      trades: [
        {
          signal_id: 'SIG-1',
          underlying: 'NIFTY',
          direction: 'CALL',
          strategy: 'ORB',
          actual_fill_price: 120,
          trigger_price: 24500,
          exit_price: 90,
          actual_pnl_inr: -2250,
          total_pnl_inr: -2250,
          status: 'LOST',
          created_at_str: '17 Sep 2026, 10:00:00 IST',
        },
        {
          signal_id: 'SIG-2',
          underlying: 'BANKNIFTY',
          direction: 'PUT',
          strategy: 'MEAN_REVERSION',
          economics_unavailable: true,
          status: 'CLOSED',
          created_at_str: '17 Sep 2026, 11:00:00 IST',
        },
      ],
      count: 2,
      summary: {},
      timestamp_ms: 1,
    });

    render(
      <RiskDataProvider>
        <AuditLedger />
      </RiskDataProvider>,
    );

    await waitFor(() => expect(screen.getByText('SIG-1')).toBeTruthy());
    expect(screen.getByText('17 Sep 2026, 10:00:00 IST')).toBeTruthy();
    const pnl = screen.getByText('-₹2,250');
    expect(pnl.className).toContain('text-down-strong');
    expect(screen.getByText('UNAVAILABLE')).toBeTruthy();
    // The old defect: every record rendered "₹0" as profit.
    expect(screen.queryByText('+₹0')).toBeNull();
    expect(screen.queryByText('₹0')).toBeNull();
  });

  it('shows an explicit unavailable state when the ledger fetch fails', async () => {
    apiMocks.getSignalsAudit.mockRejectedValue(new Error('backend unreachable'));
    render(
      <RiskDataProvider>
        <AuditLedger />
      </RiskDataProvider>,
    );
    await waitFor(() => expect(screen.getByText(/Audit ledger unavailable/)).toBeTruthy());
    expect(screen.getByText(/backend unreachable/)).toBeTruthy();
  });
});

describe('PortfolioGreeksDisplay', () => {
  it('formats signs from the value and tones theta by sign', async () => {
    apiMocks.getPortfolioGreeksSummary.mockResolvedValue({
      total_delta: 42.5,
      total_gamma: -0.05,
      total_theta_day: -1420,
      total_vega: 2150,
      gross_delta: 700,
      gross_gamma: 1.2,
      gross_theta_day: 1420,
      gross_vega: 2150,
      total_open_positions: 3,
    });

    render(<PortfolioGreeksDisplay />);

    await waitFor(() => expect(screen.getByText('+42.5')).toBeTruthy());
    expect(screen.getByText('-0.050')).toBeTruthy();
    expect(screen.queryByText('+-0.050')).toBeNull();
    const theta = screen.getByText('-₹1,420/day');
    expect(theta.className).toContain('text-down-strong');
    expect(screen.getByText('+₹2,150')).toBeTruthy();
    expect(screen.getByText('3 open positions')).toBeTruthy();
  });
});

describe('PerformanceCards', () => {
  it('renders negative expectancy with a single sign and tones win rate by value', async () => {
    apiMocks.getSignalsPerformance.mockResolvedValue({
      total_signals: 10,
      winning_signals: 4,
      losing_signals: 6,
      win_rate_pct: 40,
      profit_factor: 0.8,
      average_rr: 1.5,
      expectancy_r: -0.35,
    });

    render(
      <RiskDataProvider>
        <PerformanceCards />
      </RiskDataProvider>,
    );

    await waitFor(() => expect(screen.getByText('-0.35 R')).toBeTruthy());
    expect(screen.queryByText('+-0.35 R')).toBeNull();
    const winRate = screen.getByText('40.0%');
    expect(winRate.className).toContain('text-warn-strong');
    expect(winRate.className).not.toContain('text-up');
  });

  it('shows an explicit unavailable state instead of seeded metrics when the fetch fails', async () => {
    apiMocks.getSignalsPerformance.mockRejectedValue(new Error('perf down'));
    render(
      <RiskDataProvider>
        <PerformanceCards />
      </RiskDataProvider>,
    );
    await waitFor(() => expect(screen.getByText(/Performance metrics unavailable/)).toBeTruthy());
    expect(screen.getByText(/perf down/)).toBeTruthy();
  });
});

describe('PerformanceChart', () => {
  it('plots the real settled-P&L curve and refuses to pad a short series', async () => {
    const settled = [
      { signal_id: 'A', actual_pnl_inr: 100, exited_at_utc: 1, status: 'WON' },
      { signal_id: 'B', actual_pnl_inr: -300, exited_at_utc: 2, status: 'LOST' },
      { signal_id: 'C', actual_pnl_inr: 50, exited_at_utc: 3, status: 'WON' },
    ];
    apiMocks.getSignalsAudit.mockResolvedValue({
      trades: settled,
      count: settled.length,
      summary: {},
      timestamp_ms: 1,
    });

    const { unmount } = render(
      <RiskDataProvider>
        <PerformanceChart />
      </RiskDataProvider>,
    );
    await waitFor(() => expect(screen.getByText(/CURRENT: -₹150/)).toBeTruthy());
    expect(screen.getByText(/MAX DD: -₹300/)).toBeTruthy();
    expect(screen.getByText(/Settled trades plotted: 3/)).toBeTruthy();
    unmount();

    apiMocks.getSignalsAudit.mockReset();
    apiMocks.getSignalsAudit.mockResolvedValue({
      trades: [{ signal_id: 'A', actual_pnl_inr: 100, exited_at_utc: 1 }],
      count: 1,
      summary: {},
      timestamp_ms: 1,
    });
    render(
      <RiskDataProvider>
        <PerformanceChart />
      </RiskDataProvider>,
    );
    await waitFor(() => expect(screen.getByText(/Cumulative curve unavailable/)).toBeTruthy());
    expect(screen.queryByText(/CURRENT:/)).toBeNull();
  });

  it('shares a single audit fetch between the ledger and the chart', async () => {
    const settled = [
      { signal_id: 'A', actual_pnl_inr: 100, exited_at_utc: 1, status: 'WON' },
      { signal_id: 'B', actual_pnl_inr: -300, exited_at_utc: 2, status: 'LOST' },
      { signal_id: 'C', actual_pnl_inr: 50, exited_at_utc: 3, status: 'WON' },
    ];
    apiMocks.getSignalsAudit.mockResolvedValue({
      trades: settled,
      count: settled.length,
      summary: {},
      timestamp_ms: 1,
    });

    render(
      <RiskDataProvider>
        <AuditLedger />
        <PerformanceChart />
      </RiskDataProvider>,
    );

    await waitFor(() => expect(screen.getByText(/Settled trades plotted: 3/)).toBeTruthy());
    expect(screen.getByText('A')).toBeTruthy();
    expect(apiMocks.getSignalsAudit).toHaveBeenCalledTimes(1);
    expect(apiMocks.getSignalsAudit).toHaveBeenCalledWith({ limit: 200 });
  });
});

describe('BulkOperationsBar', () => {
  it('states the true destructive scope with counts and requires typed confirmation', async () => {
    apiMocks.getSignalsStatus.mockResolvedValue({
      active_count: 3,
      armed_count: 2,
      confirmed_count: 1,
      diagnostics: {},
      timestamp_ms: 1,
    });
    apiMocks.getSignalsAudit.mockResolvedValue({
      trades: [],
      count: 0,
      summary: { total_signals_audited: 12, open_trades: 3, closed_trades: 9 },
      timestamp_ms: 1,
    });
    apiMocks.bulkDeleteSignals.mockResolvedValue({
      status: 'success',
      message: 'deleted',
      deleted_count: 12,
      deleted_ids: [],
      requested_count: 12,
    });

    render(<BulkOperationsBar />);
    fireEvent.click(screen.getByRole('button', { name: /Purge Signals/ }));

    await waitFor(() => expect(screen.getByText(/Audit ledger reports: 12 record/)).toBeTruthy());
    expect(screen.getByText(/active signals are/i)).toBeTruthy();
    expect(screen.queryByText(/remain protected/i)).toBeNull();

    const confirm = screen.getByRole('button', { name: /PURGE ALL MATCHED SIGNALS/ }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);

    fireEvent.change(screen.getByPlaceholderText('DELETE'), { target: { value: 'DELETE' } });
    expect(confirm.disabled).toBe(false);
    fireEvent.click(confirm);

    await waitFor(() =>
      expect(apiMocks.bulkDeleteSignals).toHaveBeenCalledWith({
        delete_all: true,
        confirm_all: true,
      }),
    );
    await waitFor(() => expect(screen.getByText(/Purged 12 of 12/)).toBeTruthy());
  });

  it('surfaces a purge failure without closing the dialog silently', async () => {
    apiMocks.getSignalsStatus.mockResolvedValue({
      active_count: 0,
      armed_count: 0,
      confirmed_count: 0,
      diagnostics: {},
      timestamp_ms: 1,
    });
    apiMocks.getSignalsAudit.mockResolvedValue({
      trades: [],
      count: 0,
      summary: {},
      timestamp_ms: 1,
    });
    apiMocks.bulkDeleteSignals.mockRejectedValue(new Error('503 delete backend offline'));

    render(<BulkOperationsBar />);
    fireEvent.click(screen.getByRole('button', { name: /Purge Signals/ }));
    fireEvent.change(await screen.findByPlaceholderText('DELETE'), { target: { value: 'DELETE' } });
    fireEvent.click(screen.getByRole('button', { name: /PURGE ALL MATCHED SIGNALS/ }));

    await waitFor(() => expect(screen.getAllByText(/backend offline/).length).toBeGreaterThan(0));
  });
});

describe('PortfolioRiskPanel', () => {
  it('requires order context and evaluates the real engine response', async () => {
    apiMocks.evaluatePortfolioRisk.mockResolvedValue({
      result: 'REJECTED',
      reason: 'MARGIN_BREACH',
      failed_check: 'margin_limit',
      checks: [
        { name: 'margin_limit', passed: false, reason: 'MARGIN_BREACH 95.0% > 80%' },
        { name: 'all_portfolio_checks', passed: true, reason: 'ALL_PORTFOLIO_CHECKS_PASSED' },
      ],
      portfolio: { gross: '500000', net: '500000', margin_used: '95000' },
    });

    render(<PortfolioRiskPanel />);
    expect(screen.getByText(/Order context required/)).toBeTruthy();

    fireEvent.change(screen.getByPlaceholderText('e.g. 250000'), { target: { value: '500000' } });
    fireEvent.change(screen.getByPlaceholderText('e.g. 120000'), { target: { value: '95000' } });
    fireEvent.change(screen.getByLabelText(/Total capital/), { target: { value: '100000' } });
    fireEvent.change(screen.getByLabelText(/Margin limit/), { target: { value: '80' } });
    fireEvent.click(screen.getByRole('button', { name: /Evaluate Order/ }));

    await waitFor(() => expect(screen.getByText('REJECTED')).toBeTruthy());
    await waitFor(() =>
      expect(apiMocks.evaluatePortfolioRisk).toHaveBeenCalledWith({
        new_order_instrument: 'NIFTY',
        new_order_notional: '500000',
        new_order_margin: '95000',
        side: 'BUY',
        limits: { total_capital: 100000, margin_limit_pct: 80 },
      }),
    );
    expect(screen.getByText(/MARGIN_BREACH 95\.0%/)).toBeTruthy();
    expect(screen.getByText('margin limit')).toBeTruthy();
    expect(screen.getByText('FAIL')).toBeTruthy();
    expect(screen.getByText('PASS')).toBeTruthy();

    // Projected margin utilisation gauge: 95,000 / 100,000 = 95%.
    const gauge = screen.getByRole('progressbar', { name: 'Projected margin utilization' });
    expect(gauge.getAttribute('aria-valuenow')).toBe('95');
    expect(gauge.getAttribute('aria-valuemax')).toBe('100');
  });

  it('blocks evaluation with a visible validation error when context is missing', async () => {
    render(<PortfolioRiskPanel />);
    fireEvent.click(screen.getByRole('button', { name: /Evaluate Order/ }));
    await waitFor(() =>
      expect(screen.getByText(/Enter a positive new-order notional/)).toBeTruthy(),
    );
    expect(apiMocks.evaluatePortfolioRisk).not.toHaveBeenCalled();
  });
});
