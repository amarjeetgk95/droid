'use client';

import React, { useCallback, useRef, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { useInstrument } from '@/context/InstrumentContext';
import { useMarketSession } from '@/hooks/useMarketSession';
import { api } from '@/lib/api';
import { toNumber } from '@/lib/coerce';
import { Card } from '@/components/ui/card';
import { Badge, type BadgeVariant } from '@/components/ui/badge';
import { Modal } from '@/components/ui/modal';
import { EmptyNote, fmtINR } from '@/components/ui/desk';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import { ConfirmDialog, type ConfirmIntentRow } from '@/components/ui/ConfirmDialog';

export interface ActiveSignal {
  signal_id: string;
  instrument: string;
  direction: string;
  strategy: string;
  fsm_state: string;
  trigger: number | null;
  stop_loss: number | null;
  target_1: number | null;
  target_2: number | null;
  confidence: number | null;
  timeframe: string | null;
  distance_to_trigger_pts: number | null;
  ttl_remaining_seconds: number | null;
  data_quality: string | null;
  rationale: string[];
  risk_reward_t1: number | null;
  created_at_str: string | null;
}

function num(v: unknown): number | null {
  return toNumber(v);
}

function str(v: unknown): string | null {
  return typeof v === 'string' && v.trim().length > 0 ? v : null;
}

function toActiveSignal(raw: unknown): ActiveSignal | null {
  if (!raw || typeof raw !== 'object') return null;
  const o = raw as Record<string, unknown>;
  const signalId = str(o.signal_id);
  if (!signalId) return null;
  return {
    signal_id: signalId,
    instrument: str(o.underlying) ?? str(o.instrument) ?? '—',
    direction: str(o.direction) ?? 'UNKNOWN',
    strategy: str(o.strategy) ?? str(o.strategy_id) ?? '—',
    fsm_state: str(o.fsm_state) ?? str(o.status) ?? 'UNKNOWN',
    trigger: num(o.trigger) ?? num(o.trigger_level),
    stop_loss: num(o.stop_loss),
    target_1: num(o.target_1),
    target_2: num(o.target_2),
    confidence: num(o.confidence),
    timeframe: str(o.timeframe),
    distance_to_trigger_pts: num(o.distance_to_trigger_pts),
    ttl_remaining_seconds: num(o.ttl_remaining_seconds),
    data_quality: str(o.data_quality),
    rationale: Array.isArray(o.rationale)
      ? o.rationale.filter((r): r is string => typeof r === 'string').slice(0, 4)
      : [],
    risk_reward_t1: num(o.risk_reward_t1),
    created_at_str: str(o.created_at_str),
  };
}

function confidencePct(confidence: number | null): string {
  if (confidence === null) return '—';
  const pct = confidence <= 1 ? confidence * 100 : confidence;
  return `${pct.toFixed(0)}%`;
}

function stateVariant(state: string): BadgeVariant {
  switch (state.toUpperCase()) {
    case 'CONFIRMED':
    case 'TRIGGERED':
    case 'TARGET_1_HIT':
    case 'TARGET_2_HIT':
      return 'success';
    case 'ARMED':
    case 'VALIDATED':
    case 'DETECTED':
      return 'warning';
    case 'STOP_LOSS_HIT':
    case 'INVALIDATED':
      return 'danger';
    default:
      return 'neutral';
  }
}

function directionIsCall(direction: string): boolean {
  const d = direction.toUpperCase();
  return d.includes('CALL') || d.includes('BULL');
}

export const ActiveSignalsRibbon: React.FC = () => {
  const { instrument } = useInstrument();
  const { phase, isOpen } = useMarketSession();
  const [signals, setSignals] = useState<ActiveSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedSignal, setSelectedSignal] = useState<ActiveSignal | null>(null);
  const [pendingExec, setPendingExec] = useState<ActiveSignal | null>(null);
  const [executingId, setExecutingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastAt, setLastAt] = useState<Date | null>(null);
  const loadedRef = useRef(false);
  const hasDataRef = useRef(false);

  const load = useCallback(async () => {
    const initial = !loadedRef.current;
    if (initial) setLoading(true);
    else setRefreshing(true);
    try {
      const res = await api.getSignalsActive({ instrument });
      const rows = Array.isArray(res?.signals) ? res.signals : [];
      setSignals(rows.map(toActiveSignal).filter((s): s is ActiveSignal => s !== null));
      setError(null);
      setLastAt(new Date());
      hasDataRef.current = true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Active signals unavailable');
    } finally {
      loadedRef.current = true;
      setLoading(false);
      setRefreshing(false);
    }
  }, [instrument]);

  usePolling(() => {
    if (!isOpen && hasDataRef.current) return;
    return load();
  }, 3000);

  const handleExecutePaper = useCallback(
    async (signal: ActiveSignal) => {
      setActionError(null);
      setNotice(null);
      setExecutingId(signal.signal_id);
      try {
        const res = await api.executeSignalPaper(signal.signal_id, 1, 2);
        const qty = res?.quantity !== undefined ? ` x${res.quantity}` : '';
        setNotice(
          `Paper order ${res?.order_id ?? '(no id)'} placed — ${signal.instrument} ${signal.strategy}${qty}`,
        );
        setPendingExec(null);
        await load();
      } catch (err) {
        setActionError(err instanceof Error ? err.message : 'Paper execution failed');
      } finally {
        setExecutingId(null);
      }
    },
    [load],
  );

  const execIntentRows = (sig: ActiveSignal): ConfirmIntentRow[] => [
    { label: 'Instrument', value: sig.instrument },
    { label: 'Strategy', value: sig.strategy },
    { label: 'Direction', value: sig.direction },
    { label: 'Trigger', value: fmtINR(sig.trigger) },
    { label: 'Stop loss', value: fmtINR(sig.stop_loss) },
    { label: 'Target 1', value: fmtINR(sig.target_1) },
    { label: 'Target 2', value: fmtINR(sig.target_2) },
    { label: 'Confidence', value: confidencePct(sig.confidence) },
  ];

  const marketClosed = !isOpen;

  return (
    <>
      <Card
        title={
          <div className="flex items-center gap-2">
            <span>ACTIVE SIGNALS STREAM</span>
            <span className="text-xs px-2 py-0.5 rounded bg-accent-wash text-primary font-mono border border-accent-line">
              {signals.length} ACTIVE
            </span>
          </div>
        }
        subtitle="Real-time FSM pipeline transitions and automated trigger detection"
        glow="cyan"
      >
        {notice ? (
          <div className="mb-3 rounded-lg border border-border bg-surface-subtle px-3 py-2 text-[11px] font-mono text-ink-2">
            {notice}
          </div>
        ) : null}
        {actionError ? (
          <div className="mb-3 rounded-lg border border-down-line bg-down-wash px-3 py-2 text-[11px] font-mono text-down-strong">
            {actionError}
          </div>
        ) : null}
        {marketClosed ? (
          <div className="mb-3 rounded-lg border border-warn-line bg-warn-wash px-3 py-2 text-[11px] font-mono text-warn-ink">
            Market session {phase} — paper execution is blocked until the session opens.
          </div>
        ) : null}
        {error && signals.length > 0 ? (
          <div className="mb-3 rounded-lg border border-warn-line bg-warn-wash px-3 py-2 text-[11px] font-mono text-warn-ink">
            Signal feed degraded — showing last known list. {error}
          </div>
        ) : null}

        {loading && signals.length === 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="p-3 rounded-lg border border-border bg-card">
                <div className="skel" style={{ height: 12, width: '60%', marginBottom: 10 }}>.</div>
                <div className="skel" style={{ height: 34, width: '100%', marginBottom: 10 }}>.</div>
                <div className="skel" style={{ height: 12, width: '45%' }}>.</div>
              </div>
            ))}
          </div>
        ) : error && signals.length === 0 ? (
          <div className="text-center py-10 border border-dashed border-border rounded-lg">
            <EmptyNote>Active signals unavailable — {error}</EmptyNote>
            <button type="button" className="btn mt-3" onClick={() => void load()} disabled={refreshing}>
              {refreshing ? 'Retrying…' : 'Retry'}
            </button>
          </div>
        ) : signals.length === 0 ? (
          <div className="text-center py-10 text-ink-3 font-mono text-xs border border-dashed border-border rounded-lg">
            No active signals for {instrument} at this moment.
            {marketClosed ? ' Market is closed — the detector only scans live sessions.' : ' Auto-detector scanning live feeds.'}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {signals.map((sig) => {
              const isCall = directionIsCall(sig.direction);
              const executionBlocked = marketClosed || executingId === sig.signal_id;
              return (
                <div
                  key={sig.signal_id}
                  className="p-3 rounded-lg border border-border bg-card hover:border-border-strong shadow-xs transition-all flex flex-col justify-between"
                >
                  <div className="flex items-center justify-between mb-2 gap-2">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <Badge variant={isCall ? 'bull' : 'bear'} size="xs">
                        {sig.direction}
                      </Badge>
                      <span className="font-mono text-xs font-semibold text-foreground truncate">
                        {sig.strategy}
                      </span>
                    </div>
                    <Badge variant={stateVariant(sig.fsm_state)} size="xs" dot={true}>
                      {sig.fsm_state}
                    </Badge>
                  </div>

                  <div className="grid grid-cols-4 gap-1 py-2 border-y border-border-subtle my-2 text-center font-mono text-xs">
                    <div>
                      <div className="text-[10px] text-ink-3 font-semibold">TRIGGER</div>
                      <div className="text-primary font-bold">{fmtINR(sig.trigger)}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-ink-3 font-semibold">STOP</div>
                      <div className="text-down-strong font-bold">{fmtINR(sig.stop_loss)}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-ink-3 font-semibold">TARGET 1</div>
                      <div className="text-up-strong font-bold">{fmtINR(sig.target_1)}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-ink-3 font-semibold">TARGET 2</div>
                      <div className="text-up-strong font-bold">{fmtINR(sig.target_2)}</div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between gap-2 text-[10px] font-mono text-ink-3 mb-2">
                    <span>
                      Conf {confidencePct(sig.confidence)} · R:R{' '}
                      {sig.risk_reward_t1 !== null ? `${sig.risk_reward_t1.toFixed(2)}` : '—'}
                    </span>
                    <span>{sig.data_quality ?? 'UNKNOWN'}</span>
                  </div>

                  <div className="flex items-center justify-between pt-1 gap-2">
                    <button
                      onClick={() => setSelectedSignal(sig)}
                      className="text-xs text-ink-3 hover:text-foreground font-mono underline"
                    >
                      Dossier
                    </button>

                    <button
                      onClick={() => {
                        setActionError(null);
                        setPendingExec(sig);
                      }}
                      disabled={executionBlocked}
                      title={
                        marketClosed
                          ? `Paper execution blocked — market session ${phase}`
                          : 'Confirm paper execution'
                      }
                      className="px-3 py-1 bg-up text-primary-foreground font-mono text-xs font-semibold rounded transition-all shadow-xs disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {executingId === sig.signal_id ? 'Executing…' : 'Paper Exec'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="flex justify-end mt-3">
          <FreshnessClock
            lastAt={lastAt}
            fetching={refreshing}
            marketClosed={marketClosed}
            dataQuality={error ? 'DEGRADED' : null}
            sourceLabel="REST · 3s poll"
          />
        </div>
      </Card>

      {selectedSignal && (
        <Modal
          isOpen={true}
          onClose={() => setSelectedSignal(null)}
          title={`SIGNAL DOSSIER #${selectedSignal.signal_id.slice(0, 8)}`}
          maxWidth="lg"
        >
          <div className="space-y-4 font-mono text-xs">
            <div className="p-3 bg-surface-subtle rounded-lg border border-border flex flex-wrap items-center justify-between gap-2">
              <div>
                <span className="text-ink-3">Underlying: </span>
                <strong className="text-foreground">{selectedSignal.instrument}</strong>
              </div>
              <div>
                <span className="text-ink-3">Direction: </span>
                <Badge variant={directionIsCall(selectedSignal.direction) ? 'bull' : 'bear'} size="xs">
                  {selectedSignal.direction}
                </Badge>
              </div>
              <div>
                <span className="text-ink-3">Confidence: </span>
                <strong className="text-primary font-bold">
                  {confidencePct(selectedSignal.confidence)}
                </strong>
              </div>
              <div>
                <span className="text-ink-3">FSM: </span>
                <strong className="text-foreground">{selectedSignal.fsm_state}</strong>
              </div>
            </div>

            <div className="p-3 bg-surface-subtle rounded-lg border border-border space-y-2">
              <div className="text-ink-2 font-semibold">COHERENCE &amp; ATTRIBUTION</div>
              <div className="text-ink-2">
                Strategy <strong className="text-primary">{selectedSignal.strategy}</strong>
                {selectedSignal.timeframe ? ` · ${selectedSignal.timeframe}` : ''}
                {selectedSignal.created_at_str ? ` · created ${selectedSignal.created_at_str}` : ''}
              </div>
              <div className="grid grid-cols-2 gap-2 pt-2 border-t border-border">
                <div>Trigger: {fmtINR(selectedSignal.trigger)}</div>
                <div>Stop Loss: {fmtINR(selectedSignal.stop_loss)}</div>
                <div>Target 1: {fmtINR(selectedSignal.target_1)}</div>
                <div>Target 2: {fmtINR(selectedSignal.target_2)}</div>
                <div>
                  Distance to trigger:{' '}
                  {selectedSignal.distance_to_trigger_pts !== null
                    ? `${selectedSignal.distance_to_trigger_pts.toFixed(2)} pts`
                    : '—'}
                </div>
                <div>
                  TTL remaining:{' '}
                  {selectedSignal.ttl_remaining_seconds !== null
                    ? `${Math.round(selectedSignal.ttl_remaining_seconds)}s`
                    : '—'}
                </div>
              </div>
              {selectedSignal.rationale.length > 0 ? (
                <ul className="pt-2 border-t border-border space-y-1 text-ink-2">
                  {selectedSignal.rationale.map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
              ) : (
                <EmptyNote>No rationale recorded for this signal.</EmptyNote>
              )}
            </div>
          </div>
        </Modal>
      )}

      <ConfirmDialog
        open={pendingExec !== null}
        onOpenChange={(open) => {
          if (!open && executingId === null) setPendingExec(null);
        }}
        busy={executingId !== null}
        tone="primary"
        title={
          pendingExec
            ? `Execute paper trade — ${pendingExec.instrument} ${pendingExec.direction} ${pendingExec.strategy}?`
            : 'Execute paper trade?'
        }
        description="Places a simulated order at the signal entry. Blocked outside the live session."
        intentRows={pendingExec ? execIntentRows(pendingExec) : []}
        confirmLabel="Execute paper"
        onConfirm={() => {
          if (pendingExec) void handleExecutePaper(pendingExec);
        }}
      />
    </>
  );
};
