'use client';

import { StrategyPayoffResult } from '@/lib/types';
import { ShieldCheck, Percent, Target } from 'lucide-react';

export function StrategyMetrics({
  result,
}: {
  result: StrategyPayoffResult | null;
}) {
  if (!result) return null;

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">Strategy Risk & Portfolio Greeks</h3>
        </div>
        <span className={`text-xs px-2.5 py-0.5 rounded-full font-bold ${
          result.premium_type === 'CREDIT' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-primary/20 text-primary'
        }`}>
          Net {result.premium_type}: ₹{result.net_premium.toLocaleString('en-IN')}
        </span>
      </div>

      {/* Main Risk Metrics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        <div className="bg-secondary/40 p-3 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground block">Max Profit</span>
          <span className="font-bold font-mono text-base text-success">
            {result.max_profit !== null && result.max_profit !== undefined
              ? `₹${result.max_profit.toLocaleString('en-IN')}`
              : 'Unlimited'}
          </span>
          <span className="text-[10px] text-muted-foreground block">Capped Upside</span>
        </div>

        <div className="bg-secondary/40 p-3 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground block">Max Loss</span>
          <span className="font-bold font-mono text-base text-destructive">
            {result.max_loss !== null && result.max_loss !== undefined
              ? `₹${result.max_loss.toLocaleString('en-IN')}`
              : 'Unlimited'}
          </span>
          <span className="text-[10px] text-muted-foreground block">Capital at Risk</span>
        </div>

        <div className="bg-secondary/40 p-3 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground flex items-center gap-1">
            <Percent className="w-3 h-3 text-primary" /> POP (Prob. of Profit)
          </span>
          <span className="font-bold font-mono text-base text-primary">
            {result.pop_percent}%
          </span>
          <span className="text-[10px] text-muted-foreground block">Lognormal CDF Model</span>
        </div>

        <div className="bg-secondary/40 p-3 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground flex items-center gap-1">
            <Target className="w-3 h-3 text-warning" /> Risk / Reward Ratio
          </span>
          <span className="font-bold font-mono text-base text-foreground">
            {result.risk_reward_ratio ? `1 : ${(1 / result.risk_reward_ratio).toFixed(2)}` : '1 : 1.0'}
          </span>
          <span className="text-[10px] text-muted-foreground block">R:R Profile</span>
        </div>
      </div>

      {/* Net Greeks Strip */}
      <div className="pt-3 border-t border-border">
        <h4 className="text-xs font-semibold text-muted-foreground mb-2">Net Portfolio Greeks</h4>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
          <div className="bg-secondary/60 p-2.5 rounded-lg border border-border">
            <span className="text-[10px] text-muted-foreground block font-sans">Net Delta (Δ)</span>
            <span className={`font-bold ${result.net_delta >= 0 ? 'text-success' : 'text-destructive'}`}>
              {result.net_delta > 0 ? '+' : ''}{result.net_delta}
            </span>
          </div>

          <div className="bg-secondary/60 p-2.5 rounded-lg border border-border">
            <span className="text-[10px] text-muted-foreground block font-sans">Net Gamma (Γ)</span>
            <span className="font-bold text-foreground">
              {result.net_gamma}
            </span>
          </div>

          <div className="bg-secondary/60 p-2.5 rounded-lg border border-border">
            <span className="text-[10px] text-muted-foreground block font-sans">Daily Theta (Θ)</span>
            <span className={`font-bold ${result.net_theta >= 0 ? 'text-success' : 'text-destructive'}`}>
              {result.net_theta > 0 ? '+' : ''}₹{result.net_theta} / day
            </span>
          </div>

          <div className="bg-secondary/60 p-2.5 rounded-lg border border-border">
            <span className="text-[10px] text-muted-foreground block font-sans">Net Vega (V)</span>
            <span className="font-bold text-foreground">
              {result.net_vega > 0 ? '+' : ''}₹{result.net_vega} / 1% IV
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
