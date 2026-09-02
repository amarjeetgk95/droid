import { MarketBreadthData } from '@/lib/types';
import { DataStatus } from '../common/DataStatus';
import { safeNum, safeStr, safeInt } from '@/lib/utils';
import { BarChart3 } from 'lucide-react';

export function MarketBreadth({ data, loading }: { data: MarketBreadthData | null; loading: boolean }) {
  if (loading || !data) {
    return (
      <div className="bg-card rounded-xl border border-border p-4 space-y-3 cv-auto" style={{ contentVisibility: 'auto', containIntrinsicSize: '0 280px' } as React.CSSProperties}>
        <div className="skeleton h-4 w-36 rounded" />
        <div className="skeleton h-6 w-full rounded" />
        <div className="skeleton h-20 w-full rounded" />
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
    <div className="bg-card rounded-xl border border-border p-4 space-y-3 shadow-sm [contain:paint] cv-auto" style={{ contentVisibility: 'auto', containIntrinsicSize: '0 320px' } as React.CSSProperties}>
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-2">
          <div className="p-1 rounded-md bg-blue-500/10 border border-blue-500/15 text-blue-400">
            <BarChart3 className="w-3.5 h-3.5" />
          </div>
          <h2 className="text-[11px] font-bold tracking-widest text-muted-foreground uppercase">Market Breadth & Sectors</h2>
        </div>
        <DataStatus status={data.status} />
      </div>

      {/* Advance / Decline Bar — tight */}
      <div className="space-y-2 bg-card/50 border border-border rounded-lg p-3">
        <div className="flex justify-between text-[11px] font-medium">
          <span className="text-emerald-400 flex items-center gap-1">
            Advances <strong className="tabular-nums font-mono">{safeInt(advancing)}</strong>
            <span className="text-[10px] text-slate-500">({advPct.toFixed(0)}%)</span>
          </span>
          <span className="text-slate-500 flex items-center gap-1 text-[11px]">
            Unch <strong className="tabular-nums font-mono text-muted-foreground">{safeInt(unchanged)}</strong>
          </span>
          <span className="text-red-400 flex items-center gap-1">
            Declines <strong className="tabular-nums font-mono">{safeInt(declining)}</strong>
            <span className="text-[10px] text-slate-500">({decPct.toFixed(0)}%)</span>
          </span>
        </div>

        <div className="w-full h-2 rounded-full bg-secondary overflow-hidden flex">
          <div className="bg-emerald-500 h-full" style={{ width: `${advPct}%` }} />
          <div className="bg-slate-600 h-full" style={{ width: `${unchPct}%` }} />
          <div className="bg-red-500 h-full" style={{ width: `${decPct}%` }} />
        </div>

        <div className="flex justify-between items-center pt-2 border-t border-border text-xs">
          <div>
            <span className="text-slate-500 text-[10px] tracking-wide uppercase block leading-none">A/D Ratio</span>
            <span className="text-sm font-bold tabular-nums font-mono text-foreground leading-none mt-1 block">{safeNum(data.advance_decline_ratio)}</span>
          </div>
          <div className="text-right">
            <span className="text-slate-500 text-[10px] tracking-wide uppercase block leading-none">Sentiment</span>
            <span
              className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase inline-block mt-1 tracking-wide border ${
                isBull
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                  : isBear
                  ? 'bg-red-500/10 text-red-400 border-red-500/20'
                  : 'bg-secondary text-muted-foreground border-border'
              }`}
            >
              {safeStr(data.sentiment).replace(/_/g, ' ')}
            </span>
          </div>
        </div>
      </div>

      {data.sectors && data.sectors.length > 0 && (
        <div>
          <h3 className="text-[10px] font-semibold tracking-widest text-slate-500 uppercase mb-2">Key Sector Performance</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
            {data.sectors.slice(0, 6).map((sector) => {
              const chg = sector.change_percent ?? 0;
              const isP = chg >= 0;
              return (
                <div
                  key={sector.name}
                  className="flex justify-between items-center px-2.5 py-2 rounded-md bg-card/40 border border-border text-xs hover:bg-secondary/50 transition-colors"
                >
                  <span className="font-medium text-foreground truncate max-w-[120px] text-[12px]">{sector.name}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-[10px] text-slate-500 font-mono">
                      {sector.advancing}▲ / {sector.declining}▼
                    </span>
                    <span className={`font-mono font-semibold tabular-nums text-xs ${isP ? 'text-emerald-400' : 'text-red-400'}`}>
                      {isP ? '+' : ''}{safeNum(chg)}%
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
