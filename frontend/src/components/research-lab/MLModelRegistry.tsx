'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { Card, EmptyNote, Stat, fmtNum, fmtPct01 } from '@/components/ui/desk';
import { Button } from '@/components/ui/button';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import { ErrorNote, ExportButtons, SectionLabel } from './controls';
import { exportAsJson, timestampSlug } from './export';
import {
  asRecord,
  asString,
  errorMessage,
  formatFeatureValue,
  flattenRecord,
  parseModelManifests,
  type ModelManifestMap,
} from './contracts';

interface RegistryState {
  modelInfo: Record<string, unknown> | null;
  champion: ModelManifestMap | null;
  challenger: ModelManifestMap | null;
}

function ManifestCard({
  name,
  manifest,
  label,
}: {
  name: string;
  manifest: Record<string, unknown>;
  label: string;
}) {
  const entries = useMemo(() => flattenRecord(manifest), [manifest]);
  const title = asString(manifest.model_version) ?? name;
  return (
    <div className="rounded border border-border bg-surface-subtle p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-ink text-xs break-all">{title}</span>
        <span className="badge b-neut">{label}</span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {entries.map(({ key, value }) => (
          <div key={key} className="rounded border border-border-subtle bg-surface p-1.5">
            <div className="text-[10px] uppercase text-ink-3 truncate" title={key}>
              {key.replace(/_/g, ' ')}
            </div>
            <div className="num text-xs font-semibold text-ink break-words">
              {formatFeatureValue(value)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export const MLModelRegistry: React.FC = () => {
  const [state, setState] = useState<RegistryState>({ modelInfo: null, champion: null, challenger: null });
  const [errors, setErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const [infoRes, championRes, challengerRes] = await Promise.allSettled([
      api.getMLModelInfo(),
      api.getMLChampionInfo(),
      api.getMLChallengerInfo(),
    ]);

    const next: RegistryState = { modelInfo: null, champion: null, challenger: null };
    const nextErrors: string[] = [];

    if (infoRes.status === 'fulfilled') {
      const rec = asRecord(infoRes.value);
      next.modelInfo = rec && asRecord(rec.data) ? (asRecord(rec.data) as Record<string, unknown>) : rec;
    } else {
      nextErrors.push(`Ensemble model info — ${errorMessage(infoRes.reason)}`);
    }

    if (championRes.status === 'fulfilled') {
      const parsed = parseModelManifests(championRes.value, 'champion_models');
      if (parsed === null) {
        nextErrors.push('Champion registry — response did not include a champion_models container.');
      } else {
        next.champion = parsed;
      }
    } else {
      nextErrors.push(`Champion registry — ${errorMessage(championRes.reason)}`);
    }

    if (challengerRes.status === 'fulfilled') {
      const parsed = parseModelManifests(challengerRes.value, 'challenger_models');
      if (parsed === null) {
        nextErrors.push('Challenger registry — response did not include a challenger_models container.');
      } else {
        next.challenger = parsed;
      }
    } else {
      nextErrors.push(`Challenger registry — ${errorMessage(challengerRes.reason)}`);
    }

    setState(next);
    setErrors(nextErrors);
    setLastLoadedAt(new Date());
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const modelInfo = state.modelInfo;
  const trained = modelInfo ? modelInfo.trained === true : null;
  const metrics = asRecord(modelInfo?.metrics);
  const artifacts = asRecord(modelInfo?.artifacts);
  const featureNames = Array.isArray(modelInfo?.feature_names)
    ? (modelInfo?.feature_names as unknown[])
    : [];

  const championEntries = useMemo(() => Object.entries(state.champion ?? {}), [state.champion]);
  const challengerEntries = useMemo(() => Object.entries(state.challenger ?? {}), [state.challenger]);

  const handleExportJson = () => {
    exportAsJson(`ml-registry-${timestampSlug()}.json`, {
      model_info: state.modelInfo,
      champion_models: state.champion,
      challenger_models: state.challenger,
    });
  };

  const hasExport = state.modelInfo !== null || state.champion !== null || state.challenger !== null;

  return (
    <Card
      title="ML MODEL REGISTRY: CHAMPION VS CHALLENGER"
      meta="Artifacts on disk · /api/v1/ml/*"
      action={<ExportButtons onJson={hasExport ? handleExportJson : undefined} disabled={!hasExport} />}
    >
      <div className="space-y-3 text-xs">
        {loading ? <p className="muted" style={{ margin: 0 }}>Loading model registry…</p> : null}

        {errors.map((message) => (
          <ErrorNote key={message} message={message} onRetry={() => void load()} />
        ))}

        {modelInfo ? (
          <div className="space-y-2">
            <SectionLabel>Directional ensemble (trained artifact)</SectionLabel>
            {trained === false ? (
              <EmptyNote>
                {asString(modelInfo.message) ??
                  'No trained ensemble artifact found on this backend. Train offline and retry.'}
              </EmptyNote>
            ) : (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <Stat label="Model" value={asString(modelInfo.model_version) ?? '—'} />
                  <Stat label="Horizon" value={modelInfo.horizon_minutes === undefined ? '—' : `${formatFeatureValue(modelInfo.horizon_minutes)}m`} />
                  <Stat label="Samples" value={modelInfo.n_samples === undefined ? '—' : formatFeatureValue(modelInfo.n_samples)} />
                  <Stat label="Features" value={modelInfo.n_features === undefined ? '—' : formatFeatureValue(modelInfo.n_features)} />
                  <Stat
                    label="Ensemble acc"
                    value={metrics?.ensemble_accuracy === undefined ? '—' : fmtPct01(metrics.ensemble_accuracy)}
                  />
                  <Stat
                    label="XGB acc / logloss"
                    value={
                      metrics
                        ? `${fmtPct01(metrics.xgb_accuracy)} · ${fmtNum(metrics.xgb_logloss, 4)}`
                        : '—'
                    }
                  />
                  <Stat
                    label="LGB acc / logloss"
                    value={
                      metrics
                        ? `${fmtPct01(metrics.lgb_accuracy)} · ${fmtNum(metrics.lgb_logloss, 4)}`
                        : '—'
                    }
                  />
                  <Stat label="Target spec" value={asString(modelInfo.target_spec_version) ?? '—'} />
                </div>
                <p className="muted" style={{ margin: 0 }}>
                  Trained {asString(modelInfo.trained_at) ?? '—'}
                  {artifacts
                    ? ` · artifacts: xgb ${artifacts.xgb_exists ? 'present' : 'missing'}, lgb ${artifacts.lgb_exists ? 'present' : 'missing'}`
                    : ''}
                </p>
                {featureNames.length > 0 ? (
                  <p className="faint" style={{ margin: 0 }}>
                    feature schema: {featureNames.map((f) => String(f)).join(', ')}
                  </p>
                ) : null}
              </>
            )}
          </div>
        ) : null}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <div className="space-y-2">
            <SectionLabel>Champion models</SectionLabel>
            {state.champion && championEntries.length === 0 ? (
              <EmptyNote>No champion manifests found on disk.</EmptyNote>
            ) : (
              championEntries.map(([name, manifest]) => (
                <ManifestCard key={name} name={name} manifest={manifest} label="CHAMPION" />
              ))
            )}
          </div>

          <div className="space-y-2">
            <SectionLabel>Challenger models</SectionLabel>
            {state.challenger && challengerEntries.length === 0 ? (
              <EmptyNote>No challenger manifests found on disk.</EmptyNote>
            ) : (
              challengerEntries.map(([name, manifest]) => (
                <ManifestCard key={name} name={name} manifest={manifest} label="CHALLENGER" />
              ))
            )}
          </div>
        </div>

        <div className="rounded border border-border bg-surface-subtle p-3 space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-ink">Training trigger</span>
            <Button
              type="button"
              variant="outline"
              size="xs"
              disabled
              title="POST /api/v1/ml/train requires a verified feature matrix (min 100 samples) plus labels; this UI has no dataset feed."
            >
              Retrain ensemble
            </Button>
          </div>
          <p className="muted" style={{ margin: 0 }}>
            Unavailable from this UI: <span className="mono">POST /api/v1/ml/train</span> requires a
            verified historical feature matrix (≥100 samples) with matching labels and rejects
            synthetic generation. Run the offline dataset/training pipeline
            (<span className="mono">backend/scripts/train_*.py</span>) and reload the registry.
          </p>
        </div>

        <div className="flex items-center justify-end">
          <FreshnessClock lastAt={lastLoadedAt} fetching={loading} sourceLabel="REST · ml registry" />
        </div>
      </div>
    </Card>
  );
};
