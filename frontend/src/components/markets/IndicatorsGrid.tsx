'use client';

import { TechnicalIndicators } from '@/lib/types';
import { Activity, Gauge, TrendingUp, TrendingDown, Eye } from 'lucide-react';

export function IndicatorsGrid({
  indicators,
  spotPrice,
}: {
  indicators: TechnicalIndicators | null;
  spotPrice: number;
}) {
  if (!indicators) {
    return (
      <div className="bg-card border border-border rounded-xl p-6 text-center text-muted-foreground">
        No technical indicators available.
      </div>
    );
  }

  const rsi = indicators.rsi_14 ?? 50;
  const adx = indicators.adx_14 ?? 0;
  const isSupertrendBull = indicators.supertrend_direction === 'BULLISH';

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Gauge className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">Quantitative Technical Indicator Suite</h3>
        </div>
        <span className="text-xs text-muted-foreground">Multi-Timeframe Signals</span>
      </div>

      {/* Main Gauges Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {/* RSI (14) */}
        <div className="bg-secondary/40 p-3.5 rounded-lg border border-border space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-primary" /> RSI (14-Period)
            </span>
            <span className={`text-xs px-2 py-0.5 rounded font-bold ${
              rsi >= 70 ? 'bg-rose-500/20 text-rose-400' :
              rsi <= 30 ? 'bg-emerald-500/20 text-emerald-400' :
              rsi >= 50 ? 'bg-emerald-500/10 text-emerald-300' : 'bg-amber-500/10 text-amber-400'
            }`}>
              {rsi >= 70 ? 'OVERBOUGHT' : rsi <= 30 ? 'OVERSOLD' : rsi >= 50 ? 'BULLISH ZONE' : 'BEARISH ZONE'}
            </span>
          </div>

          <div className="flex items-baseline justify-between">
            <span className="text-2xl font-black font-mono text-foreground">{rsi}</span>
            <span className="text-[11px] text-muted-foreground">Neutral: 50.0</span>
          </div>

          <div className="w-full bg-secondary h-2 rounded-full overflow-hidden">
            <div
              style={{ width: `${Math.min(100, Math.max(0, rsi))}%` }}
              className={`h-full transition-all duration-300 ${
                rsi >= 60 ? 'bg-emerald-500' : rsi <= 40 ? 'bg-rose-500' : 'bg-primary'
              }`}
            />
          </div>
        </div>

        {/* ADX & Directional Movement */}
        <div className="bg-secondary/40 p-3.5 rounded-lg border border-border space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <TrendingUp className="w-3.5 h-3.5 text-warning" /> ADX Trend Strength
            </span>
            <span className={`text-xs px-2 py-0.5 rounded font-bold ${
              adx >= 25 ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'
            }`}>
              {adx >= 25 ? 'STRONG TREND' : 'NON-TRENDING'}
            </span>
          </div>

          <div className="flex items-baseline justify-between">
            <span className="text-2xl font-black font-mono text-foreground">{adx}</span>
            <span className="text-[11px] font-mono text-muted-foreground">
              +DI: <strong className="text-success">{indicators.plus_di}</strong> | -DI: <strong className="text-destructive">{indicators.minus_di}</strong>
            </span>
          </div>

          <div className="w-full bg-secondary h-2 rounded-full overflow-hidden">
            <div
              style={{ width: `${Math.min(100, (adx / 60) * 100)}%` }}
              className="bg-warning h-full transition-all duration-300"
            />
          </div>
        </div>

        {/* Supertrend (10, 3) */}
        <div className="bg-secondary/40 p-3.5 rounded-lg border border-border space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <Eye className="w-3.5 h-3.5 text-primary" /> Supertrend (10, 3)
            </span>
            <span className={`text-xs px-2 py-0.5 rounded font-bold flex items-center gap-1 ${
              isSupertrendBull ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
            }`}>
              {isSupertrendBull ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
              {indicators.supertrend_direction}
            </span>
          </div>

          <div className="flex items-baseline justify-between">
            <span className="text-lg font-bold font-mono text-foreground">
              ₹{(indicators.supertrend_value ?? 0).toLocaleString('en-IN')}
            </span>
            <span className="text-[11px] text-muted-foreground">
              Trailing Level
            </span>
          </div>

          <p className="text-[11px] text-muted-foreground">
            {isSupertrendBull
              ? 'Price holding above trailing support stop line.'
              : 'Price rejected below trailing resistance stop line.'}
          </p>
        </div>

        {/* Bollinger Bands & Bandwidth */}
        <div className="bg-secondary/40 p-3.5 rounded-lg border border-border space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground">Bollinger Bandwidth %</span>
            <span className="text-xs font-mono font-bold text-foreground">
              {indicators.bollinger_bandwidth}%
            </span>
          </div>
          <div className="grid grid-cols-3 gap-1 text-[11px] font-mono text-muted-foreground pt-1">
            <div>
              <span className="text-[10px] block">Upper</span>
              <strong className="text-foreground">₹{indicators.bollinger_upper}</strong>
            </div>
            <div>
              <span className="text-[10px] block">Middle (SMA)</span>
              <strong className="text-foreground">₹{indicators.bollinger_middle}</strong>
            </div>
            <div>
              <span className="text-[10px] block">Lower</span>
              <strong className="text-foreground">₹{indicators.bollinger_lower}</strong>
            </div>
          </div>
        </div>

        {/* ATR (14) Volatility Range */}
        <div className="bg-secondary/40 p-3.5 rounded-lg border border-border space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground">ATR (14-Period Range)</span>
            <span className="text-xs font-mono font-bold text-warning">
              {indicators.atr_14} Pts
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Average true bar range is{' '}
            <strong className="text-foreground">{((indicators.atr_14 / spotPrice) * 100).toFixed(2)}%</strong> of
            underlying spot price.
          </p>
        </div>

        {/* Key Moving Averages */}
        <div className="bg-secondary/40 p-3.5 rounded-lg border border-border space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground">Moving Averages (EMA/SMA)</span>
          </div>
          <div className="grid grid-cols-3 gap-1 text-[11px] font-mono text-muted-foreground pt-1">
            <div>
              <span className="text-[10px] block">20 EMA</span>
              <strong className="text-foreground">{indicators.ema_20 ? `₹${indicators.ema_20}` : '---'}</strong>
            </div>
            <div>
              <span className="text-[10px] block">50 EMA</span>
              <strong className="text-foreground">{indicators.ema_50 ? `₹${indicators.ema_50}` : '---'}</strong>
            </div>
            <div>
              <span className="text-[10px] block">200 SMA</span>
              <strong className="text-foreground">{indicators.sma_200 ? `₹${indicators.sma_200}` : '---'}</strong>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
