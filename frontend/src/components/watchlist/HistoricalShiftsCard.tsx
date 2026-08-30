'use client';

import { HistoricalShiftsResponse } from '@/lib/types';
import { History } from 'lucide-react';

export function HistoricalShiftsCard({
  shiftsData,
}: {
  shiftsData: HistoricalShiftsResponse | null;
}) {
  if (!shiftsData || shiftsData.shifts.length === 0) {
    return null;
  }

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">
            Multi-Session Positioning Shifts ({shiftsData.symbol})
          </h3>
        </div>
        <span className="text-xs text-muted-foreground">Historical Trajectory</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left border-collapse">
          <thead>
            <tr className="border-b border-border text-muted-foreground font-semibold">
              <th className="py-2 px-2">Date</th>
              <th className="py-2 px-2 text-right">Spot Close</th>
              <th className="py-2 px-2 text-right">Max Pain Strike</th>
              <th className="py-2 px-2 text-right">PCR (OI)</th>
              <th className="py-2 px-2 text-right">PCR (Vol)</th>
              <th className="py-2 px-2 text-right">ATM IV (%)</th>
              <th className="py-2 px-2 text-right">Futures Basis</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40 font-mono">
            {shiftsData.shifts.map((pt, idx) => (
              <tr key={idx} className="hover:bg-accent/30 transition-colors">
                <td className="py-2 px-2 font-sans font-medium text-foreground">{pt.date}</td>
                <td className="py-2 px-2 text-right font-bold text-foreground">₹{pt.spot_close}</td>
                <td className="py-2 px-2 text-right text-primary font-bold">₹{pt.max_pain_strike}</td>
                <td className={`py-2 px-2 text-right font-bold ${pt.pcr_oi >= 1.0 ? 'text-success' : 'text-destructive'}`}>
                  {pt.pcr_oi}
                </td>
                <td className="py-2 px-2 text-right text-muted-foreground">{pt.pcr_volume}</td>
                <td className="py-2 px-2 text-right text-warning">{pt.atm_iv}%</td>
                <td className="py-2 px-2 text-right text-foreground">+{pt.futures_basis}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
