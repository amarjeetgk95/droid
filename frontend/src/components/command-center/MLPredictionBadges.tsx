'use client';

import React, { useCallback, useRef, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { useInstrument } from '@/context/InstrumentContext';
import { useMarketSession } from '@/hooks/useMarketSession';
import { api } from '@/lib/api';
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

export const MLPredictionBadges: React.FC = () => {
  const { instrument } = useInstrument();
  const { isOpen } = useMarketSession();
  const [model, setModel] = useState<PredictionModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadedRef = useRef(false);
  const hasDataRef = useRef(false);

  const load = useCallback(async () => {
    const initial = !loadedRef.current;
    if (initial) setLoading(true);
    else setRefreshing(true);
    try {
      const res = await api.getMLPrediction(instrument);
      const parsed = parsePrediction(res?.data);
      setModel(parsed);
      if (parsed !== null) hasDataRef.current = true;
      setError(parsed === null ? 'ML service returned no usable prediction payload' : null);
    } catch (err) {
      setModel(null);
      setError(err instanceof Error ? err.message : 'ML prediction unavailable');
    } finally {
      loadedRef.current = true;
      setLoading(false);
      setRefreshing(false);
    }
  }, [instrument]);

  usePolling(() => {
    if (!isOpen && hasDataRef.current) return;
    return load();
  }, 5000);

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
        {loading && !model ? (
          <div style={{ display: 'grid', gap: 10 }}>
            <div className="skel" style={{ height: 16, width: '55%' }}>.</div>
            <div className="skel" style={{ height: 14, width: '100%' }}>.</div>
            <div className="skel" style={{ height: 40, width: '100%' }}>.</div>
          </div>
        ) : model === null ? (
          <EmptyNote>
            {error ? `ML prediction unavailable — ${error}` : 'No ML prediction available.'}
          </EmptyNote>
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
            lastAt={model?.timestamp ?? null}
            fetching={refreshing}
            marketClosed={!isOpen}
            sourceLabel="REST · 5s poll"
          />
        </div>
      </div>
    </Card>
  );
};
