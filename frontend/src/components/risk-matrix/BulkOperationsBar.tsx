'use client';

import React, { useCallback, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';

type PurgePreview = {
  auditedCount: number;
  openTrades: number;
  closedTrades: number;
  activeCount: number;
  armedCount: number;
  confirmedCount: number;
};

type PurgeResult = { deleted: number; requested: number };

/**
 * Signal database maintenance.
 *
 * Copy must match the backend `delete_all + confirm_all` path exactly: it
 * scans FSM records INCLUDING terminal states and the audit ledger, and each
 * ARMED/CONFIRMED/EXECUTED signal with an open paper position is closed at
 * market before deletion. Active signals are not protected.
 */
export const BulkOperationsBar: React.FC = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [preview, setPreview] = useState<PurgePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [result, setResult] = useState<PurgeResult | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  // Last-write-wins: a preview fetch from an earlier dialog open cannot
  // clobber the counts of a newer one.
  const previewSeqRef = useRef(0);

  const loadPreview = useCallback(async () => {
    const seq = ++previewSeqRef.current;
    setPreviewLoading(true);
    setPreviewError(null);
    const [statusRes, auditRes] = await Promise.allSettled([
      api.getSignalsStatus(),
      api.getSignalsAudit({ limit: 1 }),
    ]);
    if (seq !== previewSeqRef.current) return;
    if (statusRes.status === 'rejected' || auditRes.status === 'rejected') {
      const reason =
        statusRes.status === 'rejected' ? statusRes.reason : (auditRes as PromiseRejectedResult).reason;
      setPreview(null);
      setPreviewError(errorMessage(reason, 'backend did not return purge counts'));
    } else {
      const summary = auditRes.value?.summary ?? {};
      setPreview({
        auditedCount: Number(summary.total_signals_audited ?? 0),
        openTrades: Number(summary.open_trades ?? 0),
        closedTrades: Number(summary.closed_trades ?? 0),
        activeCount: Number(statusRes.value?.active_count ?? 0),
        armedCount: Number(statusRes.value?.armed_count ?? 0),
        confirmedCount: Number(statusRes.value?.confirmed_count ?? 0),
      });
    }
    setPreviewLoading(false);
  }, []);

  const openPurgeDialog = () => {
    setModalOpen(true);
    setResult(null);
    setFailure(null);
    void loadPreview();
  };

  const handleBulkDelete = async () => {
    setDeleting(true);
    setFailure(null);
    try {
      const res = await api.bulkDeleteSignals({ delete_all: true, confirm_all: true });
      setResult({ deleted: res?.deleted_count ?? 0, requested: res?.requested_count ?? 0 });
      setPreview(null);
    } catch (err) {
      const msg = errorMessage(err, 'Purge failed — no confirmation was recorded.');
      setFailure(msg);
      // Rethrow so ConfirmDialog keeps itself open and shows the failure inline.
      throw err instanceof Error ? err : new Error(msg);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <>
      <div className="p-3.5 rounded-xl border border-border bg-card shadow-xs flex flex-wrap items-center justify-between gap-3 font-mono text-xs">
        <div>
          <span className="text-ink-2 font-semibold">SIGNAL DATABASE MAINTENANCE:</span>
          <span className="text-ink-3 ml-2">
            Purge signal records across every state — open paper positions are closed first
          </span>
        </div>

        <div className="flex items-center gap-2">
          {result && (
            <span role="status" aria-live="polite" className="text-up-strong font-semibold">
              Purged {result.deleted} of {result.requested} matched record(s)
            </span>
          )}
          {failure && (
            <span role="alert" className="text-down-strong font-semibold">
              {failure}
            </span>
          )}
          <button
            onClick={openPurgeDialog}
            disabled={deleting}
            className="px-3 py-1.5 rounded bg-down-wash hover:bg-down/20 border border-down-line text-down-strong font-semibold transition-all disabled:opacity-50"
          >
            Purge Signals (All States)
          </button>
        </div>
      </div>

      <ConfirmDialog
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onConfirm={handleBulkDelete}
        title="PURGE ALL SIGNALS — ALL STATES"
        message={
          <div className="space-y-2">
            <p>
              This permanently deletes <strong>every signal matched by the purge</strong>: all FSM
              records (including terminal states) and all audit-ledger records. Any ARMED, CONFIRMED
              or EXECUTED signal with an open paper position is <strong>closed at market first</strong> —
              active signals are <strong>not protected</strong>. This cannot be undone.
            </p>
            {previewLoading ? (
              <p className="text-ink-3">Loading live purge counts…</p>
            ) : preview ? (
              <ul className="text-[11px] text-ink-2 space-y-0.5">
                <li>
                  Audit ledger reports: {preview.auditedCount} record(s) — {preview.openTrades} open,{' '}
                  {preview.closedTrades} settled.
                </li>
                <li>
                  FSM active: {preview.activeCount} ({preview.armedCount} armed/triggered,{' '}
                  {preview.confirmedCount} confirmed). Terminal FSM records are included by the scan.
                </li>
                <li>The backend caps a single purge at 500 records; repeat if the match is larger.</li>
              </ul>
            ) : previewError ? (
              <p role="alert" className="text-warn-strong">
                Live counts unavailable ({previewError}) — the purge would still delete every matching
                record.
              </p>
            ) : null}
          </div>
        }
        confirmLabel="PURGE ALL MATCHED SIGNALS"
        destructive={true}
        requireTypedConfirmation="DELETE"
      />
    </>
  );
};
