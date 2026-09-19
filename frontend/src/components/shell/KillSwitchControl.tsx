'use client';

import { useCallback, useEffect, useState } from 'react';
import { OctagonX, Power } from 'lucide-react';
import { api } from '@/lib/api';
import { useAppStreamRefresh, useCommandSection } from '@/context/AppStreamContext';
import { errorMessage } from '@/lib/errors';
import { asStr, getObj } from '@/lib/signalsNormalize';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/toast';

const ENGAGE_REASON = 'Operator manual control';

/**
 * Global kill-switch control for the shell header.
 *
 * State rides the CommandView `kill_switch` section (no polling in this
 * component): the app stream hydrates it on connect and pushes every change.
 * A one-time REST seed covers the gap before the first hydration. Engaging
 * requires typing KILL; releasing is a plain confirm. Both actions re-seed
 * from the backend and refresh the stream so every consumer converges.
 */
export function KillSwitchControl() {
  const { push } = useToast();
  const refreshStream = useAppStreamRefresh();
  const section = useCommandSection('kill_switch');
  const [seed, setSeed] = useState<Record<string, unknown> | null>(null);
  const [confirm, setConfirm] = useState<'engage' | 'release' | null>(null);
  const [busy, setBusy] = useState(false);

  const seedOnce = useCallback(async () => {
    try {
      const status = await api.getSignalsKillSwitch();
      setSeed(getObj(status) ?? { active: Boolean((status as { active?: unknown })?.active) });
    } catch {
      // Stream hydration remains the source of truth; a failed seed just
      // leaves the control in the unknown state until the stream lands.
    }
  }, []);

  useEffect(() => {
    if (section) return;
    void seedOnce();
  }, [section, seedOnce]);

  const value = getObj(section?.value ?? null) ?? seed;
  const active = value?.active === true;
  const reason = asStr(value?.reason);
  const degraded = section?.degraded === true;

  const runToggle = useCallback(
    async (nextActive: boolean) => {
      setBusy(true);
      try {
        await api.toggleSignalsKillSwitch(nextActive, ENGAGE_REASON);
        await seedOnce();
        await refreshStream();
        push(
          'success',
          nextActive ? 'Kill switch ENGAGED — generation and execution halted.' : 'Kill switch released.',
        );
      } catch (err) {
        push('error', errorMessage(err, 'Kill switch update failed'));
      } finally {
        setBusy(false);
        setConfirm(null);
      }
    },
    [push, refreshStream, seedOnce],
  );

  const known = value !== null;
  const badgeClass = active ? 'b-bear' : degraded ? 'b-warn' : 'b-neut';
  const label = !known ? 'KILL ?' : active ? 'KILL ACTIVE' : 'KILL READY';

  return (
    <>
      <button
        type="button"
        className={`badge ${badgeClass}`}
        title={
          !known
            ? 'Kill switch state unknown — stream not hydrated yet'
            : active
              ? `Kill switch ENGAGED${reason ? `: ${reason}` : ''} — activate to release`
              : 'Kill switch disengaged — activate to halt all generation and execution'
        }
        disabled={!known || busy}
        onClick={() => setConfirm(active ? 'release' : 'engage')}
      >
        {active ? <OctagonX size={12} /> : <Power size={12} />}
        {busy ? 'WORKING…' : label}
      </button>

      <ConfirmDialog
        open={confirm === 'engage'}
        onOpenChange={(open) => {
          if (!open) setConfirm(null);
        }}
        tone="danger"
        confirmLabel="Engage kill switch"
        busy={busy}
        requireTypedConfirmation="KILL"
        title="Engage the global kill switch?"
        description="Halts all signal generation and execution immediately. Open positions are left untouched — square them off separately."
        intentRows={[
          { label: 'Current state', value: active ? 'ENGAGED' : 'DISENGAGED' },
          { label: 'Reason recorded', value: ENGAGE_REASON },
        ]}
        onConfirm={() => runToggle(true)}
      />

      <ConfirmDialog
        open={confirm === 'release'}
        onOpenChange={(open) => {
          if (!open) setConfirm(null);
        }}
        tone="primary"
        confirmLabel="Release kill switch"
        busy={busy}
        title="Release the global kill switch?"
        description="Signal generation and execution resume on the next worker pass."
        intentRows={[{ label: 'Current state', value: 'ENGAGED' }]}
        onConfirm={() => runToggle(false)}
      />
    </>
  );
}
