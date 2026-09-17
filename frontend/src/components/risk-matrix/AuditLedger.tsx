'use client';

import React, { useCallback, useRef, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { api } from '@/lib/api';
import { fmtINR } from '@/components/ui/desk';
import { Card } from '../shared/Card';
import { Badge, type BadgeVariant } from '../shared/Badge';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import {
  type AuditTradeLike,
  UNAVAILABLE,
  ledgerEntryPrice,
  ledgerPnl,
  signedINR,
  valueToneClass,
} from './riskUtils';

function messageOf(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback;
}

function statusVariant(status: string | null | undefined): BadgeVariant {
  switch (status) {
    case 'WON':
    case 'TARGET_1_HIT':
    case 'TARGET_2_HIT':
      return 'success';
    case 'LOST':
    case 'STOP_LOSS_HIT':
      return 'danger';
    case 'EXECUTED':
    case 'CONFIRMED':
    case 'TRIGGERED':
      return 'info';
    case 'VOID':
      return 'warning';
    default:
      return 'neutral';
  }
}

function contractLabel(t: AuditTradeLike): string {
  const base = [t.underlying, t.direction].filter(Boolean).join(' ') || UNAVAILABLE;
  const option = t.option_strike
    ? `${t.option_strike}${t.option_type ?? ''}`
    : t.option_symbol;
  return option ? `${base} · ${option}` : base;
}

/**
 * Signal Audit & Accountability Ledger.
 *
 * Every row is a real backend AuditTradeRecord. Entry is the executed fill
 * (`actual_fill_price` — never the spot trigger), P&L is the backend's
 * `total_pnl_inr`/`actual_pnl_inr`, and records whose economics the backend
 * flagged as unavailable render an explicit UNAVAILABLE instead of ₹0.
 */
export const AuditLedger: React.FC = () => {
  const [trades, setTrades] = useState<AuditTradeLike[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedVoidId, setSelectedVoidId] = useState<string | null>(null);
  const [sanitizing, setSanitizing] = useState(false);
  // Last-write-wins guard: a stale poll response can never replace a newer one.
  const requestSeqRef = useRef(0);

  const fetchAudit = useCallback(async () => {
    const seq = ++requestSeqRef.current;
    try {
      const res = await api.getSignalsAudit({ limit: 50 });
      if (seq !== requestSeqRef.current) return;
      setTrades(Array.isArray(res?.trades) ? (res.trades as AuditTradeLike[]) : []);
      setError(null);
      setUpdatedAt(Date.now());
    } catch (err) {
      if (seq !== requestSeqRef.current) return;
      setError(messageOf(err, 'Audit ledger unavailable'));
    } finally {
      if (seq === requestSeqRef.current) setLoading(false);
    }
  }, []);

  usePolling(fetchAudit, 6000);

  const handleVoidTrade = async () => {
    if (!selectedVoidId) return;
    setActionMessage(null);
    setActionError(null);
    const res = await api.voidAuditTrades(
      [selectedVoidId],
      'Operator quarantined corrupt trade record',
    );
    const voided = res?.voided_count ?? 0;
    if (voided < 1) {
      // Thrown so ConfirmDialog renders the failure in-dialog and stays open.
      throw new Error(`No record voided — ${selectedVoidId} was not found in the ledger.`);
    }
    setTrades((prev) => prev.filter((t) => t.signal_id !== selectedVoidId));
    setActionMessage(
      `Quarantined ${voided} record (${selectedVoidId}) — excluded from the served ledger and P&L aggregates; retained as audit evidence.`,
    );
  };

  const handleSanitize = async () => {
    setSanitizing(true);
    setActionMessage(null);
    setActionError(null);
    try {
      const res = await api.sanitizeSignalsAudit();
      setActionMessage(
        `Sanitize complete — ${res?.db_restored_repaired ?? 0} persisted record(s) repaired, ${res?.memory_sanitized ?? 0} in-memory record(s) sanitized.`,
      );
      void fetchAudit();
    } catch (err) {
      setActionError(messageOf(err, 'Sanitize failed — ledger left unchanged.'));
    } finally {
      setSanitizing(false);
    }
  };

  const initialLoading = loading && trades.length === 0;
  const unavailable = !!error && trades.length === 0;

  return (
    <>
      <Card
        title={`SIGNAL AUDIT & ACCOUNTABILITY LEDGER (${trades.length})`}
        subtitle="Immutable ledger of generated signals, execution fills, and verified P&L outcomes"
        headerAction={
          <div className="flex items-center gap-2">
            {updatedAt !== null && !error && (
              <span className="text-[10px] text-ink-3 font-mono">
                synced {new Date(updatedAt).toLocaleTimeString('en-IN')}
              </span>
            )}
            <button
              onClick={handleSanitize}
              disabled={sanitizing}
              className="px-2.5 py-1 rounded bg-accent-wash hover:bg-accent/20 border border-accent-line text-primary font-mono text-xs font-semibold disabled:opacity-50"
            >
              {sanitizing ? 'Sanitizing Ledger…' : 'Sanitize Ledger'}
            </button>
          </div>
        }
      >
        <div className="space-y-3 font-mono text-xs">
          {actionMessage && (
            <div
              role="status"
              aria-live="polite"
              className="p-2 rounded bg-up-wash border border-up-line text-up-strong"
            >
              {actionMessage}
            </div>
          )}
          {actionError && (
            <div role="alert" className="p-2 rounded bg-down-wash border border-down-line text-down-strong">
              {actionError}
            </div>
          )}
          {error && trades.length > 0 && (
            <div role="alert" className="p-2 rounded bg-warn-wash border border-warn-line text-warn-strong">
              Refresh failed ({error}) — showing the last known ledger
              {updatedAt ? ` from ${new Date(updatedAt).toLocaleTimeString('en-IN')}` : ''}.
            </div>
          )}

          {initialLoading && (
            <p className="p-3 rounded border border-dashed border-border-strong text-ink-3">
              Loading audit ledger…
            </p>
          )}

          {unavailable && (
            <div className="p-3 rounded border border-down-line bg-down-wash text-down-strong space-y-2">
              <p>Audit ledger unavailable — {error}.</p>
              <button
                type="button"
                onClick={() => void fetchAudit()}
                className="px-2.5 py-1 rounded border border-down-line bg-surface hover:bg-down-wash font-semibold"
              >
                Retry
              </button>
            </div>
          )}

          {!initialLoading && !unavailable && trades.length === 0 && (
            <p className="p-3 rounded border border-dashed border-border-strong text-ink-3">
              No audit records — no signal has been registered by the backend yet.
            </p>
          )}

          {trades.length > 0 && (
            <div className="overflow-x-auto w-full">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-border bg-surface-subtle text-ink-3 text-[10px] uppercase">
                    <th className="py-2.5 px-3">Signal ID</th>
                    <th className="py-2.5 px-3">Contract</th>
                    <th className="py-2.5 px-3">Strategy</th>
                    <th className="py-2.5 px-3">Status</th>
                    <th className="py-2.5 px-3">Fill</th>
                    <th className="py-2.5 px-3">Exit</th>
                    <th className="py-2.5 px-3 text-right">Net P&amp;L</th>
                    <th className="py-2.5 px-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {trades.map((t) => {
                    const pnl = ledgerPnl(t);
                    const entry = ledgerEntryPrice(t);
                    const rowKey = t.signal_id ?? `${t.underlying}-${t.created_at_utc}`;
                    return (
                      <tr key={rowKey} className="hover:bg-muted transition-colors">
                        <td className="py-2 px-3">
                          <div className="text-ink-2 font-semibold">{t.signal_id ?? UNAVAILABLE}</div>
                          <div className="text-[10px] text-ink-3">{t.created_at_str || UNAVAILABLE}</div>
                        </td>
                        <td className="py-2 px-3 font-bold text-ink">{contractLabel(t)}</td>
                        <td className="py-2 px-3 text-ink-2">{t.strategy ?? UNAVAILABLE}</td>
                        <td className="py-2 px-3">
                          <Badge variant={statusVariant(t.status)} size="xs">
                            {t.status ?? 'UNKNOWN'}
                          </Badge>
                        </td>
                        <td className="py-2 px-3 text-ink-2" title={entry === null ? 'No executed fill recorded' : undefined}>
                          {entry === null ? UNAVAILABLE : fmtINR(entry)}
                        </td>
                        <td className="py-2 px-3 text-ink-2">
                          {t.exit_price === null || t.exit_price === undefined ? UNAVAILABLE : fmtINR(t.exit_price)}
                        </td>
                        <td className="py-2 px-3 text-right">
                          {t.economics_unavailable ? (
                            <span
                              className="font-bold text-warn-strong"
                              title={t.outcome_label ?? 'Backend booked no P&L for this record'}
                            >
                              UNAVAILABLE
                            </span>
                          ) : (
                            <span className={`font-bold ${valueToneClass(pnl)}`}>{signedINR(pnl)}</span>
                          )}
                        </td>
                        <td className="py-2 px-3 text-right">
                          <button
                            onClick={() => setSelectedVoidId(t.signal_id ?? null)}
                            disabled={!t.signal_id}
                            className="px-2 py-0.5 rounded bg-down-wash hover:bg-down/20 border border-down-line text-down-strong text-[10px] font-semibold disabled:opacity-40"
                          >
                            Void
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>

      <ConfirmDialog
        isOpen={selectedVoidId !== null}
        onClose={() => setSelectedVoidId(null)}
        onConfirm={handleVoidTrade}
        title="VOID AUDIT TRADE"
        message={`Quarantine trade #${selectedVoidId ?? ''}? It will be marked VOID, excluded from the served ledger and every P&L aggregate, and retained as audit evidence with operator attribution.`}
        confirmLabel="VOID TRADE"
        destructive={true}
      />
    </>
  );
};
