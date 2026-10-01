'use client';

import { useState } from 'react';
import { DEFAULT_PAP_QUERY, usePapResearch, type PapResearchQuery } from '@/hooks/usePapResearch';
import type { PapGroupedRow } from '@/lib/api/pap';
import { PAP_UNAVAILABLE_LABEL, isAll } from '@/lib/pap';
import { PapChartPanel } from './PapChartPanel';

function num(v: unknown): string {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(2) : '—';
}

function Metric({ label, value, title }: { label: string; value: unknown; title?: string }) {
  return (
    <span className="stat-chip" title={title}>
      {label} <b>{num(value)}</b>
    </span>
  );
}

function GroupTable({ rows, idLabel }: { rows: PapGroupedRow[]; idLabel: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-xs">
        <thead>
          <tr className="card-meta">
            <th>{idLabel}</th>
            <th>Samples</th>
            <th>Bal. acc</th>
            <th>Macro F1</th>
            <th>Brier</th>
            <th>UP prec</th>
            <th>DOWN prec</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name} data-testid={`pap-group-${r.name}`}>
              <td className="font-medium">{r.name}</td>
              <td className="num">{r.n.toLocaleString('en-IN')}</td>
              <td className="num">{r.balanced_accuracy ?? '—'}</td>
              <td className="num">{r.macro_f1 ?? '—'}</td>
              <td className="num">{r.brier ?? '—'}</td>
              <td className="num">{r.up_precision ?? '—'}</td>
              <td className="num">{r.down_precision ?? '—'}</td>
              <td>
                <span className={`badge ${r.status === 'OK' ? 'b-bull' : 'b-warn'}`}>{r.status}</span>
              </td>
            </tr>
          ))}
          {rows.length === 0 ? (
            <tr>
              <td colSpan={8} className="sg-empty">
                No grouped rows — {PAP_UNAVAILABLE_LABEL} for this slice.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

export function PapResearchView() {
  const [query, setQuery] = useState<PapResearchQuery>(DEFAULT_PAP_QUERY);
  const r = usePapResearch(query);
  const set = (patch: Partial<PapResearchQuery>) => setQuery((q) => ({ ...q, ...patch }));

  const summary = r.summary;
  const metrics = (summary?.metrics ?? {}) as Record<string, unknown>;
  const baseline = (summary?.baseline ?? {}) as Record<string, unknown>;
  const lift = (summary?.lift ?? {}) as Record<string, unknown>;
  const wf = summary?.walk_forward;

  return (
    <div className="flex flex-col gap-3">
      <section className="ds-commandbar" aria-label="PAP research filters">
        <div className="ds-title">
          <h2>PAP Research</h2>
          <span className="card-meta">out-of-sample validation</span>
        </div>
        <div className="ds-filters">
          <label className="seg" title="Instrument">
            {['ALL', 'NIFTY', 'BANKNIFTY', 'SENSEX'].map((o) => (
              <button key={o} type="button" className="seg-btn" data-active={query.instrument === o} onClick={() => set({ instrument: o })}>
                {o}
              </button>
            ))}
          </label>
          <label className="seg" title="Horizon">
            {['ALL', '3M', '5M', '10M'].map((o) => (
              <button key={o} type="button" className="seg-btn" data-active={query.horizon === o} onClick={() => set({ horizon: o })}>
                {o}
              </button>
            ))}
          </label>
          <label className="seg" title="Outcome filter">
            {['ALL', 'correct', 'incorrect'].map((o) => (
              <button key={o} type="button" className="seg-btn" data-active={query.outcome === o} onClick={() => set({ outcome: o })}>
                {o}
              </button>
            ))}
          </label>
          <label className="seg" title="Prediction filter">
            {['ALL', 'UP', 'DOWN', 'NEUTRAL'].map((o) => (
              <button key={o} type="button" className="seg-btn" data-active={query.prediction === o} onClick={() => set({ prediction: o })}>
                {o}
              </button>
            ))}
          </label>
          <button type="button" className="btn" disabled={r.refreshing} onClick={() => void r.refresh()}>
            {r.refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </section>

      {r.error ? <p className="sg-err">{r.error}</p> : null}
      {r.loading ? <p className="sg-empty">Loading PAP research…</p> : null}

      <section className="card" aria-label="Predictive performance">
        <div className="card-hd">
          <h3 className="card-title">Predictive performance</h3>
          <span className="card-meta num">n = {summary?.n ?? 0}</span>
        </div>
        <div className="card-bd">
          {summary?.status === 'INSUFFICIENT_SAMPLE' ? (
            <p className="sg-empty" data-testid="pap-insufficient">
              INSUFFICIENT SAMPLE — {summary.reason}
            </p>
          ) : (
            <div className="flex flex-col gap-2" data-testid="pap-performance">
              <div className="stat-chips">
                <Metric label="bal. acc" value={metrics.balanced_accuracy} />
                <Metric label="macro F1" value={metrics.macro_f1} />
                <Metric label="brier" value={metrics.brier} />
                <Metric label="cal. err" value={metrics.calibration_error} />
                <Metric label="UP prec" value={metrics.up_precision} />
                <Metric label="DOWN prec" value={metrics.down_precision} />
                <Metric label="NEU prec" value={metrics.neutral_precision} />
              </div>
              <div className="sg-kvlist">
                <div className="sg-kv">
                  <span className="l">Balanced accuracy — baseline</span>
                  <span className="v">{num(baseline.balanced_accuracy)}</span>
                </div>
                <div className="sg-kv">
                  <span className="l">Balanced accuracy — PAP</span>
                  <span className="v">{num(metrics.balanced_accuracy)}</span>
                </div>
                <div className="sg-kv">
                  <span className="l">Lift (prediction improvement, not profit)</span>
                  <span className="v" data-testid="pap-lift">
                    {typeof lift.balanced_accuracy === 'number'
                      ? `${lift.balanced_accuracy >= 0 ? '+' : ''}${Number(lift.balanced_accuracy).toFixed(2)}`
                      : '—'}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="card" aria-label="Walk-forward validation">
        <div className="card-hd">
          <h3 className="card-title">Walk-forward validation</h3>
          {wf ? (
            <span
              className={`badge ${wf.status === 'PASS' ? 'b-bull' : wf.status === 'FAIL' ? 'b-bear' : 'b-warn'}`}
              data-testid="pap-walkforward"
            >
              {wf.status}
            </span>
          ) : null}
        </div>
        <div className="card-bd">
          {!wf || wf.folds.length === 0 ? (
            <p className="sg-empty">INSUFFICIENT SAMPLE — {wf?.reason ?? 'no folds evaluated.'}</p>
          ) : (
            <>
              <div className="flex flex-wrap gap-1.5" data-testid="pap-folds">
                {wf.folds.map((f) => (
                  <span key={f.fold} className={`badge ${f.positive ? 'b-bull' : 'b-bear'}`} title={`Fold ${f.fold} · n=${f.n} · uplift ${f.uplift}`}>
                    F{f.fold} {f.positive ? '✓' : '✗'} {f.uplift >= 0 ? '+' : ''}{f.uplift}
                  </span>
                ))}
              </div>
              <div className="sg-kvlist mt-2">
                <div className="sg-kv">
                  <span className="l">Positive folds</span>
                  <span className="v">{wf.positive_folds}</span>
                </div>
                <div className="sg-kv">
                  <span className="l">Mean uplift</span>
                  <span className="v">{wf.mean_uplift !== undefined ? `${wf.mean_uplift >= 0 ? '+' : ''}${wf.mean_uplift}` : '—'}</span>
                </div>
                <div className="sg-kv">
                  <span className="l">95% CI</span>
                  <span className="v">{wf.confidence_interval ? `[${wf.confidence_interval[0]}, ${wf.confidence_interval[1]}]` : '—'}</span>
                </div>
              </div>
              {wf.reason ? <p className="sg-note mt-2">{wf.reason}</p> : null}
              <p className="sg-note">Verdict evaluated server-side against pre-registered criteria — never computed in the browser.</p>
            </>
          )}
        </div>
      </section>

      <section className="card" aria-label="Probability calibration">
        <div className="card-hd">
          <h3 className="card-title">Probability calibration</h3>
          <span className="card-meta">predicted vs observed</span>
        </div>
        <div className="card-bd">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-xs" data-testid="pap-calibration">
              <thead>
                <tr className="card-meta">
                  <th>Bucket</th>
                  <th>n</th>
                  <th>Predicted</th>
                  <th>Observed</th>
                  <th>Error</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {(r.calibration?.buckets ?? []).map((b) => (
                  <tr key={b.bucket}>
                    <td className="font-medium">{b.bucket}</td>
                    <td className="num">{b.n}</td>
                    <td className="num">{b.predicted !== null ? `${b.predicted}%` : '—'}</td>
                    <td className="num">{b.observed !== null ? `${b.observed}%` : '—'}</td>
                    <td className="num">{b.error !== null ? `${b.error}%` : '—'}</td>
                    <td>
                      <span className={`badge ${b.status === 'OK' ? 'b-bull' : 'b-warn'}`}>{b.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="card" aria-label="Prediction versus actual">
        <div className="card-hd">
          <h3 className="card-title">Prediction vs actual</h3>
          <span className="card-meta num">{r.predictionCount} rows</span>
        </div>
        <div className="card-bd">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-xs" data-testid="pap-predictions">
              <thead>
                <tr className="card-meta">
                  <th>Time</th>
                  <th>Inst</th>
                  <th>Hor</th>
                  <th>P(UP)</th>
                  <th>P(NEU)</th>
                  <th>P(DOWN)</th>
                  <th>Pred</th>
                  <th>Actual</th>
                  <th>✓</th>
                  <th>Δ%</th>
                </tr>
              </thead>
              <tbody>
                {r.predictions.map((p, i) => (
                  <tr key={`${p.time}-${i}`}>
                    <td className="mono">{p.time ? new Date(p.time).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '—'}</td>
                    <td>{p.instrument}</td>
                    <td>{p.horizon ?? '—'}</td>
                    <td className="num">{p.p_up}%</td>
                    <td className="num">{p.p_neutral}%</td>
                    <td className="num">{p.p_down}%</td>
                    <td>{p.prediction ?? '—'}</td>
                    <td>{p.actual ?? '—'}</td>
                    <td>{p.correct === null ? '—' : p.correct ? '✓' : '✗'}</td>
                    <td className="num">{p.price_change_pct !== null ? `${p.price_change_pct >= 0 ? '+' : ''}${p.price_change_pct}%` : '—'}</td>
                  </tr>
                ))}
                {r.predictions.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="sg-empty">
                      No predictions for this slice — adjust filters or settle more rows.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <PapChartPanel instrument={isAll(query.instrument) ? 'NIFTY' : query.instrument} horizon={isAll(query.horizon) ? 'ALL' : query.horizon} />

      <div className="grid gap-3 lg:grid-cols-2">
        <section className="card" aria-label="Performance by regime">
          <div className="card-hd">
            <h3 className="card-title">Performance by regime</h3>
          </div>
          <div className="card-bd">
            <GroupTable rows={r.regimes} idLabel="Regime" />
          </div>
        </section>
        <section className="card" aria-label="Performance by session">
          <div className="card-hd">
            <h3 className="card-title">Performance by session</h3>
          </div>
          <div className="card-bd">
            <GroupTable rows={r.sessions} idLabel="Session" />
          </div>
        </section>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <section className="card" aria-label="Feature ablation">
          <div className="card-hd">
            <h3 className="card-title">Feature ablation</h3>
            <span className="badge b-warn" data-testid="pap-ablation">NOT AVAILABLE</span>
          </div>
          <div className="card-bd">
            <p className="sg-empty">{r.ablation?.reason ?? 'No ablation experiment has been executed.'}</p>
          </div>
        </section>
        <section className="card" aria-label="Cost tradability">
          <div className="card-hd">
            <h3 className="card-title">Tradability</h3>
            <span className="badge b-warn" data-testid="pap-tradability">NOT AVAILABLE</span>
          </div>
          <div className="card-bd">
            <p className="sg-empty">
              {typeof r.tradability?.reason === 'string'
                ? r.tradability.reason
                : 'PAP predicts index direction — option-level expected value and cost-adjusted expectancy are separate stages.'}
            </p>
            <p className="sg-note mt-2">
              PAP UP is not a buy call and PAP DOWN is not a buy put. Index prediction ≠ option profit.
            </p>
          </div>
        </section>
      </div>

      <section className="card" aria-label="PAP status">
        <div className="card-hd">
          <h3 className="card-title">PAP status</h3>
        </div>
        <div className="card-bd">
          <div className="stat-chips">
            <span className="stat-chip">shadow <b>ACTIVE</b></span>
            <span className="stat-chip">execution <b>DISABLED</b></span>
            <span className="stat-chip">validation <b>{wf?.status ?? '—'}</b></span>
            <span className="stat-chip">ledger <b>{summary?.ledger ? `${summary.ledger.settled}/${summary.ledger.total} settled` : '—'}</b></span>
          </div>
          <p className="sg-note mt-2">
            Live PAP answers what the model predicts now; research answers whether it has worked out-of-sample.
            PAP research is never live-trading authority.
          </p>
        </div>
      </section>
    </div>
  );
}
