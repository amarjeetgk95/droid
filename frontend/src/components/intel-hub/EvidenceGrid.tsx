'use client';

import React from 'react';
import { useInstrument } from '@/context/InstrumentContext';
import { useIntelHub, type MiEvidenceItem } from './IntelHubData';
import { PanelNotice } from './IntelHubUi';
import { Card } from '../shared/Card';
import { Badge } from '../shared/Badge';

function EvidenceRow({
  item,
  bias,
}: {
  item: MiEvidenceItem;
  bias: 'SUPPORTING' | 'CONFLICTING';
}) {
  const supporting = bias === 'SUPPORTING';

  return (
    <div
      className={`flex flex-col justify-between gap-2 rounded-lg border p-2.5 shadow-xs transition-all sm:flex-row sm:items-center ${
        supporting
          ? 'border-up-line bg-up-wash'
          : 'border-down-line bg-down-wash'
      }`}
    >
      <div className="flex min-w-0 items-center gap-2">
        <Badge variant={supporting ? 'bull' : 'bear'} size="xs">
          {item.dimension || 'EVIDENCE'}
        </Badge>
        <span className="font-semibold text-ink">{item.signal || '—'}</span>
        {item.detail ? (
          <span className="hidden font-sans text-[10px] text-ink-3 md:inline">
            — {item.detail}
          </span>
        ) : null}
      </div>
      <Badge variant={supporting ? 'success' : 'danger'} size="xs">
        {item.state}
      </Badge>
    </div>
  );
}

export const EvidenceGrid: React.FC = () => {
  const { instrument } = useInstrument();
  const { mi, miError, miStatus } = useIntelHub();

  const supporting = mi?.evidence.supporting ?? [];
  const conflicting = mi?.evidence.conflicting ?? [];
  const missing = mi?.evidence.missing ?? [];
  const stale = mi?.evidence.stale ?? [];
  const invalid = mi?.evidence.invalid ?? [];

  return (
    <Card
      title={
        <div className="flex w-full items-center justify-between">
          <span>INSTITUTIONAL EVIDENCE MATRIX</span>
          <div className="flex items-center gap-2">
            <span className="rounded border border-up-line bg-up-wash px-2 py-0.5 font-mono text-xs text-up-strong">
              {supporting.length} SUPPORTING
            </span>
            <span className="rounded border border-down-line bg-down-wash px-2 py-0.5 font-mono text-xs text-down-strong">
              {conflicting.length} CONFLICTING
            </span>
          </div>
        </div>
      }
      subtitle="Backend-attributed evidence for and against the current directional read"
    >
      <div className="space-y-2 font-mono text-xs">
        {miStatus === 'error' && !mi ? (
          <PanelNotice tone="down" role="alert">
            Evidence unavailable — {miError}
          </PanelNotice>
        ) : null}
        {miStatus === 'loading' ? (
          <PanelNotice role="status">Waiting for evidence from market intelligence…</PanelNotice>
        ) : null}
        {miError && mi ? (
          <PanelNotice tone="warn" role="alert">
            Last poll failed ({miError}) — showing last known evidence.
          </PanelNotice>
        ) : null}

        {mi && supporting.length === 0 && conflicting.length === 0 ? (
          <PanelNotice>
            No supporting or conflicting evidence was reported for {instrument} in this poll.
          </PanelNotice>
        ) : null}

        {supporting.map((item, idx) => (
          <EvidenceRow
            key={`sup-${item.dimension}-${item.signal}-${idx}`}
            item={item}
            bias="SUPPORTING"
          />
        ))}
        {conflicting.map((item, idx) => (
          <EvidenceRow
            key={`con-${item.dimension}-${item.signal}-${idx}`}
            item={item}
            bias="CONFLICTING"
          />
        ))}

        {mi && (missing.length > 0 || stale.length > 0 || invalid.length > 0) ? (
          <PanelNotice>
            Coverage gaps — missing: {missing.length}, stale: {stale.length}, invalid:{' '}
            {invalid.length}
          </PanelNotice>
        ) : null}
      </div>
    </Card>
  );
};
