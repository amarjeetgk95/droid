'use client';

import { useState } from 'react';
import { AlertTriangle, CheckCircle2, Wrench, RefreshCw, HelpCircle } from 'lucide-react';
import type { HistoricalDataGap } from '@/lib/api/historical';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/toast';

interface QualityAndGapViewProps {
  gaps: HistoricalDataGap[];
  onGapUpdated: () => void;
}

export function QualityAndGapView({ gaps, onGapUpdated }: QualityAndGapViewProps) {
  const { push } = useToast();
  const [repairingId, setRepairingId] = useState<string | null>(null);

  const handleRepair = async (gapId: string) => {
    setRepairingId(gapId);
    try {
      const res = await api.repairHistoricalGap(gapId);
      push('success', 'Gap Repaired', `Status: ${res.gap.status}. ${res.gap.notes || ''}`);
      onGapUpdated();
    } catch (err: any) {
      push('error', 'Repair Failed', err?.message || 'Could not repair session gap.');
    } finally {
      setRepairingId(null);
    }
  };

  const getGapStatusBadge = (status: string) => {
    switch (status) {
      case 'RESOLVED':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-bull/10 px-2 py-0.5 text-xs font-medium text-bull">
            <CheckCircle2 className="h-3 w-3" /> Resolved
          </span>
        );
      case 'OPEN':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-bear/10 px-2 py-0.5 text-xs font-medium text-bear">
            <AlertTriangle className="h-3 w-3" /> Open Gap
          </span>
        );
      case 'UNREPAIRABLE_UPSTREAM_OMISSION':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground" title="Upstream provider confirmed 0 candles available">
            <HelpCircle className="h-3 w-3" /> Upstream Omission
          </span>
        );
      case 'REPAIRING':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
            <RefreshCw className="h-3 w-3 animate-spin" /> Repairing...
          </span>
        );
      default:
        return <span className="text-xs text-muted-foreground">{status}</span>;
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card shadow-sm">
      <div className="border-b border-border px-6 py-4">
        <h3 className="text-sm font-semibold text-foreground">Session Gap Manager & Quality Firewall</h3>
        <p className="text-xs text-muted-foreground">
          Detailed accounting of missing intraday candles against the official Indian exchange schedule (09:15 to 15:29 IST).
        </p>
      </div>

      {gaps.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-12 text-center">
          <CheckCircle2 className="h-10 w-10 text-bull" />
          <h4 className="mt-3 text-sm font-semibold text-foreground">Zero Detected Gaps</h4>
          <p className="mt-1 text-xs text-muted-foreground">
            All expected market trading session candles are fully accounted for.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-border bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-6 py-3 font-medium">Date</th>
                <th className="px-4 py-3 font-medium">Expected</th>
                <th className="px-4 py-3 font-medium">Actual</th>
                <th className="px-4 py-3 font-medium">Missing</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Notes</th>
                <th className="px-6 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {gaps.map((gap) => (
                <tr key={gap.gap_id} className="transition-colors hover:bg-muted/30">
                  <td className="px-6 py-3 font-semibold text-foreground">{gap.trading_date}</td>
                  <td className="px-4 py-3 text-muted-foreground">{gap.expected_candles}</td>
                  <td className="px-4 py-3 text-muted-foreground">{gap.actual_candles}</td>
                  <td className="px-4 py-3 font-medium text-bear">{gap.missing_candles}</td>
                  <td className="px-4 py-3">{getGapStatusBadge(gap.status)}</td>
                  <td className="px-4 py-3 text-muted-foreground">{gap.notes || '—'}</td>
                  <td className="px-6 py-3 text-right">
                    {gap.status === 'OPEN' && (
                      <button
                        onClick={() => handleRepair(gap.gap_id)}
                        disabled={repairingId === gap.gap_id}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/20 disabled:opacity-50"
                      >
                        {repairingId === gap.gap_id ? (
                          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Wrench className="h-3.5 w-3.5" />
                        )}
                        Repair
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
