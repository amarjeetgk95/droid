'use client';

import { FuturesOverview } from '@/lib/types';
import { TrendingUp, TrendingDown, Layers, Percent, Activity } from 'lucide-react';

export function FuturesHeader({
  overview,
  selectedSymbol,
  onSelectSymbol,
}: {
  overview: FuturesOverview | null;
  selectedSymbol: string;
  onSelectSymbol: (sym: string) => void;
  autoRefresh: boolean;
  onToggleRefresh: () => void;
}) {
  const symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX'];
  const nearContract = overview?.term_structure?.contracts?.[0];

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      {/* Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Symbol Selector */}
        <div className="flex items-center gap-2">
          {symbols.map((sym) => (
            <button
              key={sym}
              onClick={() => onSelectSymbol(sym)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                selectedSymbol === sym
                  ? 'bg-primary text-primary-foreground shadow-sm'
                  : 'bg-secondary hover:bg-secondary/80 text-muted-foreground hover:text-foreground'
              }`}
            >
              {sym}
            </button>
          ))}
        </div>

        {/* Status Badge */}
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2.5 py-1 rounded-md font-bold flex items-center gap-1.5 ${
            overview?.term_structure.curve_state === 'CONTANGO'
              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
              : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
          }`}>
            <Layers className="w-3.5 h-3.5" />
            Term Curve: {overview?.term_structure.curve_state || 'CONTANGO'}
          </span>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="bg-secondary/60 p-3 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground block">Spot Price</span>
          <span className="text-base font-bold text-foreground font-mono">
            {overview?.spot_price ? `₹${overview.spot_price.toLocaleString('en-IN')}` : '---'}
          </span>
          <span className="text-[10px] text-muted-foreground block">Cash Benchmark</span>
        </div>

        <div className="bg-secondary/60 p-3 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground block">Near Month Futures</span>
          <span className="text-base font-bold text-primary font-mono">
            {nearContract?.ltp ? `₹${nearContract.ltp.toLocaleString('en-IN')}` : '---'}
          </span>
          <span className={`text-[10px] font-mono flex items-center gap-0.5 ${
            (nearContract?.change ?? 0) >= 0 ? 'text-success' : 'text-destructive'
          }`}>
            {(nearContract?.change ?? 0) >= 0 ? <TrendingUp className="w-2.5 h-2.5" /> : <TrendingDown className="w-2.5 h-2.5" />}
            {nearContract?.change ? `${nearContract.change > 0 ? '+' : ''}${nearContract.change} (${nearContract.change_percent}%)` : '---'}
          </span>
        </div>

        <div className="bg-secondary/60 p-3 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground block">Futures Basis</span>
          <span className={`text-base font-bold font-mono ${
            (nearContract?.basis ?? 0) >= 0 ? 'text-success' : 'text-destructive'
          }`}>
            {nearContract?.basis !== undefined ? `${nearContract.basis > 0 ? '+' : ''}₹${nearContract.basis}` : '---'}
          </span>
          <span className="text-[10px] text-muted-foreground block">
            {nearContract?.basis_percent ? `${nearContract.basis_percent}% premium` : '---'}
          </span>
        </div>

        <div className="bg-secondary/60 p-3 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground flex items-center gap-1">
            <Percent className="w-3 h-3 text-warning" /> Annualized CoC
          </span>
          <span className="text-base font-bold text-warning font-mono">
            {nearContract?.cost_of_carry_percent ? `${nearContract.cost_of_carry_percent}%` : '---'}
          </span>
          <span className="text-[10px] text-muted-foreground block">Cost of Carry Rate</span>
        </div>

        <div className="bg-secondary/60 p-3 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground flex items-center gap-1">
            <Activity className="w-3 h-3 text-primary" /> Buildup Type
          </span>
          <span className={`text-xs font-bold font-mono block truncate ${
            overview?.buildup.buildup_type === 'LONG_BUILDUP' ? 'text-success' :
            overview?.buildup.buildup_type === 'SHORT_BUILDUP' ? 'text-destructive' :
            overview?.buildup.buildup_type === 'SHORT_COVERING' ? 'text-emerald-400' : 'text-amber-400'
          }`}>
            {overview?.buildup.buildup_type.replace('_', ' ') || '---'}
          </span>
          <span className="text-[10px] text-muted-foreground block">
            {overview?.buildup.strength || 'MODERATE'} Strength
          </span>
        </div>

        <div className="bg-secondary/60 p-3 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground block">Rollover %</span>
          <span className="text-base font-bold text-foreground font-mono">
            {overview?.rollover.rollover_percent ? `${overview.rollover.rollover_percent}%` : '---'}
          </span>
          <span className="text-[10px] text-muted-foreground block">
            Pace: {overview?.rollover.rollover_pace || 'IN_LINE'}
          </span>
        </div>
      </div>
    </div>
  );
}
