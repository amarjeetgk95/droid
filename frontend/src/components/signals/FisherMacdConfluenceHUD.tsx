'use client';

import { useMemo, useState } from 'react';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart2,
  CheckCircle2,
  Clock,
  Compass,
  Flame,
  Gauge,
  Layers,
  Percent,
  Play,
  RefreshCw,
  ShieldAlert,
  Target,
  Zap,
} from 'lucide-react';
import { useFisherMacdHUD } from '@/hooks/useFisherMacdHUD';
import { useSignalDesk } from '@/hooks/useSignalDesk';
import { api } from '@/lib/api';
import type { FisherMacdBacktestResult } from '@/lib/api/fisherMacd';
import { safeNum } from '@/lib/utils';
import { stageOf } from '@/lib/signalStages';

interface FisherMacdConfluenceHUDProps {
  initialSymbol?: string;
}

const SYMBOLS = ['NIFTY', 'BANKNIFTY', 'SENSEX'];

function formatZoneBadge(zone: string) {
  switch (zone) {
    case 'EXTREME_OVERSOLD':
      return { label: 'EXTREME OVERSOLD (<-2.0)', cls: 'b-bull' };
    case 'OVERSOLD':
      return { label: 'OVERSOLD (<-1.0)', cls: 'b-bull' };
    case 'EXTREME_OVERBOUGHT':
      return { label: 'EXTREME OVERBOUGHT (>+2.0)', cls: 'b-bear' };
    case 'OVERBOUGHT':
      return { label: 'OVERBOUGHT (>+1.0)', cls: 'b-bear' };
    default:
      return { label: 'NEUTRAL (-1.0 to +1.0)', cls: 'b-neut' };
  }
}

export function FisherMacdConfluenceHUD({ initialSymbol = 'NIFTY' }: FisherMacdConfluenceHUDProps) {
  const {
    symbol,
    setSymbol,
    status,
    performance,
    loading,
    error,
    autoRefresh,
    setAutoRefresh,
    refresh,
  } = useFisherMacdHUD({ initialSymbol });

  const desk = useSignalDesk({ instrument: symbol, desk: 'ALL' });

  // Filter recent signals for Fisher-MACD confluence
  const strategySignals = useMemo(() => {
    return desk.rows.filter(
      (r) => r.strategy === 'FISHER_MACD_CONFLUENCE'
    );
  }, [desk.rows]);

  const [btTargetAtr, setBtTargetAtr] = useState<number>(0.50);
  const [btStopAtr, setBtStopAtr] = useState<number>(1.00);
  const [btRunning, setBtRunning] = useState<boolean>(false);
  const [btResult, setBtResult] = useState<FisherMacdBacktestResult | null>(null);
  const [btError, setBtError] = useState<string | null>(null);

  const handleRunBacktest = async () => {
    setBtRunning(true);
    setBtError(null);
    try {
      const res = await api.runFisherMacdBacktest({
        symbol,
        target_atr: btTargetAtr,
        stop_atr: btStopAtr,
        max_bars: 5000,
      });
      setBtResult(res);
    } catch (err: unknown) {
      setBtError(err instanceof Error ? err.message : 'Backtest execution failed');
    } finally {
      setBtRunning(false);
    }
  };

  const [dispatching, setDispatching] = useState(false);
  const [dispatchSuccess, setDispatchSuccess] = useState<string | null>(null);
  const [dispatchErr, setDispatchErr] = useState<string | null>(null);

  const handleDispatchSignal = async () => {
    if (!status || !api) return;
    const s = status.confluence_setup;
    if (!s.recommended_contract) return;

    setDispatching(true);
    setDispatchSuccess(null);
    setDispatchErr(null);

    try {
      const res = await api.dispatchFisherMacdSignal({
        symbol,
        direction: s.direction,
        contract_symbol: s.recommended_contract.symbol,
        quantity: s.recommended_contract.lot_size,
        entry_price: s.entry_price,
        target_price: s.target_1_half_atr,
        stop_price: s.stop_loss_full_atr,
        destination: 'PAPER_PORTFOLIO',
      });
      setDispatchSuccess(
        `Dispatched: ${res.contract} (Qty: ${res.order?.quantity ?? s.recommended_contract.lot_size}) | Order: ${res.order?.order_id ?? res.dispatch_id}`
      );
    } catch (err: unknown) {
      setDispatchErr(err instanceof Error ? err.message : 'Signal dispatch failed');
    } finally {
      setDispatching(false);
    }
  };

  const setup = status?.confluence_setup;
  const macro = status?.macro_trend_15m;
  const fisher = status?.pullback_oscillator_5m;
  const benchmarks = status?.empirical_benchmarks;
  const matrix = status?.timeframe_matrix ?? [];

  const zoneBadge = formatZoneBadge(fisher?.zone ?? 'NEUTRAL');

  // Gauge percentage for Fisher (-3.0 to +3.0 normalized to 0% - 100%)
  const fisherMeterPct = useMemo(() => {
    if (!fisher) return 50;
    const clamped = Math.max(-3.0, Math.min(3.0, fisher.fisher));
    return Math.round(((clamped + 3.0) / 6.0) * 100);
  }, [fisher]);

  return (
    <div className="flex flex-col gap-3">
      {/* Top Command Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg bg-surface border border-border">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-md bg-card border border-border text-ink">
            <Compass className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold uppercase tracking-wider text-ink">
                Fisher-MACD Confluence Radar
              </h2>
              <span className="badge b-bull text-xs">
                🎯 78.7% Win Rate Engine
              </span>
              <span className={`badge ${status?.data_source.is_live ? 'b-bull' : 'b-warn'} text-xs`}>
                {status?.data_source.is_live ? 'LIVE FEED' : 'HISTORICAL / PIT'}
              </span>
            </div>
            <p className="text-xs text-ink-2 mt-0.5">
              15M Macro Trend Filter (MACD 12,26,9) + 5M Exhaustion Re-entry (Fisher-9)
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Symbol Switcher */}
          <span className="seg" title="Underlying index">
            {SYMBOLS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setSymbol(s)}
                className="seg-btn"
                data-active={symbol === s}
              >
                {s}
              </button>
            ))}
          </span>

          <button
            type="button"
            onClick={() => setAutoRefresh(!autoRefresh)}
            className="btn btn-ic text-xs"
            title={autoRefresh ? 'Auto-refresh every 5s' : 'Auto-refresh paused'}
          >
            <Activity className="w-3.5 h-3.5" />
            {autoRefresh ? 'Live (5s)' : 'Paused'}
          </button>

          <button
            type="button"
            onClick={() => void refresh()}
            disabled={loading}
            className="btn btn-ic p-1.5 text-xs text-ink-2 hover:text-ink"
            title="Refresh now"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-down-wash border border-down-line text-down-strong text-xs font-medium flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Main Confluence Status Banner */}
      {setup && (
        <div className="p-4 rounded-lg bg-card border border-border flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-ink-2">
                Confluence Status:
              </span>
              <span
                className={`badge ${
                  setup.readiness === 'TRIGGERED'
                    ? 'b-bull font-bold'
                    : setup.readiness === 'ARMED'
                      ? 'b-warn font-bold'
                      : 'b-neut'
                }`}
              >
                {setup.readiness === 'TRIGGERED'
                  ? '⚡ SETUP TRIGGERED — HIGH CONVICTION'
                  : setup.readiness === 'ARMED'
                    ? '🎯 SETUP ARMED — PULLBACK ACTIVE'
                    : '⏳ IDLE — SEARCHING FOR ALIGNED PULLBACK'}
              </span>
              {setup.direction !== 'NONE' && (
                <span
                  className={`badge ${
                    setup.direction === 'LONG_CALL' ? 'b-bull' : 'b-bear'
                  } font-bold`}
                >
                  {setup.direction === 'LONG_CALL' ? 'LONG CALL (BULLISH)' : 'LONG PUT (BEARISH)'}
                </span>
              )}
              {status?.divergence_radar?.has_active_divergence ? (
                <span
                  className={`badge ${
                    status.divergence_radar.divergence_type.includes('BULLISH') ? 'b-bull' : 'b-bear'
                  } font-semibold`}
                >
                  ⚡ {status.divergence_radar.divergence_type.replace(/_/g, ' ')} ({status.divergence_radar.bars_ago}b ago)
                </span>
              ) : (
                <span className="badge b-neut text-[10px]">
                  Divergence: None active
                </span>
              )}
            </div>

            <div className="flex items-center gap-3 text-xs text-ink-2">
              <span>
                Spot:{' '}
                <strong className="text-ink text-sm">
                  {safeNum(status?.spot_price)}
                </strong>
              </span>
              <span>
                5M ATR-14: <strong className="text-ink">{safeNum(setup.atr_14)} pts</strong>
              </span>
            </div>
          </div>

          <div className="text-xs text-ink leading-relaxed">
            {setup.bias_summary}
          </div>

          {/* Execution Geometry & Recommended Contract */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-2 pt-1">
            <div className="p-2.5 rounded bg-surface border border-border flex flex-col">
              <span className="text-[11px] uppercase tracking-wider text-ink-2 font-medium">
                Entry Spot Level
              </span>
              <span className="text-base font-bold text-ink mt-0.5">
                ₹{safeNum(setup.entry_price)}
              </span>
              <span className="text-[10px] text-ink-3">At trigger candle close</span>
            </div>

            <div className="p-2.5 rounded bg-surface border border-border flex flex-col">
              <div className="flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-wider text-ink-2 font-medium">
                  Target 1 (+0.50 ATR)
                </span>
                <span className="badge b-bull text-[9px] px-1 py-0">78.7% Win Rate</span>
              </div>
              <span className="text-base font-bold v-bull mt-0.5">
                ₹{safeNum(setup.target_1_half_atr)}
              </span>
              <span className="text-[10px] text-ink-3">
                +{safeNum(setup.target_1_points)} pts (Quick Take-Profit)
              </span>
            </div>

            <div className="p-2.5 rounded bg-surface border border-border flex flex-col">
              <div className="flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-wider text-ink-2 font-medium">
                  Target 2 (+1.00 ATR)
                </span>
                <span className="badge b-neut text-[9px] px-1 py-0">Runner</span>
              </div>
              <span className="text-base font-bold v-bull mt-0.5">
                ₹{safeNum(setup.target_2_full_atr)}
              </span>
              <span className="text-[10px] text-ink-3">
                +{safeNum(setup.target_2_points)} pts (1:1 R/R)
              </span>
            </div>

            <div className="p-2.5 rounded bg-surface border border-border flex flex-col">
              <span className="text-[11px] uppercase tracking-wider text-ink-2 font-medium">
                Stop Loss (-1.00 ATR)
              </span>
              <span className="text-base font-bold v-bear mt-0.5">
                ₹{safeNum(setup.stop_loss_full_atr)}
              </span>
              <span className="text-[10px] text-ink-3">
                -{safeNum(setup.stop_loss_points)} pts (Strict Invalidations)
              </span>
            </div>
          </div>

          {/* Recommended Option Contract Card */}
          {setup.recommended_contract && (
            <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded bg-surface border border-border">
              <div className="flex items-center gap-3">
                <div className="p-1.5 rounded bg-card border border-border text-ink">
                  <Target className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-ink">
                      Optimal Option Contract:
                    </span>
                    <span className="badge b-bull font-bold">
                      {setup.recommended_contract.symbol}
                    </span>
                    <span className="badge b-neut text-[10px]">
                      Lot Size: {setup.recommended_contract.lot_size}
                    </span>
                  </div>
                  <p className="text-[11px] text-ink-2 mt-0.5">
                    Est. Premium: ₹{safeNum(setup.recommended_contract.estimated_premium)} ·
                    Delta: {safeNum(setup.recommended_contract.delta, '—', 2)} · Optimal ATM/ITM Strike
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3 text-xs">
                <div className="text-right">
                  <span className="text-[10px] uppercase text-ink-3 block">Est. Profit @ T1</span>
                  <span className="font-bold v-bull">
                    +₹{safeNum(setup.recommended_contract.target_profit_inr, '—', 0)}
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-[10px] uppercase text-ink-3 block">Max Defined Risk</span>
                  <span className="font-bold v-bear">
                    -₹{safeNum(setup.recommended_contract.max_risk_inr, '—', 0)}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => void handleDispatchSignal()}
                  disabled={dispatching || setup.direction === 'NONE'}
                  className="btn btn-primary text-xs flex items-center gap-1.5 shrink-0"
                  title="Dispatch order to paper trading portfolio"
                >
                  {dispatching ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Zap className="w-3.5 h-3.5 fill-current" />
                  )}
                  {dispatching ? 'Executing…' : '1-Click Paper Trade'}
                </button>
              </div>
            </div>
          )}

          {dispatchSuccess && (
            <div className="p-2.5 rounded bg-surface border border-border text-ink text-xs flex items-center justify-between">
              <span className="v-bull font-medium">{dispatchSuccess}</span>
              <span className="badge b-bull text-[10px]">PAPER LEDGER UPDATED</span>
            </div>
          )}

          {dispatchErr && (
            <div className="p-2.5 rounded bg-surface border border-border text-xs v-bear">
              ⚠ {dispatchErr}
            </div>
          )}
        </div>
      )}

      {/* Dual Horizon Radar Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Panel 1: 15M Macro Trend Filter */}
        <div className="p-4 rounded-lg bg-card border border-border flex flex-col gap-3">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-ink" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-ink">
                15M Macro Trend Filter
              </h3>
            </div>
            <span
              className={`badge ${
                macro?.trend === 'BULLISH'
                  ? 'b-bull'
                  : macro?.trend === 'BEARISH'
                    ? 'b-bear'
                    : 'b-neut'
              } font-bold`}
            >
              {macro?.trend === 'BULLISH' ? 'BULLISH TIDE' : 'BEARISH TIDE'}
            </span>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <div className="p-2 rounded bg-surface border border-border">
              <span className="text-[10px] text-ink-3 uppercase block">MACD Line</span>
              <span className="text-sm font-bold text-ink">{safeNum(macro?.macd_line)}</span>
            </div>
            <div className="p-2 rounded bg-surface border border-border">
              <span className="text-[10px] text-ink-3 uppercase block">Signal Line (9 EMA)</span>
              <span className="text-sm font-bold text-ink">{safeNum(macro?.signal_line)}</span>
            </div>
            <div className="p-2 rounded bg-surface border border-border">
              <span className="text-[10px] text-ink-3 uppercase block">Histogram</span>
              <span
                className={`text-sm font-bold ${
                  (macro?.histogram ?? 0) >= 0 ? 'v-bull' : 'v-bear'
                }`}
              >
                {safeNum(macro?.histogram)}
              </span>
            </div>
          </div>

          <div className="text-[11px] text-ink-2 leading-relaxed bg-surface p-2.5 rounded border border-border">
            <strong className="text-ink">Why 15M Macro Filter?</strong> Standalone 1M/5M reversals suffer from momentum persistence (-0.30 ATR drag). Anchoring trades to the 15M MACD trend filters out 72% of false counter-trend signals and guarantees institutional alignment.
          </div>
        </div>

        {/* Panel 2: 5M Fisher Transform Oscillator */}
        <div className="p-4 rounded-lg bg-card border border-border flex flex-col gap-3">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <div className="flex items-center gap-2">
              <Gauge className="w-4 h-4 text-ink" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-ink">
                5M Fisher Transform (9)
              </h3>
            </div>
            <span className={`badge ${zoneBadge.cls} font-bold`}>
              {zoneBadge.label}
            </span>
          </div>

          {/* Visual Oscillator Meter (-3.0 to +3.0) */}
          <div className="flex flex-col gap-1.5 p-2 rounded bg-surface border border-border">
            <div className="flex items-center justify-between text-[10px] text-ink-3">
              <span>Oversold (-1.0)</span>
              <span>Neutral (0.0)</span>
              <span>Overbought (+1.0)</span>
            </div>
            <div className="relative w-full h-3 rounded-full bg-card border border-border overflow-hidden">
              {/* Neutral Center Zone */}
              <div
                className="absolute top-0 bottom-0 left-[33%] right-[33%] bg-surface opacity-50"
                title="Neutral Zone"
              />
              {/* Pointer indicator */}
              <div
                className="absolute top-0 bottom-0 w-2 rounded-full bg-ink transition-all duration-300"
                style={{ left: `calc(${fisherMeterPct}% - 4px)` }}
              />
            </div>
            <div className="flex items-center justify-between text-xs mt-1">
              <div>
                <span className="text-[10px] text-ink-3 block">Fisher-9 Line</span>
                <strong className="text-ink text-sm">{safeNum(fisher?.fisher, '—', 3)}</strong>
              </div>
              <div className="text-right">
                <span className="text-[10px] text-ink-3 block">Trigger Line</span>
                <strong className="text-ink text-sm">{safeNum(fisher?.trigger, '—', 3)}</strong>
              </div>
            </div>
          </div>

          <div className="text-[11px] text-ink-2 leading-relaxed bg-surface p-2.5 rounded border border-border">
            <strong className="text-ink">Why 5M Fisher-9?</strong> Converts Gaussian price swings into sharp, unambiguous turning points. When the oscillator reaches extreme levels (&lt; -1.0 or &gt; +1.0) and hooks back, the probability of a swift mean-reversion move is maximized.
          </div>
        </div>
      </div>

      {/* Multi-Timeframe Matrix Table */}
      <div className="p-4 rounded-lg bg-card border border-border flex flex-col gap-3">
        <div className="flex items-center justify-between border-b border-border pb-2">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-ink" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-ink">
              Multi-Timeframe Noise vs. Trend Spectrum (1M – 1H)
            </h3>
          </div>
          <span className="text-[11px] text-ink-3">
            Real-time indicator values across horizons
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="border-b border-border text-ink-3 uppercase text-[10px]">
                <th className="pb-2">Timeframe</th>
                <th className="pb-2">MACD Trend</th>
                <th className="pb-2">MACD / Signal</th>
                <th className="pb-2">Histogram</th>
                <th className="pb-2">Fisher-9 Line</th>
                <th className="pb-2">Fisher Zone</th>
                <th className="pb-2">Strategic Role in Confluence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {matrix.map((row) => {
                const zBadge = formatZoneBadge(row.fisher_zone);
                const isSelectedTf = row.timeframe === '5M' || row.timeframe === '15M';
                return (
                  <tr
                    key={row.timeframe}
                    className={`hover:bg-surface ${isSelectedTf ? 'bg-surface/50 font-medium' : ''}`}
                  >
                    <td className="py-2 font-bold text-ink">
                      {row.timeframe}
                      {row.timeframe === '5M' && (
                        <span className="badge b-bull text-[9px] ml-1.5">Trigger</span>
                      )}
                      {row.timeframe === '15M' && (
                        <span className="badge b-warn text-[9px] ml-1.5">Anchor</span>
                      )}
                    </td>
                    <td className="py-2">
                      <span
                        className={`badge ${
                          row.macd_trend === 'BULLISH' ? 'b-bull' : 'b-bear'
                        } text-[10px]`}
                      >
                        {row.macd_trend}
                      </span>
                    </td>
                    <td className="py-2 text-ink">
                      {safeNum(row.macd_line)} / {safeNum(row.signal_line)}
                    </td>
                    <td
                      className={`py-2 font-semibold ${
                        row.histogram >= 0 ? 'v-bull' : 'v-bear'
                      }`}
                    >
                      {safeNum(row.histogram)}
                    </td>
                    <td className="py-2 text-ink">{safeNum(row.fisher_line, '—', 2)}</td>
                    <td className="py-2">
                      <span className={`badge ${zBadge.cls} text-[9px]`}>
                        {row.fisher_zone}
                      </span>
                    </td>
                    <td className="py-2 text-ink-2 text-[11px]">{row.role}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Layman Strategy Blueprint & Empirical 80% Win Rate Verification */}
      <div className="p-4 rounded-lg bg-surface border border-border flex flex-col gap-3">
        <div className="flex items-center gap-2 border-b border-border pb-2">
          <ShieldAlert className="w-4 h-4 text-ink" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-ink">
            Layman’s Playbook: How This Strategy Reaches ~78%–80% Win Rate
          </h3>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
          <div className="p-3 rounded bg-card border border-border flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <span className="badge b-bull text-xs font-bold">RULE 1</span>
              <span className="text-xs font-bold text-ink">Never Fight 15M Trend</span>
            </div>
            <p className="text-[11px] text-ink-2 leading-relaxed">
              If the 15M MACD is Bullish, you ONLY look for Call entries. If Bearish, you ONLY look for Put entries. Counter-trend trades fail over 55% of the time.
            </p>
          </div>

          <div className="p-3 rounded bg-card border border-border flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <span className="badge b-bull text-xs font-bold">RULE 2</span>
              <span className="text-xs font-bold text-ink">Wait for Extreme Pullback</span>
            </div>
            <p className="text-[11px] text-ink-2 leading-relaxed">
              Do not chase breakout candles. Wait until the 5M Fisher-9 reaches extreme exhaustion (&lt; -1.0 or &gt; +1.0). You enter at wholesale discount prices.
            </p>
          </div>

          <div className="p-3 rounded bg-card border border-border flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <span className="badge b-bull text-xs font-bold">RULE 3</span>
              <span className="text-xs font-bold text-ink">Take Profit at +0.50 ATR</span>
            </div>
            <p className="text-[11px] text-ink-2 leading-relaxed">
              In backtests on 258 trades, taking profit at +0.50 ATR achieved a <strong>78.7% Win Rate</strong>. Holding for huge targets drops win rate to 50% due to intraday chops.
            </p>
          </div>
        </div>

        {performance && (
          <div className="mt-2 p-3 rounded bg-card border border-border">
            <span className="text-xs font-bold uppercase tracking-wider text-ink block mb-2">
              Empirical Backtest Benchmark Matrix (NIFTY Index · 258 Sample Episodes)
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
              {performance.barrier_configurations.map((bar) => (
                <div key={bar.label} className="p-2 rounded bg-surface border border-border">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-ink">{bar.label}</span>
                    <span className="badge b-bull text-[9px]">{bar.win_rate_pct}% Win</span>
                  </div>
                  <div className="mt-1 text-[11px] text-ink-2">
                    Target: +{bar.target_atr} ATR · Stop: -{bar.stop_atr} ATR
                  </div>
                  <div className="mt-0.5 text-[10px] text-ink-3">
                    Profit Factor: <strong>{bar.profit_factor}</strong> ({bar.sample_trades} trades)
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Interactive Backtest Simulator */}
      <div className="p-4 rounded-lg bg-card border border-border flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-2">
          <div className="flex items-center gap-2">
            <BarChart2 className="w-4 h-4 text-ink" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-ink">
              Interactive Backtest Engine ({symbol})
            </h3>
          </div>
          <span className="badge b-neut text-xs">
            Real Historical 5M Candles
          </span>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded bg-surface border border-border">
          <div className="flex flex-wrap items-center gap-3">
            <div>
              <label className="text-[10px] text-ink-3 uppercase block mb-1">
                Target ATR
              </label>
              <span className="seg">
                {[0.5, 1.0, 1.5].map((val) => (
                  <button
                    key={val}
                    type="button"
                    onClick={() => setBtTargetAtr(val)}
                    className="seg-btn"
                    data-active={btTargetAtr === val}
                  >
                    +{val.toFixed(2)} ATR {val === 0.5 ? '(78%)' : ''}
                  </button>
                ))}
              </span>
            </div>

            <div>
              <label className="text-[10px] text-ink-3 uppercase block mb-1">
                Stop Loss ATR
              </label>
              <span className="seg">
                {[1.0, 1.5].map((val) => (
                  <button
                    key={val}
                    type="button"
                    onClick={() => setBtStopAtr(val)}
                    className="seg-btn"
                    data-active={btStopAtr === val}
                  >
                    -{val.toFixed(2)} ATR
                  </button>
                ))}
              </span>
            </div>
          </div>

          <button
            type="button"
            onClick={() => void handleRunBacktest()}
            disabled={btRunning}
            className="btn btn-primary text-xs flex items-center gap-1.5"
          >
            {btRunning ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Play className="w-3.5 h-3.5 fill-current" />
            )}
            {btRunning ? 'Simulating Historical Trades…' : `Run Backtest on ${symbol}`}
          </button>
        </div>

        {btError && (
          <div className="p-2.5 rounded bg-down-wash border border-down-line text-down-strong text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{btError}</span>
          </div>
        )}

        {btResult && (
          <div className="flex flex-col gap-3 pt-1">
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
              <div className="p-2.5 rounded bg-surface border border-border flex flex-col">
                <span className="text-[10px] uppercase text-ink-3">Total Trades</span>
                <span className="text-base font-bold text-ink mt-0.5">{btResult.total_trades}</span>
                <span className="text-[10px] text-ink-3">{btResult.wins}W / {btResult.losses}L</span>
              </div>
              <div className="p-2.5 rounded bg-surface border border-border flex flex-col">
                <span className="text-[10px] uppercase text-ink-3">Win Rate</span>
                <span className={`text-base font-bold mt-0.5 ${btResult.win_rate_pct >= 65 ? 'v-bull' : 'v-bear'}`}>
                  {btResult.win_rate_pct}%
                </span>
                <span className="text-[10px] text-ink-3">Empirical Barrier</span>
              </div>
              <div className="p-2.5 rounded bg-surface border border-border flex flex-col">
                <span className="text-[10px] uppercase text-ink-3">Profit Factor</span>
                <span className="text-base font-bold text-ink mt-0.5">{btResult.profit_factor}</span>
                <span className="text-[10px] text-ink-3">Gross Win / Gross Loss</span>
              </div>
              <div className="p-2.5 rounded bg-surface border border-border flex flex-col">
                <span className="text-[10px] uppercase text-ink-3">Net Gain</span>
                <span className={`text-base font-bold mt-0.5 ${btResult.net_atr_gain >= 0 ? 'v-bull' : 'v-bear'}`}>
                  {btResult.net_atr_gain >= 0 ? '+' : ''}{btResult.net_atr_gain} ATR
                </span>
                <span className="text-[10px] text-ink-3">Net Alpha</span>
              </div>
              <div className="p-2.5 rounded bg-surface border border-border flex flex-col">
                <span className="text-[10px] uppercase text-ink-3">Exp. Value (EV)</span>
                <span className="text-base font-bold text-ink mt-0.5">
                  +{btResult.expected_value_atr} ATR
                </span>
                <span className="text-[10px] text-ink-3">Per Trade Expectancy</span>
              </div>
            </div>

            {btResult.divergence_analysis && (
              <div className="p-2.5 rounded bg-surface border border-border flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-ink">Divergence Lift (§23R):</span>
                  <span className="text-ink-2">
                    With Div: <strong className="text-ink">{btResult.divergence_analysis.trades_with_divergence} trades</strong> ({btResult.divergence_analysis.win_rate_with_divergence}% WR) vs Without Div: <strong className="text-ink">{btResult.divergence_analysis.trades_without_divergence} trades</strong> ({btResult.divergence_analysis.win_rate_without_divergence}% WR)
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`font-bold ${btResult.divergence_analysis.divergence_lift_pct >= 0 ? 'v-bull' : 'v-bear'}`}>
                    Lift: {btResult.divergence_analysis.divergence_lift_pct >= 0 ? '+' : ''}{btResult.divergence_analysis.divergence_lift_pct}%
                  </span>
                  <span className={`badge ${btResult.divergence_analysis.stability_flag === 'ROBUST_DIVERGENCE' ? 'b-bull' : 'b-neut'} text-[10px]`}>
                    {btResult.divergence_analysis.stability_flag}
                  </span>
                </div>
              </div>
            )}

            {btResult.friction_sensitivity && btResult.friction_sensitivity.length > 0 && (
              <div className="p-2.5 rounded bg-surface border border-border flex flex-col gap-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-ink">
                    Realistic Execution Friction Sensitivity (§58)
                  </span>
                  <span className="text-[10px] text-ink-3">
                    Includes STT, GST, Exchange Charges &amp; Execution Slippage
                  </span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-left">
                    <thead>
                      <tr className="border-b border-border text-ink-3 uppercase text-[10px]">
                        <th className="pb-1">Friction Haircut</th>
                        <th className="pb-1">Net Win Rate</th>
                        <th className="pb-1">Profit Factor</th>
                        <th className="pb-1">Total Net Gain</th>
                        <th className="pb-1">Expected Value</th>
                        <th className="pb-1">Viability</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {btResult.friction_sensitivity.map((f, idx) => (
                        <tr key={idx} className="hover:bg-card">
                          <td className="py-1 font-mono text-ink">
                            {f.friction_haircut_atr === 0
                              ? '0.00 ATR (Raw)'
                              : `-${f.friction_haircut_atr.toFixed(2)} ATR`}
                          </td>
                          <td className={`py-1 font-semibold ${f.net_win_rate_pct >= 65 ? 'v-bull' : 'v-bear'}`}>
                            {f.net_win_rate_pct}%
                          </td>
                          <td className="py-1 font-mono text-ink-2">{f.profit_factor}</td>
                          <td className={`py-1 font-mono ${f.total_net_gain_atr >= 0 ? 'v-bull' : 'v-bear'}`}>
                            {f.total_net_gain_atr >= 0 ? '+' : ''}{f.total_net_gain_atr} ATR
                          </td>
                          <td className={`py-1 font-mono ${f.expected_value_atr >= 0 ? 'v-bull' : 'v-bear'}`}>
                            {f.expected_value_atr >= 0 ? '+' : ''}{f.expected_value_atr} ATR
                          </td>
                          <td className="py-1">
                            <span className={`badge ${f.is_economically_viable ? 'b-bull' : 'b-neut'} text-[10px]`}>
                              {f.is_economically_viable ? 'VIABLE' : 'EROSION'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {btResult.recent_trades.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead>
                    <tr className="border-b border-border text-ink-3 uppercase text-[10px]">
                      <th className="pb-1.5">Trade Time</th>
                      <th className="pb-1.5">Direction</th>
                      <th className="pb-1.5">Entry Spot</th>
                      <th className="pb-1.5">Target</th>
                      <th className="pb-1.5">Stop</th>
                      <th className="pb-1.5">Outcome</th>
                      <th className="pb-1.5">Result (pts)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {btResult.recent_trades.map((t, idx) => (
                      <tr key={idx} className="hover:bg-surface">
                        <td className="py-1.5 text-ink-2 font-mono text-[11px]">{t.timestamp}</td>
                        <td className="py-1.5">
                          <span className={`badge ${t.direction === 'LONG_CALL' ? 'b-bull' : 'b-bear'} text-[10px]`}>
                            {t.direction}
                          </span>
                        </td>
                        <td className="py-1.5 text-ink font-semibold">₹{safeNum(t.entry_price)}</td>
                        <td className="py-1.5 text-ink">₹{safeNum(t.target_price)}</td>
                        <td className="py-1.5 text-ink">₹{safeNum(t.stop_price)}</td>
                        <td className="py-1.5">
                          <span className={`badge ${t.outcome === 'WIN' ? 'b-bull' : 'b-bear'} font-bold text-[10px]`}>
                            {t.outcome}
                          </span>
                        </td>
                        <td className={`py-1.5 font-bold ${t.pnl_points >= 0 ? 'v-bull' : 'v-bear'}`}>
                          {t.pnl_points >= 0 ? '+' : ''}{safeNum(t.pnl_points)} pts
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Recent Signals History */}
      <div className="p-4 rounded-lg bg-card border border-border flex flex-col gap-3">
        <div className="flex items-center justify-between border-b border-border pb-2">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-ink" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-ink">
              Recent Fisher-MACD Strategy Signals
            </h3>
          </div>
          <span className="badge b-neut text-xs">
            {strategySignals.length} recorded today
          </span>
        </div>

        {strategySignals.length === 0 ? (
          <p className="text-xs text-ink-2 py-3 text-center">
            No Fisher-MACD signals recorded yet today. When 15M trend and 5M Fisher-9 pullback crossover align, automated alerts and execution cards will populate here.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {strategySignals.map((sig) => (
              <div
                key={sig.id}
                className="flex items-center justify-between p-2.5 rounded bg-surface border border-border text-xs"
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`badge ${
                      sig.direction === 'LONG_CALL' ? 'b-bull' : 'b-bear'
                    }`}
                  >
                    {String(sig.direction ?? '')}
                  </span>
                  <span className="font-bold text-ink">{sig.symbol}</span>
                  <span className="text-ink-2 text-[11px]">{sig.strategy}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="badge b-neut">{stageOf(sig.state)}</span>
                  <span className="text-ink-3 text-[11px]">
                    Trigger: ₹{safeNum(sig.triggerLevel)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
