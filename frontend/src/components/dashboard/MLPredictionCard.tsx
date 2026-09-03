'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { MLPredictionResponse } from '@/lib/types';
import { Cpu, TrendingUp, TrendingDown, ShieldCheck } from 'lucide-react';
import { safeNum, safeStr } from '@/lib/utils';

export function MLPredictionCard({ symbol = 'NIFTY', refreshKey }: { symbol?: string; refreshKey?: number }) {
  const [prediction, setPrediction] = useState<MLPredictionResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    const loadPrediction = async () => {
      try {
        const res = await api.getMLPrediction(symbol);
        if (isMounted) {
          setPrediction(res.data);
          setError(null);
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to fetch ML prediction');
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    loadPrediction();
    // Chained timeout with jitter so clients don't sync up polls.
    let timeout: ReturnType<typeof setTimeout> | null = null;
    const schedule = () => {
      timeout = setTimeout(() => {
        if (!document.hidden) loadPrediction();
        schedule();
      }, 10000 * (0.8 + Math.random() * 0.4));
    };
    schedule();
    const onVis = () => { if (!document.hidden) loadPrediction(); };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      isMounted = false;
      if (timeout) clearTimeout(timeout);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [symbol, refreshKey]);

  if (loading && !prediction) {
    return (
      <div className="bg-card border border-border rounded-xl p-4 h-64 animate-pulse flex flex-col justify-between">
        <div className="h-4 bg-secondary rounded w-48" />
        <div className="h-10 bg-secondary rounded w-full" />
        <div className="h-4 bg-secondary rounded w-32" />
      </div>
    );
  }

  if (error || !prediction) {
    // Compact error state — never silently collapse the layout.
    return (
      <div className="bg-card border border-destructive/30 rounded-xl p-4 h-64 flex flex-col items-center justify-center gap-2">
        <Cpu className="w-6 h-6 text-destructive" />
        <p className="text-sm font-semibold text-foreground">ML Prediction unavailable</p>
        <p className="text-xs text-muted-foreground text-center max-w-xs">{error ?? 'No prediction data'}</p>
        <button
          onClick={() => {
            setLoading(true);
            api.getMLPrediction(symbol)
              .then(res => { setPrediction(res.data); setError(null); })
              .catch(err => setError(err instanceof Error ? err.message : 'Failed to fetch ML prediction'))
              .finally(() => setLoading(false));
          }}
          className="text-xs px-3 py-1 rounded-md bg-secondary hover:bg-secondary/80 text-foreground transition-colors cursor-pointer"
        >
          Retry
        </button>
      </div>
    );
  }

  const isBullish = prediction.predicted_bias === 'BULLISH';
  const isBearish = prediction.predicted_bias === 'BEARISH';

  const bullishPct = Number(prediction.bullish_pct) || 0;
  const neutralPct = Number(prediction.neutral_pct) || 0;
  const bearishPct = Number(prediction.bearish_pct) || 0;

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-xs">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
            <Cpu className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-foreground">
              ML Probability Engine ({prediction.symbol})
            </h3>
            <p className="text-[10px] text-muted-foreground">XGBoost & LightGBM Gradient Decision Ensemble</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`px-2 py-0.5 rounded text-[10px] font-extrabold border ${
              isBullish
                ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                : isBearish
                ? 'bg-rose-500/20 text-rose-400 border-rose-500/30'
                : 'bg-secondary text-muted-foreground border-border'
            }`}
          >
            {safeStr(prediction.predicted_bias)}
          </span>
          <span className="text-[10px] font-semibold text-muted-foreground flex items-center gap-1">
            <ShieldCheck className="w-3 h-3 text-primary" /> {safeNum(prediction.confidence_score, '—', 0)}% Conf.
          </span>
        </div>
      </div>

      {/* Probability Segmented Bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-[10px] font-bold">
          <span className="text-emerald-400 flex items-center gap-1">
            <TrendingUp className="w-3 h-3" /> Bullish {safeNum(bullishPct, '—', 0)}%
          </span>
          <span className="text-muted-foreground">Neutral {safeNum(neutralPct, '—', 0)}%</span>
          <span className="text-rose-400 flex items-center gap-1">
            <TrendingDown className="w-3 h-3" /> Bearish {safeNum(bearishPct, '—', 0)}%
          </span>
        </div>

        <div className="w-full h-2.5 rounded-full bg-secondary overflow-hidden flex">
          <div
            style={{ width: `${prediction.bullish_pct}%` }}
            className="bg-emerald-500 transition-all duration-500"
          />
          <div
            style={{ width: `${prediction.neutral_pct}%` }}
            className="bg-zinc-500/40 transition-all duration-500"
          />
          <div
            style={{ width: `${prediction.bearish_pct}%` }}
            className="bg-rose-500 transition-all duration-500"
          />
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-3 gap-2 text-center pt-1 border-t border-border/60">
        <div className="p-1.5 rounded-lg bg-secondary/50">
          <div className="text-[10px] text-muted-foreground">Trend Strength</div>
          <div className="text-xs font-mono font-bold text-foreground mt-0.5">
            {safeNum(prediction.trend_strength, '—', 0)} / 100
          </div>
        </div>
        <div className="p-1.5 rounded-lg bg-secondary/50">
          <div className="text-[10px] text-muted-foreground">Regime State</div>
          <div className="text-[10px] font-bold text-primary truncate mt-0.5">
            {safeStr(prediction.market_regime, '—').replace('_', ' ')}
          </div>
        </div>
        <div className="p-1.5 rounded-lg bg-secondary/50">
          <div className="text-[10px] text-muted-foreground">Top Factor</div>
          <div className="text-[10px] font-semibold text-foreground truncate mt-0.5">
            {prediction.top_features?.[0]?.feature_name || 'Supertrend'}
          </div>
        </div>
      </div>
    </div>
  );
}
