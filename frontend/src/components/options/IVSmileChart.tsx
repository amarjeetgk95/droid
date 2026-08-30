'use client';

import { OptionChainStrikeRow } from '@/lib/types';
import { Activity } from 'lucide-react';

export function IVSmileChart({
  strikes,
  atmStrike,
}: {
  strikes: OptionChainStrikeRow[];
  atmStrike: number;
}) {
  if (!strikes || strikes.length === 0) return null;

  // Filter strikes that have IV values
  const validPoints = strikes
    .filter((s) => s.call?.greeks?.iv || s.put?.greeks?.iv)
    .map((s) => ({
      strike: s.strike,
      ce_iv: s.call?.greeks?.iv || null,
      pe_iv: s.put?.greeks?.iv || null,
      is_atm: s.is_atm,
    }));

  if (validPoints.length === 0) return null;

  const allIvs = validPoints
    .flatMap((p) => [p.ce_iv, p.pe_iv])
    .filter((v): v is number => v !== null && v > 0);

  const minIv = Math.max(5, Math.floor(Math.min(...allIvs, 10)) - 2);
  const maxIv = Math.ceil(Math.max(...allIvs, 25)) + 2;

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">Implied Volatility Smile & Skew</h3>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-primary" /> Call IV (CE)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-warning" /> Put IV (PE)
          </span>
        </div>
      </div>

      {/* SVG Line / Dot Plot */}
      <div className="h-56 w-full flex items-end gap-1 pt-4 pb-6 px-2 overflow-x-auto border-b border-border">
        {validPoints.map((pt) => {
          const ceHeight = pt.ce_iv ? ((pt.ce_iv - minIv) / (maxIv - minIv)) * 100 : null;
          const peHeight = pt.pe_iv ? ((pt.pe_iv - minIv) / (maxIv - minIv)) * 100 : null;

          return (
            <div key={pt.strike} className="flex-1 min-w-[28px] h-full flex flex-col justify-end items-center relative group">
              {/* Tooltip */}
              <div className="absolute -top-12 z-30 hidden group-hover:flex flex-col items-center bg-popover text-popover-foreground text-[10px] px-2 py-1 rounded shadow-md pointer-events-none whitespace-nowrap border border-border">
                <span>Strike: {pt.strike}</span>
                {pt.ce_iv && <span className="text-primary">Call IV: {pt.ce_iv}%</span>}
                {pt.pe_iv && <span className="text-warning">Put IV: {pt.pe_iv}%</span>}
              </div>

              {/* ATM Reference Line */}
              {pt.is_atm && (
                <div className="absolute inset-0 w-0.5 bg-primary/40 mx-auto border-dashed" />
              )}

              {/* CE IV Dot */}
              {ceHeight !== null && (
                <div
                  style={{ bottom: `${Math.min(95, Math.max(5, ceHeight))}%` }}
                  className="absolute w-2 h-2 rounded-full bg-primary ring-1 ring-primary/60"
                />
              )}

              {/* PE IV Dot */}
              {peHeight !== null && (
                <div
                  style={{ bottom: `${Math.min(95, Math.max(5, peHeight))}%` }}
                  className="absolute w-2 h-2 rounded-full bg-warning ring-1 ring-warning/60"
                />
              )}

              {/* Label */}
              <span
                className={`text-[9px] font-mono absolute -bottom-5 transform -rotate-45 origin-top-left ${
                  pt.is_atm ? 'text-primary font-bold' : 'text-muted-foreground'
                }`}
              >
                {pt.strike}
              </span>
            </div>
          );
        })}
      </div>

      <div className="flex justify-between text-[11px] text-muted-foreground px-2">
        <span>ATM Strike: {atmStrike}</span>
        <span>IV Range: {minIv}% — {maxIv}%</span>
      </div>
    </div>
  );
}
