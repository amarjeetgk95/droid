'use client';

import { MaxPainResult } from '@/lib/types';
import { Target } from 'lucide-react';

export function PayoffChart({
  data,
  spotPrice,
}: {
  data: MaxPainResult | null;
  spotPrice: number;
}) {
  if (!data || data.strikes.length === 0) {
    return (
      <div className="bg-card border border-border rounded-xl p-6 text-center text-muted-foreground">
        No Max Pain payout distribution available for this expiry.
      </div>
    );
  }

  const maxPayout = Math.max(...data.payouts, 1);
  const minPayout = Math.min(...data.payouts);

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Target className="w-4 h-4 text-warning" />
          <h3 className="font-bold text-sm text-foreground">Max Pain Payout Distribution</h3>
        </div>
        <div className="text-xs font-mono">
          <span className="text-muted-foreground">Lowest Total Payout at: </span>
          <span className="font-bold text-warning">₹{data.max_pain_strike.toLocaleString('en-IN')}</span>
        </div>
      </div>

      {/* SVG Bar / Curve Chart */}
      <div className="h-56 w-full flex items-end gap-1.5 pt-4 pb-6 px-2 overflow-x-auto border-b border-border">
        {data.strikes.map((strike, idx) => {
          const payout = data.payouts[idx];
          const heightPercent = Math.max(8, ((payout - minPayout) / (maxPayout - minPayout || 1)) * 100);
          const isMaxPain = strike === data.max_pain_strike;
          const isSpotNear = Math.abs(strike - spotPrice) <= 50;

          return (
            <div key={strike} className="flex-1 min-w-[28px] flex flex-col items-center gap-1 group relative">
              {/* Tooltip on Hover */}
              <div className="absolute -top-12 z-30 hidden group-hover:flex flex-col items-center bg-popover text-popover-foreground text-[10px] px-2 py-1 rounded shadow-md pointer-events-none whitespace-nowrap border border-border">
                <span>Strike: {strike}</span>
                <span>Payout: ₹{(payout / 10000000).toFixed(2)} Cr</span>
              </div>

              {/* Bar */}
              <div
                style={{ height: `${heightPercent}%` }}
                className={`w-full rounded-t-xs transition-all duration-300 ${
                  isMaxPain
                    ? 'bg-warning ring-2 ring-warning/50'
                    : isSpotNear
                    ? 'bg-primary/80'
                    : 'bg-secondary hover:bg-primary/50'
                }`}
              />

              {/* Label */}
              <span
                className={`text-[9px] font-mono transform -rotate-45 origin-top-left mt-2 ${
                  isMaxPain ? 'text-warning font-bold' : 'text-muted-foreground'
                }`}
              >
                {strike}
              </span>
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between text-[11px] text-muted-foreground px-2">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-xs bg-warning" /> Max Pain Strike
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-xs bg-primary/80" /> Near Spot Strike
          </span>
        </div>
        <span>Total Option Loss Minimization Model</span>
      </div>
    </div>
  );
}
