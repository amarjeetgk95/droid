'use client';

import React from 'react';
import { useInstrument } from '@/context/InstrumentContext';
import { useIntelHub } from './IntelHubData';
import { PanelNotice, directionBadgeVariant, stateBadgeVariant } from './IntelHubUi';
import { Card } from '../shared/Card';
import { Badge } from '../shared/Badge';

function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-border bg-surface-subtle p-2 text-center shadow-xs">
      <div className="text-[10px] font-semibold text-ink-3">{label}</div>
      <div className="font-bold text-ink">{value}</div>
    </div>
  );
}

export const ShortHorizonCard: React.FC = () => {
  const { instrument } = useInstrument();
  const { mi, miError, miStatus } = useIntelHub();
  const sh = mi?.shortHorizon ?? null;
  const available = sh?.present === true && sh.status !== null;

  return (
    <Card
      title="SHORT-HORIZON EXPANSION SETUP"
      subtitle={`10-minute horizon strategy output for ${instrument}`}
      glow="cyan"
    >
      <div className="space-y-3 font-mono text-xs">
        {miStatus === 'error' && !mi ? (
          <PanelNotice tone="down" role="alert">
            Short-horizon evaluation unavailable — {miError}
          </PanelNotice>
        ) : null}
        {miStatus === 'loading' ? (
          <PanelNotice role="status">Waiting for short-horizon output…</PanelNotice>
        ) : null}
        {miError && mi ? (
          <PanelNotice tone="warn" role="alert">
            Last poll failed ({miError}) — showing last known output.
          </PanelNotice>
        ) : null}

        {available && sh ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-border bg-surface-subtle p-2">
              <span className="font-semibold text-ink-2">STATUS:</span>
              <div className="flex items-center gap-2">
                <Badge variant={directionBadgeVariant(sh.direction)} size="xs">
                  {sh.direction ?? 'NEUTRAL'}
                </Badge>
                <Badge variant={stateBadgeVariant(sh.status)} size="xs">
                  {sh.status ?? 'UNKNOWN'}
                </Badge>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Readout
                label="CONFIDENCE"
                value={sh.confidence !== null ? `${sh.confidence}%` : '—'}
              />
              <Readout
                label="HORIZON"
                value={sh.horizonMinutes !== null ? `${sh.horizonMinutes} min` : '—'}
              />
              <Readout
                label="ENTRY ZONE"
                value={sh.entryZone.length > 0 ? sh.entryZone.join(' – ') : '—'}
              />
              <Readout label="STOP LOSS" value={sh.stopLoss ?? '—'} />
              <Readout
                label="TARGET ZONE"
                value={sh.targetZone.length > 0 ? sh.targetZone.join(' – ') : '—'}
              />
              <Readout
                label="FALSE-BREAK RISK"
                value={sh.falseBreakoutRisk !== null ? `${sh.falseBreakoutRisk}` : '—'}
              />
            </div>

            {sh.reason ? (
              <div className="font-sans text-[11px] text-ink-2">{sh.reason}</div>
            ) : null}
          </>
        ) : null}

        {mi && sh && sh.present && !available ? (
          <PanelNotice tone="warn">
            Short-horizon block present but holds no usable status.
          </PanelNotice>
        ) : null}
        {mi && sh && !sh.present ? (
          <PanelNotice tone="warn">Short-horizon block missing from the MI payload.</PanelNotice>
        ) : null}
      </div>
    </Card>
  );
};
