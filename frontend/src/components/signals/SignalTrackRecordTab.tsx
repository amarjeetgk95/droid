'use client';

import React from 'react';
import dynamic from 'next/dynamic';
import { Button } from '@/components/ui/button';
import { AlertTriangle, Award, CheckCircle2 } from 'lucide-react';
import type { AuditTradeRecord, AuditSummary } from './SignalAuditTable';
import type { TrackView } from './useSignalEngine';

const SignalPerformanceView = dynamic(
  () => import('./SignalPerformanceView').then((m) => m.SignalPerformanceView),
  { ssr: false, loading: () => <div className="bg-card border border-border rounded-xl p-5 h-48 animate-pulse" /> },
);
const SignalAuditTable = dynamic(
  () => import('./SignalAuditTable').then((m) => m.SignalAuditTable),
  { ssr: false, loading: () => <div className="bg-card border border-border rounded-xl p-5 h-48 animate-pulse" /> },
);

export interface SignalTrackRecordTabProps {
  trackView: TrackView;
  setTrackView: (v: TrackView) => void;
  auditTrades: AuditTradeRecord[];
  auditSummary: AuditSummary | null;
  auditLoading: boolean;
  auditError: string | null;
  onRefreshAudit: () => void;
  onSelectSignal: (sigId: string) => void;
}

export function SignalTrackRecordTab({
  trackView,
  setTrackView,
  auditTrades,
  auditSummary,
  auditLoading,
  auditError,
  onRefreshAudit,
  onSelectSignal,
}: SignalTrackRecordTabProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-1.5">
        <button
          onClick={() => setTrackView('ledger')}
          className={`px-3 py-1.5 text-xs font-bold rounded-lg border transition-all cursor-pointer flex items-center gap-1.5 ${
            trackView === 'ledger'
              ? 'bg-primary text-primary-foreground border-primary'
              : 'bg-secondary/60 hover:bg-secondary border-transparent'
          }`}
        >
          <CheckCircle2 className="w-3.5 h-3.5" /> Ledger &amp; P&amp;L
        </button>
        <button
          onClick={() => setTrackView('performance')}
          className={`px-3 py-1.5 text-xs font-bold rounded-lg border transition-all cursor-pointer flex items-center gap-1.5 ${
            trackView === 'performance'
              ? 'bg-primary text-primary-foreground border-primary'
              : 'bg-secondary/60 hover:bg-secondary border-transparent'
          }`}
        >
          <Award className="w-3.5 h-3.5" /> Performance
        </button>
        <span className="text-[11px] text-muted-foreground font-mono ml-2 hidden sm:inline">
          Index paper trades only • crypto is read-only
        </span>
      </div>

      {trackView === 'performance' ? (
        <SignalPerformanceView />
      ) : (
        <>
          {auditError && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive flex items-center gap-2 flex-wrap">
              <AlertTriangle className="w-4 h-4 shrink-0" /> {auditError}
              <Button size="sm" variant="outline" className="h-7 text-[11px] ml-auto cursor-pointer" onClick={onRefreshAudit}>
                Retry
              </Button>
            </div>
          )}
          <SignalAuditTable
            trades={auditTrades}
            summary={auditSummary}
            loading={auditLoading}
            onRefresh={onRefreshAudit}
            onSelectSignal={onSelectSignal}
          />
        </>
      )}
    </div>
  );
}
