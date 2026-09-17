'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Trophy,
  Swords,
  Play,
  RotateCw,
  AlertTriangle,
} from 'lucide-react';
import { api } from '@/lib/api';
import { Card, fmtNum } from '@/components/ui/desk';

export function MLOperationsTab() {
  const [modelInfo, setModelInfo] = useState<any>(null);
  const [targets, setTargets] = useState<any>(null);
  const [championInfo, setChampionInfo] = useState<any>(null);
  const [challengerInfo, setChallengerInfo] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [failedMetadata, setFailedMetadata] = useState<string[]>([]);

  // Live Prediction Tester State
  const [testSymbol, setTestSymbol] = useState('NIFTY');
  const [testHorizon, setTestHorizon] = useState(60);
  const [predicting, setPredicting] = useState(false);
  const [predictionResult, setPredictionResult] = useState<any>(null);
  const [predictError, setPredictError] = useState<string | null>(null);

  // Calibration Inspector State
  const [calibSymbol, setCalibSymbol] = useState('NIFTY');
  const [calibHorizon, setCalibHorizon] = useState(60);
  const [calibData, setCalibData] = useState<any>(null);
  const [calibLoading, setCalibLoading] = useState(false);
  const [calibError, setCalibError] = useState<string | null>(null);

  // Settlement State
  const [settling, setSettling] = useState(false);
  const [settleMsg, setSettleMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const fetchMLMetadata = useCallback(async () => {
    setLoading(true);
    try {
      const [modelRes, targetsRes, champRes, challRes] = await Promise.allSettled([
        api.getMLModelInfo(),
        api.getMLTargets(),
        api.getMLChampionInfo(),
        api.getMLChallengerInfo(),
      ]);

      const failed: string[] = [];
      if (modelRes.status === 'fulfilled' && modelRes.value?.data != null) {
        setModelInfo(modelRes.value.data);
      } else {
        setModelInfo(null);
        failed.push('model-info');
      }
      if (targetsRes.status === 'fulfilled' && targetsRes.value?.data != null) {
        setTargets(targetsRes.value.data);
      } else {
        setTargets(null);
        failed.push('targets');
      }
      if (champRes.status === 'fulfilled' && champRes.value?.data != null) {
        setChampionInfo(champRes.value.data);
      } else {
        setChampionInfo(null);
        failed.push('champion-info');
      }
      if (challRes.status === 'fulfilled' && challRes.value?.data != null) {
        setChallengerInfo(challRes.value.data);
      } else {
        setChallengerInfo(null);
        failed.push('challenger-info');
      }
      setFailedMetadata(failed);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchMLMetadata();
  }, [fetchMLMetadata]);

  // Run Test Prediction
  const handleTestPredict = async () => {
    setPredicting(true);
    setPredictError(null);
    try {
      const res = await api.getMLPrediction(testSymbol, testHorizon);
      if (res?.data == null) throw new Error('Prediction endpoint returned no data');
      setPredictionResult(res.data);
    } catch (err: any) {
      setPredictionResult(null);
      setPredictError(err?.message || 'Prediction failed');
    } finally {
      setPredicting(false);
    }
  };

  // Fetch Calibration Curve
  const fetchCalibration = useCallback(async () => {
    setCalibLoading(true);
    setCalibError(null);
    try {
      const res = await api.getMLCalibration(calibSymbol, calibHorizon);
      if (res?.data == null) throw new Error('Calibration endpoint returned no data');
      setCalibData(res.data);
    } catch (err: any) {
      setCalibData(null);
      setCalibError(err?.message || 'Failed to load calibration');
    } finally {
      setCalibLoading(false);
    }
  }, [calibSymbol, calibHorizon]);

  useEffect(() => {
    void fetchCalibration();
  }, [fetchCalibration]);

  // Run Manual Settlement
  const handleRunSettlement = async () => {
    setSettling(true);
    setSettleMsg(null);
    try {
      const res = await api.runMLSettlement(testSymbol, 50);
      const summary = res?.data as
        | { settled?: number; errors?: number; skipped?: Record<string, number> }
        | undefined;
      if (summary && typeof summary.settled === 'number') {
        const skippedCount = summary.skipped
          ? Object.values(summary.skipped).reduce((a, b) => a + Number(b), 0)
          : 0;
        setSettleMsg({
          type: summary.errors ? 'error' : 'success',
          text: `Settlement run complete — settled ${summary.settled}, skipped ${skippedCount}, errors ${summary.errors ?? 0}.`,
        });
      } else {
        setSettleMsg({ type: 'error', text: 'Settlement request returned no summary — check backend logs.' });
      }
    } catch (err: any) {
      setSettleMsg({ type: 'error', text: `Settlement error: ${err?.message || 'Failed'}` });
    } finally {
      setSettling(false);
    }
  };

  // The backend returns `{trained:false, message}` when no meta.json exists;
  // when artifacts exist it returns the meta payload (no explicit `trained`
  // flag), so readiness also accepts a present `trained_at`/artifact.
  const isTrained =
    modelInfo?.trained === true ||
    (modelInfo?.trained !== false &&
      (modelInfo?.trained_at != null || modelInfo?.artifacts?.xgb_exists === true));
  const modelState: 'loading' | 'ready' | 'untrained' | 'unavailable' =
    loading && !modelInfo
      ? 'loading'
      : modelInfo?.trained === false
        ? 'untrained'
        : isTrained
          ? 'ready'
          : 'unavailable';
  const modelStateBadge: Record<typeof modelState, { cls: string; label: string }> = {
    loading: { cls: 'b-neut', label: 'LOADING…' },
    ready: { cls: 'b-bull', label: 'TRAINED & READY' },
    untrained: { cls: 'b-warn', label: 'UNTRAINED' },
    unavailable: { cls: 'b-neut', label: 'UNAVAILABLE' },
  };
  const artifactState = (exists: unknown): { label: string; cls: string } =>
    exists === true
      ? { label: 'Loaded', cls: 'text-[var(--ds-bull)]' }
      : exists === false
        ? { label: 'Missing', cls: 'text-[var(--ds-bear)]' }
        : { label: '—', cls: 'muted' };

  const xgbState = artifactState(modelInfo?.artifacts?.xgb_exists);
  const lgbState = artifactState(modelInfo?.artifacts?.lgb_exists);
  const eceValue =
    predictionResult?.ece != null && Number.isFinite(Number(predictionResult.ece))
      ? Number(predictionResult.ece).toFixed(3)
      : '—';
  // Backend contract: MLPredictionResponse.bullish_pct / neutral_pct / bearish_pct (0-100).
  const predictionPct = (value: unknown): string =>
    typeof value === 'number' && Number.isFinite(value) ? `${fmtNum(value, 1)}%` : '—';
  const championModels = championInfo?.champion_models as Record<string, unknown> | undefined;
  const challengerModels = challengerInfo?.challenger_models as Record<string, unknown> | undefined;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-[var(--ds-text)]">Machine Learning Operations & Calibration</h2>
          <p className="text-xs text-[var(--ds-muted)]">
            XGBoost + LightGBM ensemble telemetry, Platt/Isotonic calibration curves, and champion/challenger tournaments
          </p>
        </div>
        <button
          type="button"
          className="btn btn-sm flex items-center gap-1.5"
          onClick={fetchMLMetadata}
          disabled={loading}
        >
          <RotateCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh Metadata</span>
        </button>
      </div>

      {failedMetadata.length > 0 && (
        <div className="p-2.5 rounded bg-[var(--ds-warn-wash)] border border-[var(--ds-warn-line)] text-xs text-[var(--ds-warn-strong)] flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          <span>
            Live ML metadata unavailable for: {failedMetadata.join(', ')}. Affected fields show — instead of stale values.
          </span>
        </div>
      )}

      {/* 1. Ensemble Metadata & Artifacts */}
      <Card title="Gradient Boosted Ensemble Architecture" meta="XGBoost + LightGBM · §10, §12">
        <div className="space-y-3 text-xs">
          <div className="grid sm:grid-cols-4 gap-3 items-center">
            <div>
              <div className="stat-l">Model State</div>
              <div className="mt-1 flex items-center gap-1.5">
                <span className={`badge ${modelStateBadge[modelState].cls} font-bold`}>
                  {modelStateBadge[modelState].label}
                </span>
              </div>
              <div className="muted text-[11px] mt-0.5">
                Version: <span className="font-mono">{modelInfo?.model_version ?? '—'}</span>
              </div>
            </div>

            <div>
              <div className="stat-l">Target Spec</div>
              <div className="num font-bold text-sm mt-0.5 font-mono">
                {targets?.target_spec_version ?? '—'}
              </div>
              <div className="muted text-[11px]">
                Default Horizon:{' '}
                <span className="font-semibold">
                  {targets?.default_horizon_minutes != null
                    ? `${targets.default_horizon_minutes}m`
                    : '—'}
                </span>
              </div>
            </div>

            <div>
              <div className="stat-l">XGBoost Artifact</div>
              <div className="num font-bold text-sm mt-0.5">
                {modelInfo?.artifacts?.xgb_size_bytes != null
                  ? `${(modelInfo.artifacts.xgb_size_bytes / 1024).toFixed(0)} KB`
                  : '—'}
              </div>
              <div className="muted text-[11px]">
                Status: <span className={`${xgbState.cls} font-semibold`}>{xgbState.label}</span>
              </div>
            </div>

            <div>
              <div className="stat-l">LightGBM Artifact</div>
              <div className="num font-bold text-sm mt-0.5">
                {modelInfo?.artifacts?.lgb_size_bytes != null
                  ? `${(modelInfo.artifacts.lgb_size_bytes / 1024).toFixed(0)} KB`
                  : '—'}
              </div>
              <div className="muted text-[11px]">
                Status: <span className={`${lgbState.cls} font-semibold`}>{lgbState.label}</span>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* 2. Live Directional Probabilities Tester */}
      <Card title="Live Multi-Class Probability Inference" meta="Direct Ensemble Probe">
        <div className="space-y-3 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <div className="seg" role="group" aria-label="Symbol">
                {['NIFTY', 'BANKNIFTY'].map((s) => (
                  <button
                    key={s}
                    type="button"
                    className="seg-btn text-xs"
                    data-active={testSymbol === s}
                    onClick={() => setTestSymbol(s)}
                  >
                    {s}
                  </button>
                ))}
              </div>

              <div className="seg" role="group" aria-label="Horizon">
                {[15, 30, 60, 240].map((h) => (
                  <button
                    key={h}
                    type="button"
                    className="seg-btn text-xs"
                    data-active={testHorizon === h}
                    onClick={() => setTestHorizon(h)}
                  >
                    {h}m
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                className="btn btn-sm"
                disabled={settling}
                onClick={handleRunSettlement}
              >
                <span>{settling ? 'Settling…' : 'Trigger Settle'}</span>
              </button>
              <button
                type="button"
                className="btn btn-sm btn-primary flex items-center gap-1.5"
                disabled={predicting}
                onClick={handleTestPredict}
              >
                <Play className={`w-3.5 h-3.5 ${predicting ? 'animate-spin' : ''}`} />
                <span>{predicting ? 'Evaluating…' : 'Predict Probabilities'}</span>
              </button>
            </div>
          </div>

          {settleMsg && (
            <div
              className={`p-2 rounded border text-xs ${
                settleMsg.type === 'success'
                  ? 'bg-[var(--ds-bull-wash)] border-[var(--ds-bull-line)] text-[var(--ds-bull-strong)]'
                  : 'bg-[var(--ds-bear-wash)] border-[var(--ds-bear-line)] text-[var(--ds-bear-strong)]'
              }`}
            >
              {settleMsg.text}
            </div>
          )}

          {predictError && (
            <div className="p-2 rounded bg-[var(--ds-bear-wash)] border border-[var(--ds-bear-line)] text-xs text-[var(--ds-bear-strong)]">
              {predictError}
            </div>
          )}

          {predictionResult && (
            <div className="space-y-3 pt-2">
              {/* Probabilities Ribbon */}
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="p-2.5 rounded bg-[var(--ds-bear-wash)] border border-[var(--ds-bear-line)]">
                  <div className="text-[10px] text-[var(--ds-bear)] font-semibold uppercase">Bearish Prob</div>
                  <div className="num font-bold text-base mt-1 text-[var(--ds-bear)]">
                    {predictionPct(predictionResult.bearish_pct)}
                  </div>
                </div>

                <div className="p-2.5 rounded bg-[var(--ds-surface-elevated)] border border-[var(--ds-border)]">
                  <div className="text-[10px] muted font-semibold uppercase">Neutral Prob</div>
                  <div className="num font-bold text-base mt-1">
                    {predictionPct(predictionResult.neutral_pct)}
                  </div>
                </div>

                <div className="p-2.5 rounded bg-[var(--ds-bull-wash)] border border-[var(--ds-bull-line)]">
                  <div className="text-[10px] text-[var(--ds-bull)] font-semibold uppercase">Bullish Prob</div>
                  <div className="num font-bold text-base mt-1 text-[var(--ds-bull)]">
                    {predictionPct(predictionResult.bullish_pct)}
                  </div>
                </div>
              </div>

              {/* Calibration Metadata */}
              <div className="p-2.5 bg-[var(--ds-surface-elevated)] rounded border border-[var(--ds-border)] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span
                    className={`badge text-[10px] ${
                      predictionResult.calibrated === true
                        ? 'b-bull'
                        : predictionResult.calibrated === false
                          ? 'b-warn'
                          : 'b-neut'
                    }`}
                  >
                    {predictionResult.calibrated === true
                      ? 'CALIBRATED'
                      : predictionResult.calibrated === false
                        ? 'RAW / UNCALIBRATED'
                        : 'CALIBRATION UNKNOWN'}
                  </span>
                  <span className="muted text-[11px]">
                    Model source: {predictionResult.model_source ?? '—'}
                  </span>
                </div>
                <div className="num text-[11px] muted">
                  ECE: {eceValue}
                </div>
              </div>
            </div>
          )}
        </div>
      </Card>

      {/* 3. Champion vs Challenger Tournament */}
      <div className="grid md:grid-cols-2 gap-4">
        {/* Production Champion */}
        <Card title="Production Champion Model" meta="Live Inference Pipeline">
          <div className="space-y-3 text-xs">
            <div className="flex items-center gap-2 text-[var(--ds-bull)] font-semibold">
              <Trophy className="w-4 h-4" />
              <span>Active Production Champion</span>
            </div>
            <p className="muted leading-relaxed">
              Receives 100% of live trading signal traffic. Protected by strict shadow evaluation gates before promotion.
            </p>
            <div className="p-2.5 bg-[var(--ds-surface-elevated)] rounded border border-[var(--ds-border)] font-mono text-[11px]">
              {championModels && Object.keys(championModels).length > 0 ? (
                <pre>{JSON.stringify(championModels, null, 2)}</pre>
              ) : (
                <p className="muted" style={{ margin: 0 }}>
                  No champion registry reported by the backend.
                </p>
              )}
            </div>
          </div>
        </Card>

        {/* Active Challengers */}
        <Card title="Challenger Models in Shadow Arena" meta="Off-Path Validation">
          <div className="space-y-3 text-xs">
            <div className="flex items-center gap-2 text-[var(--ds-info)] font-semibold">
              <Swords className="w-4 h-4" />
              <span>Shadow Tournament Registrations</span>
            </div>
            <p className="muted leading-relaxed">
              Evaluating live market ticks in shadow mode without impacting execution. Promoted when Brier score beats champion for 14 consecutive sessions.
            </p>
            <div className="p-2.5 bg-[var(--ds-surface-elevated)] rounded border border-[var(--ds-border)] font-mono text-[11px] max-h-40 overflow-y-auto">
              {challengerModels && Object.keys(challengerModels).length > 0 ? (
                <pre>{JSON.stringify(challengerModels, null, 2)}</pre>
              ) : (
                <p className="muted" style={{ margin: 0 }}>
                  No challenger registrations reported by the backend.
                </p>
              )}
            </div>
          </div>
        </Card>
      </div>

      {/* 4. Probability Calibration Inspector */}
      <Card title="Reliability Curve & Calibration Bins" meta="Endpoint /api/v1/ml/calibration">
        <div className="space-y-3 text-xs">
          <div className="flex items-center justify-between">
            <p className="muted">
              Compares predicted probabilistic confidence against realized empirical frequencies across probability bins [0.0 - 1.0].
            </p>
            <div className="flex items-center gap-2">
              <select
                className="input input-sm text-xs"
                value={calibSymbol}
                onChange={(e) => setCalibSymbol(e.target.value)}
              >
                <option value="NIFTY">NIFTY</option>
                <option value="BANKNIFTY">BANKNIFTY</option>
              </select>
              <select
                className="input input-sm text-xs"
                value={calibHorizon}
                onChange={(e) => setCalibHorizon(Number(e.target.value))}
              >
                <option value={15}>15m</option>
                <option value={30}>30m</option>
                <option value={60}>60m</option>
                <option value={240}>240m</option>
              </select>
            </div>
          </div>

          {calibData ? (
            <div className="p-3 bg-[var(--ds-surface-elevated)] rounded border border-[var(--ds-border)] space-y-2">
              <div className="flex justify-between items-center text-[11px]">
                <span className="font-semibold text-[var(--ds-text)]">Calibration Telemetry</span>
                <span className="badge b-neut text-[10px]">
                  SPEC {calibData.target_spec_version ?? '—'}
                </span>
              </div>
              {calibData.overall?.n != null && (
                <div className="text-[11px] muted">
                  Settled samples: {calibData.overall.n} · overall hit rate:{' '}
                  {calibData.overall.hit_rate != null
                    ? `${(Number(calibData.overall.hit_rate) * 100).toFixed(1)}%`
                    : '—'}
                </div>
              )}
              <div className="font-mono text-[11px] max-h-48 overflow-y-auto p-2 bg-[var(--ds-surface)] rounded border border-[var(--ds-border)]">
                <pre>{JSON.stringify(calibData, null, 2)}</pre>
              </div>
            </div>
          ) : calibError ? (
            <div className="p-3 text-xs text-[var(--ds-bear-strong)] bg-[var(--ds-bear-wash)] border border-[var(--ds-bear-line)] rounded">
              Calibration data unavailable — {calibError}
            </div>
          ) : (
            <div className="p-4 text-center muted text-xs">
              {calibLoading ? 'Loading calibration curve…' : 'No calibration dataset found for selected parameters.'}
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
