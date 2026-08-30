'use client';

import { OptionChainStrikeRow } from '@/lib/types';

export function OptionChainTable({
  strikes,
  viewMode,
  spotPrice,
}: {
  strikes: OptionChainStrikeRow[];
  viewMode: 'standard' | 'greeks';
  spotPrice: number;
}) {
  return (
    <div className="bg-card border border-border rounded-xl shadow-xs overflow-hidden">
      <div className="overflow-x-auto max-h-[650px] overflow-y-auto">
        <table className="w-full text-xs text-left border-collapse">
          {/* Main Table Head */}
          <thead className="sticky top-0 z-20 bg-muted/95 backdrop-blur-xs text-muted-foreground border-b border-border select-none">
            {/* Top Super-Header */}
            <tr className="border-b border-border/60 text-center font-bold tracking-wider">
              <th colSpan={viewMode === 'standard' ? 6 : 6} className="py-2 px-3 text-primary bg-primary/5">
                CALLS (CE)
              </th>
              <th className="py-2 px-4 bg-secondary font-black text-foreground border-x border-border">
                STRIKE
              </th>
              <th colSpan={viewMode === 'standard' ? 6 : 6} className="py-2 px-3 text-warning bg-warning/5">
                PUTS (PE)
              </th>
            </tr>

            {/* Column Headers */}
            <tr className="text-[11px] font-semibold text-muted-foreground">
              {/* Call Columns */}
              {viewMode === 'standard' ? (
                <>
                  <th className="py-2 px-2 text-right">OI</th>
                  <th className="py-2 px-2 text-right">Vol</th>
                  <th className="py-2 px-2 text-right">Bid</th>
                  <th className="py-2 px-2 text-right">Ask</th>
                  <th className="py-2 px-2 text-right text-foreground font-bold">LTP</th>
                  <th className="py-2 px-2 text-right">IV%</th>
                </>
              ) : (
                <>
                  <th className="py-2 px-2 text-right">Delta (Δ)</th>
                  <th className="py-2 px-2 text-right">Gamma (Γ)</th>
                  <th className="py-2 px-2 text-right">Theta (Θ)</th>
                  <th className="py-2 px-2 text-right">Vega (V)</th>
                  <th className="py-2 px-2 text-right text-foreground font-bold">LTP</th>
                  <th className="py-2 px-2 text-right">IV%</th>
                </>
              )}

              {/* Center Strike Column */}
              <th className="py-2 px-4 text-center font-extrabold text-foreground bg-secondary/80 border-x border-border">
                Strike
              </th>

              {/* Put Columns */}
              {viewMode === 'standard' ? (
                <>
                  <th className="py-2 px-2 text-left">IV%</th>
                  <th className="py-2 px-2 text-left text-foreground font-bold">LTP</th>
                  <th className="py-2 px-2 text-left">Bid</th>
                  <th className="py-2 px-2 text-left">Ask</th>
                  <th className="py-2 px-2 text-left">Vol</th>
                  <th className="py-2 px-2 text-left">OI</th>
                </>
              ) : (
                <>
                  <th className="py-2 px-2 text-left">IV%</th>
                  <th className="py-2 px-2 text-left text-foreground font-bold">LTP</th>
                  <th className="py-2 px-2 text-left">Delta (Δ)</th>
                  <th className="py-2 px-2 text-left">Gamma (Γ)</th>
                  <th className="py-2 px-2 text-left">Theta (Θ)</th>
                  <th className="py-2 px-2 text-left">Vega (V)</th>
                </>
              )}
            </tr>
          </thead>

          {/* Table Body */}
          <tbody className="divide-y divide-border/40 font-mono">
            {strikes.map((row) => {
              const ce = row.call;
              const pe = row.put;
              const isAtm = row.is_atm;
              const isCallItm = row.strike < spotPrice;
              const isPutItm = row.strike > spotPrice;

              return (
                <tr
                  key={row.strike}
                  className={`hover:bg-accent/40 transition-colors ${
                    isAtm ? 'bg-primary/10 font-semibold ring-1 ring-primary/40' : ''
                  }`}
                >
                  {/* Call Data Cells */}
                  {viewMode === 'standard' ? (
                    <>
                      <td className={`py-1.5 px-2 text-right ${isCallItm ? 'bg-amber-500/5' : ''}`}>
                        {ce?.open_interest ? ce.open_interest.toLocaleString('en-IN') : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-right ${isCallItm ? 'bg-amber-500/5' : ''}`}>
                        {ce?.volume ? ce.volume.toLocaleString('en-IN') : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-right text-muted-foreground ${isCallItm ? 'bg-amber-500/5' : ''}`}>
                        {ce?.bid ? ce.bid.toFixed(2) : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-right text-muted-foreground ${isCallItm ? 'bg-amber-500/5' : ''}`}>
                        {ce?.ask ? ce.ask.toFixed(2) : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-right font-bold text-foreground ${isCallItm ? 'bg-amber-500/10 text-amber-300' : ''}`}>
                        {ce?.ltp ? `₹${ce.ltp.toFixed(2)}` : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-right text-muted-foreground ${isCallItm ? 'bg-amber-500/5' : ''}`}>
                        {ce?.greeks?.iv ? `${ce.greeks.iv}%` : '---'}
                      </td>
                    </>
                  ) : (
                    <>
                      <td className={`py-1.5 px-2 text-right text-primary ${isCallItm ? 'bg-amber-500/5' : ''}`}>
                        {ce?.greeks?.delta !== undefined ? ce.greeks.delta.toFixed(3) : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-right text-muted-foreground ${isCallItm ? 'bg-amber-500/5' : ''}`}>
                        {ce?.greeks?.gamma !== undefined ? ce.greeks.gamma.toFixed(5) : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-right text-destructive ${isCallItm ? 'bg-amber-500/5' : ''}`}>
                        {ce?.greeks?.theta !== undefined ? ce.greeks.theta.toFixed(2) : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-right text-success ${isCallItm ? 'bg-amber-500/5' : ''}`}>
                        {ce?.greeks?.vega !== undefined ? ce.greeks.vega.toFixed(2) : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-right font-bold text-foreground ${isCallItm ? 'bg-amber-500/10 text-amber-300' : ''}`}>
                        {ce?.ltp ? `₹${ce.ltp.toFixed(2)}` : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-right text-muted-foreground ${isCallItm ? 'bg-amber-500/5' : ''}`}>
                        {ce?.greeks?.iv ? `${ce.greeks.iv}%` : '---'}
                      </td>
                    </>
                  )}

                  {/* Strike Cell */}
                  <td className="py-1.5 px-4 text-center font-black bg-secondary/80 border-x border-border text-foreground">
                    <div className="flex items-center justify-center gap-1">
                      <span>{row.strike.toLocaleString('en-IN')}</span>
                      {isAtm && (
                        <span className="text-[9px] bg-primary text-primary-foreground px-1 rounded font-sans uppercase">
                          ATM
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Put Data Cells */}
                  {viewMode === 'standard' ? (
                    <>
                      <td className={`py-1.5 px-2 text-left text-muted-foreground ${isPutItm ? 'bg-amber-500/5' : ''}`}>
                        {pe?.greeks?.iv ? `${pe.greeks.iv}%` : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-left font-bold text-foreground ${isPutItm ? 'bg-amber-500/10 text-amber-300' : ''}`}>
                        {pe?.ltp ? `₹${pe.ltp.toFixed(2)}` : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-left text-muted-foreground ${isPutItm ? 'bg-amber-500/5' : ''}`}>
                        {pe?.bid ? pe.bid.toFixed(2) : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-left text-muted-foreground ${isPutItm ? 'bg-amber-500/5' : ''}`}>
                        {pe?.ask ? pe.ask.toFixed(2) : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-left ${isPutItm ? 'bg-amber-500/5' : ''}`}>
                        {pe?.volume ? pe.volume.toLocaleString('en-IN') : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-left ${isPutItm ? 'bg-amber-500/5' : ''}`}>
                        {pe?.open_interest ? pe.open_interest.toLocaleString('en-IN') : '---'}
                      </td>
                    </>
                  ) : (
                    <>
                      <td className={`py-1.5 px-2 text-left text-muted-foreground ${isPutItm ? 'bg-amber-500/5' : ''}`}>
                        {pe?.greeks?.iv ? `${pe.greeks.iv}%` : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-left font-bold text-foreground ${isPutItm ? 'bg-amber-500/10 text-amber-300' : ''}`}>
                        {pe?.ltp ? `₹${pe.ltp.toFixed(2)}` : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-left text-warning ${isPutItm ? 'bg-amber-500/5' : ''}`}>
                        {pe?.greeks?.delta !== undefined ? pe.greeks.delta.toFixed(3) : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-left text-muted-foreground ${isPutItm ? 'bg-amber-500/5' : ''}`}>
                        {pe?.greeks?.gamma !== undefined ? pe.greeks.gamma.toFixed(5) : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-left text-destructive ${isPutItm ? 'bg-amber-500/5' : ''}`}>
                        {pe?.greeks?.theta !== undefined ? pe.greeks.theta.toFixed(2) : '---'}
                      </td>
                      <td className={`py-1.5 px-2 text-left text-success ${isPutItm ? 'bg-amber-500/5' : ''}`}>
                        {pe?.greeks?.vega !== undefined ? pe.greeks.vega.toFixed(2) : '---'}
                      </td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
