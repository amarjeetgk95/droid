'use client';

import React, { useMemo } from 'react';
import { useCommandSection } from '@/context/AppStreamContext';
import { useInstrument } from '@/context/InstrumentContext';
import { useMarketSession } from '@/hooks/useMarketSession';
import { toNumber } from '@/lib/coerce';
import { Card } from '@/components/ui/card';
import { Badge, type BadgeVariant } from '@/components/ui/badge';
import { EmptyNote, StackedProbabilityBar, fmtSigned } from '@/components/ui/desk';
import { FreshnessClock } from '@/components/common/FreshnessClock';

type Bias = 'BULLISH' | 'BEARISH' | 'NEUTRAL';

interface PredictionModel {
  bias: Bias | null;
  confidence: number | null;
  bullish: number | null;
  neutral: number | null;
  bearish: number | null;
  modelVersion: string | null;
  marketRegime: string | null;
  spot: number | null;
  timestamp: string | null;
  features: Array<{ name: string; contribution: number }>;
}

function finite(v: unknown): number | null {
  return toNumber(v);
}

function str(v: unknown): string | null {
  return typeof v === 'string' && v.trim().length > 0 ? v : null;
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function parsePrediction(payload: unknown): PredictionModel | null {
  if (!payload || typeof payload !== 'object') return null;
  const o = payload as Record<string, unknown>;
  const biasRaw = str(o.predicted_bias)?.toUpperCase();
  const bias: Bias | null =
    biasRaw === 'BULLISH' || biasRaw === 'BEARISH' || biasRaw === 'NEUTRAL' ? biasRaw : null;
  const featuresRaw = Array.isArray(o.top_features) ? o.top_features : [];
  const features: Array<{ name: string; contribution: number }> = [];
  for (const entry of featuresRaw) {
    if (!entry || typeof entry !== 'object') continue;
    const fo = entry as Record<string, unknown>;
    const name = str(fo.feature_name);
    const contribution = finite(fo.contribution);
    if (name !== null && contribution !== null) features.push({ name, contribution });
  }
  const model: PredictionModel = {
    bias,
    confidence: finite(o.confidence_score),
    bullish: finite(o.bullish_pct),
    neutral: finite(o.neutral_pct),
    bearish: finite(o.bearish_pct),
    modelVersion: str(o.model_version),
    marketRegime: str(o.market_regime),
    spot: finite(o.spot_price),
    timestamp: str(o.timestamp),
    features,
  };
  const hasAny =
    model.bias !== null ||
    model.confidence !== null ||
    model.bullish !== null ||
    model.bearish !== null ||
    model.modelVersion !== null;
  return hasAny ? model : null;
}

function biasVariant(bias: Bias | null): BadgeVariant {
  if (bias === 'BULLISH') return 'bull';
  if (bias === 'BEARISH') return 'bear';
  return 'neutral';
}

/**
 * `ml.value.by_symbol` keys are the canonical broker symbols the backend
 * composes (`INSTRUMENT_SYMBOLS`): NIFTY / BANKNIFTY / SENSEX. The selection
 * surface already uses those spellings; the "NIFTY 50" alias is accepted
 * defensively. An unknown instrument reads no entry — this lookup can never
 * surface another instrument's prediction under the selected label.
 */
const ML_SYMBOL_KEYS: Record<string, string> = {
  NIFTY: 'NIFTY',
  'NIFTY 50': 'NIFTY',
  BANKNIFTY: 'BANKNIFTY',
  SENSEX: 'SENSEX',
};

function toMlSymbol(instrument: string): string {
  return ML_SYMBOL_KEYS[instrument.toUpperCase()] ?? instrument.toUpperCase();
}

/**
 * ML directional forecast — pure consumer of `ml.value.by_symbol`.
 *
 * The prediction for the selected instrument is read from the unified
 * command stream; nothing here polls. A missing section, an absent map key or
 * an explicit `null` entry all render the same honest unavailable state.
 */
export const MLPredictionBadges: React.FC = () => {
  const { instrument } = useInstrument();
  const { isOpen } = useMarketSession();
  const section = useCommandSection('ml');

  const sectionValue = asRecord(section?.value);
  const bySymbol = asRecord(sectionValue?.by_symbol);
  const symbol = toMlSymbol(instrument);
  const model = bySymbol ? parsePrediction(bySymbol[symbol]) : null;

  const loading = section === null;

  const lastAt = useMemo(() => {
    if (model?.timestamp) {
      const parsed = new Date(model.timestamp);
      if (!Number.isNaN(parsed.getTime())) return parsed;
    }
    if (section?.updated_at) {
      const parsed = new Date(section.updated_at);
      if (!Number.isNaN(parsed.getTime())) return parsed;
    }
    return null;
  }, [model?.timestamp, section?.updated_at]);

  const probabilitiesReady =
    model !== null && model.bullish !== null && model.neutral !== null && model.bearish !== null;

  return (
    <Card
      title="ML QUANT DIRECTIONAL FORECAST"
      subtitle={`Ensemble probability distribution for ${instrument}`}
      headerAction={
        <span className="text-[10px] text-ink-3 font-mono">
          {model?.modelVersion ?? 'model —'}
        </span>
      }
    >
      <div className="space-y-4 font-mono">
        {loading ? (
          <div style={{ display: 'grid', gap: 10 }}>
            <div className="skel" style={{ height: 16, width: '55%' }}>.</div>
            <div className="skel" style={{ height: 14, width: '100%' }}>.</div>
            <div className="skel" style={{ height: 40, width: '100%' }}>.</div>
          </div>
        ) : model === null ? (
          <EmptyNote>No ML prediction available.</EmptyNote>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <Badge variant={biasVariant(model.bias)} size="sm">
                {model.bias ?? 'UNKNOWN'}
              </Badge>
              <span className="text-xs text-ink-2">
                Confidence{' '}
                <strong className="text-foreground">
                  {model.confidence !== null ? `${model.confidence.toFixed(1)}%` : '—'}
                </strong>
              </span>
              {model.marketRegime ? (
                <span className="text-xs text-ink-3">Regime {model.marketRegime}</span>
              ) : null}
              {model.spot !== null ? (
                <span className="text-xs text-ink-3">
                  Spot {model.spot.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                </span>
              ) : null}
            </div>

            <div>
              {probabilitiesReady ? (
                <>
                  <div className="flex items-center justify-between text-xs mb-1.5 font-semibold">
                    <span className="text-up-strong">BULLISH {model.bullish!.toFixed(1)}%</span>
                    <span className="text-ink-3">NEUTRAL {model.neutral!.toFixed(1)}%</span>
                    <span className="text-down-strong">BEARISH {model.bearish!.toFixed(1)}%</span>
                  </div>
                  <StackedProbabilityBar
                    bullPct={model.bullish!}
                    neutPct={model.neutral!}
                    bearPct={model.bearish!}
                    height={14}
                  />
                </>
              ) : (
                <EmptyNote>Probability distribution unavailable.</EmptyNote>
              )}
            </div>

            <div className="pt-2 border-t border-border-subtle">
              <div className="text-[10px] text-ink-3 uppercase tracking-wider mb-2 font-semibold">
                Top Quantitative Feature Drivers
              </div>
              {model.features.length === 0 ? (
                <EmptyNote>No feature attribution reported by the model.</EmptyNote>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {model.features.map((feat, idx) => (
                    <div
                      key={`${feat.name}-${idx}`}
                      className="p-2 rounded bg-surface-subtle border border-border flex items-center justify-between text-xs"
                    >
                      <span className="text-ink-2 truncate max-w-[130px] font-medium">
                        {feat.name}
                      </span>
                      <span className="text-primary font-bold">
                        {fmtSigned(feat.contribution, 3)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        <div className="flex justify-end">
          <FreshnessClock
            lastAt={lastAt}
            marketClosed={!isOpen}
            dataQuality={section?.degraded === true ? 'DEGRADED' : null}
            sourceLabel="SSE · command stream"
          />
        </div>
      </div>
    </Card>
  );
};
