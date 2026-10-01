'use client';

import Link from 'next/link';
import { useMemo } from 'react';
import type { PapLiveState } from '@/hooks/usePapLive';
import type { SignalDeskState } from '@/hooks/useSignalDesk';
import { signalDirectionTone } from '@/lib/directionalConsensus';
import {
  PAP_UNAVAILABLE_LABEL,
  confidenceLabel,
  dataStatusOf,
  freshnessBadgeClass,
  isPapUnavailable,
  papFreshnessOf,
  predictionBadgeClass,
} from '@/lib/pap';
import { stageOf, stateLabel } from '@/lib/signalStages';
import { signalAgeLabel } from '@/lib/signalsNormalize';
import { Panel } from '@/components/ui/Panel';

function dirClass(tone: 'bull' | 'bear' | 'neut'): string {
  return tone === 'bull' ? 'long' : tone === 'bear' ? 'short' : 'neut';
}

function dirLabel(tone: 'bull' | 'bear' | 'neut'): string {
  return tone === 'bull' ? 'LONG' : tone === 'bear' ? 'SHORT' : 'NEUTRAL';
}

/**
 * PAP shadow predictions in place: horizon lean + calibration without leaving
 * the dashboard. Advisory only — it never feeds execution.
 */
export function PapPulsePanel({ pap, instrument }: { pap: PapLiveState; instrument: string }) {
  const live = pap.live;
  const horizons = useMemo(
    () => (live?.horizons ? Object.entries(live.horizons) : []),
    [live?.horizons],
  );

  if (pap.loading && !live && !pap.error) {
    return (
      <Panel title="PAP Shadow" meta={instrument}>
        <p className="m-0 text-[13px] text-ink-2">Loading PAP shadow predictions…</p>
      </Panel>
    );
  }

  if (pap.error && !live) {
    return (
      <Panel title="PAP Shadow" meta={instrument}>
        <p className="sg-err m-0">{pap.error}</p>
      </Panel>
    );
  }

  if (isPapUnavailable(live)) {
    return (
      <Panel title="PAP Shadow" meta={dataStatusOf(live)}>
        <p className="sg-err m-0">{PAP_UNAVAILABLE_LABEL}</p>
        <p className="sg-note mt-2">
          {live?.unavailable_reason ?? 'Shadow mode stays on; execution is unaffected.'}
        </p>
      </Panel>
    );
  }

  const freshness = papFreshnessOf(live?.data_status, live?.data_age_s);

  return (
    <Panel title="PAP Shadow" meta={<span className={`badge ${freshnessBadgeClass(freshness)}`}>{freshness}</span>}>
      <div className="flex items-center justify-between">
        <span className="stat-l">Horizon consensus</span>
        <span className="mono text-[13px] font-semibold">{live?.horizon_consensus.consensus ?? '—'}</span>
      </div>
      <div className="mt-2 grid gap-1.5">
        {horizons.map(([id, horizon]) => (
          <div key={id} className="flex items-center justify-between gap-2">
            <span className="stat-l w-9">{id.toUpperCase()}</span>
            <span
              className="meter flex-1"
              aria-hidden="true"
            >
              <i
                className={
                  horizon.prediction === 'UP'
                    ? 'bg-up'
                    : horizon.prediction === 'DOWN'
                      ? 'bg-down'
                      : 'bg-border-strong'
                }
                style={{ width: `${Math.max(0, Math.min(100, horizon.probability))}%` }}
              />
            </span>
            <span className={`badge ${predictionBadgeClass(horizon.prediction)}`}>
              {horizon.prediction}
            </span>
            <span className="mono w-14 text-right text-[11px] text-ink-2">
              {confidenceLabel(horizon)}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center justify-between border-t border-border-subtle pt-2">
        <span className="sg-note m-0">Advisory — PAP never places orders.</span>
        <Link href="/pap" className="text-[11px] font-semibold text-accent hover:underline">
          Open PAP →
        </Link>
      </div>
    </Panel>
  );
}

/**
 * Live signal book in place: long/short balance and the freshest live setups,
 * so the operator can read the execution side of the market without opening
 * the Signals module.
 */
export function SignalsPulsePanel({
  signals,
  instrument,
}: {
  signals: SignalDeskState;
  instrument: string;
}) {
  const live = useMemo(
    () => signals.rows.filter((row) => stageOf(row.state) !== 'CLOSED'),
    [signals.rows],
  );

  const counts = useMemo(() => {
    let long = 0;
    let short = 0;
    let neut = 0;
    for (const row of live) {
      const tone = signalDirectionTone(row.direction);
      if (tone === 'bull') long += 1;
      else if (tone === 'bear') short += 1;
      else neut += 1;
    }
    return { long, short, neut };
  }, [live]);

  const recent = useMemo(
    () => [...live].sort((a, b) => (b.timeMs ?? 0) - (a.timeMs ?? 0)).slice(0, 5),
    [live],
  );

  const worker = signals.worker.running;

  return (
    <Panel
      title="Live Signals"
      meta={
        <span className={`badge ${worker === true && !signals.stale ? 'b-bull' : worker === false ? 'b-warn' : 'b-neut'}`}>
          {worker === true ? (signals.stale ? 'SCANNER STALE' : 'SCANNER LIVE') : worker === false ? 'OFFLINE' : 'UNKNOWN'}
        </span>
      }
    >
      <div className="stat-chips">
        <span className="stat-chip">
          live <b>{live.length}</b>
        </span>
        <span className="stat-chip">
          long <b className="v-bull">{counts.long}</b>
        </span>
        <span className="stat-chip">
          short <b className="v-bear">{counts.short}</b>
        </span>
        <span className="stat-chip">
          neutral <b>{counts.neut}</b>
        </span>
      </div>

      {signals.error ? <p className="sg-err mt-2">{signals.error}</p> : null}

      {recent.length === 0 ? (
        <p className="sg-note mt-2">
          No live signals on the books for {instrument}. The scanner populates them on the next
          candle close while the market is open.
        </p>
      ) : (
        <div className="mt-2 grid gap-1.5">
          {recent.map((row) => {
            const tone = signalDirectionTone(row.direction);
            return (
              <div key={row.id} className="flex items-center justify-between gap-2">
                <span className={`sg-dir ${dirClass(tone)}`}>{dirLabel(tone)}</span>
                <span className="min-w-0 flex-1 truncate text-[12px] font-semibold text-ink">
                  {row.symbol}
                  <span className="faint"> · {row.strategy}</span>
                </span>
                <span className="card-meta">{stateLabel(row.state)}</span>
                <span className="mono w-16 text-right text-[11px] text-ink-3">
                  {signalAgeLabel(row.timeMs)}
                </span>
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-3 flex items-center justify-between border-t border-border-subtle pt-2">
        <span className="sg-note m-0">
          {signals.ageMs !== null ? `Last scan ${signalAgeLabel(signals.updatedAt)}` : 'Scan age unknown'}
        </span>
        <Link href="/signals" className="text-[11px] font-semibold text-accent hover:underline">
          Open Signals →
        </Link>
      </div>
    </Panel>
  );
}
