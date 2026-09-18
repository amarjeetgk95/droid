'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { useInstrument, type SupportedInstrument } from '@/context/InstrumentContext';
import { api } from '@/lib/api';
import { asNumber, asRecord, asString, errorMessage } from './IntelHubData';
import { PanelNotice, formatStrike, sentimentBadgeVariant } from './IntelHubUi';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

const OPTIONS_FLOW_POLL_MS = 5_000;

interface FlowSnapshot {
  pcrOi: number | null;
  pcrVolume: number | null;
  maxPain: number | null;
  callWall: number | null;
  putWall: number | null;
  totalCallOi: number | null;
  totalPutOi: number | null;
  sentiment: string | null;
  status: string | null;
  reason: string | null;
  expiry: string | null;
}

function parseFlow(raw: Record<string, unknown> | null): FlowSnapshot {
  const analytics = asRecord(raw?.analytics);
  return {
    pcrOi: asNumber(raw?.pcr_oi),
    pcrVolume: asNumber(raw?.pcr_volume),
    maxPain: asNumber(analytics?.max_pain),
    callWall: asNumber(raw?.call_resistance),
    putWall: asNumber(raw?.put_support),
    totalCallOi: asNumber(analytics?.total_call_oi),
    totalPutOi: asNumber(analytics?.total_put_oi),
    sentiment: asString(raw?.breakout_confirmation),
    status: asString(raw?.status),
    reason: asString(raw?.reason),
    expiry: asString(raw?.expiry),
  };
}

function oiInLakhs(value: number | null): string {
  if (value === null) return '—';
  return `${(value / 100_000).toFixed(1)}L`;
}

export const OptionsFlowPanel: React.FC = () => {
  const { instrument } = useInstrument();
  const [snapshot, setSnapshot] = useState<{ instrument: SupportedInstrument; data: FlowSnapshot } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const seqRef = useRef(0);

  const load = useCallback(async () => {
    const seq = ++seqRef.current;
    try {
      const raw = await api.getCallsPutsFull(instrument);
      if (seq !== seqRef.current) return; // stale response for a switched symbol
      setSnapshot({ instrument, data: parseFlow(raw ?? null) });
      setError(null);
    } catch (err) {
      if (seq !== seqRef.current) return;
      setError(errorMessage(err));
    }
  }, [instrument]);

  usePolling(load, OPTIONS_FLOW_POLL_MS);

  const prevInstrumentRef = useRef(instrument);
  useEffect(() => {
    if (prevInstrumentRef.current === instrument) return;
    prevInstrumentRef.current = instrument;
    seqRef.current += 1; // invalidate in-flight response for the old symbol
    void load();
  }, [instrument, load]);

  const flow = snapshot && snapshot.instrument === instrument ? snapshot.data : null;
  const notApplicable = flow !== null && flow.status !== null && flow.status !== 'LIVE';

  const putOi = flow?.totalPutOi ?? null;
  const callOi = flow?.totalCallOi ?? null;
  const oiTotal = (putOi ?? 0) + (callOi ?? 0);
  const hasOiSplit = putOi !== null && callOi !== null && oiTotal > 0;
  const putPct = hasOiSplit ? ((putOi ?? 0) / oiTotal) * 100 : 0;
  const callPct = hasOiSplit ? 100 - putPct : 0;

  const pcr = flow?.pcrOi ?? null;
  const pcrTone = pcr === null ? 'text-ink' : pcr >= 1 ? 'text-up-strong' : 'text-down-strong';

  return (
    <Card
      title="DERIVATIVES & OPTIONS FLOW DYNAMICS"
      subtitle={`Institutional open interest and gamma levels for ${instrument}${
        flow?.expiry ? ` · expiry ${flow.expiry}` : ''
      }`}
    >
      <div className="space-y-4 font-mono text-xs">
        {error ? (
          <PanelNotice tone="down" role="alert">
            Options flow unavailable — {error}
          </PanelNotice>
        ) : null}
        {!flow && !error ? (
          <PanelNotice role="status">Waiting for option-chain analytics…</PanelNotice>
        ) : null}

        {flow && notApplicable ? (
          <PanelNotice tone="warn">
            {flow.status}: {flow.reason ?? 'options intelligence is not applicable for this instrument.'}
          </PanelNotice>
        ) : null}

        {flow && !notApplicable ? (
          <>
            {/* KPI Strip */}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <div className="rounded-lg border border-border bg-surface-subtle p-2.5 shadow-xs">
                <div className="text-[10px] font-semibold uppercase text-ink-3">
                  PCR (Open Interest)
                </div>
                <div className={`mt-0.5 text-base font-bold ${pcrTone}`}>
                  {pcr !== null ? pcr.toFixed(2) : '—'}
                </div>
              </div>

              <div className="rounded-lg border border-border bg-surface-subtle p-2.5 shadow-xs">
                <div className="text-[10px] font-semibold uppercase text-ink-3">
                  Max Pain Strike
                </div>
                <div className="mt-0.5 text-base font-bold text-primary">
                  {formatStrike(flow.maxPain)}
                </div>
              </div>

              <div className="rounded-lg border border-border bg-surface-subtle p-2.5 shadow-xs">
                <div className="text-[10px] font-semibold uppercase text-ink-3">
                  Major Put Wall (Support)
                </div>
                <div className="mt-0.5 text-base font-bold text-up-strong">
                  {formatStrike(flow.putWall)}
                </div>
              </div>

              <div className="rounded-lg border border-border bg-surface-subtle p-2.5 shadow-xs">
                <div className="text-[10px] font-semibold uppercase text-ink-3">
                  Major Call Wall (Resistance)
                </div>
                <div className="mt-0.5 text-base font-bold text-down-strong">
                  {formatStrike(flow.callWall)}
                </div>
              </div>
            </div>

            {/* Sentiment / vol context from the backend */}
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-surface-subtle p-2.5">
              <span className="font-semibold text-ink-2">BREAKOUT CONFIRMATION:</span>
              <div className="flex items-center gap-2">
                <Badge variant={sentimentBadgeVariant(flow.sentiment)} size="xs">
                  {flow.sentiment ?? 'UNKNOWN'}
                </Badge>
                <span className="text-[10px] text-ink-3">
                  PCR(vol):{' '}
                  {flow.pcrVolume !== null ? flow.pcrVolume.toFixed(2) : '—'}
                </span>
              </div>
            </div>

            {/* OI Buildup Comparison */}
            <div>
              <div className="mb-1.5 flex items-center justify-between text-[11px]">
                <span className="font-semibold text-up-strong">
                  PUT OI: {oiInLakhs(putOi)} Contracts
                </span>
                <span className="font-semibold text-down-strong">
                  CALL OI: {oiInLakhs(callOi)} Contracts
                </span>
              </div>

              {hasOiSplit ? (
                <div
                  role="progressbar"
                  aria-label={`Put OI ${Math.round(putPct)} percent versus call OI ${Math.round(callPct)} percent`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(putPct)}
                  aria-valuetext={`Put OI ${Math.round(putPct)} percent, call OI ${Math.round(
                    callPct,
                  )} percent`}
                  className="flex h-3 w-full overflow-hidden rounded-full border border-border bg-muted"
                >
                  <div style={{ width: `${putPct}%` }} className="bg-up" />
                  <div style={{ width: `${callPct}%` }} className="bg-down" />
                </div>
              ) : (
                <PanelNotice>
                  OI split unavailable — no call/put open interest in this poll.
                </PanelNotice>
              )}
            </div>
          </>
        ) : null}
      </div>
    </Card>
  );
};
