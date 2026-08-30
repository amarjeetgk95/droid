'use client';

import { ScannedStrategy } from '@/lib/types';
import { Percent, Target, ArrowRight } from 'lucide-react';
import Link from 'next/link';

export function ScannerCard({
  strategy,
}: {
  strategy: ScannedStrategy;
}) {
  const getOutlookBadge = (outlook: string) => {
    switch (outlook) {
      case 'BULLISH':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
      case 'BEARISH':
        return 'bg-rose-500/20 text-rose-400 border-rose-500/30';
      case 'HIGH_VOLATILITY':
        return 'bg-purple-500/20 text-purple-400 border-purple-500/30';
      default:
        return 'bg-primary/20 text-primary border-primary/30';
    }
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-xs hover:border-primary/40 transition-all flex flex-col justify-between">
      {/* Header */}
      <div className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-mono font-bold text-muted-foreground uppercase">
            {strategy.underlying} • {strategy.category.replace('_', ' ')}
          </span>
          <span className={`text-[11px] px-2 py-0.5 rounded-full font-bold border ${getOutlookBadge(strategy.outlook)}`}>
            {strategy.outlook}
          </span>
        </div>
        <h3 className="font-bold text-sm text-foreground">{strategy.name}</h3>
      </div>

      {/* Probability & Payoff Metrics */}
      <div className="grid grid-cols-3 gap-2 bg-secondary/40 p-2.5 rounded-lg border border-border text-xs font-mono">
        <div>
          <span className="text-[10px] text-muted-foreground block font-sans flex items-center gap-0.5">
            <Percent className="w-2.5 h-2.5 text-primary" /> POP
          </span>
          <span className="font-bold text-primary text-sm">{strategy.pop_percent}%</span>
        </div>

        <div>
          <span className="text-[10px] text-muted-foreground block font-sans">Max Profit</span>
          <span className="font-bold text-success text-xs">
            {strategy.max_profit !== null && strategy.max_profit !== undefined
              ? `₹${strategy.max_profit.toLocaleString('en-IN')}`
              : 'Unlimited'}
          </span>
        </div>

        <div>
          <span className="text-[10px] text-muted-foreground block font-sans">Max Loss</span>
          <span className="font-bold text-destructive text-xs">
            {strategy.max_loss !== null && strategy.max_loss !== undefined
              ? `₹${strategy.max_loss.toLocaleString('en-IN')}`
              : 'Unlimited'}
          </span>
        </div>
      </div>

      {/* Net Premium & Breakevens */}
      <div className="flex items-center justify-between text-xs text-muted-foreground pt-1">
        <span className="font-mono">
          Net {strategy.premium_type}: <strong className="text-foreground font-bold">₹{strategy.net_premium.toLocaleString('en-IN')}</strong>
        </span>
        <span className="flex items-center gap-1 text-[11px]">
          <Target className="w-3 h-3 text-warning" />
          BE: {strategy.breakevens.length > 0 ? strategy.breakevens.map((b) => `₹${b}`).join(', ') : 'None'}
        </span>
      </div>

      {/* Load into Builder Button */}
      <Link
        href={`/strategy?symbol=${strategy.underlying}&template=${strategy.id.split('_')[0]}`}
        className="w-full flex items-center justify-center gap-1.5 py-2 px-3 bg-secondary hover:bg-primary hover:text-primary-foreground text-foreground text-xs font-bold rounded-lg border border-border transition-all cursor-pointer"
      >
        <span>Load into Strategy Builder</span>
        <ArrowRight className="w-3.5 h-3.5" />
      </Link>
    </div>
  );
}
