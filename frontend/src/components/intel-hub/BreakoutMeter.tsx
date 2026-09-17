'use client';

import React from 'react';
import { useInstrument } from '@/context/InstrumentContext';
import { useIntelHub } from './IntelHubData';
import {
  PanelNotice,
  directionBadgeVariant,
  stateBadgeVariant,
} from './IntelHubUi';
import { Card } from '../shared/Card';
import { Gauge } from '../shared/Gauge';
import { Badge } from '../shared/Badge';

function formatLevel(level: string | null): string | null {
  if (level === null) return null;
  const n = Number(level);
  if (!Number.isFinite(n)) return level;
  return `₹${n.toLocaleString('en-IN')}`;
}

export const BreakoutMeter: React.FC = () => {
  const { instrument } = useInstrument();
  const { mi, miError, miStatus } = useIntelHub();

  const breakout = mi?.breakout ?? null;
  const level = formatLevel(breakout?.breakoutLevel ?? null);

  return (
    <Card
      title="BREAKOUT PRESSURE & FALSE-BREAK RISK"
      subtitle={`Breakout-engine scores for ${instrument}`}
      glow={breakout?.direction === 'BULLISH' ? 'emerald' : breakout?.direction === 'BEARISH' ? 'rose' : 'none'}
    >
      <div className="space-y-4 font-mono">
        {miStatus === 'error' && !mi ? (
          <PanelNotice tone="down" role="alert">
            Breakout evaluation unavailable — {miError}
          </PanelNotice>
        ) : null}
        {miStatus === 'loading' ? (
          <PanelNotice role="status">Waiting for breakout engine output…</PanelNotice>
        ) : null}
        {miError && mi ? (
          <PanelNotice tone="warn" role="alert">
            Last poll failed ({miError}) — showing last known values.
          </PanelNotice>
        ) : null}

        {breakout?.present ? (
          <>
            {/* Engine verdict */}
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-surface-subtle p-2.5">
              <span className="text-xs font-semibold text-ink-2">ENGINE VERDICT:</span>
              <div className="flex items-center gap-2">
                <Badge variant={directionBadgeVariant(breakout.direction)} size="xs">
                  {breakout.direction ?? 'NEUTRAL'}
                </Badge>
                <Badge variant={stateBadgeVariant(breakout.status)} size="xs">
                  {breakout.status ?? 'UNKNOWN'}
                </Badge>
                <span className="text-xs text-ink-2">
                  Confidence: {breakout.confidence !== null ? `${breakout.confidence}%` : '—'}
                </span>
              </div>
            </div>

            {/* Two Gauges */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {breakout.breakoutPressure !== null ? (
                <Gauge
                  value={breakout.breakoutPressure}
                  min={0}
                  max={100}
                  label="Breakout Pressure"
                  sublabel="Directional breakout pressure from the MI score block"
                  thresholds={{ warning: 40, danger: 20 }}
                  invertThresholds
                  unit=""
                />
              ) : (
                <PanelNotice>Breakout pressure unavailable in this poll.</PanelNotice>
              )}

              {breakout.falseBreakoutRisk !== null ? (
                <Gauge
                  value={breakout.falseBreakoutRisk}
                  min={0}
                  max={100}
                  label="False-Breakout Trap Risk"
                  sublabel="False-breakout risk from the MI score block"
                  thresholds={{ warning: 40, danger: 70 }}
                  unit=""
                />
              ) : (
                <PanelNotice>False-breakout risk unavailable in this poll.</PanelNotice>
              )}
            </div>

            {/* Boundary + real secondary readings */}
            <div className="grid grid-cols-2 gap-3 border-t border-border-subtle pt-2 text-xs">
              <div className="rounded border border-border bg-surface-subtle p-2 shadow-xs">
                <div className="text-[10px] font-semibold uppercase text-ink-3">
                  Breakout Trigger
                </div>
                <div className="mt-0.5 text-sm font-bold text-up-strong">
                  {level ?? '— unavailable'}
                </div>
              </div>
              <div className="rounded border border-border bg-surface-subtle p-2 shadow-xs">
                <div className="text-[10px] font-semibold uppercase text-ink-3">
                  Breakdown Pressure
                </div>
                <div className="mt-0.5 text-sm font-bold text-down-strong">
                  {breakout.breakdownPressure !== null
                    ? breakout.breakdownPressure.toFixed(1)
                    : '—'}
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-ink-2">
              <span>
                Quality: {breakout.breakoutQuality !== null ? breakout.breakoutQuality : '—'}
              </span>
              <span>
                Support: {breakout.supporting.length} · Conflicts: {breakout.conflicts.length}
              </span>
            </div>

            {breakout.reason ? (
              <PanelNotice>{breakout.reason}</PanelNotice>
            ) : null}
          </>
        ) : null}

        {mi && breakout && !breakout.present ? (
          <PanelNotice tone="warn">Breakout block missing from the MI payload.</PanelNotice>
        ) : null}
      </div>
    </Card>
  );
};
