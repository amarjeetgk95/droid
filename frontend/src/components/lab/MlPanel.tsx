'use client';

import { useCallback, useState } from 'react';
import { useToast } from '@/components/ui/toast';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Meter, Stat } from '@/components/ui/desk';
import { countManifests, fmtLabNum, mlProbs, probToPct, shadowDecision, tagClass, unwrapMlData } from '@/lib/labDesk';
import { getObj, pickNum, pickStr } from '@/lib/signalsNormalize';
import { toNumber } from '@/lib/coerce';
import type { useMlDesk, useMlTrain } from '@/hooks/useMlDesk';
import type { useResearchLab } from '@/hooks/useResearchLab';

type Ml = ReturnType<typeof useMlDesk>;
type Lab = ReturnType<typeof useResearchLab>;
type Trainer = ReturnType<typeof useMlTrain>;

function Kv({ label, value }: { label: string; value: string }) {
  return (
    <div className="sg-kv">
      <span className="l">{label}</span>
      <span className="v">{value}</span>
    </div>
  );
}

export function MlPanel({ ml, lab, symbol, trainer }: { ml: Ml; lab: Lab; symbol: string; trainer?: Trainer }) {
  const { push } = useToast();
  const [confirmSettle, setConfirmSettle] = useState(false);
  const [confirmTrain, setConfirmTrain] = useState(false);
  const [settleForm, setSettleForm] = useState({ prediction_id: '', outcome_spot: '', atr_at_t: '', spot_at_t: '' });

  const probs = mlProbs(ml.prediction);
  const bullPct = probToPct(probs.bull);
  const bearPct = probToPct(probs.bear);
  const decision = shadowDecision(ml.shadow);
  const trained = pickStr(getObj(ml.modelInfo) ?? {}, 'trained', 'status');

  const handleSettle = useCallback(async () => {
    const payload = {
      prediction_id: settleForm.prediction_id.trim(),
      outcome_spot: toNumber(settleForm.outcome_spot, { rejectBlankString: true }) ?? NaN,
      atr_at_t: toNumber(settleForm.atr_at_t, { rejectBlankString: true }) ?? NaN,
      spot_at_t: toNumber(settleForm.spot_at_t, { rejectBlankString: true }) ?? NaN,
    };
    if (!payload.prediction_id) {
      push('error', 'prediction_id (UUID) is required.');
      return;
    }
    if (!Number.isFinite(payload.outcome_spot) || !Number.isFinite(payload.atr_at_t) || !Number.isFinite(payload.spot_at_t)) {
      push('error', 'outcome_spot, atr_at_t and spot_at_t must be positive numbers.');
      return;
    }
    const res = await ml.settleOutcome(payload);
    push(res.ok ? 'success' : 'error', res.message);
    if (res.ok) setConfirmSettle(false);
  }, [settleForm, ml, push]);

  const handleSettleRun = useCallback(async () => {
    const res = await ml.runSettlement(100);
    push(res.ok ? 'success' : 'error', res.message);
    setConfirmSettle(false);
  }, [ml, push]);

  const handleTrain = useCallback(async () => {
    if (!trainer) {
      push('error', 'Trainer unavailable in this build.');
      return;
    }
    push('info', 'Training needs verified feature vectors — submit via API client with ≥100 samples.');
    setConfirmTrain(false);
  }, [trainer, push]);

  const targetsObj = ml.targets ? getObj(ml.targets) : null;
  const calObj = ml.calibration ? unwrapMlData({ data: ml.calibration }) : null;

  return (
    <div className="flex flex-col gap-3">
      <p className="sg-note">
        Instrument-aware ML desk for {symbol} · prediction refreshes every 60s while the market is open. Training is heavy — typed confirmation required.
      </p>

      <div className="grid gap-3 lg:grid-cols-3">
        <section className="card" aria-label="ML prediction">
          <div className="card-hd"><h3 className="card-title">Predict · {symbol}</h3><span className="card-meta num">{ml.updatedAt ? new Date(ml.updatedAt).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '—'}</span></div>
          <div className="card-bd">
            {ml.predLoading ? <p className="sg-empty">Loading ML prediction…</p> : null}
            {ml.predError && !ml.predLoading ? <p className="sg-err">{ml.predError}</p> : null}
            {ml.prediction && !ml.predError ? (
              <>
                <div className="flex items-center justify-between gap-2">
                  <span className={`badge ${pickStr(ml.prediction, 'predicted_bias', 'bias')?.includes('BULL') ? 'b-bull' : pickStr(ml.prediction, 'predicted_bias', 'bias')?.includes('BEAR') ? 'b-bear' : 'b-neut'}`}>
                    {pickStr(ml.prediction, 'predicted_bias', 'bias') ?? '—'}
                  </span>
                  <span className="card-meta num">calibrated {String(ml.prediction.calibrated ?? '—')}</span>
                </div>
                <div className="mt-2 grid gap-2">
                  <div><div className="stat-l">Bull {bullPct !== null ? `${bullPct}%` : '—'}</div><Meter value={probs.bull} label="Bull probability" /></div>
                  <div><div className="stat-l">Bear {bearPct !== null ? `${bearPct}%` : '—'}</div><Meter value={probs.bear} label="Bear probability" /></div>
                </div>
                <div className="sg-kvlist mt-2">
                  <Kv label="confidence" value={fmtLabNum(pickNum(ml.prediction, 'confidence', 'confidence_score'))} />
                  <Kv label="horizon" value={String(pickNum(ml.prediction, 'horizon_minutes') ?? '—')} />
                  <Kv label="model" value={pickStr(ml.prediction, 'model_version') ?? '—'} />
                </div>
              </>
            ) : null}
          </div>
        </section>

        <section className="card" aria-label="Model info and regime">
          <div className="card-hd"><h3 className="card-title">Model · regime</h3></div>
          <div className="card-bd">
            {ml.modelError ? <p className="sg-err">{ml.modelError}</p> : null}
            {ml.modelInfo && !ml.modelError ? (
              <div className="sg-kvlist">
                <Kv label="trained" value={trained ?? String(getObj(ml.modelInfo)?.trained ?? '—')} />
                <Kv label="spec" value={pickStr(ml.modelInfo, 'target_spec_version') ?? '—'} />
              </div>
            ) : null}
            {ml.regimeError ? <p className="sg-err">{ml.regimeError}</p> : null}
            {ml.regime && !ml.regimeError ? (
              <div className="sg-kvlist">
                <Kv label="regime" value={pickStr(ml.regime, 'regime', 'current_regime') ?? fmtLabNum(ml.regime.regime_id)} />
                <Kv label="confidence" value={fmtLabNum(pickNum(ml.regime, 'confidence', 'probability'))} />
              </div>
            ) : null}
            {!ml.modelInfo && !ml.modelError ? <p className="sg-empty">No model metadata yet.</p> : null}
          </div>
        </section>

        <section className="card" aria-label="Manifests and shadow gate">
          <div className="card-hd"><h3 className="card-title">Manifests · shadow</h3></div>
          <div className="card-bd">
            {ml.manifestError ? <p className="sg-err">{ml.manifestError}</p> : null}
            <div className="stat-chips">
              <span className="stat-chip">challengers <b>{countManifests(ml.challenger, 'challenger_models')}</b></span>
              <span className="stat-chip">champions <b>{countManifests(ml.champion, 'champion_models')}</b></span>
            </div>
            {ml.shadowError ? <p className="sg-err">{ml.shadowError}</p> : null}
            {ml.shadow && !ml.shadowError ? (
              <p className="sg-note">Shadow decision <span className={`sg-tag ${tagClass(decision.tone)}`}>{decision.label}</span></p>
            ) : null}
            <div className="mt-2 flex gap-2">
              <Stat label="Forecasts" value={String(lab.predictions.length)} compact />
              <Stat label="Indicators" value={String(lab.indicators.length)} compact />
            </div>
          </div>
        </section>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <section className="card" aria-label="Targets and calibration">
          <div className="card-hd"><h3 className="card-title">Targets · calibration</h3></div>
          <div className="card-bd">
            {ml.targetsError ? <p className="sg-err">{ml.targetsError}</p> : null}
            {targetsObj ? (
              <div className="sg-kvlist">
                <Kv label="spec" value={pickStr(targetsObj, 'target_spec_version') ?? '—'} />
                <Kv label="default horizon" value={String(pickNum(targetsObj, 'default_horizon_minutes') ?? '—')} />
              </div>
            ) : null}
            {ml.calError ? <p className="sg-err">{ml.calError}</p> : null}
            {calObj ? (
              <div className="sg-kvlist">
                {Object.entries(calObj).slice(0, 6).map(([k, v]) => (
                  <Kv key={k} label={k.replace(/_/g, ' ')} value={typeof v === 'number' ? fmtLabNum(v) : typeof v === 'string' || typeof v === 'boolean' ? String(v) : '—'} />
                ))}
              </div>
            ) : null}
            {!targetsObj && !ml.targetsError ? <p className="sg-empty">No target specs yet.</p> : null}
          </div>
        </section>

        <section className="card" aria-label="Settle and train">
          <div className="card-hd"><h3 className="card-title">Settle · train</h3><span className="card-meta">guarded</span></div>
          <div className="card-bd">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="field"><span className="field-l">prediction_id (UUID)</span><input className="input mono" value={settleForm.prediction_id} onChange={(e) => setSettleForm((f) => ({ ...f, prediction_id: e.target.value }))} placeholder="uuid" /></label>
              <label className="field"><span className="field-l">outcome_spot</span><input className="input num" value={settleForm.outcome_spot} onChange={(e) => setSettleForm((f) => ({ ...f, outcome_spot: e.target.value }))} /></label>
              <label className="field"><span className="field-l">atr_at_t</span><input className="input num" value={settleForm.atr_at_t} onChange={(e) => setSettleForm((f) => ({ ...f, atr_at_t: e.target.value }))} /></label>
              <label className="field"><span className="field-l">spot_at_t</span><input className="input num" value={settleForm.spot_at_t} onChange={(e) => setSettleForm((f) => ({ ...f, spot_at_t: e.target.value }))} /></label>
            </div>
            <div className="ds-filters">
              <button type="button" className="btn btn-primary" disabled={ml.busy} onClick={() => setConfirmSettle(true)}>Settle…</button>
              <button type="button" className="btn btn-sell" onClick={() => setConfirmTrain(true)}>Train…</button>
              <button type="button" className="btn" disabled={ml.busy} onClick={() => void ml.refresh()}>Refresh</button>
            </div>
            <p className="sg-note">Settle appends an immutable outcome. Train rebuilds the ensemble and is heavy — type TRAIN to confirm.</p>
          </div>
        </section>
      </div>

      <ConfirmDialog
        open={confirmSettle}
        onOpenChange={(o) => setConfirmSettle(o)}
        tone="primary"
        confirmLabel="Settle outcome"
        busy={ml.busy}
        title="Settle this ML prediction?"
        description="Append-only: the outcome is recorded permanently. Or run the auto-settlement pass for due horizons."
        intentRows={[
          { label: 'Prediction', value: settleForm.prediction_id.slice(0, 12) || 'auto-run' },
          { label: 'Symbol', value: symbol },
        ]}
        onConfirm={settleForm.prediction_id.trim() ? handleSettle : handleSettleRun}
      />

      <ConfirmDialog
        open={confirmTrain}
        onOpenChange={(o) => setConfirmTrain(o)}
        tone="danger"
        confirmLabel="Train ensemble"
        busy={trainer?.busy ?? false}
        requireTypedConfirmation="TRAIN"
        title="Train the XGBoost + LightGBM ensemble?"
        description="Heavy operation over ≥100 verified samples. Type TRAIN to confirm."
        onConfirm={handleTrain}
      />
    </div>
  );
}
