// @vitest-environment happy-dom
import React from 'react';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QuantFalsificationPanel } from './QuantFalsificationPanel';
import { runStrategyMatrix, quantApi } from '@/lib/api/quant';

vi.mock('@/lib/api', () => ({
  api: {
    listDatasets: vi.fn().mockResolvedValue({
      data: [
        {
          symbol: 'SENSEX',
          timeframe: '1m',
          row_count: 67500,
          data_quality_score: 100,
        },
      ],
    }),
    runG0Baseline: vi.fn().mockResolvedValue({
      data: {
        metrics: {
          total_trades: 120,
          win_rate: 0.45,
          gross_expectancy_pct: 0.002,
          net_expectancy_pct: -0.001,
          profit_factor: 0.95,
          max_drawdown_pct: 0.04,
          annualized_sharpe: -0.5,
          deflated_sharpe_ratio: 0.1,
          cost_survival_max_multiplier: 0.8,
          gate_g0_verdict: 'FAILED',
          verdict_reasons: ['Net expectancy is negative after statutory costs'],
        },
        sample_trades: [],
      },
    }),
    runG1Ablation: vi.fn(),
    simulateOptionsTrade: vi.fn(),
  },
}));

vi.mock('@/lib/api/quant', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/quant')>('@/lib/api/quant');
  return {
    ...actual,
    quantApi: {
      ...(actual.quantApi as object),
      getS6Trials: vi.fn().mockResolvedValue({ data: { trials: [] } }),
      runS6Battery: vi.fn(),
      runG2Robustness: vi.fn(),
      exportStrategyMatrix: vi.fn(),
      exportG0Trades: vi.fn(),
      simulateOptionsSpread: vi.fn(),
    },
    runStrategyMatrix: vi.fn().mockResolvedValue({
      data: {
        provenance: {
          source_dataset: 'SENSEX 1m (67,500 bars)',
          source_bars: 67500,
          resampled_timeframe: '15m',
          cost_model: 'Statutory Indian F&O',
        },
        matrix: [
          {
            strategy_key: 'S1',
            strategy_name: 'Opening Range Breakout (ORB)',
            total_trades: 210,
            win_rate: 0.44,
            gross_expectancy_pct: 0.0015,
            net_expectancy_pct: -0.0005,
            profit_factor: 0.96,
            max_drawdown_pct: 0.05,
            gate_g0_verdict: 'FAILED',
          },
          {
            strategy_key: 'S2',
            strategy_name: '20-bar Momentum Breakout',
            total_trades: 180,
            win_rate: 0.42,
            gross_expectancy_pct: 0.001,
            net_expectancy_pct: -0.0012,
            profit_factor: 0.91,
            max_drawdown_pct: 0.06,
            gate_g0_verdict: 'FAILED',
          },
          {
            strategy_key: 'S3',
            strategy_name: 'VWAP Reclaim / Reject',
            total_trades: 195,
            win_rate: 0.46,
            gross_expectancy_pct: 0.0018,
            net_expectancy_pct: -0.0004,
            profit_factor: 0.98,
            max_drawdown_pct: 0.045,
            gate_g0_verdict: 'FAILED',
          },
          {
            strategy_key: 'S4',
            strategy_name: 'Volatility Squeeze Breakout',
            total_trades: 160,
            win_rate: 0.41,
            gross_expectancy_pct: 0.0012,
            net_expectancy_pct: -0.0015,
            profit_factor: 0.89,
            max_drawdown_pct: 0.07,
            gate_g0_verdict: 'FAILED',
          },
          {
            strategy_key: 'ALL',
            strategy_name: 'Portfolio Combination (S1-S4)',
            total_trades: 745,
            win_rate: 0.43,
            gross_expectancy_pct: 0.0014,
            net_expectancy_pct: -0.0009,
            profit_factor: 0.93,
            max_drawdown_pct: 0.055,
            gate_g0_verdict: 'FAILED',
          },
        ],
      },
    }),
  };
});

afterEach(() => cleanup());

describe('QuantFalsificationPanel', () => {
  it('renders the persistent institutional research integrity banner', () => {
    render(<QuantFalsificationPanel />);

    expect(screen.getByText('EXPERIMENTAL RESEARCH PROTOCOL')).toBeDefined();
    expect(
      screen.getByText(
        /Displayed metrics are empirical measurements under statutory Indian F&O costs \(STT, BSE turnover, SEBI, GST, ₹20 brokerage, slippage\)\. Software correctness does not equal trading edge\. Downstream ML \(G1\) and Execution \(Tier 3\) are strictly BLOCKED until base edge survives Gate G0\./,
      ),
    ).toBeDefined();
  });

  it('renders dataset provenance semantics with explicit source, analysis, and quality clean scores', async () => {
    render(<QuantFalsificationPanel />);

    await waitFor(() => {
      expect(screen.getByText(/Source: SENSEX 1m \(67,500 bars\)/)).toBeDefined();
      expect(screen.getByText(/Analysis: 15m \(Resampled\)/)).toBeDefined();
      expect(screen.getByText(/Data Quality: 100\/100 \(Firewall Clean\)/)).toBeDefined();
    });
  });

  it('renders Strategy Isolation Benchmark table with all 5 strategies and initial NOT RUN badges', () => {
    render(<QuantFalsificationPanel />);

    expect(
      screen.getByText('STRATEGY ISOLATION BENCHMARK (GATE G0 PRE-REQUISITE)'),
    ).toBeDefined();
    expect(
      screen.getByText(
        'Independent evaluation of individual hypotheses under identical execution assumptions before portfolio pooling or ML filtering.',
      ),
    ).toBeDefined();
    expect(screen.getByRole('button', { name: /Run Strategy Isolation Matrix/i })).toBeDefined();

    // Verify columns
    expect(screen.getByText('Strategy')).toBeDefined();
    expect(screen.getByText('Trades')).toBeDefined();
    expect(screen.getAllByText('Win Rate').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Gross Exp')).toBeDefined();
    expect(screen.getByText('Net Exp')).toBeDefined();
    expect(screen.getAllByText('Profit Factor').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Max DD')).toBeDefined();
    expect(screen.getByText('Gate G0 Status')).toBeDefined();

    // Verify default NOT RUN badges (at least 7 for S1-S6, ALL)
    const notRunBadges = screen.getAllByText('NOT RUN');
    expect(notRunBadges.length).toBeGreaterThanOrEqual(7);
  });

  it('renders DROID Signature Strategy S6 section with 2x2 matrix and experimental badges', () => {
    render(<QuantFalsificationPanel />);

    expect(
      screen.getByText('DROID SIGNATURE STRATEGY S6: ADAPTIVE COMPRESSION-EXPANSION BREAKOUT'),
    ).toBeDefined();
    expect(screen.getByText('Track A: S6-A / T1')).toBeDefined();
    expect(screen.getByText('Track B: S6-A / T4')).toBeDefined();
    expect(screen.getByText('Track C: S6-F / T1')).toBeDefined();
    expect(screen.getByText('Track D: S6-F / T4')).toBeDefined();
    expect(screen.getByRole('button', { name: /Run S6 Triage Battery/i })).toBeDefined();
  });

  it('renders Gate G1 Blocked badge and explanation when baseline is not qualified', () => {
    render(<QuantFalsificationPanel />);

    expect(screen.getAllByText('BLOCKED (Baseline Not Qualified)').length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getByText(
        'Machine Learning gate cannot be evaluated or promoted on negative baseline expectancy.',
      ),
    ).toBeDefined();
  });

  it('executes Strategy Isolation Matrix and updates rows with empirical verdicts', async () => {
    render(<QuantFalsificationPanel />);

    const runBtn = screen.getByRole('button', { name: /Run Strategy Isolation Matrix/i });
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(runStrategyMatrix).toHaveBeenCalled();
      const failedBadges = screen.getAllByText('FAILED');
      expect(failedBadges.length).toBeGreaterThanOrEqual(5);
    });
  });

  it('exports runStrategyMatrix and quantApi contract', () => {
    expect(typeof runStrategyMatrix).toBe('function');
    expect(quantApi).toBeDefined();
    expect(typeof quantApi.runStrategyMatrix).toBe('function');
    expect(typeof quantApi.runG2Robustness).toBe('function');
    expect(typeof quantApi.exportStrategyMatrix).toBe('function');
    expect(typeof quantApi.exportG0Trades).toBe('function');
  });

  it('exposes S8 strategy, G2 gate, and CSV export actions', () => {
    render(<QuantFalsificationPanel />);

    expect(screen.getByRole('button', { name: /Run Gate G2 Robustness/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /Export Matrix CSV/i })).toBeDefined();
    // S8 appears both in the matrix table and the hypothesis selector.
    expect(screen.getAllByText('S8').length).toBeGreaterThanOrEqual(1);
    // Confluence filter is selectable as a hypothesis.
    expect(screen.getByRole('option', { name: /S4\+S8/i })).toBeDefined();
  });
});
