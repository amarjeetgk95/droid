'use client';

import React, { useCallback, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { useAsyncAction } from '@/hooks/useAsyncAction';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import type { AlgoKillSwitchStatus } from '@/lib/api/algo';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { StatusDot } from '@/components/ui/status-dot';

export const KillSwitchButton: React.FC = () => {
  const [halt, setHalt] = useState<AlgoKillSwitchStatus | null>(null);
  const [statusLoaded, setStatusLoaded] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [exitError, setExitError] = useState<string | null>(null);
  const action = useAsyncAction({
    errorFallback: 'Unknown kill-switch error',
    busyMessage: 'A kill request is already in progress.',
  });

  const readStatus = useCallback(async () => {
    try {
      const res = await api.getAlgoKillSwitch();
      if (!res?.data) throw new Error('Kill-switch status payload missing.');
      setHalt({
        is_killed: res.data.is_killed === true,
        kill_level: res.data.kill_level ?? 'UNKNOWN',
        killed_at: res.data.killed_at,
        reason: res.data.reason,
      });
      setStatusLoaded(true);
      setStatusError(null);
    } catch (err) {
      setStatusError(errorMessage(err, 'Unknown kill-switch error'));
    }
  }, []);

  usePolling(readStatus, 10000);

  const handleTriggerKill = async () => {
    setActionError(null);
    setActionNotice(null);
    setExitError(null);

    const killOutcome = await action.run(async () => {
      const res = await api.triggerAlgoKillSwitch(
        'FULL_EXECUTION_STOP',
        'Emergency Kill Switch Triggered by Cockpit Operator',
      );
      const data = res?.data;
      if (!data || data.is_killed !== true) {
        throw new Error(
          `Kill switch was not confirmed by the backend (is_killed: ${String(
            data?.is_killed,
          )}). Engines may still be live.`,
        );
      }
      return data;
    });

    if (!killOutcome.ok) {
      setActionError(killOutcome.message);
      throw new Error(killOutcome.message);
    }

    setHalt({
      is_killed: true,
      kill_level: killOutcome.value.kill_level ?? 'FULL_EXECUTION_STOP',
      killed_at: killOutcome.value.killed_at,
      reason: killOutcome.value.reason,
    });
    setStatusLoaded(true);
    setStatusError(null);

    let closedCount: number | null = null;
    const exitOutcome = await action.run(
      async () => {
        const res = await api.exitAllAlgoPositions();
        const count = res?.data?.closed_count;
        if (typeof count !== 'number' || !Number.isFinite(count)) {
          throw new Error('Exit-all did not return a confirmed closed-count.');
        }
        closedCount = count;
        return true;
      },
      { busyMessage: 'unknown error' },
    );

    if (!exitOutcome.ok) {
      setExitError(
        `Engines halted, but exiting open algo positions failed: ${exitOutcome.message}. Positions may remain open — use Square Off All or retry the exit.`,
      );
    } else {
      setActionNotice(
        `Engines halted. Exit-all confirmed: ${closedCount ?? 0} position(s) closed.`,
      );
    }
  };

  const halted = halt?.is_killed === true;
  const statusUnknown = statusLoaded === false && statusError !== null;

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setActionError(null);
          setActionNotice(null);
          setExitError(null);
          setModalOpen(true);
        }}
        disabled={action.isPending || halted}
        className="btn btn-sell w-full py-3.5 px-4 rounded-xl font-mono font-black text-sm tracking-widest shadow-md transition-all flex items-center justify-center gap-3 group disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <StatusDot status={halted ? 'error' : 'warning'} />
        <span className="group-hover:tracking-[0.2em] transition-all">
          {action.isPending
            ? 'HALTING…'
            : halted
              ? 'EXECUTION ENGINES HALTED'
              : 'EMERGENCY COCKPIT KILL SWITCH (EXIT ALL)'}
        </span>
      </button>

      <div className="mt-2 space-y-1.5 font-mono text-[11px]">
        {actionError && (
          <div
            role="alert"
            className="rounded border border-down-line bg-down-wash px-2.5 py-1.5 text-down-strong"
          >
            {actionError}
          </div>
        )}
        {exitError && (
          <div
            role="alert"
            className="rounded border border-warn-line bg-warn-wash px-2.5 py-1.5 text-warn-strong"
          >
            {exitError}
          </div>
        )}
        {actionNotice && (
          <div
            role="status"
            className="rounded border border-up-line bg-up-wash px-2.5 py-1.5 text-up-strong"
          >
            {actionNotice}
          </div>
        )}
        {statusUnknown && (
          <div
            role="alert"
            className="rounded border border-warn-line bg-warn-wash px-2.5 py-1.5 text-warn-strong"
          >
            Halt state UNKNOWN — kill-switch status could not be read: {statusError}. Verify before
            acting; the trigger remains available.
          </div>
        )}
        {halt && statusError && (
          <div className="rounded border border-warn-line bg-warn-wash px-2.5 py-1.5 text-warn-strong">
            Kill-switch status refresh failed — showing last known state: {statusError}
          </div>
        )}
        {halt && !statusError && (
          <div
            className={`rounded border px-2.5 py-1.5 ${
              halted
                ? 'border-down-line bg-down-wash text-down-strong'
                : 'border-border bg-surface-subtle text-ink-2'
            }`}
          >
            Kill switch {halted ? 'ENGAGED' : 'not engaged'} · level {halt.kill_level}
            {halt.killed_at ? ` · since ${halt.killed_at}` : ''}
            {halt.reason ? ` · ${halt.reason}` : ''}
          </div>
        )}
      </div>

      <ConfirmDialog
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onConfirm={handleTriggerKill}
        title="CRITICAL EXECUTION HALT"
        message={
          <div className="space-y-2 font-mono text-xs">
            <p>
              This immediately stops all algo engines, sends cancel requests for all active orders, and
              executes emergency market exits for{' '}
              <span className="font-bold text-ink">ALL open positions</span> across all instruments.
            </p>
            <dl className="rounded border border-border bg-surface-subtle p-2.5 space-y-1">
              <div className="flex justify-between gap-3">
                <dt className="text-ink-3">Action</dt>
                <dd className="font-semibold text-ink">FULL_EXECUTION_STOP</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-ink-3">Scope</dt>
                <dd className="text-ink-2">All algo engines · all orders · all positions</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-ink-3">Reversible</dt>
                <dd className="text-down-strong font-semibold">No — requires backend reset</dd>
              </div>
            </dl>
            <p className="text-ink-3">
              The kill level is reported separately from the position exit result, so a partial failure
              is never hidden.
            </p>
          </div>
        }
        confirmLabel="EXECUTE EMERGENCY HALT"
        destructive={true}
        requireTypedConfirmation="KILL"
      />
    </>
  );
};
