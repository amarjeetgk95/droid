'use client';

import React from 'react';
import { api } from '@/lib/api';
import { Card } from '../shared/Card';
import { Gauge } from '../shared/Gauge';
import { Badge, type BadgeVariant } from '../shared/Badge';
import {
  PanelFreshness,
  PanelStateBanner,
  TelemetryTile,
  asNumber,
  asString,
  formatPercent,
  usePanelResource,
} from './PanelState';

const POLL_MS = 20_000;

interface BiasShift {
  name: string;
  shift: number;
}

interface DriftSnapshot {
  state: string | null;
  reason: string | null;
  flags: string[];
  confidenceShift: number | null;
  recentConfMean: number | null;
  baselineConfMean: number | null;
  schemaFailureRate: number | null;
  biasShifts: BiasShift[];
  timestamp: string | null;
}

async function fetchDrift(): Promise<DriftSnapshot> {
  const res = await api.request<{
    data: Record<string, unknown>;
    error: string | null;
    meta?: { timestamp?: string };
  }>('/api/v1/algo/ai/drift');
  if (res.error) throw new Error(res.error);
  const metrics = res.data ?? {};

  const rawFlags = Array.isArray(metrics.drift_flags) ? metrics.drift_flags : [];
  const flags = rawFlags.filter((flag): flag is string => typeof flag === 'string');

  const biasShifts = Object.entries(metrics)
    .filter(([key]) => key.startsWith('bias_shift_'))
    .map(([key, value]) => ({ name: key.slice('bias_shift_'.length), value: asNumber(value) }))
    .filter((entry): entry is { name: string; value: number } => entry.value !== null)
    .map((entry) => ({ name: entry.name, shift: entry.value }));

  return {
    state: asString(metrics.drift_state),
    reason: asString(metrics.reason),
    flags,
    confidenceShift: asNumber(metrics.confidence_shift),
    recentConfMean: asNumber(metrics.recent_conf_mean),
    baselineConfMean: asNumber(metrics.baseline_conf_mean),
    schemaFailureRate: asNumber(metrics.schema_failure_rate),
    biasShifts,
    timestamp: asString(res.meta?.timestamp),
  };
}

function stateVariant(state: string | null, insufficient: boolean): BadgeVariant {
  if (insufficient) return 'neutral';
  switch ((state ?? '').toUpperCase()) {
    case 'NORMAL':
      return 'success';
    case 'DRIFT_WARNING':
      return 'warning';
    case 'DRIFT_CRITICAL':
    case 'ROLLBACK_REQUIRED':
      return 'danger';
    default:
      return 'neutral';
  }
}

function featureLabel(name: string): string {
  return name.replace(/_/g, ' ');
}

export const AIDriftMonitor: React.FC = () => {
  const resource = usePanelResource(fetchDrift, POLL_MS, (snap) => snap.timestamp);
  const drift = resource.data;

  const insufficient = drift?.reason === 'INSUFFICIENT_DATA';
  const state = drift?.state ?? null;
  const stateLabel = insufficient ? 'INSUFFICIENT DATA' : (state ?? 'UNKNOWN');
  const confidencePct =
    drift?.confidenceShift !== null && drift?.confidenceShift !== undefined
      ? drift.confidenceShift * 100
      : null;
  const schemaPct =
    drift?.schemaFailureRate !== null && drift?.schemaFailureRate !== undefined
      ? drift.schemaFailureRate * 100
      : null;

  return (
    <Card
      title="AI Statistical Drift Monitor"
      subtitle="Confidence, bias and schema drift across recorded AI decisions"
      headerAction={
        <button
          type="button"
          className="btn"
          onClick={resource.refresh}
          disabled={resource.fetching}
          aria-label="Refresh AI drift evaluation"
        >
          {resource.fetching ? 'Refreshing…' : 'Refresh'}
        </button>
      }
      footer={
        <PanelFreshness
          error={resource.error}
          hasData={drift !== null}
          updatedAt={resource.updatedAt}
          generatedAt={resource.generatedAt}
          intervalMs={POLL_MS}
        />
      }
    >
      <div className="space-y-4 font-mono text-xs">
        <PanelStateBanner
          label="AI drift evaluation"
          error={resource.error}
          hasData={drift !== null}
          updatedAt={resource.updatedAt}
          onRetry={resource.refresh}
        />

        <div className="flex flex-wrap items-center justify-between gap-2 p-2.5 rounded-md bg-surface-subtle border border-border">
          <span className="text-ink-2 font-semibold">DRIFT EVALUATION</span>
          <Badge variant={stateVariant(state, insufficient)} size="xs" dot={drift !== null}>
            {stateLabel}
          </Badge>
        </div>

        {drift !== null && insufficient ? (
          <div className="notice notice--info" role="status">
            <span>
              Fewer decisions are recorded than the drift window requires, so no drift verdict can
              be produced. This is not a healthy result — it is an absence of evidence.
            </span>
          </div>
        ) : null}

        {drift !== null && !insufficient && state === null ? (
          <div className="notice notice--warn" role="alert">
            <span>
              The drift endpoint returned no <code>drift_state</code> field, so the evaluation
              state is unknown.
            </span>
          </div>
        ) : null}

        {drift !== null && !insufficient ? (
          confidencePct !== null ? (
            <Gauge
              value={confidencePct}
              label="Confidence distribution shift"
              unit="%"
              thresholds={{ warning: 15, danger: 30 }}
              sublabel={`Flagged above 15% · recent mean ${
                formatPercent(drift.recentConfMean, 1) ?? 'not reported'
              } vs baseline ${formatPercent(drift.baselineConfMean, 1) ?? 'not reported'}`}
            />
          ) : (
            <div className="notice notice--warn" role="status">
              <span>
                Confidence-shift metrics are unavailable for the evaluated window — no gauge value
                is shown rather than a fabricated 0%.
              </span>
            </div>
          )
        ) : null}

        {drift !== null && !insufficient ? (
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-2">
            <TelemetryTile
              label="Schema Failure Rate"
              value={formatPercent(schemaPct, 1) ?? 'UNKNOWN'}
              sub={
                schemaPct === null
                  ? 'not reported'
                  : schemaPct > 5
                    ? 'above 5% backend alert threshold'
                    : 'within threshold'
              }
            />
            <TelemetryTile
              label="Drift Flags"
              value={
                drift.flags.length > 0 ? (
                  <Badge variant="warning" size="xs">
                    {drift.flags.length} FLAGGED
                  </Badge>
                ) : (
                  <Badge variant="neutral" size="xs">
                    NONE REPORTED
                  </Badge>
                )
              }
              sub={drift.flags.join(', ') || 'no flag names returned'}
            />
            <TelemetryTile
              label="Bias Shift Features"
              value={String(drift.biasShifts.length)}
              sub="features with divergence metrics"
            />
          </div>
        ) : null}

        {drift !== null && drift.biasShifts.length > 0 ? (
          <div>
            <div className="micro-label mb-2">Feature-level distribution shift</div>
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-2">
              {drift.biasShifts.map((bias) => {
                const flagged = bias.shift > 0.15;
                return (
                  <div
                    key={bias.name}
                    className={`p-2 rounded-md border text-center ${
                      flagged
                        ? 'bg-warn-wash border-warn-line'
                        : 'bg-surface-subtle border-border'
                    }`}
                  >
                    <div className="text-[10px] text-ink-2 truncate" title={bias.name}>
                      {featureLabel(bias.name)}
                    </div>
                    <div
                      className={`font-bold mt-0.5 ${flagged ? 'text-warn-strong' : 'text-ink'}`}
                    >
                      {(bias.shift * 100).toFixed(1)}% shift
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : drift !== null && !insufficient ? (
          <div className="text-[10px] text-ink-3">
            No per-feature bias-shift metrics were returned for this window.
          </div>
        ) : null}
      </div>
    </Card>
  );
};
