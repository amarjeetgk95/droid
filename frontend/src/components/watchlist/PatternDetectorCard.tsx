'use client';

import { DetectedPatternModel } from '@/lib/types';
import { Sparkles, TrendingUp, TrendingDown, Layers, Target, ShieldAlert } from 'lucide-react';

export function PatternDetectorCard({
  patterns,
  timeframe,
  onSelectTimeframe,
  symbol,
}: {
  patterns: DetectedPatternModel[];
  timeframe: string;
  onSelectTimeframe: (tf: string) => void;
  symbol: string;
}) {
  const timeframes = ['5m', '15m', '1h', '1D'];

  const getBiasConfig = (b: string) => {
    switch (b) {
      case 'BULLISH':
        return {
          icon: <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />,
          badge: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
        };
      case 'BEARISH':
        return {
          icon: <TrendingDown className="w-3.5 h-3.5 text-rose-400" />,
          badge: 'bg-rose-500/20 text-rose-400 border-rose-500/30',
        };
      default:
        return {
          icon: <Layers className="w-3.5 h-3.5 text-primary" />,
          badge: 'bg-primary/20 text-primary border-primary/30',
        };
    }
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">
            Price Action & Candlestick Pattern Detector ({symbol})
          </h3>
        </div>

        {/* Timeframe Selector */}
        <div className="flex items-center gap-1 bg-secondary/60 p-1 rounded-lg border border-border">
          {timeframes.map((tf) => (
            <button
              key={tf}
              onClick={() => onSelectTimeframe(tf)}
              className={`px-2.5 py-1 rounded text-xs font-bold transition-all cursor-pointer ${
                timeframe === tf
                  ? 'bg-primary text-primary-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      {patterns.length === 0 ? (
        <div className="p-8 text-center bg-secondary/30 rounded-lg border border-border text-muted-foreground text-xs">
          No distinct candlestick pattern triggers identified on the {timeframe} timeframe. Market is currently consolidating.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {patterns.map((pat, idx) => {
            const config = getBiasConfig(pat.bias);
            return (
              <div
                key={idx}
                className="bg-secondary/40 border border-border rounded-xl p-3.5 space-y-2.5 hover:border-primary/40 transition-all"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className={`text-[11px] px-2 py-0.5 rounded-full font-bold border flex items-center gap-1 ${config.badge}`}>
                    {config.icon}
                    {pat.bias} ({pat.confidence}%)
                  </span>
                  <span className="text-[10px] font-mono text-muted-foreground">
                    TF: {pat.timeframe}
                  </span>
                </div>

                <div>
                  <h4 className="text-xs font-bold text-foreground">{pat.name}</h4>
                  <p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5">
                    {pat.description}
                  </p>
                </div>

                {/* Levels Strip */}
                <div className="grid grid-cols-3 gap-1.5 pt-2 border-t border-border text-[11px] font-mono">
                  <div className="bg-secondary/70 p-1.5 rounded">
                    <span className="text-[9px] text-muted-foreground block font-sans">Trigger</span>
                    <strong className="text-foreground">₹{pat.trigger_price}</strong>
                  </div>

                  <div className="bg-secondary/70 p-1.5 rounded">
                    <span className="text-[9px] text-muted-foreground block font-sans flex items-center gap-0.5">
                      <ShieldAlert className="w-2.5 h-2.5 text-destructive" /> Stop / Inval
                    </span>
                    <strong className="text-destructive">₹{pat.invalidation_level}</strong>
                  </div>

                  <div className="bg-secondary/70 p-1.5 rounded">
                    <span className="text-[9px] text-muted-foreground block font-sans flex items-center gap-0.5">
                      <Target className="w-2.5 h-2.5 text-success" /> Target
                    </span>
                    <strong className="text-success">₹{pat.target_level}</strong>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
