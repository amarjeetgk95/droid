'use client';

import { OIBuildupItem } from '@/lib/types';
import { Activity, TrendingUp, TrendingDown } from 'lucide-react';

export function OIBuildupMatrix({
  buildup,
  allTrackedBuildups,
}: {
  buildup: OIBuildupItem | null;
  allTrackedBuildups: OIBuildupItem[];
}) {
  const quadrants = [
    {
      type: 'LONG_BUILDUP',
      title: 'Long Buildup',
      condition: 'Price ▲ + OI ▲',
      sentiment: 'Bullish Accumulation',
      bgColor: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
      activeBorder: 'ring-2 ring-emerald-500',
      desc: 'Institutions creating fresh long positions with rising open interest.',
    },
    {
      type: 'SHORT_BUILDUP',
      title: 'Short Buildup',
      condition: 'Price ▼ + OI ▲',
      sentiment: 'Bearish Shorting',
      bgColor: 'bg-rose-500/10 border-rose-500/30 text-rose-400',
      activeBorder: 'ring-2 ring-rose-500',
      desc: 'Institutions creating aggressive short positions with rising open interest.',
    },
    {
      type: 'SHORT_COVERING',
      title: 'Short Covering',
      condition: 'Price ▲ + OI ▼',
      sentiment: 'Short Squeeze / Relief',
      bgColor: 'bg-teal-500/10 border-teal-500/30 text-teal-400',
      activeBorder: 'ring-2 ring-teal-500',
      desc: 'Bearish short-sellers liquidating and buying back positions.',
    },
    {
      type: 'LONG_UNWINDING',
      title: 'Long Unwinding',
      condition: 'Price ▼ + OI ▼',
      sentiment: 'Profit Taking / Long Exit',
      bgColor: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
      activeBorder: 'ring-2 ring-amber-500',
      desc: 'Long position holders closing positions and booking profits.',
    },
  ];

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">4-Quadrant Open Interest Buildup Engine</h3>
        </div>
        <span className="text-xs text-muted-foreground">Price Action vs OI Dynamics</span>
      </div>

      {/* 4 Quadrants Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {quadrants.map((q) => {
          const isActive = buildup?.buildup_type === q.type;
          return (
            <div
              key={q.type}
              className={`p-3.5 rounded-lg border transition-all ${q.bgColor} ${
                isActive ? `${q.activeBorder} shadow-md bg-opacity-20` : 'opacity-70'
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-bold text-xs flex items-center gap-1.5">
                  {q.title}
                  {isActive && (
                    <span className="text-[10px] bg-primary text-primary-foreground px-1.5 py-0.5 rounded font-bold">
                      ACTIVE
                    </span>
                  )}
                </span>
                <span className="font-mono text-[11px] font-semibold">{q.condition}</span>
              </div>
              <p className="text-[11px] opacity-90 mb-2">{q.desc}</p>
              <div className="text-[10px] font-semibold uppercase tracking-wider opacity-75">
                Signal: {q.sentiment}
              </div>
            </div>
          );
        })}
      </div>

      {/* Active Symbol Interpretation Box */}
      {buildup && (
        <div className="bg-secondary/40 rounded-lg p-3 border border-border space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <span className="font-bold text-foreground">
              {buildup.underlying} Near Futures Buildup Summary:
            </span>
            <span className="text-muted-foreground font-mono">
              Strength: <strong className="text-foreground font-bold">{buildup.strength}</strong>
            </span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">{buildup.interpretation}</p>
        </div>
      )}

      {/* Multi-Index Buildup Leaderboard */}
      {allTrackedBuildups.length > 0 && (
        <div className="space-y-2 pt-2 border-t border-border">
          <h4 className="text-xs font-semibold text-muted-foreground">Tracked Index Futures Buildups</h4>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {allTrackedBuildups.map((b) => (
              <div key={b.underlying} className="bg-secondary/60 p-2.5 rounded-lg border border-border text-xs">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-bold text-foreground">{b.underlying}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                    b.buildup_type === 'LONG_BUILDUP' ? 'bg-emerald-500/20 text-emerald-400' :
                    b.buildup_type === 'SHORT_BUILDUP' ? 'bg-rose-500/20 text-rose-400' :
                    b.buildup_type === 'SHORT_COVERING' ? 'bg-teal-500/20 text-teal-400' : 'bg-amber-500/20 text-amber-400'
                  }`}>
                    {b.buildup_type.replace('_', ' ')}
                  </span>
                </div>
                <div className="flex justify-between text-[11px] text-muted-foreground font-mono">
                  <span className={`flex items-center gap-0.5 ${b.price_change >= 0 ? 'text-success' : 'text-destructive'}`}>
                    {b.price_change >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                    {b.price_change_percent}%
                  </span>
                  <span>OI: {b.oi_change_percent > 0 ? '+' : ''}{b.oi_change_percent}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
