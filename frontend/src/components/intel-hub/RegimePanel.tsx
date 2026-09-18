'use client';

import React from 'react';
import { useInstrument } from '@/context/InstrumentContext';
import { useIntelHub } from './IntelHubData';
import { PanelNotice } from './IntelHubUi';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Gauge } from '@/components/ui/gauge';
import { confidencePct, isUsableRegimeOverview } from '@/components/markets/truthful';

function mtfBadgeVariant(bias: string): 'bull' | 'bear' | 'neutral' {
  const s = bias.toUpperCase();
  if (s.includes('BULL')) return 'bull';
  if (s.includes('BEAR')) return 'bear';
  return 'neutral';
}

export const RegimePanel: React.FC = () => {
  const { instrument } = useInstrument();
  const { mi, miError, miStatus, regime, regimeError, regimeLoading } = useIntelHub();

  const usableOverview = regime && isUsableRegimeOverview(regime, instrument) ? regime : null;
  const regimeState = usableOverview?.regime_state ?? mi?.regime ?? null;
  const stateLabel = regimeState ? regimeState.replace(/_/g, ' ') : null;
  const isBull = regimeState?.includes('BULL') ?? false;
  const isBear = regimeState?.includes('BEAR') ?? false;
  const confidence = usableOverview ? confidencePct(usableOverview.confidence_score) : null;

  const adxRaw = usableOverview?.indicators?.adx_14 ?? null;
  const adx = adxRaw !== null && Number.isFinite(adxRaw) && adxRaw > 0 ? adxRaw : null;

  const mtfEntries = mi?.multiTimeframe ? Object.entries(mi.multiTimeframe) : [];

  return (
    <Card
      title="MARKET REGIME & MTF ALIGNMENT"
      subtitle={`Authoritative regime classification engine for ${instrument}`}
      glow={isBull ? 'emerald' : isBear ? 'rose' : 'none'}
    >
      <div className="space-y-4 font-mono">
        {/* Top Overview */}
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-surface-subtle p-3">
          <div>
            <div className="text-[10px] font-semibold uppercase text-ink-3">
              Regime Classification
            </div>
            <div className="mt-0.5 flex items-center gap-2 text-sm font-bold text-ink">
              <span>{stateLabel ?? 'UNAVAILABLE'}</span>
              {mi?.volatility ? (
                <Badge
                  variant={isBull ? 'bull' : isBear ? 'bear' : 'neutral'}
                  size="xs"
                >
                  {mi.volatility.toUpperCase()}
                </Badge>
              ) : null}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] font-semibold uppercase text-ink-3">
              Model Confidence
            </div>
            <div className="mt-0.5 text-sm font-bold text-primary">
              {confidence !== null ? `${confidence}%` : regimeLoading ? '…' : '—'}
            </div>
          </div>
        </div>

        {miStatus === 'error' && !mi ? (
          <PanelNotice tone="down" role="alert">
            Market intelligence unavailable — {miError}
          </PanelNotice>
        ) : null}
        {miStatus === 'loading' ? (
          <PanelNotice role="status">Waiting for market intelligence…</PanelNotice>
        ) : null}
        {miError && mi ? (
          <PanelNotice tone="warn" role="alert">
            Last poll failed ({miError}) — showing last known values.
          </PanelNotice>
        ) : null}
        {!usableOverview && !regimeLoading ? (
          <PanelNotice tone="warn">
            {regimeError ?? `Regime diagnosis unavailable for ${instrument}.`}
          </PanelNotice>
        ) : null}

        {/* Multi-timeframe Alignment Strip */}
        <div>
          <div className="mb-2 text-xs font-semibold text-ink-2">
            MULTI-TIMEFRAME (MTF) VECTOR
          </div>
          {mtfEntries.length > 0 ? (
            <div className="grid grid-cols-5 gap-2 text-center">
              {mtfEntries.map(([tf, bias]) => (
                <div
                  key={tf}
                  className="flex flex-col items-center justify-center gap-1 rounded-lg border border-border bg-surface-subtle p-2 shadow-xs"
                >
                  <span className="text-[10px] font-bold text-ink-2">
                    {tf.toUpperCase()}
                  </span>
                  <Badge variant={mtfBadgeVariant(bias)} size="xs">
                    {bias.toUpperCase()}
                  </Badge>
                </div>
              ))}
            </div>
          ) : (
            <PanelNotice>
              MTF alignment unavailable — no multi-timeframe vector in this poll.
            </PanelNotice>
          )}
        </div>

        {/* Trend Strength Gauge — ADX(14) is the backend reading; a weak trend
            is the warning condition, so the thresholds are inverted. */}
        {adx !== null ? (
          <Gauge
            value={adx}
            min={0}
            max={100}
            label="ADX(14) Trend Strength"
            sublabel="Average Directional Index from the regime engine"
            thresholds={{ warning: 25, danger: 15 }}
            invertThresholds
            unit=""
          />
        ) : (
          <PanelNotice>
            Trend strength unavailable — no ADX(14) reading in this diagnosis.
          </PanelNotice>
        )}
      </div>
    </Card>
  );
};
