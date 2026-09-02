import { MarketBreadthData } from '@/lib/types';
import { DataStatus } from '../common/DataStatus';
import { safeNum, safeStr, safeInt } from '@/lib/utils';
import { BarChart3 } from 'lucide-react';

export function MarketBreadth({ data, loading }: { data: MarketBreadthData | null; loading: boolean }) {
  if (loading || !data) {
    return (
      <div className="bg-card rounded-xl border border-border p-5 h-72 animate-pulse flex flex-col justify-between">
        <div className="h-4 bg-secondary rounded w-36" />
        <div className="h-8 bg-secondary rounded w-full" />
        <div className="h-24 bg-secondary rounded w-full" />
      </div>
    );
  }

  const advancing = Number(data.advancing) || 0;
  const declining = Number(data.declining) || 0;
  const unchanged = Number(data.unchanged) || 0;
  const total = advancing + declining + unchanged || 1;
  const advPct = (advancing / total) * 100;
  const decPct = (declining / total) * 100;
  const unchPct = (unchanged / total) * 100;

  const sentiment = (data.sentiment || 'NEUTRAL').toUpperCase();
  const isBull = sentiment.includes('BULL') || (data.advance_decline_ratio ?? 0) > 1.2;
  const isBear = sentiment.includes('BEAR') || (data.advance_decline_ratio ?? 0) < 0.8;

  return (
    <div className="bg-card rounded-xl border border-border p-5 space-y-4 shadow-xs">
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
            <BarChart3 className="w-4 h-4" />
          </div>
          <h2 className="text-sm font-bold tracking-tight text-foreground uppercase">
            Market Breadth &amp; Sectors
          </h2>
        </div>
        <DataStatus status={data.status} />
      </div>

      {/* Advance / Decline Bar */}
      <div className="space-y-1.5 bg-secondary/30 border border-border/50 rounded-xl p-3.5">
        <div className="flex justify-between text-xs font-semibold">
          <span className="text-emerald-500 flex items-center gap-1">
            <span>Advances:</span>
            <strong className="tabular-nums font-mono">{safeInt(advancing)}</strong>
            <span className="text-[10px] text-muted-foreground">({advPct.toFixed(0)}%)</span>
          </span>
          <span className="text-muted-foreground flex items-center gap-1">
            <span>Unchanged:</span>
            <strong className="tabular-nums font-mono">{safeInt(unchanged)}</strong>
          </span>
          <span className="text-rose-500 flex items-center gap-1">
            <span>Declines:</span>
            <strong className="tabular-nums font-mono">{safeInt(declining)}</strong>
            <span className="text-[10px] text-muted-foreground">({decPct.toFixed(0)}%)</span>
          </span>
        </div>

        <div className="w-full h-2.5 rounded-full bg-secondary overflow-hidden flex">
          <div className="bg-emerald-500 h-full transition-all duration-500" style={{ width: `${advPct}%` }} />
          <div className="bg-muted-foreground/30 h-full transition-all duration-500" style={{ width: `${unchPct}%` }} />
          <div className="bg-rose-500 h-full transition-all duration-500" style={{ width: `${decPct}%` }} />
        </div>

        <div className="flex justify-between items-center pt-2 mt-2 border-t border-border/40 text-xs">
          <div>
            <span className="text-muted-foreground text-[11px] block">A/D Ratio</span>
            <span className="text-base font-black tabular-nums font-mono text-foreground">
              {safeNum(data.advance_decline_ratio)}
            </span>
          </div>
          <div className="text-right">
            <span className="text-muted-foreground text-[11px] block">Breadth Sentiment</span>
            <span
              className={`text-xs px-2 py-0.5 rounded font-bold uppercase inline-block mt-0.5 ${
                isBull
                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                  : isBear
                  ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                  : 'bg-secondary text-foreground'
              }`}
            >
              {safeStr(data.sentiment).replace(/_/g, ' ')}
            </span>
          </div>
        </div>
      </div>

      {/* Sector Performance Grid */}
      {data.sectors && data.sectors.length > 0 && (
        <div>
          <h3 className="text-xs font-bold text-muted-foreground uppercase mb-2">
            Key Sector Performance
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {data.sectors.slice(0, 6).map((sector) => {
              const chg = sector.change_percent ?? 0;
              const isP = chg >= 0;
              return (
                <div
                  key={sector.name}
                  className="flex justify-between items-center px-3 py-2 rounded-lg bg-secondary/20 border border-border/40 text-xs hover:bg-secondary/40 transition-colors"
                >
                  <span className="font-medium text-foreground truncate max-w-[120px]">
                    {sector.name}
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-muted-foreground font-mono">
                      {sector.advancing}▲ / {sector.declining}▼
                    </span>
                    <span
                      className={`font-mono font-bold tabular-nums ${
                        isP ? 'text-emerald-500' : 'text-rose-500'
                      }`}
                    >
                      {isP ? '+' : ''}
                      {safeNum(chg)}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
