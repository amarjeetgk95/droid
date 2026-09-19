'use client';

import { useCallback, useState } from 'react';
import { useToast } from '@/components/ui/toast';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { fmtLabNum, fmtLabTime } from '@/lib/labDesk';
import { getObj, pickNum, pickStr } from '@/lib/signalsNormalize';
import { toNumber } from '@/lib/coerce';
import type { useResearchLab } from '@/hooks/useResearchLab';

type Lab = ReturnType<typeof useResearchLab>;

export function ExperimentsPanel({ lab }: { lab: Lab }) {
  const { push } = useToast();
  const [expForm, setExpForm] = useState({ indicator_id: '', timeframe: '5m', horizon_candles: '5', stride: '5' });
  const [confirmExp, setConfirmExp] = useState(false);
  const [snapForm, setSnapForm] = useState({ timeframe: '5m', price: '', regime: '' });
  const [annForm, setAnnForm] = useState({ title: '', notes: '' });

  const handleRun = useCallback(async () => {
    if (!expForm.indicator_id.trim()) {
      push('error', 'Pick an indicator to run the experiment.');
      return;
    }
    const res = await lab.runExperiment({
      indicator_id: expForm.indicator_id.trim(),
      instrument: lab.apiInstrument,
      timeframe: expForm.timeframe,
      horizon_candles: toNumber(expForm.horizon_candles, { rejectBlankString: true }) ?? 5,
      stride: toNumber(expForm.stride, { rejectBlankString: true }) ?? 5,
    });
    push(res.ok ? 'success' : 'error', res.message);
    setConfirmExp(false);
  }, [expForm, lab, push]);

  const handleSnapshot = useCallback(async () => {
    const price = toNumber(snapForm.price, { rejectBlankString: true });
    if (price === null) {
      push('error', 'Snapshot price is required.');
      return;
    }
    const res = await lab.createSnapshot({
      instrument: lab.apiInstrument,
      timeframe: snapForm.timeframe,
      price,
      regime: snapForm.regime.trim() || undefined,
      features: {},
    });
    push(res.ok ? 'success' : 'error', res.message);
  }, [snapForm, lab, push]);

  const handleAnnotation = useCallback(async () => {
    if (!annForm.title.trim()) {
      push('error', 'Annotation title is required.');
      return;
    }
    const res = await lab.createAnnotation({
      annotation_id: '',
      instrument: lab.apiInstrument,
      timeframe: '5m',
      timestamp: new Date().toISOString(),
      title: annForm.title.trim(),
      notes: annForm.notes.trim(),
    });
    push(res.ok ? 'success' : 'error', res.message);
    if (res.ok) setAnnForm({ title: '', notes: '' });
  }, [annForm, lab, push]);

  const expObj = lab.experiment ? getObj(lab.experiment) : null;
  const runObj = expObj ? getObj(expObj.run) : null;
  const reportObj = expObj ? getObj(expObj.report) : null;

  return (
    <div className="flex flex-col gap-3">
      <section className="card" aria-label="Run experiment">
        <div className="card-hd"><h3 className="card-title">Offline validation · Cheap Gate</h3><span className="card-meta num">{lab.apiInstrument}</span></div>
        <div className="card-bd">
          <p className="sg-note">Runs the Cheap Validation Gate over ≥35 historical candles. Read-heavy backtest — confirm before running.</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="field"><span className="field-l">indicator</span>
              <select className="input mono" value={expForm.indicator_id} onChange={(e) => setExpForm((f) => ({ ...f, indicator_id: e.target.value }))}>
                <option value="">Select…</option>
                {lab.indicators.map((i) => <option key={i.id} value={i.id}>{i.id}</option>)}
              </select>
            </label>
            <label className="field"><span className="field-l">timeframe</span>
              <select className="input" value={expForm.timeframe} onChange={(e) => setExpForm((f) => ({ ...f, timeframe: e.target.value }))}>
                <option>1m</option><option>5m</option><option>15m</option>
              </select>
            </label>
            <label className="field"><span className="field-l">horizon candles (1–50)</span><input className="input num" value={expForm.horizon_candles} onChange={(e) => setExpForm((f) => ({ ...f, horizon_candles: e.target.value }))} /></label>
            <label className="field"><span className="field-l">stride (1–20)</span><input className="input num" value={expForm.stride} onChange={(e) => setExpForm((f) => ({ ...f, stride: e.target.value }))} /></label>
          </div>
          <div className="ds-filters">
            <button type="button" className="btn btn-primary" disabled={lab.expBusy} onClick={() => setConfirmExp(true)}>
              {lab.expBusy ? 'Running…' : 'Run experiment'}
            </button>
          </div>
          {lab.expError ? <p className="sg-err">{lab.expError}</p> : null}
          {expObj ? (
            <div className="mt-3 border-t border-border-subtle pt-3">
              <div className="sg-kvlist">
                <div className="sg-kv"><span className="l">samples</span><span className="v">{String(pickNum(runObj ?? {}, 'sample_count') ?? '—')}</span></div>
                <div className="sg-kv"><span className="l">status</span><span className="v">{pickStr(runObj ?? {}, 'status') ?? '—'}</span></div>
                <div className="sg-kv"><span className="l">accuracy</span><span className="v">{fmtLabNum(pickNum(reportObj ?? {}, 'accuracy'))}</span></div>
                <div className="sg-kv"><span className="l">excess accuracy</span><span className="v">{fmtLabNum(pickNum(reportObj ?? {}, 'excess_accuracy'))}</span></div>
                <div className="sg-kv"><span className="l">significant</span><span className="v">{String(reportObj?.is_statistically_significant ?? '—')}</span></div>
              </div>
            </div>
          ) : null}
        </div>
      </section>

      <div className="grid gap-3 lg:grid-cols-2">
        <section className="card" aria-label="Snapshots">
          <div className="card-hd"><h3 className="card-title">Snapshots</h3><span className="card-meta num">{lab.snapshots.length} cached</span></div>
          <div className="card-bd">
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="field"><span className="field-l">timeframe</span><input className="input" value={snapForm.timeframe} onChange={(e) => setSnapForm((f) => ({ ...f, timeframe: e.target.value }))} /></label>
              <label className="field"><span className="field-l">price</span><input className="input num" value={snapForm.price} onChange={(e) => setSnapForm((f) => ({ ...f, price: e.target.value }))} placeholder="24900" /></label>
              <label className="field"><span className="field-l">regime</span><input className="input" value={snapForm.regime} onChange={(e) => setSnapForm((f) => ({ ...f, regime: e.target.value }))} placeholder="TRENDING_BULLISH" /></label>
            </div>
            <div className="ds-filters"><button type="button" className="btn btn-primary" disabled={lab.mutating} onClick={() => void handleSnapshot()}>Save snapshot</button></div>
            {lab.snapError ? <p className="sg-err">{lab.snapError}</p> : null}
            {lab.snapshots.length === 0 && !lab.snapError ? <p className="sg-empty">No snapshots cached this session.</p> : null}
            {lab.snapshots.length > 0 ? (
              <div className="tbl-scroll">
                <table className="sg-table">
                  <thead><tr><th>Time</th><th>ID</th><th className="r">Price</th><th>Regime</th></tr></thead>
                  <tbody>
                    {lab.snapshots.slice(0, 10).map((s) => (
                      <tr key={s.id}>
                        <td className="num">{fmtLabTime(s.timeMs)}</td>
                        <td><span className="sg-sym">{s.id.slice(0, 12)}</span></td>
                        <td className="r num">{s.price !== null ? fmtLabNum(s.price) : '—'}</td>
                        <td><span className="sg-tag neut">{s.regime ?? '—'}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        </section>

        <section className="card" aria-label="Annotations">
          <div className="card-hd"><h3 className="card-title">Annotations</h3><span className="card-meta num">{lab.annotations.length} cached</span></div>
          <div className="card-bd">
            <label className="field"><span className="field-l">title</span><input className="input" value={annForm.title} onChange={(e) => setAnnForm((f) => ({ ...f, title: e.target.value }))} placeholder="Breakout retest" /></label>
            <label className="field"><span className="field-l">notes</span><input className="input" value={annForm.notes} onChange={(e) => setAnnForm((f) => ({ ...f, notes: e.target.value }))} placeholder="Qualitative note" /></label>
            <div className="ds-filters"><button type="button" className="btn btn-primary" disabled={lab.mutating} onClick={() => void handleAnnotation()}>Add annotation</button></div>
            {lab.annError ? <p className="sg-err">{lab.annError}</p> : null}
            {lab.annotations.length === 0 && !lab.annError ? <p className="sg-empty">No annotations recorded yet.</p> : null}
            {lab.annotations.slice(0, 8).map((a) => (
              <div key={a.id} className="sg-kv">
                <span className="l">{fmtLabTime(a.timeMs)}</span>
                <span className="v">{a.title}</span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <ConfirmDialog
        open={confirmExp}
        onOpenChange={(o) => setConfirmExp(o)}
        tone="primary"
        confirmLabel="Run backtest"
        busy={lab.expBusy}
        title={`Run validation for ${expForm.indicator_id || 'indicator'}?`}
        description="Backtests over historical candles. Heavy compute — runs once on confirm."
        onConfirm={handleRun}
      />
    </div>
  );
}
