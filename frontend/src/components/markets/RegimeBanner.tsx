'use client';

import { MarketRegimeOverview } from '@/lib/types';
import { Compass, ShieldCheck, AlertTriangle, Zap, ArrowUpRight, ArrowDownRight, Layers } from 'lucide-react';

export function RegimeBanner({
  overview,
  selectedSymbol,
  onSelectSymbol,
}: {
  overview: MarketRegimeOverview | null;
  selectedSymbol: string;
  onSelectSymbol: (sym: string) => void;
}) {
  const symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX'];
  const state = overview?.regime_state;

  const getStateConfig = (s?: string) => {
    switch (s) {
      case 'TRENDING_BULLISH':
        return {
          icon: <ArrowUpRight className="w-5 h-5 text-emerald-400" />,
          badge: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
          border: 'border-emerald-500/40',
        };
      case 'TRENDING_BEARISH':
        return {
          icon: <ArrowDownRight className="w-5 h-5 text-rose-400" />,
          badge: 'bg-rose-500/20 text-rose-400 border-rose-500/30',
          border: 'border-rose-500/40',
        };
      case 'COMPRESSION_SQUEEZE':
        return {
          icon: <Zap className="w-5 h-5 text-amber-400" />,
          badge: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
          border: 'border-amber-500/40',
        };
      case 'VOLATILE_EXPANSION':
        return {
          icon: <AlertTriangle className="w-5 h-5 text-purple-400" />,
          badge: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
          border: 'border-purple-500/40',
        };
      default:
        return {
          icon: <Layers className="w-5 h-5 text-primary" />,
          badge: 'bg-primary/20 text-primary border-primary/30',
          border: 'border-border',
        };
    }
  };

  const config = getStateConfig(state);

  return (
    <div className={`bg-card border ${config.border} rounded-xl p-4 space-y-4 shadow-sm transition-all`}>
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

        {/* Regime State Badge */}
        <div className="flex items-center gap-2">
          <span className={`text-xs px-3 py-1 rounded-lg font-bold border flex items-center gap-1.5 ${config.badge}`}>
            {config.icon}
            {state?.replace(/_/g, ' ') || 'COMPUTING REGIME'}
          </span>
          <span className="text-xs bg-secondary text-foreground px-2.5 py-1 rounded-lg font-mono font-semibold border border-border">
            Confidence: {overview?.confidence_score ?? 85}%
          </span>
        </div>
      </div>

      {/* Headline & Institutional Rationale */}
      <div className="bg-secondary/40 rounded-lg p-3.5 border border-border space-y-2">
        <div className="flex items-center gap-2">
          <Compass className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">{overview?.summary_headline || 'Market State Diagnosis'}</h3>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">{overview?.institutional_rationale}</p>
      </div>

      {/* Proximity Summary Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        <div className="bg-secondary/60 p-2.5 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground block">Spot Price</span>
          <span className="font-bold font-mono text-sm text-foreground">
            {overview?.spot_price ? `₹${overview.spot_price.toLocaleString('en-IN')}` : '---'}
          </span>
        </div>

        <div className="bg-secondary/60 p-2.5 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground block">Nearest Resistance</span>
          <span className="font-bold font-mono text-sm text-destructive">
            {overview?.key_levels?.nearest_resistance ? `₹${overview.key_levels.nearest_resistance}` : '---'}
          </span>
          <span className="text-[10px] text-muted-foreground block">
            +{overview?.key_levels?.distance_to_resistance_pts ?? 0} pts away
          </span>
        </div>

        <div className="bg-secondary/60 p-2.5 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground block">Nearest Support</span>
          <span className="font-bold font-mono text-sm text-success">
            {overview?.key_levels?.nearest_support ? `₹${overview.key_levels.nearest_support}` : '---'}
          </span>
          <span className="text-[10px] text-muted-foreground block">
            -{overview?.key_levels?.distance_to_support_pts ?? 0} pts away
          </span>
        </div>

        <div className="bg-secondary/60 p-2.5 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground flex items-center gap-1">
            <ShieldCheck className="w-3 h-3 text-primary" /> VIX Regime
          </span>
          <span className="font-bold font-mono text-sm text-foreground">
            {overview?.vix_regime?.regime_category?.replace('_', ' ') || 'NORMAL'}
          </span>
          <span className="text-[10px] text-muted-foreground block">
            VIX: {overview?.vix_regime?.vix_value ?? '---'} ({overview?.vix_regime?.change_percent ?? 0}%)
          </span>
        </div>
      </div>
    </div>
  );
}
