'use client';

import { useState } from 'react';
import { AlertCircle, CheckCircle2, FlaskConical, Loader2, Sparkles, TrendingUp } from 'lucide-react';
import type { SelectivityResponse } from '@/lib/api/indicatorResearch';
import { fmt, fmtInt, fmtPct, toneClass } from '@/lib/indicatorResearch';

type Props = {
  result: SelectivityResponse | null;
  loading: boolean;
  error: string | null;
  features: string[];
  onRun: (
    feature: string,
    thresholds: number[],
    operator?: string,
    direction?: 'long' | 'short',
    forwardHorizon?: number,
  ) => void;
};

export function SelectivityPanel({ result, loading, error, features, onRun }: Props) {
  const [selectedFeature, setSelectedFeature] = useState(features[0] ?? 'fisher');
  const [operator, setOperator] = useState('>');
  const [direction, setDirection] = useState<'long' | 'short'>('long');
  const [minVal, setMinVal] = useState('-2.0');
  const [maxVal, setMaxVal] = useState('2.0');
  const [steps, setSteps] = useState('9');
  const [forwardHorizon, setForwardHorizon] = useState('5');

  const handleRun = () => {
    const min = parseFloat(minVal);
    const max = parseFloat(maxVal);
    const count = Math.max(3, Math.min(50, parseInt(steps, 10) || 9));
    const h = Math.max(1, parseInt(forwardHorizon, 10) || 5);
    const thresholds: number[] = [];
    const step = (max - min) / (count - 1);
    for (let i = 0; i < count; i++) {
      thresholds.push(Number((min + i * step).toFixed(4)));
    }
    onRun(selectedFeature, thresholds, operator, direction, h);
  };

  return (
    <div className="flex flex-col gap-3">
      {/* ── Control Card ───────────────────────────────────────────────────── */}
      <section className="card">
        <div className="card-hd">
          <div className="flex items-center gap-2">
            <TrendingUp size={16} className="text-accent" />
            <h3 className="card-title">Selectivity &amp; Threshold Sweeps</h3>
          </div>
          <span className="card-meta">Evaluates signal frequency vs forward return &amp; adequacy tiers</span>
        </div>
        <div className="card-bd flex flex-wrap items-end gap-3">
          <label className="field w-auto">
            <span className="field-l">Feature</span>
            <select
              className="input py-1"
              value={selectedFeature}
              onChange={(e) => setSelectedFeature(e.target.value)}
            >
              {features.length > 0 ? (
                features.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))
              ) : (
                <option value="fisher">fisher</option>
              )}
            </select>
          </label>

          <label className="field w-auto">
            <span className="field-l">Condition</span>
            <select className="input py-1" value={operator} onChange={(e) => setOperator(e.target.value)}>
              <option value=">">&gt; (is above)</option>
              <option value="<">&lt; (is below)</option>
              <option value=">=">&gt;= (at or above)</option>
              <option value="<=">&lt;= (at or below)</option>
              <option value="turns_up">turns up</option>
              <option value="turns_down">turns down</option>
            </select>
          </label>

          <label className="field w-auto">
            <span className="field-l">Trade Direction</span>
            <select className="input py-1" value={direction} onChange={(e) => setDirection(e.target.value as 'long' | 'short')}>
              <option value="long">Long (Buy)</option>
              <option value="short">Short (Sell)</option>
            </select>
          </label>

          <label className="field w-24">
            <span className="field-l">Min Threshold</span>
            <input className="input py-1" type="number" step="any" value={minVal} onChange={(e) => setMinVal(e.target.value)} />
          </label>

          <label className="field w-24">
            <span className="field-l">Max Threshold</span>
            <input className="input py-1" type="number" step="any" value={maxVal} onChange={(e) => setMaxVal(e.target.value)} />
          </label>

          <label className="field w-20">
            <span className="field-l">Steps</span>
            <input className="input py-1" type="number" min="3" max="50" value={steps} onChange={(e) => setSteps(e.target.value)} />
          </label>

          <label className="field w-24">
            <span className="field-l">Horizon (bars)</span>
            <input className="input py-1" type="number" min="1" max="100" value={forwardHorizon} onChange={(e) => setForwardHorizon(e.target.value)} />
          </label>

          <button type="button" className="btn btn-primary" disabled={loading} onClick={handleRun}>
            {loading ? <Loader2 size={13} className="animate-spin" /> : <FlaskConical size={13} />}
            Run Selectivity Sweep
          </button>
        </div>
      </section>

      {error ? (
        <div className="notice notice--down">
          <span>{error}</span>
        </div>
      ) : null}

      {/* ── Results Display ────────────────────────────────────────────────── */}
      {result ? (
        <div className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="kpi">
              <span className="kpi-l">Response Monotonicity</span>
              <span className="kpi-v flex items-center gap-1.5">
                {result.is_monotonic ? (
                  <>
                    <CheckCircle2 size={16} className="text-up-strong" />
                    <span className="text-up-strong text-sm">Monotonic Response ✓</span>
                  </>
                ) : (
                  <>
                    <AlertCircle size={16} className="text-warn" />
                    <span className="text-warn text-sm">Non-Monotonic Curve ⚠</span>
                  </>
                )}
              </span>
            </div>

            <div className="kpi">
              <span className="kpi-l">Optimal Threshold</span>
              <span className="kpi-v num text-accent-strong">
                {result.optimal_threshold !== null ? fmt(result.optimal_threshold, 3) : 'None'}
              </span>
            </div>

            <div className="kpi">
              <span className="kpi-l">Sweep Range</span>
              <span className="kpi-v num text-xs">
                {fmt(result.thresholds[0], 2)} → {fmt(result.thresholds[result.thresholds.length - 1], 2)} ({result.rows.length} levels)
              </span>
            </div>
          </div>

          <section className="card">
            <div className="card-hd">
              <h3 className="card-title">Threshold Selectivity &amp; Adequacy Table</h3>
              <span className="card-meta">
                Tested condition: {result.feature} {result.operator} threshold ({result.direction})
              </span>
            </div>
            <div className="card-bd overflow-x-auto">
              <table className="table w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-border-subtle text-ink-3">
                    <th className="py-2 pr-3">Threshold</th>
                    <th className="py-2 pr-3">Signals</th>
                    <th className="py-2 pr-3">Sample Tier</th>
                    <th className="py-2 pr-3">Win Rate</th>
                    <th className="py-2 pr-3">Profit Factor</th>
                    <th className="py-2 pr-3">Total Return</th>
                    <th className="py-2 pr-3">Sharpe (ann.)</th>
                    <th className="py-2 pr-3">Forward Mean %</th>
                    <th className="py-2 pr-3">Excess Return %</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {result.rows.map((row) => {
                    const isOptimal = row.threshold === result.optimal_threshold;
                    return (
                      <tr
                        key={row.threshold}
                        className={`hover:bg-surface-subtle transition-colors ${
                          isOptimal ? 'bg-accent-wash font-medium' : ''
                        }`}
                      >
                        <td className="py-2 pr-3 num flex items-center gap-1">
                          {fmt(row.threshold, 3)}
                          {isOptimal ? <Sparkles size={11} className="text-accent" /> : null}
                        </td>
                        <td className="py-2 pr-3 num">{fmtInt(row.n_signals)}</td>
                        <td className="py-2 pr-3">
                          <span
                            className={`badge badge-sm ${
                              row.sample_tier === 'SUFFICIENT'
                                ? 'b-bull'
                                : row.sample_tier === 'MARGINAL'
                                ? 'b-warn'
                                : 'b-bear'
                            }`}
                          >
                            {row.sample_tier}
                          </span>
                        </td>
                        <td className="py-2 pr-3 num">{fmtPct(row.win_rate_pct)}</td>
                        <td className="py-2 pr-3 num">{fmt(row.profit_factor, 2)}</td>
                        <td className={`py-2 pr-3 num ${toneClass(row.total_return_pct)}`}>
                          {fmtPct(row.total_return_pct)}
                        </td>
                        <td className="py-2 pr-3 num">{fmt(row.sharpe_annualized, 2)}</td>
                        <td className={`py-2 pr-3 num ${toneClass(row.mean_forward_return_pct)}`}>
                          {fmtPct(row.mean_forward_return_pct)}
                        </td>
                        <td className={`py-2 pr-3 num ${toneClass(row.excess_return_pct)}`}>
                          {fmtPct(row.excess_return_pct)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      ) : (
        <div className="card">
          <div className="card-bd py-8 text-center text-ink-3">
            <p className="text-sm">Configure threshold limits above and click &quot;Run Selectivity Sweep&quot; to test feature sensitivity and sample size adequacy.</p>
          </div>
        </div>
      )}
    </div>
  );
}
