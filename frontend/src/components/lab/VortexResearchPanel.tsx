'use client';

import { useState, useEffect, useCallback, useId } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileText,
  FlaskConical,
  Layers,
  Play,
  RefreshCw,
  TrendingUp,
} from 'lucide-react';
import { api } from '@/lib/api';
import type {
  VortexBacktestResult,
  VortexAblationReport,
  VortexExperimentSummary,
  VortexExperimentDetail,
} from '@/lib/api/vortex';

interface VortexResearchPanelProps {
  symbol?: string;
}

export function VortexResearchPanel({ symbol: defaultSymbol = 'SENSEX' }: VortexResearchPanelProps) {
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [slippageStress, setSlippageStress] = useState<number>(1.0);
  const [executionLag, setExecutionLag] = useState<number>(1);
  const [maxBars, setMaxBars] = useState<number>(1500);

  // Data states
  const [backtestResult, setBacktestResult] = useState<VortexBacktestResult | null>(null);
  const [ablationReport, setAblationReport] = useState<VortexAblationReport | null>(null);
  const [experiments, setExperiments] = useState<VortexExperimentSummary[]>([]);
  const [selectedExperiment, setSelectedExperiment] = useState<VortexExperimentDetail | null>(null);

  // Loading states
  const [runningBacktest, setRunningBacktest] = useState(false);
  const [runningAblation, setRunningAblation] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Active sub-tab
  const [viewMode, setViewMode] = useState<'backtest' | 'ablation' | 'reports'>('backtest');

  const gradientId = useId();

  // Load initial backtest and experiments
  const runBacktest = useCallback(async () => {
    setRunningBacktest(true);
    setError(null);
    try {
      const res = await api.runVortexBacktest({
        symbol,
        slippage_stress: slippageStress,
        execution_lag: executionLag,
        max_bars: maxBars,
        initial_capital: 500000.0,
      });
      setBacktestResult(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to execute event-driven backtest';
      setError(msg);
    } finally {
      setRunningBacktest(false);
    }
  }, [symbol, slippageStress, executionLag, maxBars]);

  const runAblation = useCallback(async () => {
    setRunningAblation(true);
    setError(null);
    try {
      const res = await api.getVortexAblation(symbol, maxBars);
      setAblationReport(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to run 9-stage component ablation study';
      setError(msg);
    } finally {
      setRunningAblation(false);
    }
  }, [symbol, maxBars]);

  const loadExperiments = useCallback(async () => {
    try {
      const list = await api.getVortexExperiments();
      setExperiments(list);
    } catch {
      // Non-fatal
    }
  }, []);

  const viewExperimentDetail = async (id: string) => {
    try {
      const detail = await api.getVortexExperiment(id);
      setSelectedExperiment(detail);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load report detail';
      setError(msg);
    }
  };

  useEffect(() => {
    void runBacktest();
    void loadExperiments();
  }, [runBacktest, loadExperiments]);

  return (
    <div className="flex flex-col gap-3.5 text-ink">
      {/* Research Controls Header */}
      <div className="card p-3 sm:p-4 bg-surface border border-border rounded-lg shadow-sm flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-accent-wash border border-accent-line text-accent">
            <FlaskConical className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-base tracking-tight text-ink">VORTEX-SNAP Research Engine</h3>
              <span className="badge b-info">
                §30–§35 Event Simulator
              </span>
            </div>
            <p className="text-xs text-ink-2 mt-0.5">
              Point-in-Time Event Simulator · Statutory Cost Friction · 9-Stage Ablation Matrix
            </p>
          </div>
        </div>

        {/* Sub-view Navigation */}
        <span className="seg" title="Research view mode">
          <button
            type="button"
            onClick={() => setViewMode('backtest')}
            className="seg-btn"
            data-active={viewMode === 'backtest'}
          >
            Simulator &amp; Performance
          </button>
          <button
            type="button"
            onClick={() => {
              setViewMode('ablation');
              if (!ablationReport) void runAblation();
            }}
            className="seg-btn"
            data-active={viewMode === 'ablation'}
          >
            9-Stage Ablation Matrix
          </button>
          <button
            type="button"
            onClick={() => setViewMode('reports')}
            className="seg-btn"
            data-active={viewMode === 'reports'}
          >
            Saved Reports ({experiments.length})
          </button>
        </span>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-down-wash border border-down-line text-down-strong text-xs font-medium flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Simulator Control Ribbon */}
      <div className="card p-3 bg-surface-subtle border border-border rounded-lg shadow-sm flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3 text-xs">
          {/* Symbol */}
          <div className="flex items-center gap-1.5">
            <span className="text-ink-2">Instrument:</span>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="bg-surface border border-border rounded px-2.5 py-1 text-ink font-mono focus:border-accent outline-none"
            >
              <option value="SENSEX">SENSEX</option>
              <option value="NIFTY">NIFTY</option>
              <option value="BANKNIFTY">BANKNIFTY</option>
            </select>
          </div>

          {/* Sample Bars */}
          <div className="flex items-center gap-1.5">
            <span className="text-ink-2">Bars:</span>
            <select
              value={maxBars}
              onChange={(e) => setMaxBars(Number(e.target.value))}
              className="bg-surface border border-border rounded px-2.5 py-1 text-ink font-mono focus:border-accent outline-none"
            >
              <option value={750}>750 (2 Days)</option>
              <option value={1500}>1,500 (4 Days)</option>
              <option value={3000}>3,000 (8 Days)</option>
            </select>
          </div>

          {/* Slippage Stress */}
          <div className="flex items-center gap-1.5">
            <span className="text-ink-2">Slippage Stress:</span>
            <select
              value={slippageStress}
              onChange={(e) => setSlippageStress(Number(e.target.value))}
              className="bg-surface border border-border rounded px-2.5 py-1 text-ink font-mono focus:border-accent outline-none"
            >
              <option value={1.0}>1.0x (Standard)</option>
              <option value={1.5}>1.5x (Elevated)</option>
              <option value={2.0}>2.0x (Severe)</option>
              <option value={3.0}>3.0x (Stress Test)</option>
            </select>
          </div>

          {/* Execution Lag */}
          <div className="flex items-center gap-1.5">
            <span className="text-ink-2">Lag:</span>
            <select
              value={executionLag}
              onChange={(e) => setExecutionLag(Number(e.target.value))}
              className="bg-surface border border-border rounded px-2.5 py-1 text-ink font-mono focus:border-accent outline-none"
            >
              <option value={0}>0 (Immediate Bar Close)</option>
              <option value={1}>1 (Next Bar Open - Conservative)</option>
            </select>
          </div>
        </div>

        <button
          type="button"
          onClick={() => void runBacktest()}
          disabled={runningBacktest}
          className="btn btn-primary flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold"
        >
          {runningBacktest ? (
            <>
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              Simulating…
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 fill-current" />
              Run Simulation
            </>
          )}
        </button>
      </div>

      {/* VIEW MODE 1: BACKTEST SIMULATION RESULTS */}
      {viewMode === 'backtest' && backtestResult && (
        <div className="flex flex-col gap-3.5">
          {backtestResult.data_source?.is_simulated && (
            <span
              className="self-start px-2 py-0.5 text-xs font-mono font-semibold rounded bg-warn-wash text-warn-strong border border-warn-line"
              title={backtestResult.data_source.note}
            >
              SIMULATED DATA
            </span>
          )}

          {/* Institutional KPI Summary Grid */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2.5 font-mono">
            {/* Net PnL */}
            <div className="card p-3 bg-surface border border-border rounded-lg shadow-sm flex flex-col justify-between hover:border-border-strong transition">
              <span className="text-[10px] uppercase font-bold text-ink-2 tracking-wider">Net Return</span>
              <span
                className={`text-xl font-bold mt-1 ${
                  backtestResult.metrics.net_pnl_rupees >= 0 ? 'text-up-strong' : 'text-down-strong'
                }`}
              >
                {backtestResult.metrics.net_pnl_rupees >= 0 ? '+' : ''}₹
                {backtestResult.metrics.net_pnl_rupees.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
              </span>
              <span className="text-[11px] text-ink-3 mt-1">
                Gross: ₹{backtestResult.metrics.gross_pnl_rupees.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
              </span>
            </div>

            {/* Win Rate */}
            <div className="card p-3 bg-surface border border-border rounded-lg shadow-sm flex flex-col justify-between hover:border-border-strong transition">
              <span className="text-[10px] uppercase font-bold text-ink-2 tracking-wider">Win Rate</span>
              <span className="text-xl font-bold text-ink mt-1">
                {backtestResult.metrics.win_rate_pct.toFixed(1)}%
              </span>
              <span className="text-[11px] text-ink-3 mt-1">
                {backtestResult.metrics.winning_trades}W / {backtestResult.metrics.losing_trades}L (
                {backtestResult.metrics.total_trades} total)
              </span>
            </div>

            {/* Profit Factor */}
            <div className="card p-3 bg-surface border border-border rounded-lg shadow-sm flex flex-col justify-between hover:border-border-strong transition">
              <span className="text-[10px] uppercase font-bold text-ink-2 tracking-wider">Profit Factor</span>
              <span className="text-xl font-bold text-accent mt-1">
                {backtestResult.metrics.profit_factor >= 999 ? '∞' : backtestResult.metrics.profit_factor.toFixed(2)}
              </span>
              <span className="text-[11px] text-ink-3 mt-1">
                Win/Loss Ratio: {backtestResult.metrics.win_loss_ratio ? backtestResult.metrics.win_loss_ratio.toFixed(2) : '—'}
              </span>
            </div>

            {/* Annualized Sharpe */}
            <div className="card p-3 bg-surface border border-border rounded-lg shadow-sm flex flex-col justify-between hover:border-border-strong transition">
              <span className="text-[10px] uppercase font-bold text-ink-2 tracking-wider">Annualized Sharpe</span>
              <span className="text-xl font-bold text-ink mt-1">
                {backtestResult.metrics.annualized_sharpe.toFixed(2)}
              </span>
              <span className="text-[11px] text-ink-3 mt-1">
                Sortino: {backtestResult.metrics.annualized_sortino ? backtestResult.metrics.annualized_sortino.toFixed(2) : '—'}
              </span>
            </div>

            {/* Max Drawdown */}
            <div className="card p-3 bg-surface border border-border rounded-lg shadow-sm flex flex-col justify-between hover:border-border-strong transition">
              <span className="text-[10px] uppercase font-bold text-ink-2 tracking-wider">Max Drawdown</span>
              <span className="text-xl font-bold text-down-strong mt-1">
                -{backtestResult.metrics.max_drawdown_pct.toFixed(1)}%
              </span>
              <span className="text-[11px] text-ink-3 mt-1">
                ₹{backtestResult.metrics.max_drawdown_rupees.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
              </span>
            </div>

            {/* Cost Drag */}
            <div className="card p-3 bg-surface border border-border rounded-lg shadow-sm flex flex-col justify-between hover:border-border-strong transition">
              <span className="text-[10px] uppercase font-bold text-ink-2 tracking-wider">Cost Drag</span>
              <span className="text-xl font-bold text-warn-strong mt-1">
                {backtestResult.metrics.cost_drag_pct.toFixed(1)}%
              </span>
              <span className="text-[11px] text-ink-3 mt-1">
                Friction: ₹{backtestResult.metrics.total_friction_rupees.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
              </span>
            </div>
          </div>

          {/* Equity Curve SVG Chart */}
          {backtestResult.equity_curve && backtestResult.equity_curve.length > 1 && (
            <div className="card p-4 bg-surface border border-border rounded-lg shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-semibold uppercase tracking-wider text-ink-2 flex items-center gap-1.5">
                  <TrendingUp className="w-4 h-4 text-accent" />
                  Simulated Equity Curve (INR)
                </span>
                <span className="text-xs text-ink-3 font-mono">
                  Initial: ₹5,00,000 &rarr; Final: ₹
                  {backtestResult.equity_curve[backtestResult.equity_curve.length - 1].toLocaleString('en-IN', {
                    maximumFractionDigits: 0,
                  })}
                </span>
              </div>

              {/* Render Responsive SVG Sparkline/Equity Curve */}
              <div className="w-full h-44 relative bg-surface-subtle rounded-lg p-2 border border-border">
                {(() => {
                  const curve = backtestResult.equity_curve;
                  const min = Math.min(...curve);
                  const max = Math.max(...curve);
                  const range = max - min || 1;
                  const width = 800;
                  const height = 150;

                  const points = curve
                    .map((val, idx) => {
                      const x = (idx / (curve.length - 1)) * width;
                      const y = height - ((val - min) / range) * (height - 20) - 10;
                      return `${x.toFixed(1)},${y.toFixed(1)}`;
                    })
                    .join(' ');

                  const areaPoints = `0,${height} ${points} ${width},${height}`;

                  return (
                    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full overflow-visible">
                      <defs>
                        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="var(--ds-accent)" stopOpacity="0.2" />
                          <stop offset="100%" stopColor="var(--ds-accent)" stopOpacity="0.0" />
                        </linearGradient>
                      </defs>
                      <polygon points={areaPoints} fill={`url(#${gradientId})`} />
                      <polyline fill="none" stroke="var(--ds-accent)" strokeWidth="2" points={points} />
                    </svg>
                  );
                })()}
              </div>
            </div>
          )}

          {/* Exit Attribution & Recent Trades Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            {/* Exit Attribution */}
            <div className="card p-4 bg-surface border border-border rounded-lg shadow-sm">
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-2 flex items-center gap-1.5 mb-3">
                <Layers className="w-4 h-4 text-accent" />
                Exit Reason Attribution (§20–§23)
              </span>

              <div className="flex flex-col gap-2 font-mono text-xs">
                {Object.entries(backtestResult.exit_breakdown).map(([reason, count]) => {
                  const total = backtestResult.metrics.total_trades || 1;
                  const pct = ((count / total) * 100).toFixed(0);
                  return (
                    <div key={reason} className="p-2 rounded-md bg-surface-subtle border border-border">
                      <div className="flex justify-between text-ink-2">
                        <span>{reason}</span>
                        <span className="font-bold text-ink">
                          {count} ({pct}%)
                        </span>
                      </div>
                      <div className="w-full bg-inset rounded-full h-1 mt-1.5 overflow-hidden">
                        <div
                          className={`h-1 rounded-full ${
                            reason.includes('TARGET')
                              ? 'bg-up-strong'
                              : reason.includes('STOP')
                              ? 'bg-down-strong'
                              : 'bg-warn-strong'
                          }`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Recent Executed Trades */}
            <div className="card p-4 bg-surface border border-border rounded-lg shadow-sm lg:col-span-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-2 flex items-center gap-1.5 mb-3">
                <Clock className="w-4 h-4 text-accent" />
                Recent Simulated Trades (Last 50)
              </span>

              <div className="tbl-wrap max-h-72 overflow-y-auto">
                <table className="tbl w-full text-left text-xs font-mono">
                  <thead className="sticky top-0 bg-surface-subtle border-b border-border text-[11px] text-ink-3 uppercase">
                    <tr>
                      <th className="pb-2">Direction</th>
                      <th className="pb-2">Entry</th>
                      <th className="pb-2">Exit</th>
                      <th className="pb-2">Holding</th>
                      <th className="pb-2">Exit Reason</th>
                      <th className="pb-2 text-right">Net PnL</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-subtle">
                    {backtestResult.recent_trades.length > 0 ? (
                      backtestResult.recent_trades.map((tr) => (
                        <tr key={tr.trade_id} className="hover:bg-hover transition">
                          <td className="py-2">
                            <span
                              className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                tr.direction.includes('CALL')
                                  ? 'bg-up-wash text-up-strong border border-up-line'
                                  : 'bg-down-wash text-down-strong border border-down-line'
                              }`}
                            >
                              {tr.direction}
                            </span>
                          </td>
                          <td className="py-2 text-ink">₹{tr.entry_price.toFixed(1)}</td>
                          <td className="py-2 text-ink">₹{tr.exit_price.toFixed(1)}</td>
                          <td className="py-2 text-ink-3">{tr.holding_minutes.toFixed(0)}m</td>
                          <td className="py-2 text-ink-2 text-[11px]">{tr.exit_reason}</td>
                          <td
                            className={`py-2 text-right font-bold ${
                              tr.net_pnl_rupees >= 0 ? 'text-up-strong' : 'text-down-strong'
                            }`}
                          >
                            {tr.net_pnl_rupees >= 0 ? '+' : ''}₹{tr.net_pnl_rupees.toFixed(1)}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={6} className="text-center py-6 text-ink-3 italic">
                          No executed trades generated in this window. Disciplined NO-TRADE filters preserved capital.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* VIEW MODE 2: 9-STAGE COMPONENT ABLATION MATRIX */}
      {viewMode === 'ablation' && (
        <div className="flex flex-col gap-3.5">
          {/* Primary Hypothesis Verification Card */}
          {ablationReport?.data_source?.is_simulated && (
            <span
              className="self-start px-2 py-0.5 text-xs font-mono font-semibold rounded bg-warn-wash text-warn-strong border border-warn-line"
              title={ablationReport.data_source.note}
            >
              SIMULATED DATA
            </span>
          )}
          {ablationReport && (
            <div
              className={`p-4 rounded-lg border flex flex-col gap-1 ${
                ablationReport.primary_hypothesis_supported
                  ? 'bg-up-wash border-up-line'
                  : 'bg-warn-wash border-warn-line'
              }`}
            >
              <div className="flex items-center gap-2 mb-0.5">
                {ablationReport.primary_hypothesis_supported ? (
                  <CheckCircle2 className="w-5 h-5 text-up-strong shrink-0" />
                ) : (
                  <AlertTriangle className="w-5 h-5 text-warn-strong shrink-0" />
                )}
                <h4 className="text-sm font-bold text-ink">
                  Primary Hypothesis Evaluation: Translation Ratio Engine (§8)
                </h4>
              </div>
              <p className="text-xs text-ink-2 leading-relaxed">
                {ablationReport.primary_hypothesis_supported
                  ? `Hypothesis VALIDATED: Incorporating Translation Ratio yields positive marginal Sharpe ratio delta (+${ablationReport.primary_hypothesis_delta_sharpe.toFixed(
                      2
                    )}), confirming that directional acceptance vs absorption delivers predictive short-horizon alpha.`
                  : `Hypothesis INCONCLUSIVE: Translation Ratio marginal Sharpe delta (${ablationReport.primary_hypothesis_delta_sharpe.toFixed(
                      2
                    )}) did not meet statistical threshold on this specific sample slice.`}
              </p>
            </div>
          )}

          {/* Ablation Comparison Table */}
          <div className="card p-4 bg-surface border border-border rounded-lg shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-2 flex items-center gap-1.5">
                <Layers className="w-4 h-4 text-accent" />
                9-Stage Controlled Component Matrix (§32)
              </span>
              <button
                type="button"
                onClick={() => void runAblation()}
                disabled={runningAblation}
                className="btn btn-ic text-xs text-ink-2 hover:text-ink"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${runningAblation ? 'animate-spin' : ''}`} />
                Re-run Ablation Study
              </button>
            </div>

            <div className="tbl-wrap">
              <table className="tbl w-full text-left text-xs font-mono">
                <thead className="bg-surface-subtle border-b border-border text-[11px] text-ink-3 uppercase">
                  <tr>
                    <th className="pb-2.5">Stage</th>
                    <th className="pb-2.5">Configuration</th>
                    <th className="pb-2.5 text-center">Trades</th>
                    <th className="pb-2.5 text-center">Win Rate</th>
                    <th className="pb-2.5 text-center">Profit Factor</th>
                    <th className="pb-2.5 text-center">Annualized Sharpe</th>
                    <th className="pb-2.5 text-center">Max Drawdown</th>
                    <th className="pb-2.5 text-center">dSharpe vs Baseline</th>
                    <th className="pb-2.5 text-right">Marginal Sharpe</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {ablationReport?.stages.map((st) => (
                    <tr
                      key={st.stage}
                      className={`hover:bg-hover transition ${
                        st.stage === 'C' ? 'bg-accent-wash/40 font-semibold' : ''
                      }`}
                    >
                      <td className="py-2.5">
                        <span className="px-2 py-0.5 rounded bg-inset text-accent border border-border font-bold">
                          Config {st.stage}
                        </span>
                      </td>
                      <td className="py-2.5 text-ink">
                        {st.config_name}
                        <span className="block text-[10px] text-ink-3 font-sans">{st.description}</span>
                      </td>
                      <td className="py-2.5 text-center text-ink-2">{st.trades}</td>
                      <td className="py-2.5 text-center text-ink">{st.win_rate_pct.toFixed(1)}%</td>
                      <td className="py-2.5 text-center text-accent font-bold">
                        {st.profit_factor >= 999 ? '∞' : st.profit_factor.toFixed(2)}
                      </td>
                      <td className="py-2.5 text-center font-bold text-ink">{st.annualized_sharpe.toFixed(2)}</td>
                      <td className="py-2.5 text-center text-down-strong">-{st.max_dd_pct.toFixed(1)}%</td>
                      <td
                        className={`py-2.5 text-center font-bold ${
                          st.delta_sharpe >= 0 ? 'text-up-strong' : 'text-down-strong'
                        }`}
                      >
                        {st.delta_sharpe >= 0 ? '+' : ''}
                        {st.delta_sharpe.toFixed(2)}
                      </td>
                      <td
                        className={`py-2.5 text-right font-bold ${
                          st.marginal_sharpe >= 0 ? 'text-up-strong' : 'text-down-strong'
                        }`}
                      >
                        {st.marginal_sharpe >= 0 ? '+' : ''}
                        {st.marginal_sharpe.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* VIEW MODE 3: PRE-COMPUTED EXPERIMENT REPORTS */}
      {viewMode === 'reports' && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Reports List */}
          <div className="card p-4 bg-surface border border-border rounded-lg shadow-sm">
            <span className="text-xs font-semibold uppercase tracking-wider text-ink-2 flex items-center gap-1.5 mb-3">
              <FileText className="w-4 h-4 text-accent" />
              Saved Research Reports (§50)
            </span>

            <div className="flex flex-col gap-2">
              {experiments.map((exp) => (
                <button
                  key={exp.id}
                  type="button"
                  onClick={() => void viewExperimentDetail(exp.id)}
                  className={`p-3 rounded-lg text-left transition border ${
                    selectedExperiment?.id === exp.id
                      ? 'bg-accent-wash border-accent-line'
                      : 'bg-surface-subtle border-border hover:bg-hover'
                  }`}
                >
                  <div className="flex justify-between items-center">
                    <span className="text-sm font-semibold text-ink font-mono">{exp.instrument}</span>
                    <span className="text-[10px] text-ink-3">{exp.generated_at.slice(0, 10)}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 mt-2 text-xs font-mono text-ink-2">
                    <div>
                      Trades: <strong className="text-ink">{exp.metrics.total_trades}</strong>
                    </div>
                    <div>
                      Win Rate: <strong className="text-ink">{exp.metrics.win_rate_pct.toFixed(1)}%</strong>
                    </div>
                    <div>
                      Sharpe: <strong className="text-accent">{exp.metrics.annualized_sharpe.toFixed(2)}</strong>
                    </div>
                    <div>
                      Profit Factor: <strong className="text-accent">{exp.metrics.profit_factor.toFixed(2)}</strong>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Report Markdown Viewer */}
          <div className="card p-4 bg-surface border border-border rounded-lg shadow-sm md:col-span-2">
            {selectedExperiment ? (
              <div>
                <div className="flex items-center justify-between pb-3 border-b border-border mb-3">
                  <span className="text-sm font-semibold text-ink font-mono">
                    {selectedExperiment.id}.md
                  </span>
                  <span className="text-xs text-ink-3">Publication-Ready Research Dossier</span>
                </div>
                <div className="p-3.5 rounded-md bg-surface-subtle border border-border text-xs leading-relaxed text-ink font-mono whitespace-pre-wrap max-h-96 overflow-y-auto">
                  {selectedExperiment.markdown}
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-20 text-ink-3">
                <FileText className="w-10 h-10 stroke-1 mb-2 text-ink-4" />
                <p className="text-sm">Select an experiment report from the left panel to read findings.</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
