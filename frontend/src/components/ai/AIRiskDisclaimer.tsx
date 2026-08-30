'use client';

import { ShieldAlert, AlertTriangle } from 'lucide-react';

export function AIRiskDisclaimer({
  riskNotes,
  disclaimer,
}: {
  riskNotes?: string;
  disclaimer?: string;
}) {
  return (
    <div className="space-y-3">
      {/* Risk Management Notes */}
      {riskNotes && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl p-4 space-y-1.5 text-xs text-foreground">
          <div className="flex items-center gap-2 font-bold text-destructive">
            <ShieldAlert className="w-4 h-4" />
            <span>Risk Invalidation & Capital Preservation Framework</span>
          </div>
          <p className="text-muted-foreground leading-relaxed">
            {riskNotes}
          </p>
        </div>
      )}

      {/* Institutional Compliance Disclaimer */}
      <div className="bg-secondary/30 border border-border rounded-xl p-3.5 flex items-start gap-2.5 text-[11px] text-muted-foreground">
        <AlertTriangle className="w-4 h-4 text-warning shrink-0 mt-0.5" />
        <p className="leading-relaxed">
          <strong className="text-foreground">Compliance Notice: </strong>
          {disclaimer ||
            'This AI analysis is strictly for quantitative research, strategy backtesting, and educational purposes. DROID does not provide financial advisory services or guaranteed trade execution.'}
        </p>
      </div>
    </div>
  );
}
