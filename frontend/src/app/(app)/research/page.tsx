'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
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
  X,
  AlertTriangle,
  AlertCircle,
  Info,
  Sliders,
  HelpCircle,
} from 'lucide-react';

export default function ResearchLabPage() {
  const [instrument, setInstrument] = useState<string>('NIFTY 50');
  const [timeframe, setTimeframe] = useState<string>('5m');
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [calculating, setCalculating] = useState<boolean>(false);
  const [backtesting, setBacktesting] = useState<boolean>(false);
  const [measuringId, setMeasuringId] = useState<string | null>(null);
  const [calculatingIndId, setCalculatingIndId] = useState<string | null>(null);
  const [loggingPrediction, setLoggingPrediction] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [backtestError, setBacktestError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [autoRefreshSecs, setAutoRefreshSecs] = useState<number>(0);

  // Data states
  const [indicators, setIndicators] = useState<any[]>([]);
  const [ompiData, setOmpiData] = useState<any | null>(null);
  const [features, setFeatures] = useState<any | null>(null);
  const [optionsCtx, setOptionsCtx] = useState<any | null>(null);
  const [predictions, setPredictions] = useState<any[]>([]);
  const [outcomes, setOutcomes] = useState<Record<string, any>>({});
  const [experimentResult, setExperimentResult] = useState<any | null>(null);
  const [selectedValidatorInd, setSelectedValidatorInd] = useState<string>('ompi');
  const [loggedNotification, setLoggedNotification] = useState<string | null>(null);

  // Modal and Toast states
  const [showLogConfirmModal, setShowLogConfirmModal] = useState<boolean>(false);
  const [calcModalData, setCalcModalData] = useState<{
    indicatorName: string;
    indicatorId: string;
    result: any;
  } | null>(null);
  const [toastNotification, setToastNotification] = useState<{
    type: 'success' | 'error' | 'info';
    message: string;
  } | null>(null);

  // Load predictions and prefetch known outcomes
  const loadPredictionsWithOutcomes = useCallback(async (preds: any[]) => {
    setPredictions(preds);
    const outcomeMap: Record<string, any> = {};
    const predsToFetch = preds.slice(0, 15);
    await Promise.allSettled(
      predsToFetch.map(async (p) => {
        try {
          const out = await api.getResearchPredictionOutcome(p.prediction_id);
          if (out && out.outcome_id) {
            outcomeMap[p.prediction_id] = out;
          }
        } catch {
          // Outcome not measured yet
        }
      })
    );
    if (Object.keys(outcomeMap).length > 0) {
      setOutcomes((prev) => ({ ...prev, ...outcomeMap }));
    }
  }, []);

  // Fetch initial registry & state
  const loadData = useCallback(async (isInitial = true) => {
    if (isInitial) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);
    try {
      const [inds, chartFeat, optCtx, preds] = await Promise.allSettled([
        api.getResearchIndicators(),
        api.getResearchFeatures(instrument, timeframe),
        api.getResearchOptionsContext(instrument),
        api.listResearchPredictions({ instrument, limit: 30 }),
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
        await loadPredictionsWithOutcomes(preds.value);
      }

      // Calculate OMPI live
      const ompiRes = await api.calculateResearchIndicator('ompi', {
        instrument,
        timeframe,
      });
      setOmpiData(ompiRes);
      setLastUpdated(new Date());
    } catch (err: any) {
      console.error('Failed to load research data:', err);
      setError(err?.message || 'Failed to connect to Research Laboratory services');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [instrument, timeframe, loadPredictionsWithOutcomes]);

  useEffect(() => {
    loadData(true);
  }, [loadData]);

  // Auto-refresh interval
  useEffect(() => {
    if (!autoRefreshSecs || autoRefreshSecs <= 0) return;
    const interval = setInterval(() => {
      loadData(false);
    }, autoRefreshSecs * 1000);
    return () => clearInterval(interval);
  }, [autoRefreshSecs, loadData]);

  // Trigger custom OMPI recalculation
  const handleRecalculateOmpi = async () => {
    setCalculating(true);
    try {
      const res = await api.calculateResearchIndicator('ompi', {
        instrument,
        timeframe,
      });
      setOmpiData(res);
      setLastUpdated(new Date());
      setToastNotification({
        type: 'info',
        message: 'OMPI indicator recalculated successfully.',
      });
      setTimeout(() => setToastNotification(null), 3000);
    } catch (err: any) {
      setError(err?.message || 'Calculation error');
    } finally {
      setCalculating(false);
    }
  };

  // Run Cheap Validation Gate
  const handleRunBacktest = async () => {
    setBacktesting(true);
    setBacktestError(null);
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
      setBacktestError(err?.message || 'Backtest walk-forward evaluation failed');
    } finally {
      setBacktesting(false);
    }
  };

  // Open Log Prediction Modal with Validation
  const handleOpenLogModal = () => {
    const spotPrice = features?.current_price ?? ompiData?.current_price ?? null;
    if (!spotPrice) {
      setToastNotification({
        type: 'error',
        message: 'Cannot log prediction: Current spot price is missing. Rule N5 prevents logging dummy values.',
      });
      setTimeout(() => setToastNotification(null), 5000);
      return;
    }
    setShowLogConfirmModal(true);
  };

  // Commit Immutable Prediction (§26, Rule N5)
  const handleConfirmLogPrediction = async () => {
    if (!ompiData) return;
    const spotPrice = features?.current_price ?? ompiData?.current_price ?? null;
    if (!spotPrice) {
      setToastNotification({
        type: 'error',
        message: 'Validation failed: Valid spot price required.',
      });
      setShowLogConfirmModal(false);
      return;
    }

    setLoggingPrediction(true);
    try {
      const pred = {
        prediction_id: `pred_${Date.now().toString(36)}`,
        indicator_id: ompiData.indicator_id,
        indicator_version: ompiData.version,
        instrument,
        timeframe,
        timestamp: new Date().toISOString(),
        current_price: spotPrice,
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
      setLoggedNotification('Prediction successfully recorded as immutable database row!');
      setTimeout(() => setLoggedNotification(null), 4000);
      setShowLogConfirmModal(false);
      const updated = await api.listResearchPredictions({ instrument, limit: 30 });
      if (Array.isArray(updated)) {
        await loadPredictionsWithOutcomes(updated);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to record prediction');
    } finally {
      setLoggingPrediction(false);
    }
  };

  // Measure Forward Outcome (Replaces alert() with inline badge & toast)
  const handleMeasurePrediction = async (predictionId: string) => {
    setMeasuringId(predictionId);
    try {
      const out = await api.measureResearchPrediction(predictionId);
      setOutcomes((prev) => ({ ...prev, [predictionId]: out }));
      setToastNotification({
        type: 'success',
        message: `Outcome measured: ${out.is_correct ? 'CORRECT' : 'INCORRECT'} (MFE: +${out.mfe ?? 0} pts, MAE: -${out.mae ?? 0} pts)`,
      });
      setTimeout(() => setToastNotification(null), 5000);
    } catch (e: any) {
      setToastNotification({
        type: 'error',
        message: `Measurement pending: ${e?.message || 'Forward candles not yet settled'}`,
      });
      setTimeout(() => setToastNotification(null), 5000);
    } finally {
      setMeasuringId(null);
    }
  };

  // Calculate Indicator from Registry (Replaces alert() with rich Modal)
  const handleCalculateRegistryIndicator = async (ind: any) => {
    setCalculatingIndId(ind.indicator_id);
    try {
      const res = await api.calculateResearchIndicator(ind.indicator_id, {
        instrument,
        timeframe,
      });
      setCalcModalData({
        indicatorName: ind.name,
        indicatorId: ind.indicator_id,
        result: res,
      });
    } catch (err: any) {
      setToastNotification({
        type: 'error',
        message: `Failed to calculate ${ind.name}: ${err?.message || 'Unknown error'}`,
      });
      setTimeout(() => setToastNotification(null), 5000);
    } finally {
      setCalculatingIndId(null);
    }
  };

  // Score color helper
  const getScoreColor = (score: number) => {
    if (score >= 20) return 'text-emerald-600 dark:text-emerald-400';
    if (score <= -20) return 'text-rose-600 dark:text-rose-400';
    return 'text-amber-600 dark:text-amber-400';
  };

  const getPressureBg = (score: number) => {
    if (score > 0) return 'bg-emerald-500/10 dark:bg-emerald-500/20 border-emerald-500/30 text-emerald-700 dark:text-emerald-300';
    if (score < 0) return 'bg-rose-500/10 dark:bg-rose-500/20 border-rose-500/30 text-rose-700 dark:text-rose-300';
    return 'bg-muted border-border text-muted-foreground';
  };

  // Gauge bar geometry
  const scoreVal = ompiData?.score ?? 0;
  const isNegative = scoreVal < 0;
  const barWidthPct = Math.min(50, (Math.abs(scoreVal) / 100) * 50);
  const barLeftPct = isNegative ? 50 - barWidthPct : 50;

  // Data quality status computation (§5)
  const dataQuality = useMemo(() => {
    if (error && !ompiData) return { status: 'FAILED', label: 'Feed Offline / Error', color: 'bg-rose-500 text-rose-700 dark:text-rose-300' };
    if (!optionsCtx?.available || ompiData?.data_quality === 'DEGRADED') {
      return { status: 'DEGRADED', label: 'Options Degraded (Synthetic Fallback)', color: 'bg-amber-500 text-amber-700 dark:text-amber-300' };
    }
    return { status: 'LIVE', label: 'Live Research Feed (Options Active)', color: 'bg-emerald-500 text-emerald-700 dark:text-emerald-300' };
  }, [optionsCtx, ompiData, error]);

  // Prediction summary metrics (§3)
  const predictionStats = useMemo(() => {
    const total = predictions.length;
    const measuredEntries = Object.values(outcomes);
    const measuredCount = measuredEntries.length;
    const correctCount = measuredEntries.filter((o: any) => o.is_correct).length;
    const winRate = measuredCount > 0 ? Math.round((correctCount / measuredCount) * 100) : null;
    const avgMfe = measuredCount > 0
      ? (measuredEntries.reduce((acc: number, o: any) => acc + (o.mfe || 0), 0) / measuredCount).toFixed(1)
      : null;
    return { total, measuredCount, correctCount, winRate, avgMfe };
  }, [predictions, outcomes]);

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-12">
      {/* Toast Notification */}
      {toastNotification && (
        <div
          role="status"
          aria-live="polite"
          className={`fixed top-4 right-4 z-50 p-4 rounded-xl shadow-lg border flex items-center gap-3 max-w-md transition-all animate-in fade-in slide-in-from-top-3 ${
            toastNotification.type === 'success'
              ? 'bg-emerald-500/10 dark:bg-emerald-950/80 border-emerald-500/30 text-emerald-800 dark:text-emerald-200'
              : toastNotification.type === 'error'
              ? 'bg-rose-500/10 dark:bg-rose-950/80 border-rose-500/30 text-rose-800 dark:text-rose-200'
              : 'bg-purple-500/10 dark:bg-purple-950/80 border-purple-500/30 text-purple-800 dark:text-purple-200'
          }`}
        >
          {toastNotification.type === 'success' && <CheckCircle2 className="w-5 h-5 shrink-0 text-emerald-600 dark:text-emerald-400" />}
          {toastNotification.type === 'error' && <AlertCircle className="w-5 h-5 shrink-0 text-rose-600 dark:text-rose-400" />}
          {toastNotification.type === 'info' && <Info className="w-5 h-5 shrink-0 text-purple-600 dark:text-purple-400" />}
          <span className="text-xs font-semibold flex-1">{toastNotification.message}</span>
          <button
            onClick={() => setToastNotification(null)}
            className="p-1 hover:bg-black/5 dark:hover:bg-white/5 rounded-md transition-colors"
            aria-label="Dismiss notification"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Header Banner */}
      <header className="rounded-2xl border border-border bg-card shadow-sm p-6 space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-600 dark:text-purple-400 shrink-0">
                <FlaskConical className="w-5 h-5" />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-xl md:text-2xl font-bold tracking-tight text-foreground">
                    Chart Intelligence & Indicator Research Laboratory
                  </h1>
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-500/15 text-purple-700 dark:text-purple-300 border border-purple-500/30">
                    Phases 0–7 Active
                  </span>
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30">
                    Non-Production Isolated
                  </span>
                </div>
                <p className="text-xs md:text-sm text-muted-foreground mt-0.5">
                  Analytical research-first laboratory for proprietary indicators (OMPI), point-in-time features, and cheap validation backtesting.
                </p>
              </div>
            </div>
          </div>

          {/* Instrument & Timeframe Selector with Keyboard Accessibility (§13) */}
          <div className="flex flex-wrap items-center gap-2.5">
            {/* Instrument Buttons */}
            <div role="tablist" aria-label="Select Instrument" className="flex rounded-lg bg-muted p-1 border border-border">
              {['NIFTY 50', 'BANKNIFTY', 'SENSEX'].map((inst) => (
                <button
                  key={inst}
                  role="tab"
                  aria-selected={instrument === inst}
                  aria-label={`Select ${inst}`}
                  onClick={() => setInstrument(inst)}
                  className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 ${
                    instrument === inst
                      ? 'bg-primary text-primary-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {inst}
                </button>
              ))}
            </div>

            {/* Timeframe Buttons */}
            <div role="tablist" aria-label="Select Timeframe" className="flex rounded-lg bg-muted p-1 border border-border">
              {['1m', '5m', '15m', '1h', '1D'].map((tf) => (
                <button
                  key={tf}
                  role="tab"
                  aria-selected={timeframe === tf}
                  aria-label={`Select timeframe ${tf}`}
                  onClick={() => setTimeframe(tf)}
                  className={`px-2.5 py-1.5 rounded-md text-xs font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 ${
                    timeframe === tf
                      ? 'bg-card text-foreground font-bold shadow-sm border border-border'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {tf}
                </button>
              ))}
            </div>

            {/* Auto-Refresh & Refresh Control (§9) */}
            <div className="flex items-center gap-1.5">
              <select
                value={autoRefreshSecs}
                onChange={(e) => setAutoRefreshSecs(Number(e.target.value))}
                aria-label="Auto-refresh frequency"
                className="h-8 text-xs bg-muted border border-border text-muted-foreground hover:text-foreground rounded-lg px-2 focus-visible:ring-2 focus-visible:ring-purple-500 outline-none"
                title="Auto-refresh frequency"
              >
                <option value={0}>Auto: Off</option>
                <option value={15}>Auto: 15s</option>
                <option value={30}>Auto: 30s</option>
                <option value={60}>Auto: 60s</option>
              </select>

              <button
                onClick={() => loadData(false)}
                disabled={loading || refreshing}
                className="p-2 rounded-lg bg-muted hover:bg-muted/80 border border-border text-muted-foreground hover:text-foreground transition-colors focus-visible:ring-2 focus-visible:ring-purple-500"
                title={lastUpdated ? `Last updated ${lastUpdated.toLocaleTimeString('en-IN')}. Click to refresh.` : 'Refresh Data'}
                aria-label="Refresh Data"
              >
                <RefreshCw className={`w-4 h-4 ${refreshing || loading ? 'animate-spin text-purple-500' : ''}`} />
              </button>
            </div>
          </div>
        </div>

        {/* Live Context Quick Bar - No bogus fallbacks (§6) & Surfaced Data Quality (§5) */}
        <div className="pt-3 border-t border-border flex flex-wrap items-center justify-between text-xs gap-3">
          <div className="flex flex-wrap items-center gap-6">
            <div>
              <span className="text-muted-foreground">Spot Price: </span>
              {loading && !features ? (
                <span className="inline-block w-16 h-3.5 bg-muted rounded animate-pulse" />
              ) : (
                <span className="font-mono font-bold text-foreground">
                  {features?.current_price ? `₹${features.current_price.toLocaleString('en-IN')}` : '—'}
                </span>
              )}
            </div>

            <div>
              <span className="text-muted-foreground">Market Regime: </span>
              {loading && !features ? (
                <span className="inline-block w-16 h-3.5 bg-muted rounded animate-pulse" />
              ) : (
                <span className="font-semibold text-purple-600 dark:text-purple-400">
                  {features?.regime || '—'}
                </span>
              )}
            </div>

            <div>
              <span className="text-muted-foreground">Session (IST): </span>
              {loading && !features ? (
                <span className="inline-block w-12 h-3.5 bg-muted rounded animate-pulse" />
              ) : (
                <span className="font-semibold text-foreground">
                  {features?.session || '—'}
                </span>
              )}
            </div>

            <div>
              <span className="text-muted-foreground">ATM IV: </span>
              {loading && !optionsCtx ? (
                <span className="inline-block w-12 h-3.5 bg-muted rounded animate-pulse" />
              ) : (
                <span className="font-mono font-semibold text-foreground">
                  {optionsCtx?.atm_iv != null ? `${optionsCtx.atm_iv}%` : '—'}
                </span>
              )}
            </div>

            <div>
              <span className="text-muted-foreground">PCR (OI): </span>
              {loading && !optionsCtx ? (
                <span className="inline-block w-10 h-3.5 bg-muted rounded animate-pulse" />
              ) : (
                <span className="font-mono font-semibold text-foreground">
                  {optionsCtx?.pcr_oi != null ? Number(optionsCtx.pcr_oi).toFixed(2) : '—'}
                </span>
              )}
            </div>

            {lastUpdated && (
              <div className="hidden lg:block text-muted-foreground text-[11px] font-mono">
                Updated {lastUpdated.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </div>
            )}
          </div>

          {/* Dynamic Data Quality Badge (§5) */}
          <div className="flex items-center gap-2">
            <span className={`inline-block w-2.5 h-2.5 rounded-full ${dataQuality.color.split(' ')[0]} animate-pulse`} />
            <span className="font-semibold text-foreground text-xs">{dataQuality.label}</span>
          </div>
        </div>
      </header>

      {/* Dismissable Top-level Error Banner (§10) */}
      {error && (
        <div
          role="alert"
          className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-700 dark:text-rose-300 text-sm flex items-center justify-between gap-2"
        >
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={() => setError(null)}
            className="p-1 hover:bg-rose-500/20 rounded-md transition-colors"
            aria-label="Dismiss error"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Notification Toast for Prediction Logging */}
      {loggedNotification && (
        <div
          role="status"
          className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-700 dark:text-emerald-300 text-sm flex items-center gap-2"
        >
          <CheckCircle2 className="w-4 h-4" />
          <span>{loggedNotification}</span>
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
            badgeClassName:
              ompiData?.score >= 20
                ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                : ompiData?.score <= -20
                ? 'bg-rose-500/15 text-rose-700 dark:text-rose-300'
                : 'bg-muted text-muted-foreground',
            content: (
              <div className="space-y-6">
                {/* OMPI Primary Gauge Card */}
                <div className="rounded-2xl bg-card border border-border p-6 shadow-sm">
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 pb-6 border-b border-border">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-xl font-bold text-foreground">
                          Option Market Pressure Index (OMPI) v0.1
                        </h2>
                        <span className="px-2 py-0.5 rounded text-xs font-mono font-semibold bg-purple-500/15 text-purple-700 dark:text-purple-300 border border-purple-500/30">
                          PROPRIETARY
                        </span>
                        {ompiData?.data_quality === 'DEGRADED' && (
                          <span className="px-2 py-0.5 rounded text-xs font-semibold bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30 flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3" /> Degraded Feed
                          </span>
                        )}
                      </div>
                      <p className="text-xs md:text-sm text-muted-foreground mt-1 max-w-2xl">
                        Synthesizes price momentum, options positioning, volume participation, volatility regime, and theta friction into a normalized -100 to +100 pressure metric.
                      </p>
                    </div>

                    <div className="flex items-center gap-3">
                      <button
                        onClick={handleRecalculateOmpi}
                        disabled={calculating || loading}
                        className="px-4 py-2 rounded-xl bg-muted hover:bg-muted/80 text-foreground text-xs font-semibold flex items-center gap-2 transition-all border border-border focus-visible:ring-2 focus-visible:ring-purple-500 disabled:opacity-50"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${calculating ? 'animate-spin' : ''}`} />
                        {calculating ? 'Recalculating...' : 'Recalculate'}
                      </button>

                      <button
                        onClick={handleOpenLogModal}
                        disabled={loading || !ompiData}
                        className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold flex items-center gap-2 shadow-sm transition-all focus-visible:ring-2 focus-visible:ring-purple-500 disabled:opacity-50"
                      >
                        <BookmarkPlus className="w-3.5 h-3.5" />
                        Log Prediction
                      </button>
                    </div>
                  </div>

                  {/* Skeleton Loading State for OMPI (§2) */}
                  {loading && !ompiData ? (
                    <div className="pt-6 space-y-6 animate-pulse">
                      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                        <div className="md:col-span-2 rounded-xl bg-muted/40 p-6 h-52" />
                        <div className="rounded-xl bg-muted/40 p-5 h-52" />
                        <div className="rounded-xl bg-muted/40 p-5 h-52" />
                      </div>
                      <div className="pt-6 border-t border-border">
                        <div className="h-4 w-48 bg-muted rounded mb-4" />
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
                          {[1, 2, 3, 4, 5].map((i) => (
                            <div key={i} className="h-24 bg-muted/40 rounded-xl" />
                          ))}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <>
                      {/* Pressure Metric Row */}
                      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 pt-6">
                        {/* Main Score & Direction */}
                        <div className="md:col-span-2 rounded-xl bg-muted/40 border border-border/70 p-6 flex flex-col justify-between">
                          <div className="flex items-center justify-between">
                            <span className="text-xs uppercase font-semibold text-muted-foreground tracking-wider">
                              Composite Pressure Index
                            </span>
                            <span
                              className={`px-2.5 py-1 rounded-full text-xs font-bold ${
                                ompiData?.direction === 'BULLISH'
                                  ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30'
                                  : ompiData?.direction === 'BEARISH'
                                  ? 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border border-rose-500/30'
                                  : 'bg-muted text-muted-foreground border border-border'
                              }`}
                            >
                              {ompiData?.direction || 'NEUTRAL'}
                            </span>
                          </div>

                          <div className="my-4">
                            <div className="flex items-baseline gap-2">
                              <span className={`text-5xl font-black font-mono tracking-tight ${getScoreColor(ompiData?.score || 0)}`}>
                                {ompiData ? (ompiData.score > 0 ? `+${ompiData.score}` : ompiData.score) : '0.00'}
                              </span>
                              <span className="text-muted-foreground text-sm font-semibold">/ ±100</span>
                            </div>

                            {/* Visual Slider / Bidirectional Gauge Bar */}
                            <div className="relative mt-5 h-3.5 bg-muted rounded-full overflow-hidden border border-border">
                              <div className="absolute left-1/2 top-0 bottom-0 w-0.5 bg-foreground/40 z-10" />
                              <div
                                className={`absolute top-0 bottom-0 transition-all duration-500 ${
                                  isNegative
                                    ? 'bg-gradient-to-r from-rose-500 to-rose-600 dark:from-rose-400 dark:to-rose-600'
                                    : 'bg-gradient-to-r from-emerald-500 to-emerald-600 dark:from-emerald-400 dark:to-emerald-600'
                                }`}
                                style={{
                                  left: `${barLeftPct}%`,
                                  width: `${barWidthPct}%`,
                                }}
                              />
                            </div>

                            <div className="relative text-[11px] text-muted-foreground font-mono mt-2 h-4">
                              <span className="absolute left-0">-100 Bearish</span>
                              <span className="absolute left-1/2 -translate-x-1/2 font-semibold text-foreground/80">0 Neutral</span>
                              <span className="absolute right-0">+100 Bullish</span>
                            </div>
                          </div>

                          <div className="flex items-center justify-between text-xs text-muted-foreground pt-3 border-t border-border/70">
                            <span>Confidence: <strong className="text-foreground font-mono">{Math.round((ompiData?.confidence || 0) * 100)}%</strong></span>
                            <span>Horizon: <strong className="text-foreground">15m (5 candles)</strong></span>
                          </div>
                        </div>

                        {/* Target & Invalidation Levels - Fixed for NEUTRAL (§7) */}
                        <div className="rounded-xl bg-muted/40 border border-border/70 p-5 flex flex-col justify-between">
                          <span className="text-xs uppercase font-semibold text-muted-foreground tracking-wider">
                            Targets & Invalidation
                          </span>
                          <div className="space-y-4 my-2">
                            <div>
                              <div className="text-[11px] text-emerald-600 dark:text-emerald-400 flex items-center gap-1 font-semibold">
                                <TrendingUp className="w-3.5 h-3.5" /> Favorable Target (+1.6 ATR)
                              </div>
                              <div className="text-xl font-bold font-mono text-foreground mt-0.5">
                                {ompiData?.target_price ? `₹${ompiData.target_price.toLocaleString('en-IN')}` : '—'}
                              </div>
                            </div>
                            <div>
                              <div className="text-[11px] text-rose-600 dark:text-rose-400 flex items-center gap-1 font-semibold">
                                <TrendingDown className="w-3.5 h-3.5" /> Invalidation Stop (-1.0 ATR)
                              </div>
                              <div className="text-xl font-bold font-mono text-foreground mt-0.5">
                                {ompiData?.invalidation_price ? `₹${ompiData.invalidation_price.toLocaleString('en-IN')}` : '—'}
                              </div>
                            </div>
                          </div>
                          <div className="text-[10px] text-muted-foreground">
                            {ompiData?.direction === 'NEUTRAL'
                              ? 'Neutral signal — no directional target assigned.'
                              : 'Calculated strictly without lookahead bias.'}
                          </div>
                        </div>

                        {/* Options Context Quick Stats - No hardcoded fallbacks (§6) */}
                        <div className="rounded-xl bg-muted/40 border border-border/70 p-5 flex flex-col justify-between">
                          <span className="text-xs uppercase font-semibold text-muted-foreground tracking-wider">
                            Options Context
                          </span>
                          <div className="space-y-2 text-xs">
                            <div className="flex justify-between py-1.5 border-b border-border/60">
                              <span className="text-muted-foreground">Put-Call Ratio:</span>
                              <span className="font-mono font-bold text-foreground">
                                {optionsCtx?.pcr_oi != null ? Number(optionsCtx.pcr_oi).toFixed(2) : '—'}
                              </span>
                            </div>
                            <div className="flex justify-between py-1.5 border-b border-border/60">
                              <span className="text-muted-foreground">Call Wall (Res):</span>
                              <span className="font-mono font-bold text-rose-600 dark:text-rose-400">
                                {optionsCtx?.call_wall ? `₹${optionsCtx.call_wall.toLocaleString('en-IN')}` : '—'}
                              </span>
                            </div>
                            <div className="flex justify-between py-1.5 border-b border-border/60">
                              <span className="text-muted-foreground">Put Wall (Sup):</span>
                              <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
                                {optionsCtx?.put_wall ? `₹${optionsCtx.put_wall.toLocaleString('en-IN')}` : '—'}
                              </span>
                            </div>
                            <div className="flex justify-between py-1.5">
                              <span className="text-muted-foreground">Max Pain Strike:</span>
                              <span className="font-mono font-bold text-amber-600 dark:text-amber-400">
                                {optionsCtx?.max_pain ? `₹${optionsCtx.max_pain.toLocaleString('en-IN')}` : '—'}
                              </span>
                            </div>
                          </div>
                          <div className="text-[10px] text-muted-foreground">
                            Days to Expiry: {optionsCtx?.days_to_expiry != null ? `${optionsCtx.days_to_expiry}d` : '—'}
                          </div>
                        </div>
                      </div>

                      {/* Component Breakdown (§17) */}
                      <div className="mt-8 pt-6 border-t border-border">
                        <div className="flex items-center justify-between mb-4">
                          <div>
                            <h3 className="text-sm font-bold uppercase tracking-wider text-foreground">
                              Full Transparency Sub-Pressures (§17)
                            </h3>
                            <p className="text-xs text-muted-foreground">
                              Zero black-box logic: each of the 5 pressure vectors is independently normalized and weighted.
                            </p>
                          </div>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
                          {/* P_dir */}
                          <div className="rounded-xl bg-card border border-border p-3.5 space-y-2 shadow-xs">
                            <div className="flex justify-between text-xs">
                              <span className="text-foreground font-semibold">1. Directional (P_dir)</span>
                              <span className="text-[10px] text-muted-foreground font-mono font-semibold">wt: 30%</span>
                            </div>
                            <div className={`px-2 py-1 rounded text-sm font-mono font-bold border ${getPressureBg(ompiData?.component_values?.p_dir || 0)}`}>
                              {ompiData?.component_values?.p_dir ?? '—'}
                            </div>
                            <p className="text-[11px] text-muted-foreground leading-snug">EMA20/50 structures + Wilder RSI tilt</p>
                          </div>

                          {/* P_opt */}
                          <div className="rounded-xl bg-card border border-border p-3.5 space-y-2 shadow-xs">
                            <div className="flex justify-between text-xs">
                              <span className="text-foreground font-semibold">2. Options (P_opt)</span>
                              <span className="text-[10px] text-muted-foreground font-mono font-semibold">wt: 25%</span>
                            </div>
                            <div className={`px-2 py-1 rounded text-sm font-mono font-bold border ${getPressureBg(ompiData?.component_values?.p_opt || 0)}`}>
                              {ompiData?.component_values?.p_opt ?? '—'}
                            </div>
                            <p className="text-[11px] text-muted-foreground leading-snug">PCR deviation, wall proximity, max pain gravity</p>
                          </div>

                          {/* P_part */}
                          <div className="rounded-xl bg-card border border-border p-3.5 space-y-2 shadow-xs">
                            <div className="flex justify-between text-xs">
                              <span className="text-foreground font-semibold">3. Participation (P_part)</span>
                              <span className="text-[10px] text-muted-foreground font-mono font-semibold">wt: 20%</span>
                            </div>
                            <div className={`px-2 py-1 rounded text-sm font-mono font-bold border ${getPressureBg(ompiData?.component_values?.p_part || 0)}`}>
                              {ompiData?.component_values?.p_part ?? '—'}
                            </div>
                            <p className="text-[11px] text-muted-foreground leading-snug">Relative volume surge & signed candle flow</p>
                          </div>

                          {/* P_vol */}
                          <div className="rounded-xl bg-card border border-border p-3.5 space-y-2 shadow-xs">
                            <div className="flex justify-between text-xs">
                              <span className="text-foreground font-semibold">4. Volatility (P_vol)</span>
                              <span className="text-[10px] text-muted-foreground font-mono font-semibold">wt: 15%</span>
                            </div>
                            <div className={`px-2 py-1 rounded text-sm font-mono font-bold border ${getPressureBg(ompiData?.component_values?.p_vol || 0)}`}>
                              {ompiData?.component_values?.p_vol ?? '—'}
                            </div>
                            <p className="text-[11px] text-muted-foreground leading-snug">Bollinger bandwidth squeeze & IV deviation</p>
                          </div>

                          {/* P_decay */}
                          <div className="rounded-xl bg-card border border-border p-3.5 space-y-2 shadow-xs">
                            <div className="flex justify-between text-xs">
                              <span className="text-foreground font-semibold">5. Decay (P_decay)</span>
                              <span className="text-[10px] text-muted-foreground font-mono font-semibold">wt: 10%</span>
                            </div>
                            <div className={`px-2 py-1 rounded text-sm font-mono font-bold border ${getPressureBg(ompiData?.component_values?.p_decay || 0)}`}>
                              {ompiData?.component_values?.p_decay ?? '—'}
                            </div>
                            <p className="text-[11px] text-muted-foreground leading-snug">ATM Theta burn friction relative to DTE</p>
                          </div>
                        </div>
                      </div>
                    </>
                  )}
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
                <div className="rounded-2xl bg-card border border-border p-6 shadow-sm">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-border">
                    <div>
                      <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
                        <ShieldAlert className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                        Cheap Validation Gate (§19, §20)
                      </h2>
                      <p className="text-xs md:text-sm text-muted-foreground mt-1">
                        Executes lightweight offline walk-forward evaluation with strict Point-In-Time (PIT) integrity and dynamic regime classification to determine if an indicator delivers statistically verifiable edge.
                      </p>
                    </div>

                    <div className="flex items-center gap-3">
                      <select
                        value={selectedValidatorInd}
                        onChange={(e) => setSelectedValidatorInd(e.target.value)}
                        className="px-3 py-2 rounded-xl bg-muted border border-border text-foreground text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-purple-500"
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
                        className="px-5 py-2 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-bold flex items-center gap-2 shadow-sm transition-all disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-purple-500"
                      >
                        {backtesting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 fill-current" />}
                        {backtesting ? 'Evaluating...' : 'Run Validation Gate'}
                      </button>
                    </div>
                  </div>

                  {/* Scoped Backtest Error Banner (§10) */}
                  {backtestError && (
                    <div className="mt-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-700 dark:text-rose-300 text-xs flex items-center justify-between">
                      <span>{backtestError}</span>
                      <button onClick={() => setBacktestError(null)} className="p-1 hover:bg-rose-500/20 rounded">
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}

                  {/* Results Panel */}
                  {experimentResult ? (
                    <div className="mt-6 space-y-6">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span
                            className={`px-3 py-1 rounded-full text-xs font-bold tracking-wide border ${
                              experimentResult.report?.is_statistically_significant
                                ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30'
                                : 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30'
                            }`}
                          >
                            {experimentResult.report?.is_statistically_significant
                              ? '[PASS: STATISTICALLY SIGNIFICANT]'
                              : '[FAIL: NOT STATISTICALLY SIGNIFICANT]'}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            Evaluated on <strong>{experimentResult.report?.sample_size}</strong> historical walk-forward points
                          </span>
                        </div>
                        <span className="text-xs text-muted-foreground font-mono">
                          Run ID: {experimentResult.run?.run_id}
                        </span>
                      </div>

                      {/* Primary Metrics Grid */}
                      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                        <div className="p-3.5 rounded-xl bg-muted/40 border border-border/70">
                          <span className="text-[11px] text-muted-foreground font-semibold">Indicator Accuracy</span>
                          <div className="text-2xl font-bold font-mono text-foreground mt-1">
                            {experimentResult.report?.accuracy}%
                          </div>
                          <span className="text-[10px] text-muted-foreground font-mono">
                            95% CI: [{experimentResult.report?.confidence_interval_95?.[0]}%, {experimentResult.report?.confidence_interval_95?.[1]}%]
                          </span>
                        </div>

                        <div className="p-3.5 rounded-xl bg-muted/40 border border-border/70">
                          <span className="text-[11px] text-muted-foreground font-semibold">Baseline Accuracy</span>
                          <div className="text-2xl font-bold font-mono text-muted-foreground mt-1">
                            {experimentResult.report?.baseline_accuracy}%
                          </div>
                          <span className="text-[10px] text-muted-foreground">Naive momentum</span>
                        </div>

                        <div className="p-3.5 rounded-xl bg-muted/40 border border-border/70">
                          <span className="text-[11px] text-muted-foreground font-semibold">Excess Accuracy</span>
                          <div
                            className={`text-2xl font-bold font-mono mt-1 ${
                              experimentResult.report?.excess_accuracy > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
                            }`}
                          >
                            {experimentResult.report?.excess_accuracy > 0 ? '+' : ''}{experimentResult.report?.excess_accuracy}%
                          </div>
                          <span className="text-[10px] text-muted-foreground">Alpha over baseline</span>
                        </div>

                        <div className="p-3.5 rounded-xl bg-muted/40 border border-border/70">
                          <span className="text-[11px] text-muted-foreground font-semibold">p-value</span>
                          <div className="text-2xl font-bold font-mono text-purple-600 dark:text-purple-300 mt-1">
                            {experimentResult.report?.p_value}
                          </div>
                          <span className="text-[10px] text-muted-foreground">Target &lt; 0.05</span>
                        </div>

                        <div className="p-3.5 rounded-xl bg-muted/40 border border-border/70">
                          <span className="text-[11px] text-muted-foreground font-semibold">Mean Favorable (MFE)</span>
                          <div className="text-2xl font-bold font-mono text-emerald-600 dark:text-emerald-400 mt-1">
                            {experimentResult.report?.mfe_mean} pts
                          </div>
                          <span className="text-[10px] text-muted-foreground">Average peak gain</span>
                        </div>

                        <div className="p-3.5 rounded-xl bg-muted/40 border border-border/70">
                          <span className="text-[11px] text-muted-foreground font-semibold">Mean Adverse (MAE)</span>
                          <div className="text-2xl font-bold font-mono text-rose-600 dark:text-rose-400 mt-1">
                            {experimentResult.report?.mae_mean} pts
                          </div>
                          <span className="text-[10px] text-muted-foreground">Average drawdown</span>
                        </div>
                      </div>

                      {/* Detailed Breakdowns */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                        {/* Session Breakdown */}
                        <div className="p-4 rounded-xl bg-muted/40 border border-border/70">
                          <h4 className="text-xs uppercase font-bold text-foreground tracking-wider mb-3">
                            Session Breakdown
                          </h4>
                          <div className="space-y-2 text-xs">
                            {Object.entries(experimentResult.report?.session_breakdown || {}).map(([sess, val]: any) => (
                              <div key={sess} className="flex justify-between py-1.5 border-b border-border/60">
                                <span className="text-muted-foreground font-medium">{sess}</span>
                                <div className="space-x-3">
                                  <span className="text-muted-foreground">{val.sample_size} samples</span>
                                  <span className="font-mono font-bold text-foreground">{val.accuracy}%</span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Regime Breakdown */}
                        <div className="p-4 rounded-xl bg-muted/40 border border-border/70">
                          <h4 className="text-xs uppercase font-bold text-foreground tracking-wider mb-3">
                            Regime Breakdown
                          </h4>
                          <div className="space-y-2 text-xs">
                            {Object.entries(experimentResult.report?.regime_breakdown || {}).map(([reg, val]: any) => (
                              <div key={reg} className="flex justify-between py-1.5 border-b border-border/60">
                                <span className="text-muted-foreground font-medium">{reg}</span>
                                <div className="space-x-3">
                                  <span className="text-muted-foreground">{val.sample_size} samples</span>
                                  <span className="font-mono font-bold text-foreground">{val.accuracy}%</span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-8 text-center py-12 rounded-xl bg-muted/30 border border-border/70">
                      <Activity className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                      <p className="text-sm font-semibold text-foreground">No Validation Run Selected</p>
                      <p className="text-xs text-muted-foreground mt-1">
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
                  <h3 className="text-sm font-bold uppercase tracking-wider text-foreground">
                    Registered Research Indicators (§13, §14)
                  </h3>
                  <span className="text-xs text-muted-foreground">
                    Standardized output contract (§46) allows interchangeable comparison.
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {indicators.map((ind) => (
                    <div
                      key={ind.indicator_id}
                      className="rounded-xl bg-card border border-border p-5 space-y-3 hover:border-purple-500/50 shadow-xs transition-all flex flex-col justify-between"
                    >
                      <div>
                        <div className="flex items-start justify-between gap-2">
                          <h4 className="font-bold text-foreground text-sm">{ind.name}</h4>
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              ind.category === 'PROPRIETARY'
                                ? 'bg-purple-500/15 text-purple-700 dark:text-purple-300 border border-purple-500/30'
                                : 'bg-muted text-muted-foreground'
                            }`}
                          >
                            {ind.category}
                          </span>
                        </div>
                        <div className="text-[11px] text-muted-foreground font-mono mt-1">
                          ID: {ind.indicator_id} | v{ind.current_version}
                        </div>
                        <p className="text-xs text-muted-foreground mt-2 line-clamp-2">
                          {ind.description || ind.formula_summary}
                        </p>
                      </div>

                      <div className="pt-3 border-t border-border flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">
                          Lifecycle: <strong className="text-foreground">{ind.lifecycle}</strong>
                        </span>
                        {/* Calculate Button - Now triggers sleek Modal (§1) */}
                        <button
                          onClick={() => handleCalculateRegistryIndicator(ind)}
                          disabled={calculatingIndId === ind.indicator_id}
                          className="text-purple-600 dark:text-purple-400 hover:underline font-semibold flex items-center gap-1 focus-visible:ring-2 focus-visible:ring-purple-500 rounded px-1 disabled:opacity-50"
                        >
                          {calculatingIndId === ind.indicator_id ? (
                            <>
                              <RefreshCw className="w-3 h-3 animate-spin" /> Calculating...
                            </>
                          ) : (
                            <>
                              Calculate <ChevronRight className="w-3.5 h-3.5" />
                            </>
                          )}
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
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-bold uppercase tracking-wider text-foreground">
                      Immutable Prediction Journal & Outcomes (§26, N5)
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      Predictions are written once and never modified. Outcomes are measured and appended forward once the horizon elapses.
                    </p>
                  </div>

                  <button
                    onClick={handleOpenLogModal}
                    disabled={!ompiData}
                    className="self-start sm:self-auto px-3.5 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-xs transition-all disabled:opacity-50"
                  >
                    <BookmarkPlus className="w-3.5 h-3.5" />
                    Log Current Signal
                  </button>
                </div>

                {/* Performance Summary Bar (§3) */}
                {predictions.length > 0 && (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 rounded-xl bg-card border border-border shadow-xs text-xs">
                    <div>
                      <span className="text-muted-foreground">Total Predictions</span>
                      <div className="text-lg font-bold font-mono text-foreground mt-0.5">
                        {predictionStats.total}
                      </div>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Measured Outcomes</span>
                      <div className="text-lg font-bold font-mono text-foreground mt-0.5">
                        {predictionStats.measuredCount} / {predictionStats.total}
                      </div>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Directional Win Rate</span>
                      <div
                        className={`text-lg font-bold font-mono mt-0.5 ${
                          predictionStats.winRate !== null
                            ? predictionStats.winRate >= 50
                              ? 'text-emerald-600 dark:text-emerald-400'
                              : 'text-rose-600 dark:text-rose-400'
                            : 'text-muted-foreground'
                        }`}
                      >
                        {predictionStats.winRate !== null ? `${predictionStats.winRate}%` : '—'}
                      </div>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Average Peak Gain (MFE)</span>
                      <div className="text-lg font-bold font-mono text-emerald-600 dark:text-emerald-400 mt-0.5">
                        {predictionStats.avgMfe !== null ? `+${predictionStats.avgMfe} pts` : '—'}
                      </div>
                    </div>
                  </div>
                )}

                {/* Predictions & Outcomes Table - Responsive & Complete (§3, §8) */}
                {predictions.length > 0 ? (
                  <div className="rounded-xl border border-border overflow-hidden bg-card shadow-xs">
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[920px] text-left text-xs">
                        <thead className="bg-muted/60 text-muted-foreground uppercase font-semibold border-b border-border">
                          <tr>
                            <th className="p-3">Time</th>
                            <th className="p-3">Indicator</th>
                            <th className="p-3">Direction</th>
                            <th className="p-3">Score</th>
                            <th className="p-3">Entry</th>
                            <th className="p-3">Target</th>
                            <th className="p-3">Invalidation</th>
                            <th className="p-3">Outcome</th>
                            <th className="p-3">MFE / MAE</th>
                            <th className="p-3 text-right">Action</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/60 font-mono">
                          {predictions.map((p) => {
                            const outcome = outcomes[p.prediction_id];
                            const isMeasuring = measuringId === p.prediction_id;

                            return (
                              <tr key={p.prediction_id} className="hover:bg-muted/30 transition-colors">
                                <td className="p-3 text-muted-foreground whitespace-nowrap">
                                  {new Date(p.timestamp).toLocaleTimeString('en-IN', {
                                    hour: '2-digit',
                                    minute: '2-digit',
                                  })}
                                </td>
                                <td className="p-3 font-semibold text-foreground uppercase whitespace-nowrap">
                                  {p.indicator_id}
                                </td>
                                <td className="p-3 whitespace-nowrap">
                                  <span
                                    className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                      p.direction === 'BULLISH'
                                        ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                                        : p.direction === 'BEARISH'
                                        ? 'bg-rose-500/15 text-rose-700 dark:text-rose-300'
                                        : 'bg-muted text-muted-foreground'
                                    }`}
                                  >
                                    {p.direction}
                                  </span>
                                </td>
                                <td className="p-3 text-foreground whitespace-nowrap">{p.score}</td>
                                <td className="p-3 text-foreground font-semibold whitespace-nowrap">
                                  ₹{p.current_price?.toLocaleString('en-IN') ?? '—'}
                                </td>
                                <td className="p-3 text-emerald-600 dark:text-emerald-400 font-semibold whitespace-nowrap">
                                  {p.target_price ? `₹${p.target_price.toLocaleString('en-IN')}` : '—'}
                                </td>
                                <td className="p-3 text-rose-600 dark:text-rose-400 font-semibold whitespace-nowrap">
                                  {p.invalidation_price ? `₹${p.invalidation_price.toLocaleString('en-IN')}` : '—'}
                                </td>

                                {/* Dedicated Outcome Column (§3) */}
                                <td className="p-3 whitespace-nowrap">
                                  {outcome ? (
                                    <span
                                      className={`px-2 py-0.5 rounded text-[10px] font-bold flex items-center gap-1 w-fit ${
                                        outcome.is_correct
                                          ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30'
                                          : 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border border-rose-500/30'
                                      }`}
                                    >
                                      {outcome.is_correct ? <Check className="w-3 h-3" /> : <X className="w-3 h-3" />}
                                      {outcome.is_correct ? 'CORRECT' : 'INCORRECT'}
                                    </span>
                                  ) : (
                                    <span className="text-[11px] text-muted-foreground font-sans">Pending</span>
                                  )}
                                </td>

                                {/* MFE / MAE Realized Column (§3) */}
                                <td className="p-3 whitespace-nowrap text-[11px]">
                                  {outcome ? (
                                    <div className="space-x-1.5">
                                      <span className="text-emerald-600 dark:text-emerald-400 font-bold">
                                        +{outcome.mfe ?? 0}
                                      </span>
                                      <span className="text-muted-foreground">/</span>
                                      <span className="text-rose-600 dark:text-rose-400 font-bold">
                                        -{outcome.mae ?? 0}
                                      </span>
                                    </div>
                                  ) : (
                                    <span className="text-muted-foreground">—</span>
                                  )}
                                </td>

                                {/* Measure Action Button - Replaced alert() (§1) */}
                                <td className="p-3 text-right whitespace-nowrap">
                                  <button
                                    onClick={() => handleMeasurePrediction(p.prediction_id)}
                                    disabled={isMeasuring}
                                    className="px-2.5 py-1 rounded bg-muted hover:bg-muted/80 text-foreground text-[11px] font-sans border border-border focus-visible:ring-2 focus-visible:ring-purple-500 disabled:opacity-50"
                                  >
                                    {isMeasuring ? (
                                      <span className="flex items-center gap-1">
                                        <RefreshCw className="w-3 h-3 animate-spin" /> Measuring...
                                      </span>
                                    ) : outcome ? (
                                      'Re-measure'
                                    ) : (
                                      'Measure'
                                    )}
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-12 rounded-xl bg-card border border-border text-muted-foreground text-xs shadow-xs">
                    No predictions recorded yet for {instrument}. Click "Log Current Signal" to record an immutable prediction.
                  </div>
                )}
              </div>
            ),
          },
        ]}
      />

      {/* Confirmation Modal for Logging Immutable Predictions (§4) */}
      {showLogConfirmModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-log-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in"
        >
          <div className="rounded-2xl bg-card border border-border max-w-lg w-full p-6 shadow-2xl space-y-5 animate-in zoom-in-95">
            <div className="flex items-start justify-between">
              <div>
                <h3 id="confirm-log-title" className="text-lg font-bold text-foreground flex items-center gap-2">
                  <BookmarkPlus className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                  Confirm Immutable Prediction
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Research Engine Rule N5 Compliance Review
                </p>
              </div>
              <button
                onClick={() => setShowLogConfirmModal(false)}
                className="p-1 text-muted-foreground hover:text-foreground rounded-lg transition-colors"
                aria-label="Close modal"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Immutability Caution Banner */}
            <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-800 dark:text-amber-200 text-xs flex items-start gap-2.5">
              <AlertTriangle className="w-4 h-4 shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
              <div>
                <strong className="font-semibold block">Permanent & Non-Updatable</strong>
                Once committed, this prediction row cannot be edited or deleted. It will permanently track forward predictive accuracy in the research audit log.
              </div>
            </div>

            {/* Preview Grid */}
            <div className="grid grid-cols-2 gap-3 p-4 rounded-xl bg-muted/40 border border-border text-xs">
              <div>
                <span className="text-muted-foreground">Instrument & TF:</span>
                <div className="font-bold text-foreground mt-0.5">
                  {instrument} ({timeframe})
                </div>
              </div>

              <div>
                <span className="text-muted-foreground">Direction:</span>
                <div className="mt-0.5">
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      ompiData?.direction === 'BULLISH'
                        ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                        : ompiData?.direction === 'BEARISH'
                        ? 'bg-rose-500/15 text-rose-700 dark:text-rose-300'
                        : 'bg-muted text-muted-foreground'
                    }`}
                  >
                    {ompiData?.direction || 'NEUTRAL'}
                  </span>
                </div>
              </div>

              <div>
                <span className="text-muted-foreground">OMPI Score:</span>
                <div className={`font-mono font-bold mt-0.5 ${getScoreColor(ompiData?.score || 0)}`}>
                  {ompiData?.score ?? 0} (Conf: {Math.round((ompiData?.confidence || 0) * 100)}%)
                </div>
              </div>

              <div>
                <span className="text-muted-foreground">Spot Entry Price:</span>
                <div className="font-mono font-bold text-foreground mt-0.5">
                  ₹{(features?.current_price ?? ompiData?.current_price)?.toLocaleString('en-IN') ?? '—'}
                </div>
              </div>

              <div>
                <span className="text-muted-foreground">Target Price (+1.6 ATR):</span>
                <div className="font-mono font-semibold text-emerald-600 dark:text-emerald-400 mt-0.5">
                  {ompiData?.target_price ? `₹${ompiData.target_price.toLocaleString('en-IN')}` : 'None (Neutral)'}
                </div>
              </div>

              <div>
                <span className="text-muted-foreground">Invalidation Stop (-1.0 ATR):</span>
                <div className="font-mono font-semibold text-rose-600 dark:text-rose-400 mt-0.5">
                  {ompiData?.invalidation_price ? `₹${ompiData.invalidation_price.toLocaleString('en-IN')}` : 'None (Neutral)'}
                </div>
              </div>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setShowLogConfirmModal(false)}
                disabled={loggingPrediction}
                className="px-4 py-2 rounded-xl bg-muted hover:bg-muted/80 text-foreground text-xs font-semibold transition-colors border border-border"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmLogPrediction}
                disabled={loggingPrediction}
                className="px-5 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold flex items-center gap-2 shadow-sm transition-all disabled:opacity-50"
              >
                {loggingPrediction ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                {loggingPrediction ? 'Committing...' : 'Confirm & Commit Permanently'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Indicator Calculation Result Modal (Replaces alert() from Registry (§1)) */}
      {calcModalData && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="calc-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in"
        >
          <div className="rounded-2xl bg-card border border-border max-w-md w-full p-6 shadow-2xl space-y-5 animate-in zoom-in-95">
            <div className="flex items-start justify-between">
              <div>
                <h3 id="calc-modal-title" className="text-lg font-bold text-foreground">
                  {calcModalData.indicatorName}
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Calculated for {instrument} ({timeframe})
                </p>
              </div>
              <button
                onClick={() => setCalcModalData(null)}
                className="p-1 text-muted-foreground hover:text-foreground rounded-lg transition-colors"
                aria-label="Close modal"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Output Display */}
            <div className="p-4 rounded-xl bg-muted/40 border border-border space-y-3 text-xs">
              <div className="flex items-center justify-between pb-3 border-b border-border/60">
                <span className="text-muted-foreground">Direction:</span>
                <span
                  className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${
                    calcModalData.result?.direction === 'BULLISH'
                      ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30'
                      : calcModalData.result?.direction === 'BEARISH'
                      ? 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border border-rose-500/30'
                      : 'bg-muted text-muted-foreground border border-border'
                  }`}
                >
                  {calcModalData.result?.direction || 'NEUTRAL'}
                </span>
              </div>

              <div className="flex items-center justify-between py-1 border-b border-border/60">
                <span className="text-muted-foreground">Normalized Score:</span>
                <span className={`font-mono font-bold text-base ${getScoreColor(calcModalData.result?.score || 0)}`}>
                  {calcModalData.result?.score > 0 ? `+${calcModalData.result?.score}` : calcModalData.result?.score}
                </span>
              </div>

              <div className="flex items-center justify-between py-1 border-b border-border/60">
                <span className="text-muted-foreground">Analytical Confidence:</span>
                <span className="font-mono font-bold text-foreground">
                  {Math.round((calcModalData.result?.confidence || 0) * 100)}%
                </span>
              </div>

              {calcModalData.result?.target_price && (
                <div className="flex items-center justify-between py-1 border-b border-border/60">
                  <span className="text-muted-foreground">Target Level:</span>
                  <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
                    ₹{calcModalData.result.target_price.toLocaleString('en-IN')}
                  </span>
                </div>
              )}

              {calcModalData.result?.invalidation_price && (
                <div className="flex items-center justify-between py-1">
                  <span className="text-muted-foreground">Invalidation Stop:</span>
                  <span className="font-mono font-bold text-rose-600 dark:text-rose-400">
                    ₹{calcModalData.result.invalidation_price.toLocaleString('en-IN')}
                  </span>
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setCalcModalData(null)}
                className="px-5 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold shadow-xs hover:bg-primary/90 transition-all"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
