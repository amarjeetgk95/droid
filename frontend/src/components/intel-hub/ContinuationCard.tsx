'use client';

import React from 'react';
import { useInstrument } from '@/context/InstrumentContext';
import { useIntelHub } from './IntelHubData';
import { PanelNotice, directionBadgeVariant, stateBadgeVariant } from './IntelHubUi';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

export const ContinuationCard: React.FC = () => {
  const { instrument } = useInstrument();
  const { mi, miError, miStatus } = useIntelHub();
  const cont = mi?.continuation ?? null;
  const available = cont?.present === true && cont.status !== null;

  return (
    <Card
      title="TREND CONTINUATION FILTER"
      subtitle={`Intraday continuation strategy output for ${instrument}`}
      glow="indigo"
    >
      <div className="space-y-3 font-mono text-xs">
        {miStatus === 'error' && !mi ? (
          <PanelNotice tone="down" role="alert">
            Continuation evaluation unavailable — {miError}
          </PanelNotice>
        ) : null}
        {miStatus === 'loading' ? (
          <PanelNotice role="status">Waiting for continuation output…</PanelNotice>
        ) : null}
        {miError && mi ? (
          <PanelNotice tone="warn" role="alert">
            Last poll failed ({miError}) — showing last known output.
          </PanelNotice>
        ) : null}

        {available && cont ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-border bg-surface-subtle p-2">
              <span className="font-semibold text-ink-2">STATUS:</span>
              <div className="flex items-center gap-2">
                <Badge variant={directionBadgeVariant(cont.direction)} size="xs">
                  {cont.direction ?? 'NEUTRAL'}
                </Badge>
                <Badge variant={stateBadgeVariant(cont.status)} size="xs">
                  {cont.status ?? 'UNKNOWN'}
                </Badge>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 text-center">
              <div className="rounded border border-border bg-surface-subtle p-2 shadow-xs">
                <div className="text-[10px] font-semibold text-ink-3">CONFIDENCE</div>
                <div className="font-bold text-ink">
                  {cont.confidence !== null ? `${cont.confidence}%` : '—'}
                </div>
              </div>
              <div className="rounded border border-border bg-surface-subtle p-2 shadow-xs">
                <div className="text-[10px] font-semibold text-ink-3">MAX HOLDING</div>
                <div className="font-bold text-ink">
                  {cont.maxHoldingMinutes !== null ? `${cont.maxHoldingMinutes} min` : '—'}
                </div>
              </div>
            </div>

            {cont.reason ? (
              <div className="font-sans text-[11px] text-ink-2">{cont.reason}</div>
            ) : null}

            <div className="rounded border border-warn-line bg-warn-wash p-2">
              <div className="text-[10px] font-semibold uppercase text-warn-strong">
                Invalidation
              </div>
              <div className="mt-0.5 font-sans text-[11px] text-ink-2">
                {cont.invalidation ?? 'No invalidation level supplied.'}
              </div>
            </div>
          </>
        ) : null}

        {mi && cont && cont.present && !available ? (
          <PanelNotice tone="warn">
            Continuation block present but holds no usable status.
          </PanelNotice>
        ) : null}
        {mi && cont && !cont.present ? (
          <PanelNotice tone="warn">Continuation block missing from the MI payload.</PanelNotice>
        ) : null}
      </div>
    </Card>
  );
};
