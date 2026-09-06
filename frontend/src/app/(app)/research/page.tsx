'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import { PageTabs } from '@/components/ui/PageTabs';
import {
  FlaskConical,
  Gauge,
  CheckCircle2,
  XCircle,
  TrendingUp,
  TrendingDown,
  Activity,
  Layers,
  Sparkles,
  RefreshCw,
  Clock,
  ShieldAlert,
  BarChart2,
  Percent,
  Compass,
  Zap,
  BookmarkPlus,
  Play,
  Check,
  ChevronRight,
} from 'lucide-react';

export default function ResearchLabPage() {
  const [instrument, setInstrument] = useState<string>('NIFTY 50');
  const [timeframe, setTimeframe] = useState<string>('5m');
  const [loading, setLoading] = useState<boolean>(true);
  const [calculating, setCalculating] = useState<boolean>(false);
  const [backtesting, setBacktesting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Data states
  const [indicators, setIndicators] = useState<any[]>([]);
  const [ompiData, setOmpiData] = useState<any | null>(null);
  const [features, setFeatures] = useState<any | null>(null);
  const [optionsCtx, setOptionsCtx] = useState<any | null>(null);
  const [predictions, setPredictions] = useState<any[]>([]);
  const [experimentResult, setExperimentResult] = useState<any | null>(null);
  const [selectedValidatorInd, setSelectedValidatorInd] = useState<string>('ompi');
  const [loggedNotification, setLoggedNotification] = useState<string | null>(null);

  // Fetch initial registry & state
  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [inds, chartFeat, optCtx, preds] = await Promise.allSettled([
        api.getResearchIndicators(),
        api.getResearchFeatures(instrument, timeframe),
        api.getResearchOptionsContext(instrument),
        api.listResearchPredictions({ instrument, limit: 20 }),
      ]);

      if (inds.status === 'fulfilled' && Array.isArray(inds.value)) {
        setIndicators(inds.value);
      }
      if (chartFeat.status === 'fulfilled') {
        setFeatures(chartFeat.value);
      }
      if (optCtx.status === 'fulfilled') {
        setOptionsCtx(optCtx.value);
      }
      if (preds.status === 'fulfilled' && Array.isArray(preds.value)) {
        setPredictions(preds.value);
      }

      // Calculate OMPI live
      const ompiRes = await api.calculateResearchIndicator('ompi', {
        instrument,
        timeframe,
      });
      setOmpiData(ompiRes);
    } catch (err: any) {
      console.error('Failed to load research data:', err);
      setError(err?.message || 'Failed to connect to Research Laboratory services');
    } finally {
      setLoading(false);
    }
  }, [instrument, timeframe]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Trigger custom OMPI recalculation
  const handleRecalculateOmpi = async () => {
    setCalculating(true);
    try {
      const res = await api.calculateResearchIndicator('ompi', {
        instrument,
        timeframe,
      });
      setOmpiData(res);
    } catch (err: any) {
      setError(err?.message || 'Calculation error');
    } finally {
      setCalculating(false);
    }
  };

  // Run Cheap Validation Gate
  const handleRunBacktest = async () => {
    setBacktesting(true);
    setError(null);
    try {
      const res = await api.runResearchExperiment({
        indicator_id: selectedValidatorInd,
        instrument,
        timeframe,
        horizon_candles: 5,
        stride: 3,
      });
      setExperimentResult(res);
    } catch (err: any) {
      setError(err?.message || 'Backtest evaluation failed');
    } finally {
      setBacktesting(false);
    }
  };

  // Log Immutable Prediction
  const handleLogPrediction = async () => {
    if (!ompiData) return;
    try {
      const pred = {
        prediction_id: `pred_${Date.now().toString(36)}`,
        indicator_id: ompiData.indicator_id,
        indicator_version: ompiData.version,
        instrument,
        timeframe,
        timestamp: new Date().toISOString(),
        current_price: features?.current_price || ompiData.target_price || 24000,
        direction: ompiData.direction,
        score: ompiData.score,
        confidence: ompiData.confidence,
        raw_value: ompiData.raw_value,
        normalized_value: ompiData.normalized_value,
        component_values: ompiData.component_values,
        forecast_horizon: ompiData.horizon || '15m',
        horizon_candles: 5,
        target_price: ompiData.target_price,
        invalidation_price: ompiData.invalidation_price,
      };
      await api.recordResearchPrediction(pred);
      setLoggedNotification('Prediction successfully recorded as immutable row in database!');
      setTimeout(() => setLoggedNotification(null), 4000);
      const updated = await api.listResearchPredictions({ instrument, limit: 20 });
      setPredictions(updated);
    } catch (err: any) {
      setError(err?.message || 'Failed to log prediction');
    }
  };

  // Score color helper
  const getScoreColor = (score: number) => {
    if (score >= 20) return 'text-emerald-400';
    if (score <= -20) return 'text-rose-400';
    return 'text-amber-400';
  };

  const getPressureBg = (score: number) => {
    if (score > 0) return 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300';
    if (score < 0) return 'bg-rose-500/20 border-rose-500/40 text-rose-300';
    return 'bg-zinc-500/20 border-zinc-500/40 text-zinc-300';
  };

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-12">
      {/* Header Banner */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-zinc-950 via-purple-950/40 to-zinc-950 border border-purple-800/30 p-6 shadow-2xl backdrop-blur-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-purple-600/20 border border-purple-500/40 text-purple-400">
                <FlaskConical className="w-6 h-6 animate-pulse" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-2xl font-bold tracking-tight text-zinc-100">
                    Chart Intelligence & Indicator Research Laboratory
                  </h1>
                  <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                    Phases 0–7 Active
                  </span>
                  <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
                    Non-Production Isolated
                  </span>
                </div>
                <p className="text-sm text-zinc-400">
                  Analytical research-first laboratory for proprietary indicators (OMPI), point-in-time features, and cheap validation backtesting.
                </p>
              </div>
            </div>
          </div>

          {/* Instrument & Timeframe Selector */}
          <div className="flex flex-wrap items-center gap-2.5">
            {/* Instrument Buttons */}
            <div className="flex rounded-lg bg-zinc-900/80 p-1 border border-zinc-800">
              {['NIFTY 50', 'BANKNIFTY', 'SENSEX'].map((inst) => (
                <button
                  key={inst}
                  onClick={() => setInstrument(inst)}
                  className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                    instrument === inst
                      ? 'bg-purple-600 text-white shadow-lg shadow-purple-600/30'
                      : 'text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  {inst}
                </button>
              ))}
            </div>

            {/* Timeframe Buttons */}
            <div className="flex rounded-lg bg-zinc-900/80 p-1 border border-zinc-800">
              {['1m', '5m', '15m', '1h', '1D'].map((tf) => (
                <button
                  key={tf}
                  onClick={() => setTimeframe(tf)}
                  className={`px-2.5 py-1.5 rounded-md text-xs font-semibold transition-all ${
                    timeframe === tf
                      ? 'bg-zinc-700 text-white shadow-md'
                      : 'text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  {tf}
                </button>
              ))}
            </div>

            {/* Refresh Button */}
            <button
              onClick={loadData}
              disabled={loading}
              className="p-2 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
              title="Refresh Data"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-purple-400' : ''}`} />
            </button>
          </div>
        </div>

        {/* Live Context Quick Bar */}
        <div className="mt-4 pt-4 border-t border-zinc-800/80 flex flex-wrap items-center justify-between text-xs text-zinc-400 gap-4">
          <div className="flex items-center gap-6">
            <div>
              <span className="text-zinc-500">Spot Price: </span>
              <span className="font-mono font-semibold text-zinc-200">
                {features?.current_price ? `₹${features.current_price.toLocaleString('en-IN')}` : 'Loading...'}
              </span>
            </div>
            <div>
              <span className="text-zinc-500">Market Regime: </span>
              <span className="font-semibold text-purple-400">
                {features?.regime || 'RANGING'}
              </span>
            </div>
            <div>
              <span className="text-zinc-500">Session (IST): </span>
              <span className="font-medium text-zinc-300">
                {features?.session || 'MID'}
              </span>
            </div>
            <div>
              <span className="text-zinc-500">ATM IV: </span>
              <span className="font-mono text-zinc-300">
                {optionsCtx?.atm_iv ? `${optionsCtx.atm_iv}%` : '15.0%'}
              </span>
            </div>
            <div>
              <span className="text-zinc-500">PCR (OI): </span>
              <span className="font-mono text-zinc-300">
                {optionsCtx?.pcr_oi ?? 1.0}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
            <span className="text-emerald-400 font-medium">Research Engine Online</span>
          </div>
        </div>
      </div>

      {/* Notification Toast */}
      {loggedNotification && (
        <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" />
          <span>{loggedNotification}</span>
        </div>
      )}

      {error && (
        <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-center gap-2">
          <ShieldAlert className="w-4 h-4" />
          <span>{error}</span>
        </div>
      )}

      {/* Main Tabs */}
      <PageTabs
        tabs={[
          {
            id: 'ompi-lab',
            label: 'OMPI v0.1 Lab',
            icon: Gauge,
            badge: ompiData ? `${ompiData.score > 0 ? '+' : ''}${ompiData.score}` : undefined,
            badgeClassName: ompiData?.score >= 20 ? 'bg-emerald-500/20 text-emerald-300' : ompiData?.score <= -20 ? 'bg-rose-500/20 text-rose-300' : 'bg-zinc-700 text-zinc-300',
            content: (
              <div className="space-y-6">
                {/* OMPI Primary Gauge Card */}
                <div className="rounded-2xl bg-zinc-900/60 border border-zinc-800 p-6 backdrop-blur-md shadow-xl">
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 pb-6 border-b border-zinc-800">
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-xl font-bold text-zinc-100">
                          Option Market Pressure Index (OMPI) v0.1
                        </h2>
                        <span className="px-2 py-0.5 rounded text-xs font-mono bg-purple-500/20 text-purple-300 border border-purple-500/30">
                          PROPRIETARY
                        </span>
                      </div>
                      <p className="text-sm text-zinc-400 mt-1 max-w-2xl">
                        Synthesizes price momentum, options positioning, volume participation, volatility regime, and theta friction into a normalized -100 to +100 pressure metric.
                      </p>
                    </div>

                    <div className="flex items-center gap-3">
                      <button
                        onClick={handleRecalculateOmpi}
                        disabled={calculating}
                        className="px-4 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-semibold flex items-center gap-2 transition-all border border-zinc-700"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${calculating ? 'animate-spin' : ''}`} />
                        Recalculate
                      </button>

                      <button
                        onClick={handleLogPrediction}
                        className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold flex items-center gap-2 shadow-lg shadow-purple-600/20 transition-all"
                      >
                        <BookmarkPlus className="w-3.5 h-3.5" />
                        Log Prediction
                      </button>
                    </div>
                  </div>

                  {/* Pressure Metric Row */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-6 pt-6">
                    {/* Main Score & Direction */}
                    <div className="md:col-span-2 rounded-xl bg-zinc-950/70 border border-zinc-800 p-6 flex flex-col justify-between">
                      <div className="flex items-center justify-between">
                        <span className="text-xs uppercase font-semibold text-zinc-400 tracking-wider">
                          Composite Pressure Index
                        </span>
                        <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${
                          ompiData?.direction === 'BULLISH'
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                            : ompiData?.direction === 'BEARISH'
                            ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                            : 'bg-zinc-700/40 text-zinc-300 border border-zinc-600'
                        }`}>
                          {ompiData?.direction || 'NEUTRAL'}
                        </span>
                      </div>

                      <div className="my-4">
                        <div className="flex items-baseline gap-2">
                          <span className={`text-5xl font-black font-mono tracking-tight ${getScoreColor(ompiData?.score || 0)}`}>
                            {ompiData ? (ompiData.score > 0 ? `+${ompiData.score}` : ompiData.score) : '0.00'}
                          </span>
                          <span className="text-zinc-500 text-sm">/ ±100</span>
                        </div>

                        {/* Visual Slider / Gauge Bar */}
                        <div className="relative mt-4 h-3 bg-zinc-800 rounded-full overflow-hidden flex items-center">
                          <div className="absolute left-1/2 w-0.5 h-full bg-zinc-500 z-10" />
                          <div
                            className={`h-full transition-all duration-500 ${
                              (ompiData?.score || 0) >= 0 ? 'bg-gradient-to-r from-emerald-600 to-emerald-400' : 'bg-gradient-to-l from-rose-600 to-rose-400'
                            }`}
                            style={{
                              width: `${Math.abs(ompiData?.score || 0) / 2}%`,
                              marginLeft: (ompiData?.score || 0) >= 0 ? '50%' : `${50 - Math.abs(ompiData?.score || 0) / 2}%`,
                            }}
                          />
                        </div>
                        <div className="flex justify-between text-[10px] text-zinc-500 font-mono mt-1">
                          <span>-100 Bearish</span>
                          <span>0 Neutral</span>
                          <span>+100 Bullish</span>
                        </div>
                      </div>

                      <div className="flex items-center justify-between text-xs text-zinc-400 pt-2 border-t border-zinc-900">
                        <span>Confidence: <strong className="text-zinc-200 font-mono">{Math.round((ompiData?.confidence || 0) * 100)}%</strong></span>
                        <span>Horizon: <strong className="text-zinc-200">15m (5 candles)</strong></span>
                      </div>
                    </div>

                    {/* Target & Invalidation Levels */}
                    <div className="rounded-xl bg-zinc-950/70 border border-zinc-800 p-5 flex flex-col justify-between">
                      <span className="text-xs uppercase font-semibold text-zinc-400 tracking-wider">
                        Targets & Invalidation
                      </span>
                      <div className="space-y-4 my-2">
                        <div>
                          <div className="text-[11px] text-emerald-400 flex items-center gap-1 font-medium">
                            <TrendingUp className="w-3.5 h-3.5" /> Favorable Target (+1.6 ATR)
                          </div>
                          <div className="text-xl font-bold font-mono text-zinc-100">
                            {ompiData?.target_price ? `₹${ompiData.target_price.toLocaleString('en-IN')}` : '—'}
                          </div>
                        </div>
                        <div>
                          <div className="text-[11px] text-rose-400 flex items-center gap-1 font-medium">
                            <TrendingDown className="w-3.5 h-3.5" /> Invalidation Stop (-1.0 ATR)
                          </div>
                          <div className="text-xl font-bold font-mono text-zinc-100">
                            {ompiData?.invalidation_price ? `₹${ompiData.invalidation_price.toLocaleString('en-IN')}` : '—'}
                          </div>
                        </div>
                      </div>
                      <div className="text-[10px] text-zinc-500">Calculated strictly without lookahead bias.</div>
                    </div>

                    {/* Options Context Quick Stats */}
                    <div className="rounded-xl bg-zinc-950/70 border border-zinc-800 p-5 flex flex-col justify-between">
                      <span className="text-xs uppercase font-semibold text-zinc-400 tracking-wider">
                        Options Context
                      </span>
                      <div className="space-y-2 text-xs">
                        <div className="flex justify-between py-1 border-b border-zinc-900">
                          <span className="text-zinc-400">Put-Call Ratio:</span>
                          <span className="font-mono font-semibold text-zinc-200">{optionsCtx?.pcr_oi ?? 1.0}</span>
                        </div>
                        <div className="flex justify-between py-1 border-b border-zinc-900">
                          <span className="text-zinc-400">Call Wall (Res):</span>
                          <span className="font-mono font-semibold text-rose-400">{optionsCtx?.call_wall ? `₹${optionsCtx.call_wall}` : '—'}</span>
                        </div>
                        <div className="flex justify-between py-1 border-b border-zinc-900">
                          <span className="text-zinc-400">Put Wall (Sup):</span>
                          <span className="font-mono font-semibold text-emerald-400">{optionsCtx?.put_wall ? `₹${optionsCtx.put_wall}` : '—'}</span>
                        </div>
                        <div className="flex justify-between py-1">
                          <span className="text-zinc-400">Max Pain Strike:</span>
                          <span className="font-mono font-semibold text-amber-400">{optionsCtx?.max_pain ? `₹${optionsCtx.max_pain}` : '—'}</span>
                        </div>
                      </div>
                      <div className="text-[10px] text-zinc-500">Days to Expiry: {optionsCtx?.days_to_expiry ?? 2.0}d</div>
                    </div>
                  </div>

                  {/* Section 17 Full Transparency Component Breakdown */}
                  <div className="mt-8 pt-6 border-t border-zinc-800">
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-300">
                          Full Transparency Sub-Pressures (§17)
                        </h3>
                        <p className="text-xs text-zinc-500">
                          Zero black-box logic: each of the 5 pressure vectors is independently normalized and weighted.
                        </p>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
                      {/* P_dir */}
                      <div className="rounded-xl bg-zinc-950/60 border border-zinc-800 p-3.5 space-y-2">
                        <div className="flex justify-between text-xs">
                          <span className="text-zinc-400 font-medium">1. Directional (P_dir)</span>
                          <span className="text-[10px] text-zinc-500 font-mono">wt: 30%</span>
                        </div>
                        <div className={`px-2 py-1 rounded text-sm font-mono font-bold border ${getPressureBg(ompiData?.component_values?.p_dir || 0)}`}>
                          {ompiData?.component_values?.p_dir || 0}
                        </div>
                        <p className="text-[11px] text-zinc-500 leading-snug">EMA20/50 structures + Wilder RSI tilt</p>
                      </div>

                      {/* P_opt */}
                      <div className="rounded-xl bg-zinc-950/60 border border-zinc-800 p-3.5 space-y-2">
                        <div className="flex justify-between text-xs">
                          <span className="text-zinc-400 font-medium">2. Options (P_opt)</span>
                          <span className="text-[10px] text-zinc-500 font-mono">wt: 25%</span>
                        </div>
                        <div className={`px-2 py-1 rounded text-sm font-mono font-bold border ${getPressureBg(ompiData?.component_values?.p_opt || 0)}`}>
                          {ompiData?.component_values?.p_opt || 0}
                        </div>
                        <p className="text-[11px] text-zinc-500 leading-snug">PCR deviation, wall proximity, max pain gravity</p>
                      </div>

                      {/* P_part */}
                      <div className="rounded-xl bg-zinc-950/60 border border-zinc-800 p-3.5 space-y-2">
                        <div className="flex justify-between text-xs">
                          <span className="text-zinc-400 font-medium">3. Participation (P_part)</span>
                          <span className="text-[10px] text-zinc-500 font-mono">wt: 20%</span>
                        </div>
                        <div className={`px-2 py-1 rounded text-sm font-mono font-bold border ${getPressureBg(ompiData?.component_values?.p_part || 0)}`}>
                          {ompiData?.component_values?.p_part || 0}
                        </div>
                        <p className="text-[11px] text-zinc-500 leading-snug">Relative volume surge & signed candle flow</p>
                      </div>

                      {/* P_vol */}
                      <div className="rounded-xl bg-zinc-950/60 border border-zinc-800 p-3.5 space-y-2">
                        <div className="flex justify-between text-xs">
                          <span className="text-zinc-400 font-medium">4. Volatility (P_vol)</span>
                          <span className="text-[10px] text-zinc-500 font-mono">wt: 15%</span>
                        </div>
                        <div className={`px-2 py-1 rounded text-sm font-mono font-bold border ${getPressureBg(ompiData?.component_values?.p_vol || 0)}`}>
                          {ompiData?.component_values?.p_vol || 0}
                        </div>
                        <p className="text-[11px] text-zinc-500 leading-snug">Bollinger bandwidth squeeze & IV deviation</p>
                      </div>

                      {/* P_decay */}
                      <div className="rounded-xl bg-zinc-950/60 border border-zinc-800 p-3.5 space-y-2">
                        <div className="flex justify-between text-xs">
                          <span className="text-zinc-400 font-medium">5. Decay (P_decay)</span>
                          <span className="text-[10px] text-zinc-500 font-mono">wt: 10%</span>
                        </div>
                        <div className={`px-2 py-1 rounded text-sm font-mono font-bold border ${getPressureBg(ompiData?.component_values?.p_decay || 0)}`}>
                          {ompiData?.component_values?.p_decay || 0}
                        </div>
                        <p className="text-[11px] text-zinc-500 leading-snug">ATM Theta burn friction relative to DTE</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ),
          },
          {
            id: 'validation-gate',
            label: 'Cheap Validation Gate',
            icon: CheckCircle2,
            content: (
              <div className="space-y-6">
                {/* Backtest Configuration Card */}
                <div className="rounded-2xl bg-zinc-900/60 border border-zinc-800 p-6 backdrop-blur-md shadow-xl">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-zinc-800">
                    <div>
                      <h2 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
                        <ShieldAlert className="w-5 h-5 text-purple-400" />
                        Cheap Validation Gate (§19, §20)
                      </h2>
                      <p className="text-sm text-zinc-400 mt-1">
                        Executes lightweight offline walk-forward evaluation with strict Point-In-Time (PIT) integrity to determine if an indicator delivers statistically verifiable edge over naive baselines.
                      </p>
                    </div>

                    <div className="flex items-center gap-3">
                      <select
                        value={selectedValidatorInd}
                        onChange={(e) => setSelectedValidatorInd(e.target.value)}
                        className="px-3 py-2 rounded-xl bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-purple-500"
                      >
                        <option value="ompi">Option Market Pressure Index (OMPI)</option>
                        <option value="rsi">Relative Strength Index (RSI)</option>
                        <option value="vwap">Volume Weighted Average Price (VWAP)</option>
                        <option value="macd">MACD Histogram</option>
                        <option value="momentum">Multi-Period Momentum Composite</option>
                      </select>

                      <button
                        onClick={handleRunBacktest}
                        disabled={backtesting}
                        className="px-5 py-2 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-xs font-bold flex items-center gap-2 shadow-lg shadow-purple-600/30 transition-all disabled:opacity-50"
                      >
                        {backtesting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 fill-white" />}
                        {backtesting ? 'Evaluating Historical Data...' : 'Run Validation Gate'}
                      </button>
                    </div>
                  </div>

                  {/* Results Panel */}
                  {experimentResult ? (
                    <div className="mt-6 space-y-6">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span className={`px-3 py-1 rounded-full text-xs font-bold tracking-wide border ${
                            experimentResult.report?.is_statistically_significant
                              ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                              : 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                          }`}>
                            {experimentResult.report?.is_statistically_significant
                              ? '[PASS: STATISTICALLY SIGNIFICANT]'
                              : '[FAIL: NOT STATISTICALLY SIGNIFICANT]'}
                          </span>
                          <span className="text-xs text-zinc-400">
                            Evaluated on <strong>{experimentResult.report?.sample_size}</strong> historical walk-forward points
                          </span>
                        </div>
                        <span className="text-xs text-zinc-500 font-mono">
                          Run ID: {experimentResult.run?.run_id}
                        </span>
                      </div>

                      {/* Primary Metrics Grid */}
                      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                        <div className="p-3.5 rounded-xl bg-zinc-950/70 border border-zinc-800">
                          <span className="text-[11px] text-zinc-500 font-medium">Indicator Accuracy</span>
                          <div className="text-2xl font-bold font-mono text-zinc-100 mt-1">
                            {experimentResult.report?.accuracy}%
                          </div>
                          <span className="text-[10px] text-zinc-400 font-mono">
                            95% CI: [{experimentResult.report?.confidence_interval_95?.[0]}%, {experimentResult.report?.confidence_interval_95?.[1]}%]
                          </span>
                        </div>

                        <div className="p-3.5 rounded-xl bg-zinc-950/70 border border-zinc-800">
                          <span className="text-[11px] text-zinc-500 font-medium">Baseline Accuracy</span>
                          <div className="text-2xl font-bold font-mono text-zinc-400 mt-1">
                            {experimentResult.report?.baseline_accuracy}%
                          </div>
                          <span className="text-[10px] text-zinc-500">Naive momentum</span>
                        </div>

                        <div className="p-3.5 rounded-xl bg-zinc-950/70 border border-zinc-800">
                          <span className="text-[11px] text-zinc-500 font-medium">Excess Accuracy</span>
                          <div className={`text-2xl font-bold font-mono mt-1 ${
                            experimentResult.report?.excess_accuracy > 0 ? 'text-emerald-400' : 'text-rose-400'
                          }`}>
                            {experimentResult.report?.excess_accuracy > 0 ? '+' : ''}{experimentResult.report?.excess_accuracy}%
                          </div>
                          <span className="text-[10px] text-zinc-500">Alpha over baseline</span>
                        </div>

                        <div className="p-3.5 rounded-xl bg-zinc-950/70 border border-zinc-800">
                          <span className="text-[11px] text-zinc-500 font-medium">p-value</span>
                          <div className="text-2xl font-bold font-mono text-purple-300 mt-1">
                            {experimentResult.report?.p_value}
                          </div>
                          <span className="text-[10px] text-zinc-500">Target &lt; 0.05</span>
                        </div>

                        <div className="p-3.5 rounded-xl bg-zinc-950/70 border border-zinc-800">
                          <span className="text-[11px] text-zinc-500 font-medium">Mean Favorable (MFE)</span>
                          <div className="text-2xl font-bold font-mono text-emerald-400 mt-1">
                            {experimentResult.report?.mfe_mean} pts
                          </div>
                          <span className="text-[10px] text-zinc-500">Average peak gain</span>
                        </div>

                        <div className="p-3.5 rounded-xl bg-zinc-950/70 border border-zinc-800">
                          <span className="text-[11px] text-zinc-500 font-medium">Mean Adverse (MAE)</span>
                          <div className="text-2xl font-bold font-mono text-rose-400 mt-1">
                            {experimentResult.report?.mae_mean} pts
                          </div>
                          <span className="text-[10px] text-zinc-500">Average drawdown</span>
                        </div>
                      </div>

                      {/* Detailed Breakdowns */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                        {/* Session Breakdown */}
                        <div className="p-4 rounded-xl bg-zinc-950/60 border border-zinc-800">
                          <h4 className="text-xs uppercase font-semibold text-zinc-300 tracking-wider mb-3">
                            Session Breakdown
                          </h4>
                          <div className="space-y-2 text-xs">
                            {Object.entries(experimentResult.report?.session_breakdown || {}).map(([sess, val]: any) => (
                              <div key={sess} className="flex justify-between py-1.5 border-b border-zinc-900">
                                <span className="text-zinc-400">{sess}</span>
                                <div className="space-x-3">
                                  <span className="text-zinc-500">{val.sample_size} samples</span>
                                  <span className="font-mono font-bold text-zinc-200">{val.accuracy}%</span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Regime Breakdown */}
                        <div className="p-4 rounded-xl bg-zinc-950/60 border border-zinc-800">
                          <h4 className="text-xs uppercase font-semibold text-zinc-300 tracking-wider mb-3">
                            Regime Breakdown
                          </h4>
                          <div className="space-y-2 text-xs">
                            {Object.entries(experimentResult.report?.regime_breakdown || {}).map(([reg, val]: any) => (
                              <div key={reg} className="flex justify-between py-1.5 border-b border-zinc-900">
                                <span className="text-zinc-400">{reg}</span>
                                <div className="space-x-3">
                                  <span className="text-zinc-500">{val.sample_size} samples</span>
                                  <span className="font-mono font-bold text-zinc-200">{val.accuracy}%</span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-8 text-center py-12 rounded-xl bg-zinc-950/40 border border-zinc-800/60">
                      <Activity className="w-8 h-8 text-zinc-600 mx-auto mb-2" />
                      <p className="text-sm font-semibold text-zinc-300">No Validation Run Selected</p>
                      <p className="text-xs text-zinc-500 mt-1">
                        Select an indicator above and click "Run Validation Gate" to trigger historical walk-forward evaluation.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            ),
          },
          {
            id: 'indicator-registry',
            label: 'Indicator Registry',
            icon: Layers,
            badge: indicators.length,
            content: (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-300">
                    Registered Research Indicators (§13, §14)
                  </h3>
                  <span className="text-xs text-zinc-500">
                    Standardized output contract (§46) allows interchangeable comparison.
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {indicators.map((ind) => (
                    <div
                      key={ind.indicator_id}
                      className="rounded-xl bg-zinc-900/60 border border-zinc-800 p-5 space-y-3 hover:border-purple-500/50 transition-all flex flex-col justify-between"
                    >
                      <div>
                        <div className="flex items-start justify-between gap-2">
                          <h4 className="font-bold text-zinc-100 text-sm">{ind.name}</h4>
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            ind.category === 'PROPRIETARY'
                              ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40'
                              : 'bg-zinc-800 text-zinc-300'
                          }`}>
                            {ind.category}
                          </span>
                        </div>
                        <div className="text-[11px] text-zinc-500 font-mono mt-1">
                          ID: {ind.indicator_id} | v{ind.current_version}
                        </div>
                        <p className="text-xs text-zinc-400 mt-2 line-clamp-2">
                          {ind.description || ind.formula_summary}
                        </p>
                      </div>

                      <div className="pt-3 border-t border-zinc-800/80 flex items-center justify-between text-xs">
                        <span className="text-zinc-500">
                          Lifecycle: <strong className="text-zinc-300">{ind.lifecycle}</strong>
                        </span>
                        <button
                          onClick={async () => {
                            setSelectedValidatorInd(ind.indicator_id);
                            const res = await api.calculateResearchIndicator(ind.indicator_id, {
                              instrument,
                              timeframe,
                            });
                            alert(`Calculated ${ind.name}:\nScore: ${res.score}\nDirection: ${res.direction}`);
                          }}
                          className="text-purple-400 hover:text-purple-300 font-semibold flex items-center gap-1"
                        >
                          Calculate <ChevronRight className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ),
          },
          {
            id: 'predictions-log',
            label: 'Predictions & Outcomes',
            icon: BookmarkPlus,
            badge: predictions.length,
            content: (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-300">
                      Immutable Prediction Journal (§26, N5)
                    </h3>
                    <p className="text-xs text-zinc-500">
                      Predictions are written once and never updated. Outcomes are appended separately once the horizon elapses.
                    </p>
                  </div>
                </div>

                {predictions.length > 0 ? (
                  <div className="rounded-xl border border-zinc-800 overflow-hidden bg-zinc-900/60">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-zinc-950/80 text-zinc-400 uppercase font-semibold border-b border-zinc-800">
                        <tr>
                          <th className="p-3">Time</th>
                          <th className="p-3">Indicator</th>
                          <th className="p-3">Direction</th>
                          <th className="p-3">Score</th>
                          <th className="p-3">Entry</th>
                          <th className="p-3">Target</th>
                          <th className="p-3">Invalidation</th>
                          <th className="p-3 text-right">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800/60 font-mono">
                        {predictions.map((p) => (
                          <tr key={p.prediction_id} className="hover:bg-zinc-800/30 transition-colors">
                            <td className="p-3 text-zinc-400">
                              {new Date(p.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
                            </td>
                            <td className="p-3 font-semibold text-zinc-200 uppercase">{p.indicator_id}</td>
                            <td className="p-3">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                p.direction === 'BULLISH' ? 'bg-emerald-500/20 text-emerald-300' : p.direction === 'BEARISH' ? 'bg-rose-500/20 text-rose-300' : 'bg-zinc-700 text-zinc-300'
                              }`}>
                                {p.direction}
                              </span>
                            </td>
                            <td className="p-3 text-zinc-300">{p.score}</td>
                            <td className="p-3 text-zinc-200">₹{p.current_price?.toLocaleString('en-IN')}</td>
                            <td className="p-3 text-emerald-400">₹{p.target_price?.toLocaleString('en-IN') || '—'}</td>
                            <td className="p-3 text-rose-400">₹{p.invalidation_price?.toLocaleString('en-IN') || '—'}</td>
                            <td className="p-3 text-right">
                              <button
                                onClick={async () => {
                                  try {
                                    const out = await api.measureResearchPrediction(p.prediction_id);
                                    alert(`Outcome Measured:\nResult: ${out.is_correct ? 'CORRECT' : 'INCORRECT'}\nMFE: ${out.mfe} pts\nMAE: ${out.mae} pts`);
                                  } catch (e: any) {
                                    alert(`Outcome measurement: ${e?.message || 'Pending candles'}`);
                                  }
                                }}
                                className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-[11px] font-sans"
                              >
                                Measure
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="text-center py-12 rounded-xl bg-zinc-950/40 border border-zinc-800 text-zinc-500 text-xs">
                    No predictions recorded yet for {instrument}. Click "Log Prediction" in the OMPI tab to create an immutable log row.
                  </div>
                )}
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}
