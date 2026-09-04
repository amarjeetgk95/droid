'use client';

import { VixRegimeInfo } from '@/lib/types';
import { Activity, ShieldAlert, Sparkles, TrendingUp, TrendingDown } from 'lucide-react';

export function VixRegimeCard({
  vixInfo,
}: {
  vixInfo: VixRegimeInfo | null;
}) {
  if (!vixInfo) {
    return (
      <div className="bg-card border border-border rounded-xl p-6 text-center text-muted-foreground">
        No India VIX volatility regime data available.
      </div>
    );
  }

  const category = vixInfo.regime_category || 'NORMAL';
  const isElevated = category === 'ELEVATED_VOLATILITY' || category === 'EXTREME_VOLATILITY';

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">India VIX Volatility & Options Playbook</h3>
        </div>
        <span className={`text-xs px-2.5 py-0.5 rounded-full font-bold flex items-center gap-1 ${
          isElevated ? 'bg-rose-500/20 text-rose-400' : 'bg-primary/20 text-primary'
        }`}>
          {isElevated ? <ShieldAlert className="w-3 h-3" /> : <Sparkles className="w-3 h-3" />}
          {category.replace('_', ' ')}
        </span>
      </div>

      {/* Main Metrics Card */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="bg-secondary/40 p-3.5 rounded-lg border border-border space-y-1">
          <span className="text-xs text-muted-foreground block">India VIX Benchmark</span>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-black font-mono text-foreground">{vixInfo.vix_value}</span>
            <span className={`text-xs font-mono flex items-center gap-0.5 ${
              vixInfo.change >= 0 ? 'text-rose-400' : 'text-emerald-400'
            }`}>
              {vixInfo.change >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
              {vixInfo.change > 0 ? '+' : ''}{vixInfo.change} ({vixInfo.change_percent}%)
            </span>
          </div>
          <span className="text-[10px] text-muted-foreground block">Implied 30-Day Volatility</span>
        </div>

        <div className="bg-secondary/40 p-3.5 rounded-lg border border-border space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Historical Percentile Rank:</span>
            <span className="font-mono font-bold text-foreground">{vixInfo.historical_percentile}%</span>
          </div>
          <div className="w-full bg-secondary h-2 rounded-full overflow-hidden">
            <div
              style={{ width: `${Math.min(100, vixInfo.historical_percentile)}%` }}
              className={`h-full transition-all duration-300 ${
                vixInfo.historical_percentile >= 75 ? 'bg-rose-500' :
                vixInfo.historical_percentile <= 30 ? 'bg-emerald-500' : 'bg-primary'
              }`}
            />
          </div>
          <span className="text-[10px] text-muted-foreground block">Relative to 1-Year Range</span>
        </div>

        <div className="bg-secondary/40 p-3.5 rounded-lg border border-border space-y-1 sm:col-span-1 col-span-1">
          <span className="text-xs text-muted-foreground block">Recommended Options Playbook</span>
          <p className="text-xs font-bold text-foreground leading-snug">{vixInfo.recommended_option_strategy}</p>
        </div>
      </div>

      {/* Institutional Volatility Notes */}
      <div className="bg-secondary/30 rounded-lg p-3 border border-border text-xs text-muted-foreground leading-relaxed">
        <strong className="text-foreground font-semibold">Volatility Interpretation: </strong>
        {vixInfo.interpretation}
      </div>
    </div>
  );
}
