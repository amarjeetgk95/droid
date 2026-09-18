'use client';

import React, { useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { api } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { errorMessage, parseMLShadowGate, type MLShadowGate } from './forgeLogic';

type GateState =
  | { status: 'loading' }
  | { status: 'ready'; gate: MLShadowGate }
  | { status: 'error'; error: string };

/**
 * ML shadow gate readout. The real decision lives at
 * `data.shadow_decision.recommendation` (PASS | VETO) with `p_t1`; while the
 * evaluation is loading or failed the panel says so — it never renders an
 * optimistic pass.
 */
export const MLGateIndicator: React.FC = () => {
  const [state, setState] = useState<GateState>({ status: 'loading' });

  usePolling(async () => {
    try {
      const res = await api.getMLShadowGateEval();
      const gate = parseMLShadowGate(res?.data);
      if (!gate) {
        setState({ status: 'error', error: 'shadow_decision missing from response' });
        return;
      }
      setState({ status: 'ready', gate });
    } catch (e) {
      setState({ status: 'error', error: errorMessage(e, 'ML shadow gate endpoint unreachable') });
    }
  }, 6000);

  const gate = state.status === 'ready' ? state.gate : null;
  const pct = gate?.pT1 !== null && gate?.pT1 !== undefined ? `${(gate.pT1 * 100).toFixed(1)}%` : null;

  return (
    <div
      className="p-3 rounded-lg bg-surface border border-border shadow-xs font-mono text-xs flex items-center justify-between gap-3"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-ink-2 font-semibold">ML SHADOW GATE:</span>
        {state.status === 'loading' ? (
          <Badge variant="neutral" size="xs" dot={true}>
            CHECKING…
          </Badge>
        ) : gate ? (
          <Badge variant={gate.recommendation === 'PASS' ? 'success' : 'danger'} size="xs" dot={true}>
            {gate.recommendation === 'PASS' ? 'GATE PASSED (OBSERVATIONAL)' : 'SHADOW VETO ACTIVE'}
          </Badge>
        ) : (
          <Badge variant="warning" size="xs">
            ML GATE UNAVAILABLE
          </Badge>
        )}
      </div>
      <div className="text-[11px] text-ink-3 hidden sm:block text-right">
        {gate
          ? `p(T1) ${pct ?? '—'}${gate.threshold !== null ? ` · threshold ${gate.threshold}` : ''}${
              gate.authority ? ` · ${gate.authority}` : ''
            }`
          : state.status === 'error'
            ? state.error
            : 'Evaluating shadow gate…'}
      </div>
    </div>
  );
};
