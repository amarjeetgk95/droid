'use client';

import { useState } from 'react';
import { Play, Microscope } from 'lucide-react';
import type { ForwardReturnStats, HorizonStudy, PredictionStudy, PredictResponse } from '@/lib/api/indicatorResearch';
import { fmt, fmtInt, fmtPct } from '@/lib/indicatorResearch';

const HORIZON_OPTIONS = [1, 2, 3, 5, 10, 20, 50];

type Props = {
  result: PredictResponse | null;
  loading: boolean;
  error: string | null;
  onRun: (horizons: number[]) => void;
};

/**
 * Prediction analysis answers the narrow question §41 draws: after this exact
 * signal, on this instrument/timeframe/window, what did the next N bars do —
 * and how does that differ from what *every* bar did? The unconditional
 * baseline column is the whole point: a mean forward return means nothing
 * until it is compared to the market's own drift over the same sample.
 */
export function PredictionPanel({ result, loading, error, onRun }: Props) {
  const [horizons, setHorizons] = useState<number[]>([1, 5, 10, 20]);

  const toggleHorizon = (h: number) =>
    setHorizons((prev) => (prev.includes(h) ? prev.filter((x) => x !== h) : [...prev, h].sort((a, b) => a - b)));

  return (
    <div className="flex flex-col gap-3">
      <section className="card">
        <div className="card-hd">
          <h3 className="card-title">
            <Microscope size={13} className="mr-1 inline" />
            Forward-return prediction analysis
          </h3>
          <span className="card-meta">gross of costs · descriptive only</span>
        </div>
        <div className="card-bd flex flex-col gap-2">
          <p className="sg-note">
            Measures what actually happened after each signal against what happens after <i>every</i> bar. A positive
            mean means nothing on its own — only the excess over the unconditional baseline is informative, and only
            with the sample size attached. This is not a probability of profit and applies no costs.
          </p>

          <div className="flex flex-wrap items-center gap-2">
            <span className="micro-label">Horizons (bars)</span>
            <div className="flex flex-wrap gap-1">
              {HORIZON_OPTIONS.map((h) => (
                <button
                  key={h}
                  type="button"
                  className={`chip ${horizons.includes(h) ? 'is-active' : ''}`}
                  aria-pressed={horizons.includes(h)}
                  onClick={() => toggleHorizon(h)}
                >
                  {h}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="btn btn-primary ml-auto w-fit"
              disabled={loading || horizons.length === 0}
              onClick={() => onRun(horizons)}
            >
              <Play size={12} /> {loading ? 'Studying…' : 'Run study'}
            </button>
          </div>

          {error ? <p className="notice notice--down text-[11px]">{error}</p> : null}
        </div>
      </section>

      {result ? (
        <>
          <div className="notice notice--warn">
            <span className="text-[11px]">{result.disclaimer}</span>
          </div>

          {(['long', 'short'] as const).map((side) => {
            const study = result.studies?.[side];
            if (!study) return null;
            return <StudyPanel key={side} side={side} study={study} ruleSummary={result.rule_summaries?.[side] ?? null} />;
          })}
        </>
      ) : null}
    </div>
  );
}

type Study = PredictionStudy;

function StudyPanel({ side, study, ruleSummary }: { side: 'long' | 'short'; study: Study; ruleSummary: string | null }) {
  const horizonKeys = Object.keys(study.horizons ?? {});
  if (study.n_signals === 0 || horizonKeys.length === 0) {
    return (
      <section className="card">
        <div className="card-hd">
          <h3 className="card-title">{side === 'long' ? 'Long signals' : 'Short signals'}</h3>
        </div>
        <div className="card-bd">
          <p className="sg-note">{study.note ?? 'This rule produced no signals in the requested range.'}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="card">
      <div className="card-hd">
        <h3 className="card-title">{side === 'long' ? 'Long signals' : 'Short signals'}</h3>
        <span className="badge badge-sm b-warn">{study.sample_status ?? 'in_sample'}</span>
      </div>
      <div className="card-bd flex flex-col gap-2">
        <div className="sg-kvlist">
          <div className="sg-kv">
            <span className="sg-lab">Signal definition</span>
            <span className="sg-num">{ruleSummary ?? study.signal_definition}</span>
          </div>
          <div className="sg-kv">
            <span className="sg-lab">Signals / bars</span>
            <span className="sg-num num">
              {fmtInt(study.n_signals)} / {fmtInt(study.n_bars)}
            </span>
          </div>
          <div className="sg-kv">
            <span className="sg-lab">Context</span>
            <span className="sg-num">
              {String(study.instrument ?? '—')} · {String(study.timeframe ?? '—')} ·{' '}
              {study.date_range?.start ? String(study.date_range.start).slice(0, 10) : '—'} →{' '}
              {study.date_range?.end ? String(study.date_range.end).slice(0, 10) : '—'}
            </span>
          </div>
        </div>

        <div className="tbl-wrap">
          <table className="tbl tbl--zebra tbl-dense w-full">
            <thead>
              <tr>
                <th>Horizon</th>
                <th className="text-right">n</th>
                <th className="text-right" title="Mean forward return after the signal">
                  Mean after signal
                </th>
                <th className="text-right" title="Mean forward return over every bar in the same window — the baseline to beat">
                  Mean all bars
                </th>
                <th className="text-right" title="Signal mean minus unconditional mean">
                  Excess
                </th>
                <th className="text-right">Positive %</th>
                <th className="text-right">p (2-sided)</th>
                <th>Reading</th>
              </tr>
            </thead>
            <tbody>
              {horizonKeys.map((key) => {
                const h: HorizonStudy = study.horizons[key];
                const sig = h.signal;
                const base = h.unconditional;
                return (
                  <tr key={key}>
                    <td className="num">{h.horizon_bars} bars</td>
                    <td className="col-num">
                      <span title={sig.low_sample ? 'Low sample — treat as anecdote' : undefined}>{fmtInt(sig.n)}</span>
                      {sig.low_sample ? <span className="badge badge-sm b-warn ml-1">low</span> : null}
                    </td>
                    <td className={`col-num ${toneOf(sig.mean_pct)}`}>{fmtPct(sig.mean_pct, 3)}</td>
                    <td className="col-num text-ink-3">{fmtPct(base.mean_pct, 3)}</td>
                    <td className={`col-num ${toneOf(h.excess_mean_pct)}`}>
                      {fmtPct(h.excess_mean_pct, 3)}
                      {h.excess_mean_pct !== null ? <span className="faint ml-1">{h.excess_positive ? '+' : '−'}</span> : null}
                    </td>
                    <td className="col-num">{fmtPct(sig.positive_rate_pct, 1)}</td>
                    <td className="col-num">{sig.p_value_two_sided === null ? '—' : fmt(sig.p_value_two_sided, 3)}</td>
                    <td className="text-[10px] text-ink-3">{reading(h)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {Object.values(study.horizons).some((h: HorizonStudy) => h.overlapping_windows) ? (
          <p className="faint text-[10px]">
            Consecutive signals share forward bars, so observations overlap and the effective sample is smaller than n —
            every p-value here is optimistic.
          </p>
        ) : null}

        <TimeOfDay byTimeOfDay={study.by_time_of_day} horizon={horizonKeys[0]} />
      </div>
    </section>
  );
}

function TimeOfDay({ byTimeOfDay, horizon }: { byTimeOfDay?: Record<string, ForwardReturnStats>; horizon: string }) {
  const rows = Object.entries(byTimeOfDay ?? {});
  if (rows.length === 0) return null;
  return (
    <details className="sg-sect">
      <summary className="micro-label cursor-pointer">By entry time of day · {horizon}-bar horizon</summary>
      <div className="tbl-wrap mt-1.5">
        <table className="tbl tbl--zebra tbl-dense w-full">
          <thead>
            <tr>
              <th>Bucket</th>
              <th className="text-right">n</th>
              <th className="text-right">Mean %</th>
              <th className="text-right">Median %</th>
              <th className="text-right">Positive %</th>
              <th>Sample</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([bucket, s]) => (
              <tr key={bucket}>
                <td className="text-ink">{bucket}</td>
                <td className="col-num">{fmtInt(s.n)}</td>
                <td className={`col-num ${toneOf(s.mean_pct)}`}>{fmtPct(s.mean_pct, 3)}</td>
                <td className="col-num text-ink-2">{fmtPct(s.median_pct, 3)}</td>
                <td className="col-num">{fmtPct(s.positive_rate_pct, 1)}</td>
                <td>
                  <span className={`badge badge-sm ${s.low_sample ? 'b-warn' : 'b-info'}`}>
                    {s.low_sample ? 'low sample' : 'ok'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="faint mt-1 text-[10px]">
        A time-of-day pattern here is a hypothesis for further study — with buckets this small it is usually noise.
      </p>
    </details>
  );
}

function toneOf(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '';
  return v > 0 ? 'text-up-strong' : v < 0 ? 'text-down-strong' : 'text-ink-3';
}

function reading(h: { excess_mean_pct: number | null; signal: ForwardReturnStats }): string {
  if (h.signal.n < 30) return 'too few signals to read';
  if (h.excess_mean_pct === null) return '—';
  if (!h.signal.is_significant_5pct) return 'not distinguishable from zero';
  return h.excess_mean_pct > 0 ? 'positive excess, significant' : 'negative excess, significant';
}
