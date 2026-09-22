'use client';

import { useCallback, useState } from 'react';
import { useToast } from '@/components/ui/toast';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { ForecastHorizonCard } from '@/components/dashboard/ForecastHorizonCard';
import { FORECAST_HORIZONS } from '@/lib/forecastBoard';
import { fmtLabNum, fmtLabTime, tagClass, directionToneOf } from '@/lib/labDesk';
import { getObj, pickNum, pickStr } from '@/lib/signalsNormalize';
import { toNumber } from '@/lib/coerce';
import type { useResearchLab } from '@/hooks/useResearchLab';

type Lab = ReturnType<typeof useResearchLab>;

function KvList({ data, keys }: { data: Record<string, unknown> | null; keys?: string[] }) {
  if (!data) return <p className="sg-empty">No data returned.</p>;
  const entries = Object.entries(data).filter(([, v]) => {
    const t = typeof v;
    return t === 'number' || t === 'string' || t === 'boolean';
  });
  const scoped = keys ? entries.filter(([k]) => keys.includes(k)) : entries;
  if (scoped.length === 0) return <p className="sg-empty">No scalar readouts in this payload.</p>;
  return (
    <div className="sg-kvlist">
      {scoped.slice(0, 10).map(([k, v]) => (
        <div key={k} className="sg-kv">
          <span className="l">{k.replace(/_/g, ' ')}</span>
          <span className="v">{typeof v === 'number' ? fmtLabNum(v) : String(v)}</span>
        </div>
      ))}
    </div>
  );
}

export function ForecastPanel({ lab }: { lab: Lab }) {
  const { push } = useToast();
  const [timeframe, setTimeframe] = useState('5m');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [confirmMeasureId, setConfirmMeasureId] = useState<string | null>(null);
  const [recordOpen, setRecordOpen] = useState(false);
  const [form, setForm] = useState({ indicator_id: '', direction: 'BULLISH', score: '', confidence: '', current_price: '' });

  const handleGenerate = useCallback(async () => {
    try {
      await lab.board.refresh({ record: true });
      push('success', 'Forecast regenerated and recorded.');
    } catch {
      push('error', 'Forecast generation failed.');
    }
  }, [lab, push]);

  const handleOpen = useCallback(async (id: string) => {
    setSelectedId(id);
    await lab.openPrediction(id);
  }, [lab]);

  const handleMeasure = useCallback(async () => {
    if (!confirmMeasureId) return;
    const res = await lab.measurePrediction(confirmMeasureId);
    push(res.ok ? 'success' : 'error', res.message);
    setConfirmMeasureId(null);
  }, [confirmMeasureId, lab, push]);

  const handleRecord = useCallback(async () => {
    const price = toNumber(form.current_price, { rejectBlankString: true });
    const score = toNumber(form.score, { rejectBlankString: true });
    const confPct = toNumber(form.confidence, { rejectBlankString: true });
    if (!form.indicator_id.trim()) {
      push('error', 'indicator_id is required.');
      return;
    }
    if (price === null) {
      push('error', 'current_price is required.');
      return;
    }
    if (score === null) {
      push('error', 'score is required (enter a number between -100 and 100).');
      return;
    }
    if (confPct === null) {
      push('error', 'confidence % is required (enter a number between 0 and 100).');
      return;
    }
    const pid = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `pred_${Date.now()}`;
    const res = await lab.createPrediction({
      prediction_id: pid,
      indicator_id: form.indicator_id.trim(),
      indicator_version: 'v1',
      instrument: lab.apiInstrument,
      timeframe: '5m',
      timestamp: new Date().toISOString(),
      current_price: price,
      direction: form.direction,
      score,
      confidence: Math.max(0, Math.min(1, confPct / 100)),
      horizon_candles: 5,
    });
    push(res.ok ? 'success' : 'error', res.message);
    if (res.ok) setRecordOpen(false);
  }, [form, lab, push]);

  const healthObj = getObj(lab.health);
  const configObj = getObj(lab.config);

  return (
    <div className="flex flex-col gap-3">
      <section className="card" aria-label="Tactical bias">
        <div className="card-hd">
          <h3 className="card-title">Tactical bias · 1m–60m</h3>
          <span className="card-meta">{lab.apiInstrument}</span>
        </div>
        <div className="card-bd flex flex-col gap-3">
          <div className="ds-filters">
            <span className="seg">
              {['1m', '5m', '15m'].map((tf) => (
                <button key={tf} type="button" className="seg-btn" data-active={timeframe === tf} onClick={() => { setTimeframe(tf); void lab.loadChart(tf); }}>
                  {tf}
                </button>
              ))}
            </span>
            <button type="button" className="btn btn-primary" disabled={lab.board.refreshing} onClick={() => void handleGenerate()}>
              {lab.board.refreshing ? 'Generating…' : 'Generate + record'}
            </button>
            <button type="button" className="btn" onClick={() => setRecordOpen(true)}>
              Record prediction
            </button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {FORECAST_HORIZONS.map((h) => (
              <ForecastHorizonCard
                key={h}
                horizon={h}
                forecast={(lab.board.forecasts as Record<string, never>)[h] as never}
                error={(lab.board.errors as Record<string, string>)[h]}
                loading={lab.board.loading}
              />
            ))}
          </div>
        </div>
      </section>

      <div className="grid gap-3 lg:grid-cols-3">
        <section className="card" aria-label="Chart state">
          <div className="card-hd"><h3 className="card-title">Chart state</h3><span className="card-meta num">{timeframe}</span></div>
          <div className="card-bd">
            {lab.chartError ? <p className="sg-err">{lab.chartError}</p> : <KvList data={lab.chartState} keys={['instrument', 'timeframe', 'current_price', 'change_pct', 'candles_count']} />}
          </div>
        </section>
        <section className="card" aria-label="Features">
          <div className="card-hd"><h3 className="card-title">Features</h3></div>
          <div className="card-bd">
            {lab.chartFeatures ? <KvList data={getObj(lab.chartFeatures) ?? lab.chartFeatures as Record<string, unknown>} /> : <p className="sg-empty">No feature payload yet.</p>}
          </div>
        </section>
        <section className="card" aria-label="Options context">
          <div className="card-hd"><h3 className="card-title">Options context</h3></div>
          <div className="card-bd">
            {lab.optionsError ? <p className="sg-err">{lab.optionsError}</p> : <KvList data={lab.optionsContext} />}
          </div>
        </section>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <section className="card" aria-label="Forecast health">
          <div className="card-hd"><h3 className="card-title">Monitoring · health</h3><span className="card-meta">limit 30</span></div>
          <div className="card-bd">
            {lab.healthError ? <p className="sg-err">{lab.healthError}</p> : null}
            {!lab.health && !lab.healthError ? <p className="sg-empty">Loading forecast health…</p> : null}
            {healthObj ? (
              <div className="sg-kvlist">
                <div className="sg-kv"><span className="l">status</span><span className="v">{pickStr(healthObj, 'status') ?? '—'}</span></div>
                <div className="sg-kv"><span className="l">degraded</span><span className="v">{String(healthObj.degraded ?? '—')}</span></div>
                <div className="sg-kv"><span className="l">window</span><span className="v">{String(pickNum(healthObj, 'window') ?? '—')}</span></div>
              </div>
            ) : null}
          </div>
        </section>
        <section className="card" aria-label="Forecast config">
          <div className="card-hd"><h3 className="card-title">Monitoring · config</h3></div>
          <div className="card-bd">
            {lab.configError ? <p className="sg-err">{lab.configError}</p> : null}
            {!configObj && !lab.configError ? <p className="sg-empty">Loading forecast config…</p> : null}
            {configObj ? <KvList data={getObj(configObj.bundle)} /> : null}
          </div>
        </section>
      </div>

      <section className="card" aria-label="Prediction ledger">
        <div className="card-hd"><h3 className="card-title">Prediction ledger</h3><span className="card-meta num">{lab.predictions.length} rows</span></div>
        <div className="card-bd">
          {lab.predError ? <p className="sg-err">{lab.predError}</p> : null}
          {lab.predLoading ? <p className="sg-empty">Loading predictions…</p> : null}
          {!lab.predLoading && lab.predictions.length === 0 && !lab.predError ? (
            <p className="sg-empty">No predictions recorded for {lab.apiInstrument} yet.</p>
          ) : null}
          {lab.predictions.length > 0 ? (
            <div className="tbl-scroll">
              <table className="sg-table">
                <thead><tr><th>Time</th><th>ID</th><th>Direction</th><th className="r">Score</th><th className="r">Conf</th><th>Actions</th></tr></thead>
                <tbody>
                  {lab.predictions.slice(0, 20).map((p) => (
                    <tr key={p.id} data-active={selectedId === p.id}>
                      <td className="num">{fmtLabTime(p.timeMs)}</td>
                      <td><span className="sg-sym">{p.id.slice(0, 12)}</span><div className="sg-rownote">{p.indicatorId ?? '—'}</div></td>
                      <td><span className={`sg-tag ${tagClass(directionToneOf(p.direction))}`}>{p.direction}</span></td>
                      <td className="r num">{p.score !== null ? fmtLabNum(p.score, 1) : '—'}</td>
                      <td className="r num">{p.confidence !== null ? `${Math.round((p.confidence > 1 ? p.confidence / 100 : p.confidence) * 100)}%` : '—'}</td>
                      <td><span className="sg-actions">
                        <button type="button" className="sg-ibtn" title="View detail + outcome" onClick={() => void handleOpen(p.id)}>↗</button>
                        <button type="button" className="sg-ibtn" title="Measure outcome" onClick={() => setConfirmMeasureId(p.id)}>✓</button>
                      </span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {selectedId ? (
            <div className="mt-3 border-t border-border-subtle pt-3">
              {lab.detailLoading ? <p className="sg-empty">Loading detail…</p> : null}
              {lab.detailError ? <p className="sg-err">{lab.detailError}</p> : null}
              {lab.detail ? <KvList data={lab.detail as Record<string, unknown>} /> : null}
              {lab.outcomeError ? <p className="sg-note">{lab.outcomeError}</p> : null}
              {lab.outcome ? <KvList data={lab.outcome as Record<string, unknown>} /> : null}
            </div>
          ) : null}
        </div>
      </section>

      <ConfirmDialog
        open={confirmMeasureId !== null}
        onOpenChange={(o) => { if (!o) setConfirmMeasureId(null); }}
        tone="primary"
        confirmLabel="Measure outcome"
        busy={lab.measuring}
        title="Measure forward outcome for this prediction?"
        description="Evaluates forward candles and appends an immutable outcome record."
        onConfirm={handleMeasure}
      />

      <ConfirmDialog
        open={recordOpen}
        onOpenChange={(o) => setRecordOpen(o)}
        tone="primary"
        confirmLabel="Record immutable"
        busy={lab.mutating}
        title="Record a research prediction?"
        description="Immutable once logged — it can never be updated."
        onConfirm={handleRecord}
      />
      {recordOpen ? (
        <section className="card" aria-label="Record prediction form">
          <div className="card-bd grid gap-3 sm:grid-cols-2">
            <label className="field"><span className="field-l">indicator_id</span><input className="input mono" value={form.indicator_id} onChange={(e) => setForm((f) => ({ ...f, indicator_id: e.target.value }))} placeholder="e.g. rsi_momentum" /></label>
            <label className="field"><span className="field-l">direction</span><select className="input" value={form.direction} onChange={(e) => setForm((f) => ({ ...f, direction: e.target.value }))}><option>BULLISH</option><option>BEARISH</option><option>NEUTRAL</option></select></label>
            <label className="field"><span className="field-l">score (-100..100, required)</span><input className="input num" value={form.score} onChange={(e) => setForm((f) => ({ ...f, score: e.target.value }))} placeholder="e.g. 10" /></label>
            <label className="field"><span className="field-l">confidence % (0..100, required)</span><input className="input num" value={form.confidence} onChange={(e) => setForm((f) => ({ ...f, confidence: e.target.value }))} placeholder="e.g. 60" /></label>
            <label className="field"><span className="field-l">current_price (required)</span><input className="input num" value={form.current_price} onChange={(e) => setForm((f) => ({ ...f, current_price: e.target.value }))} placeholder="e.g. 24900" /></label>
            <p className="sg-note sm:col-span-2">
              Fields are recorded verbatim beside the prediction — blank score/confidence are rejected,
              never silently replaced. Confidence is entered as a percent (60 = 0.60 in the ledger).
            </p>
          </div>
        </section>
      ) : null}
    </div>
  );
}
