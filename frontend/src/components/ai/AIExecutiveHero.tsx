'use client';

import React from 'react';
import { AIInsightResponse } from '@/lib/types';
import {
  TrendingUp,
  TrendingDown,
  Activity,
  Zap,
  ShieldAlert,
  Clock,
  Sparkles,
  Target,
} from 'lucide-react';

interface AIExecutiveHeroProps {
  insight: AIInsightResponse;
  symbol: string;
}

export function AIExecutiveHero({ insight, symbol }: AIExecutiveHeroProps) {
  const bias = insight.market_bias || 'NEUTRAL';
  const confidence = Math.min(100, Math.max(0, insight.confidence || 50));

  const getBiasConfig = (b: string) => {
    switch (b) {
      case 'BULLISH':
        return {
          title: 'BULLISH BIAS',
          subtitle: 'Quant engines detect upward momentum & call-buying support',
          icon: <TrendingUp className="w-6 h-6 text-emerald-500" />,
          badgeBg: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30',
          barColor: 'bg-emerald-500',
          textColor: 'text-emerald-600',
        };
      case 'BEARISH':
        return {
          title: 'BEARISH BIAS',
          subtitle: 'Quant engines detect downward pressure & put-buying / call-writing',
          icon: <TrendingDown className="w-6 h-6 text-rose-500" />,
          badgeBg: 'bg-rose-500/10 text-rose-600 border-rose-500/30',
          barColor: 'bg-rose-500',
          textColor: 'text-rose-600',
        };
      case 'VOLATILE':
        return {
          title: 'HIGH VOLATILITY / EXPANSION',
          subtitle: 'Expanding range expected; avoid unhedged directional bets',
          icon: <Zap className="w-6 h-6 text-purple-500" />,
          badgeBg: 'bg-purple-500/10 text-purple-600 border-purple-500/30',
          barColor: 'bg-purple-500',
          textColor: 'text-purple-600',
        };
      default:
        return {
          title: 'NEUTRAL / RANGE-BOUND',
          subtitle: 'Market is oscillating between key support and resistance boundaries',
          icon: <Activity className="w-6 h-6 text-blue-500" />,
          badgeBg: 'bg-blue-500/10 text-blue-600 border-blue-500/30',
          barColor: 'bg-blue-500',
          textColor: 'text-blue-600',
        };
    }
  };

  const cfg = getBiasConfig(bias);

  return (
    <div className="bg-card border border-border rounded-2xl p-5 sm:p-6 shadow-xs space-y-5">
      {/* Top Hero Row */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-border/70">
        <div className="flex items-start gap-3.5">
          <div className="p-3 bg-secondary/80 rounded-xl border border-border shrink-0 mt-0.5">
            {cfg.icon}
          </div>
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className={`px-3 py-1 rounded-full text-xs font-black tracking-wide border ${cfg.badgeBg}`}>
                {cfg.title}
              </span>
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-secondary text-foreground border border-border">
                {symbol}
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
              {cfg.subtitle}
            </p>
          </div>
        </div>

        {/* Conviction Meter */}
        <div className="bg-secondary/40 border border-border rounded-xl p-3 sm:px-4 sm:py-3 min-w-[220px]">
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="font-semibold text-muted-foreground">Quant Conviction</span>
            <span className={`font-mono font-bold text-sm ${cfg.textColor}`}>
              {confidence}%
            </span>
          </div>
          <div className="w-full bg-secondary rounded-full h-2 overflow-hidden border border-border/50">
            <div
              className={`h-full rounded-full transition-all duration-500 ${cfg.barColor}`}
              style={{ width: `${confidence}%` }}
            />
          </div>
          <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
            <span>Low</span>
            <span>Moderate</span>
            <span>Strong</span>
          </div>
        </div>
      </div>

      {/* 1-Minute Executive Summary */}
      <div className="bg-secondary/20 rounded-xl p-4 border border-border/70 space-y-2">
        <h4 className="text-xs font-bold uppercase tracking-wider text-foreground flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5 text-primary" />
          The Core Market Thesis (Plain English)
        </h4>
        <p className="text-xs text-foreground/90 leading-relaxed font-sans font-medium">
          {insight.executive_summary}
        </p>
      </div>

      {/* Meta Footer */}
      <div className="flex flex-wrap items-center justify-between text-[11px] text-muted-foreground pt-1">
        <span className="flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5" />
          Generated: {new Date(insight.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </span>
        <span className="font-mono">
          Engine: <strong className="text-foreground">{insight.provider_used}</strong>
        </span>
      </div>
    </div>
  );
}
