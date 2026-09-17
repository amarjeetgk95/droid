'use client';

import React, { useCallback, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { useExecutionGuard } from '@/hooks/useExecutionGuard';
import { api } from '@/lib/api';
import { Badge } from '../shared/Badge';
import { ConfirmDialog } from '../shared/ConfirmDialog';

type Mode = 'OFF' | 'PAPER' | 'LIVE';
type ModeState = 'loading' | 'ready' | 'error';

const MODES: readonly Mode[] = ['OFF', 'PAPER', 'LIVE'];

function errorMessage(err: unknown): string {
  return err instanceof Error && err.message ? err.message : 'Unknown mode error';
}

export const ExecutionModeSwitcher: React.FC = () => {
  const [mode, setMode] = useState<Mode | null>(null);
  const [modeState, setModeState] = useState<ModeState>('loading');
  const [modeError, setModeError] = useState<string | null>(null);
  const [consentOk, setConsentOk] = useState(false);
  const [disclosureVersion, setDisclosureVersion] = useState<string | null>(null);
  const [consentError, setConsentError] = useState<string | null>(null);
  const [pendingMode, setPendingMode] = useState<Mode | null>(null);
  const [liveAck, setLiveAck] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const guard = useExecutionGuard();

  const readState = useCallback(async () => {
    try {
      const acc = await api.getAlgoAccount();
      if (!acc?.data?.mode) throw new Error('Backend returned no execution mode.');
      setMode(acc.data.mode);
      setModeState('ready');
      setModeError(null);
    } catch (err) {
      setMode(null);
      setModeState('error');
      setModeError(errorMessage(err));
    }

    try {
      const consent = await api.getAlgoConsent();
      if (!consent?.data) throw new Error('Consent payload missing.');
      setConsentOk(consent.data.current_ok === true);
      setDisclosureVersion(consent.data.disclosure?.version ?? null);
      setConsentError(null);
    } catch (err) {
      setConsentOk(false);
      setDisclosureVersion(null);
      setConsentError(errorMessage(err));
    }
  }, []);

  usePolling(readState, 5000);

  const closeConfirm = () => {
    setPendingMode(null);
    setLiveAck(false);
  };

  const handleModeChange = async () => {
    const target = pendingMode;
    if (!target) return;
    setActionError(null);
    setActionNotice(null);

    if (target === 'LIVE') {
      if (!disclosureVersion) {
        throw new Error(
          'Risk-disclosure version unavailable — cannot activate LIVE. Wait for the consent service to respond and retry.',
        );
      }
      if (!liveAck) {
        throw new Error('Explicit acknowledgment of the risk disclosure is required before LIVE activation.');
      }
    }

    let failure: string | null = null;
    const outcome = await guard.execute(async () => {
      try {
        if (target === 'LIVE' && !consentOk) {
          const ackRes = await api.acknowledgeAlgoConsent(disclosureVersion as string, true);
          if (ackRes?.data?.acknowledged !== true) {
            throw new Error('Risk-disclosure acknowledgment was not recorded by the backend.');
          }
          setConsentOk(true);
        }
        const res = await api.setAlgoMode(target);
        const applied = res?.data?.mode;
        if (applied !== target) {
          throw new Error(
            `Backend did not confirm the mode switch (reported: ${String(applied)}). Mode unchanged.`,
          );
        }
        return true;
      } catch (err) {
        failure = errorMessage(err);
        throw err;
      }
    });

    if (outcome === null) {
      const message = failure ?? 'A mode update is already in progress. Wait for it to finish.';
      setActionError(message);
      throw new Error(message);
    }

    setMode(target);
    setModeState('ready');
    setModeError(null);
    setActionNotice(`Execution mode confirmed: ${target}.`);
    await readState();
  };

  const modeLabel = mode ?? 'UNKNOWN';
  const switchingDisabled = modeState !== 'ready' || guard.isPending;

  return (
    <>
      <div className="p-3.5 rounded-xl border border-border bg-card shadow-xs flex flex-wrap items-center justify-between gap-3 font-mono text-xs">
        <div className="flex items-center gap-3">
          <span className="text-ink-2 font-semibold">EXECUTION ENGINE MODE:</span>
          <div className="flex rounded-lg overflow-hidden border border-border bg-muted p-0.5">
            {MODES.map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => {
                  setActionError(null);
                  setActionNotice(null);
                  setLiveAck(false);
                  setPendingMode(m);
                }}
                disabled={switchingDisabled || mode === m}
                className={`px-4 py-1.5 font-bold rounded transition-all disabled:cursor-not-allowed ${
                  mode === m
                    ? m === 'LIVE'
                      ? 'bg-down text-white shadow-sm'
                      : m === 'PAPER'
                        ? 'bg-primary text-white shadow-sm'
                        : 'bg-muted-strong text-ink'
                    : 'text-ink-2 hover:text-ink hover:bg-muted-strong disabled:opacity-50'
                }`}
              >
                {m === 'LIVE' ? 'LIVE BROKER' : m === 'PAPER' ? 'PAPER DESK' : 'OFF'}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Badge
            variant={mode === 'LIVE' ? 'danger' : mode === 'PAPER' ? 'info' : 'neutral'}
            size="sm"
            dot={true}
          >
            {mode === 'LIVE'
              ? 'ACTIVE LIVE TRADING'
              : mode === 'PAPER'
                ? 'VIRTUAL EXECUTION'
                : mode === 'OFF'
                  ? 'SYSTEM INERT'
                  : 'MODE UNKNOWN'}
          </Badge>
          <span className="text-[10px] text-ink-3">SEBI §88.6 Guarded</span>
        </div>

        {(modeState === 'error' || actionError || actionNotice || consentError) && (
          <div className="w-full space-y-1.5 text-[11px]">
            {modeState === 'error' && (
              <div
                role="alert"
                className="rounded border border-down-line bg-down-wash px-2.5 py-1.5 text-down-strong"
              >
                Execution mode state UNKNOWN — switching is blocked until the backend responds: {modeError}
              </div>
            )}
            {actionError && (
              <div
                role="alert"
                className="rounded border border-down-line bg-down-wash px-2.5 py-1.5 text-down-strong"
              >
                Mode update failed: {actionError} Mode unchanged ({modeLabel}).
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
            {consentError && modeState !== 'error' && (
              <div className="rounded border border-warn-line bg-warn-wash px-2.5 py-1.5 text-warn-strong">
                Risk disclosure unavailable — LIVE activation is blocked: {consentError}
              </div>
            )}
          </div>
        )}
      </div>

      <ConfirmDialog
        isOpen={pendingMode !== null}
        onClose={closeConfirm}
        onConfirm={handleModeChange}
        title={
          pendingMode === 'LIVE'
            ? 'ACTIVATE LIVE BROKER TRADING'
            : `SWITCH MODE TO ${pendingMode ?? 'UNKNOWN'}`
        }
        message={
          pendingMode === 'LIVE' ? (
            <div className="space-y-3 font-mono text-xs">
              <p>You are about to enable LIVE ORDER EXECUTION through your authenticated broker account.</p>
              <dl className="rounded border border-border bg-surface-subtle p-2.5 space-y-1">
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-3">Mode</dt>
                  <dd className="font-semibold text-ink">LIVE</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-3">Disclosure</dt>
                  <dd className="text-ink-2">{disclosureVersion ?? 'unavailable'}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-3">Consent status</dt>
                  <dd className={consentOk ? 'text-up-strong' : 'text-warn-strong'}>
                    {consentOk ? 'acknowledged' : 'acknowledgment required now'}
                  </dd>
                </div>
              </dl>
              <label className="flex items-start gap-2 rounded border border-warn-line bg-warn-wash p-2.5 text-warn-strong">
                <input
                  type="checkbox"
                  checked={liveAck}
                  onChange={(e) => setLiveAck(e.target.checked)}
                  className="mt-0.5"
                />
                <span>
                  I have read and acknowledge risk disclosure{' '}
                  <span className="font-bold">{disclosureVersion ?? '(unavailable)'}</span>. Real
                  financial orders will be placed under my capital allocation and risk limits.
                </span>
              </label>
            </div>
          ) : (
            <div className="space-y-2 font-mono text-xs">
              <p>
                Transition the execution engine mode from{' '}
                <span className="font-bold text-ink">{modeLabel}</span> to{' '}
                <span className="font-bold text-ink">{pendingMode}</span>?
              </p>
              <p className="text-ink-3">Active orders and open positions are managed according to the new mode.</p>
            </div>
          )
        }
        confirmLabel={pendingMode === 'LIVE' ? 'ACKNOWLEDGE & ACTIVATE LIVE' : `SWITCH TO ${pendingMode ?? ''}`}
        destructive={pendingMode === 'LIVE'}
        requireTypedConfirmation={pendingMode === 'LIVE' ? 'LIVE' : undefined}
      />
    </>
  );
};
