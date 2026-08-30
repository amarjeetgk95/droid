'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { BacktestPayload, BacktestPreset, BacktestResult } from '@/lib/types';
import { BacktestConfigForm } from '@/components/backtesting/BacktestConfigForm';
import { PerformanceMetrics } from '@/components/backtesting/PerformanceMetrics';
import { EquityCurveChart } from '@/components/backtesting/EquityCurveChart';
import { MonthlyReturnsMatrix } from '@/components/backtesting/MonthlyReturnsMatrix';
import { TradeLogTable } from '@/components/backtesting/TradeLogTable';
import { Activity } from 'lucide-react';

export default function BacktestingPage() {
  const [payload, setPayload] = useState<BacktestPayload>({
    strategy_id: 'short_straddle',
    underlying: 'NIFTY',
    initial_capital: 500000,
    num_days: 60,
    stop_loss_pct: 25.0,
    target_pct: 50.0,
    slippage_pct: 0.001,
    include_costs: true,
  });

  const [presets, setPresets] = useState<BacktestPreset[]>([]);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Initial load presets & run baseline backtest
  useEffect(() => {
    let isMounted = true;

    const init = async () => {
      try {
        const presetsRes = await api.getBacktestPresets();
        if (isMounted) {
          setPresets(presetsRes.data);
          const runRes = await api.runBacktest({
            strategy_id: 'short_straddle',
            underlying: 'NIFTY',
            initial_capital: 500000,
            num_days: 60,
            stop_loss_pct: 25.0,
            target_pct: 50.0,
            slippage_pct: 0.001,
            include_costs: true,
          });
          if (isMounted) {
            setResult(runRes.data);
            setError(null);
          }
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to initialize backtest engine');
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    init();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleRunBacktest = () => {
    setLoading(true);
    api
      .runBacktest(payload)
      .then((res) => {
        setResult(res.data);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Backtest execution failed'))
      .finally(() => setLoading(false));
  };

  return (
    <div className="space-y-4">
      {/* Configuration Form */}
      <BacktestConfigForm
        payload={payload}
        presets={presets}
        onChange={(upd) => setPayload((prev) => ({ ...prev, ...upd }))}
        onRun={handleRunBacktest}
        loading={loading}
      />

      {/* Main Results Display */}
      {error ? (
        <div className="p-8 text-center bg-card border border-destructive/20 rounded-xl text-destructive">
          <p className="font-semibold text-sm">Error executing backtest simulation</p>
          <p className="text-xs mt-1 opacity-80">{error}</p>
        </div>
      ) : loading && !result ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center text-muted-foreground animate-pulse space-y-2">
          <Activity className="w-8 h-8 text-primary mx-auto animate-bounce" />
          <p className="font-semibold text-sm">Simulating multi-period options orders & execution fills...</p>
          <p className="text-xs text-muted-foreground">
            Applying STT, NSE charges, GST, SEBI fees, and adverse bid-ask slippage.
          </p>
        </div>
      ) : result ? (
        <div className="space-y-4">
          {/* Performance Scorecard */}
          <PerformanceMetrics result={result} />

          {/* Equity & Drawdown Curve */}
          <EquityCurveChart
            equityCurve={result.equity_curve}
            initialCapital={result.initial_capital}
          />

          {/* Monthly P&L Breakdown */}
          <MonthlyReturnsMatrix monthlyPnl={result.monthly_pnl} />

          {/* Executed Trade Log Table */}
          <TradeLogTable trades={result.trades} />
        </div>
      ) : null}
    </div>
  );
}
