'use client';

import React, { useCallback, useRef, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { api } from '@/lib/api';
import { asBoolean, asNumber, asString, errorMessage } from './IntelHubData';
import { PanelNotice, formatSigned } from './IntelHubUi';
import { Card } from '../shared/Card';
import { Badge } from '../shared/Badge';
import type { FIIDIIOverviewResponse } from '@/lib/types';

const FII_DII_POLL_MS = 60_000;

interface FiiDiiSnapshot {
  fiiCash: number | null;
  diiCash: number | null;
  fiiFuturesNet: number | null;
  fiiLongShortRatio: number | null;
  source: string | null;
  asOf: string | null;
  liveAvailable: boolean | null;
}

function parseFiiDii(data: FIIDIIOverviewResponse | null): FiiDiiSnapshot {
  return {
    fiiCash: asNumber(data?.fii_cash_net_crores),
    diiCash: asNumber(data?.dii_cash_net_crores),
    fiiFuturesNet: asNumber(data?.fii_futures_net_contracts),
    fiiLongShortRatio: asNumber(data?.fii_long_short_ratio),
    source: asString(data?.source),
    asOf: asString(data?.as_of),
    liveAvailable: asBoolean(data?.live_available),
  };
}

function CashCell({
  label,
  value,
  suffix,
}: {
  label: string;
  value: number | null;
  suffix: string;
}) {
  const tone =
    value === null ? 'text-ink' : value >= 0 ? 'text-up-strong' : 'text-down-strong';
  return (
    <div className="rounded-lg border border-border bg-surface-subtle p-2.5 shadow-xs">
      <div className="text-[10px] font-semibold uppercase text-ink-3">{label}</div>
      <div className={`mt-0.5 text-sm font-bold ${tone}`}>{formatSigned(value, 1, suffix)}</div>
    </div>
  );
}

export const InstitutionalFlowTicker: React.FC = () => {
  const [snapshot, setSnapshot] = useState<FiiDiiSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const seqRef = useRef(0);

  const load = useCallback(async () => {
    const seq = ++seqRef.current;
    try {
      const res = await api.getFiiDiiActivity();
      if (seq !== seqRef.current) return;
      setSnapshot(parseFiiDii(res?.data ?? null));
      setError(res?.error ?? null);
    } catch (err) {
      if (seq !== seqRef.current) return;
      setError(errorMessage(err));
    }
  }, []);

  usePolling(load, FII_DII_POLL_MS);

  const liveLabel =
    snapshot === null
      ? 'UNAVAILABLE'
      : snapshot.liveAvailable === true
        ? 'LIVE'
        : 'DAILY SNAPSHOT (T+1)';

  return (
    <Card
      title="INSTITUTIONAL PARTICIPANT ACTIVITY"
      subtitle={`FII & DII positioning · ${snapshot?.source ?? 'source unknown'} · as of ${
        snapshot?.asOf ?? '—'
      }`}
      headerAction={
        <Badge
          variant={snapshot?.liveAvailable === true ? 'success' : 'warning'}
          size="xs"
        >
          {liveLabel}
        </Badge>
      }
    >
      <div className="space-y-3">
        {error ? (
          <PanelNotice tone="down" role="alert">
            FII/DII data unavailable — {error}
          </PanelNotice>
        ) : null}
        {!snapshot && !error ? (
          <PanelNotice role="status">Waiting for FII/DII positioning…</PanelNotice>
        ) : null}

        {snapshot ? (
          <div className="grid grid-cols-2 gap-2 font-mono text-xs sm:grid-cols-4">
            <CashCell label="FII Net Cash" value={snapshot.fiiCash} suffix=" Cr" />
            <CashCell label="DII Net Cash" value={snapshot.diiCash} suffix=" Cr" />
            <CashCell
              label="FII Index Futures Net"
              value={snapshot.fiiFuturesNet}
              suffix=" contracts"
            />
            <div className="rounded-lg border border-border bg-surface-subtle p-2.5 shadow-xs">
              <div className="text-[10px] font-semibold uppercase text-ink-3">
                FII Long/Short Ratio
              </div>
              <div className="mt-0.5 text-sm font-bold text-ink">
                {snapshot.fiiLongShortRatio !== null
                  ? snapshot.fiiLongShortRatio.toFixed(2)
                  : '—'}
              </div>
            </div>
          </div>
        ) : null}

        {snapshot?.liveAvailable === false ? (
          <PanelNotice tone="warn">
            Exchange daily file — not an intraday live feed; values are the latest published
            snapshot.
          </PanelNotice>
        ) : null}
      </div>
    </Card>
  );
};
