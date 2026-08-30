'use client';

import { TermStructureCurve } from '@/lib/types';
import { Layers, ArrowRight } from 'lucide-react';

export function TermStructureCard({
  termStructure,
}: {
  termStructure: TermStructureCurve | null;
}) {
  if (!termStructure || termStructure.contracts.length === 0) {
    return (
      <div className="bg-card border border-border rounded-xl p-6 text-center text-muted-foreground">
        No futures contracts available for term structure modeling.
      </div>
    );
  }

  const contracts = termStructure.contracts;

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">Futures Term Structure & Carrying Cost</h3>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-muted-foreground">
            Next-Near Spread:{' '}
            <span className="font-bold font-mono text-foreground">
              {termStructure.calendar_spread_next_near > 0 ? '+' : ''}₹{termStructure.calendar_spread_next_near}
            </span>
          </span>
          <span className="text-muted-foreground">
            Far-Next Spread:{' '}
            <span className="font-bold font-mono text-foreground">
              {termStructure.calendar_spread_far_next > 0 ? '+' : ''}₹{termStructure.calendar_spread_far_next}
            </span>
          </span>
        </div>
      </div>

      {/* Contracts Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left border-collapse">
          <thead>
            <tr className="border-b border-border text-muted-foreground font-semibold">
              <th className="py-2 px-3">Tenor</th>
              <th className="py-2 px-3">Contract</th>
              <th className="py-2 px-3">Expiry</th>
              <th className="py-2 px-3 text-right">LTP</th>
              <th className="py-2 px-3 text-right">Basis (Pts)</th>
              <th className="py-2 px-3 text-right">Basis %</th>
              <th className="py-2 px-3 text-right">Annualized CoC</th>
              <th className="py-2 px-3 text-right">Fair Value</th>
              <th className="py-2 px-3 text-right">Spread</th>
              <th className="py-2 px-3 text-right">Open Interest</th>
              <th className="py-2 px-3 text-right">DTE</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40 font-mono">
            {contracts.map((c) => (
              <tr key={c.symbol} className="hover:bg-accent/40 transition-colors">
                <td className="py-2.5 px-3">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    c.tenor === 'NEAR' ? 'bg-primary/20 text-primary' :
                    c.tenor === 'NEXT' ? 'bg-secondary text-foreground' : 'bg-muted text-muted-foreground'
                  }`}>
                    {c.tenor}
                  </span>
                </td>
                <td className="py-2.5 px-3 font-sans font-bold text-foreground">{c.symbol}</td>
                <td className="py-2.5 px-3 text-muted-foreground">{c.expiry}</td>
                <td className="py-2.5 px-3 text-right font-bold text-foreground">₹{c.ltp.toLocaleString('en-IN')}</td>
                <td className={`py-2.5 px-3 text-right font-bold ${c.basis >= 0 ? 'text-success' : 'text-destructive'}`}>
                  {c.basis > 0 ? '+' : ''}₹{c.basis}
                </td>
                <td className="py-2.5 px-3 text-right text-muted-foreground">{c.basis_percent}%</td>
                <td className="py-2.5 px-3 text-right font-bold text-warning">{c.cost_of_carry_percent}%</td>
                <td className="py-2.5 px-3 text-right text-muted-foreground">₹{c.fair_value.toLocaleString('en-IN')}</td>
                <td className="py-2.5 px-3 text-right text-muted-foreground">
                  {c.fair_value_spread > 0 ? '+' : ''}₹{c.fair_value_spread}
                </td>
                <td className="py-2.5 px-3 text-right">{c.open_interest.toLocaleString('en-IN')}</td>
                <td className="py-2.5 px-3 text-right text-muted-foreground">{c.days_to_expiry}d</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Visual Curve Flow */}
      <div className="bg-secondary/40 rounded-lg p-3 border border-border flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground font-medium">Curve Progression:</span>
          <span className="font-bold text-foreground">Cash (₹{termStructure.spot_price.toLocaleString('en-IN')})</span>
          <ArrowRight className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="font-bold text-primary">Near (₹{contracts[0]?.ltp.toLocaleString('en-IN')})</span>
          {contracts[1] && (
            <>
              <ArrowRight className="w-3.5 h-3.5 text-muted-foreground" />
              <span className="font-bold text-foreground">Next (₹{contracts[1].ltp.toLocaleString('en-IN')})</span>
            </>
          )}
          {contracts[2] && (
            <>
              <ArrowRight className="w-3.5 h-3.5 text-muted-foreground" />
              <span className="font-bold text-muted-foreground">Far (₹{contracts[2].ltp.toLocaleString('en-IN')})</span>
            </>
          )}
        </div>
        <span className="text-[11px] text-muted-foreground">
          Market Status:{' '}
          <strong className="text-foreground font-semibold">
            {termStructure.curve_state === 'CONTANGO' ? 'Contango (Normal Premium)' : 'Backwardation (Discount)'}
          </strong>
        </span>
      </div>
    </div>
  );
}
