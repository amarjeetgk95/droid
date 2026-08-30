'use client';

import { SeasonalityResponse } from '@/lib/types';
import { Calendar, Sparkles, TrendingUp, TrendingDown } from 'lucide-react';

export function SeasonalityCard({
  seasonality,
}: {
  seasonality: SeasonalityResponse | null;
}) {
  if (!seasonality) return null;

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">
            Day-of-Week Seasonality Distribution ({seasonality.symbol})
          </h3>
        </div>
        <span className="text-xs text-muted-foreground">Historical Benchmark</span>
      </div>

      {/* Weekday Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5">
        {seasonality.days.map((d) => {
          const isPos = d.avg_return_pct >= 0;
          return (
            <div
              key={d.day_name}
              className="bg-secondary/40 border border-border rounded-xl p-3 space-y-1.5 hover:border-primary/40 transition-all"
            >
              <span className="text-xs font-bold text-foreground block">{d.day_name}</span>

              <div className={`text-sm font-mono font-black flex items-center gap-1 ${
                isPos ? 'text-emerald-400' : 'text-rose-400'
              }`}>
                {isPos ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                {isPos ? '+' : ''}{d.avg_return_pct}%
              </div>

              <div className="text-[10px] font-mono text-muted-foreground space-y-0.5 pt-1 border-t border-border/50">
                <div className="flex justify-between">
                  <span>Win Rate:</span>
                  <strong className="text-foreground">{d.win_rate_pct}%</strong>
                </div>
                <div className="flex justify-between">
                  <span>Avg Range:</span>
                  <strong className="text-foreground">{d.avg_range_pts} pts</strong>
                </div>
                <div className="flex justify-between">
                  <span>Volatility:</span>
                  <strong className="text-foreground">{d.volatility_pct}%</strong>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Best Day Tags */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs pt-1">
        <div className="bg-emerald-500/10 border border-emerald-500/20 p-2.5 rounded-lg flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-emerald-400 shrink-0" />
          <div>
            <span className="text-[10px] text-emerald-400 font-bold block">Best Day for Option Buyers:</span>
            <span className="text-foreground font-semibold">{seasonality.best_day_for_buyers}</span>
          </div>
        </div>

        <div className="bg-primary/10 border border-primary/20 p-2.5 rounded-lg flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-primary shrink-0" />
          <div>
            <span className="text-[10px] text-primary font-bold block">Best Day for Option Sellers:</span>
            <span className="text-foreground font-semibold">{seasonality.best_day_for_sellers}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
