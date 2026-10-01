'use client';

import { useEffect, useMemo, useState } from 'react';
import { Play, ShieldCheck } from 'lucide-react';
import type {
  IndicatorMetadata,
  OptimizeResponse,
  WalkForwardResponse,
} from '@/lib/api/indicatorResearch';
import { fmt, fmtInt, fmtMoney, fmtPct, toneClass } from '@/lib/indicatorResearch';

const OBJECTIVES = [
  { id: 'net_profit', label: 'Net profit' },
  { id: 'profit_factor', label: 'Profit factor' },
  { id: 'sharpe_annualized', label: 'Sharpe (annualised)' },
  { id: 'expectancy_per_trade', label: 'Expectancy per trade' },
  { id: 'calmar', label: 'Calmar' },
  { id: 'total_return_pct', label: 'Total return %' },
];

const OBJECTIVE_COLUMN: Record<string, (row: Record<string, unknown>) => number | null> = {
  net_profit: (r) => asNum(r.net_profit),
  profit_factor: (r) => asNum(r.profit_factor),
  sharpe_annualized: (r) => asNum(r.sharpe_annualized),
  expectancy_per_trade: (r) => asNum(r.expectancy_per_trade),
  calmar: (r) => asNum(r.calmar),
  total_return_pct: (r) => asNum(r.total_return_pct),
};

function asNum(v: unknown): number | null {
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

type Props = {
  meta: IndicatorMetadata | null;
  result: OptimizeResponse | null;
  loading: boolean;
  error: string | null;
  onRun: (
    objective: string,
    maxCombinations: number,
    minTrades: number,
    overrides: Record<string, Array<number | string>>,
    searchMode?: 'grid' | 'random',
  ) => void;
  walkForward: WalkForwardResponse | null;
  wfLoading: boolean;
  wfError: string | null;
  onRunWalkForward: (objective: string, folds: number, purgeBars: number, overrides: Record<string, Array<number | string>>) => void;
};

/** Suggested grid derived from the indicator's own declared parameter bounds. */
function suggestedGrid(meta: IndicatorMetadata | null): Record<string, number[]> {
  if (!meta) return {};
  const grid: Record<string, number[]> = {};
  for (const p of meta.parameters) {
    if (p.type !== 'integer' && p.type !== 'number') continue;
    const min = p.min ?? (typeof p.default === 'number' ? Math.max(1, p.default / 2) : 1);
    const max = p.max ?? (typeof p.default === 'number' ? p.default * 2 : 10);
    const values = new Set<number>();
    for (let i = 0; i < 5; i += 1) {
      const v = min + ((max - min) * i) / 4;
      values.add(p.type === 'integer' ? Math.round(v) : Number(v.toFixed(2)));
    }
    grid[p.name] = [...values].sort((a, b) => a - b);
  }
  return grid;
}

export function ParameterOptimizer({
  meta,
  result,
  loading,
  error,
  onRun,
  walkForward,
  wfLoading,
  wfError,
  onRunWalkForward,
}: Props) {
  const [objective, setObjective] = useState('net_profit');
  const [searchMode, setSearchMode] = useState<'grid' | 'random'>('grid');
  const [maxCombos, setMaxCombos] = useState(200);
  const [minTrades, setMinTrades] = useState(20);
  const [folds, setFolds] = useState(5);
  const [purge, setPurge] = useState(10);
  const [overrides, setOverrides] = useState<Record<string, string>>({});

  const grid = useMemo(() => (result?.parameter_space as Record<string, number[]> | undefined) ?? suggestedGrid(meta), [result, meta]);

  useEffect(() => {
    setOverrides({});
  }, [meta?.id]);

  const parsedOverrides = (): Record<string, Array<number | string>> => {
    const out: Record<string, Array<number | string>> = {};
    for (const [key, raw] of Object.entries(overrides)) {
      const values = raw
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .map((s) => (Number.isFinite(Number(s)) ? Number(s) : s));
      if (values.length > 0) out[key] = values;
    }
    return out;
  };

  const sortedRows = useMemo(() => {
    if (!result?.rows?.length) return [];
    const pick = OBJECTIVE_COLUMN[result.objective] ?? OBJECTIVE_COLUMN.net_profit;
    const dir = result.objective_direction === 'min' ? 1 : -1;
    return [...result.rows].sort((a, b) => {
      if (a.insufficient_trades !== b.insufficient_trades) return a.insufficient_trades ? 1 : -1;
      const av = pick(a as unknown as Record<string, unknown>) ?? Number.NEGATIVE_INFINITY;
      const bv = pick(b as unknown as Record<string, unknown>) ?? Number.NEGATIVE_INFINITY;
      return dir * (av - bv);
    });
  }, [result]);

  return (
    <div className="flex flex-col gap-3">
      <section className="card">
        <div className="card-hd">
          <h3 className="card-title">Parameter optimisation</h3>
          <span className="badge badge-sm b-warn">in-sample</span>
        </div>
        <div className="card-bd flex flex-col gap-2">
          <p className="sg-note">
            Every combination is re-run bar-by-bar with the same no-lookahead engine. A high in-sample score is a
            hypothesis generator — it is not evidence. Confirm any winner with walk-forward testing below.
          </p>

          <div className="grid gap-2 sm:grid-cols-4">
            <label className="field">
              <span className="field-l">Objective</span>
              <select className="input w-full" value={objective} onChange={(e) => setObjective(e.target.value)}>
                {OBJECTIVES.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-l">Search mode</span>
              <select
                className="input w-full"
                value={searchMode}
                onChange={(e) => setSearchMode(e.target.value as 'grid' | 'random')}
              >
                <option value="grid">Grid Search</option>
                <option value="random">Random Search (DSR)</option>
              </select>
            </label>
            <label className="field">
              <span className="field-l">Max combinations</span>
              <input
                type="number"
                className="input w-full"
                value={maxCombos}
                min={1}
                max={2000}
                step={10}
                onChange={(e) => setMaxCombos(Math.max(1, Math.min(2000, Number(e.target.value) || 1)))}
              />
            </label>
            <label className="field">
              <span className="field-l">Min trades to qualify</span>
              <input
                type="number"
                className="input w-full"
                value={minTrades}
                min={1}
                max={500}
                onChange={(e) => setMinTrades(Math.max(1, Number(e.target.value) || 1))}
              />
            </label>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="micro-label">Search grid (edit as comma-separated values)</span>
            {Object.keys(grid).length === 0 ? (
              <p className="sg-note">This indicator exposes no numeric parameters, so there is nothing to optimise.</p>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {Object.entries(grid).map(([key, values]) => (
                  <label key={key} className="field">
                    <span className="field-l">{key}</span>
                    <input
                      className="input w-full"
                      value={overrides[key] ?? values.join(', ')}
                      onChange={(e) => setOverrides((prev) => ({ ...prev, [key]: e.target.value }))}
                    />
                  </label>
                ))}
              </div>
            )}
          </div>

          <button
            type="button"
            className="btn btn-primary w-fit"
            disabled={loading || !meta}
            onClick={() => onRun(objective, maxCombos, minTrades, parsedOverrides(), searchMode)}
          >
            <Play size={12} /> {loading ? 'Optimising…' : 'Run optimisation'}
          </button>

          {error ? <p className="notice notice--down text-[11px]">{error}</p> : null}

          {result ? (
            <>
              <div className="sg-kvlist">
                <div className="sg-kv">
                  <span className="sg-lab">Evaluated</span>
                  <span className="sg-num num">
                    {fmtInt(result.combinations_evaluated)} / {fmtInt(result.combinations_total)}
                    {result.truncated ? ' (truncated — narrow the grid)' : ''}
                  </span>
                </div>
                <div className="sg-kv">
                  <span className="sg-lab">Causality verified per run</span>
                  <span className="sg-num">{result.causality_verified ? 'yes' : 'no'}</span>
                </div>
                <div className="sg-kv">
                  <span className="sg-lab">Best params</span>
                  <span className="sg-num">{result.best ? JSON.stringify(result.best.params) : '—'}</span>
                </div>
                {result.search_mode ? (
                  <div className="sg-kv">
                    <span className="sg-lab">Search mode</span>
                    <span className="sg-num">{result.search_mode === 'random' ? 'Random Search' : 'Grid Search'}</span>
                  </div>
                ) : null}
                {result.multiple_testing_penalty !== undefined && result.multiple_testing_penalty !== null ? (
                  <div className="sg-kv">
                    <span className="sg-lab">Trial haircut</span>
                    <span className="sg-num num text-warn">{fmtPct(result.multiple_testing_penalty * 100, 1)} haircut</span>
                  </div>
                ) : null}
                {result.deflated_sharpe_ratio !== undefined && result.deflated_sharpe_ratio !== null ? (
                  <div className="sg-kv">
                    <span className="sg-lab">Deflated Sharpe (DSR)</span>
                    <span className="sg-num num text-accent-strong">{fmt(result.deflated_sharpe_ratio, 2)}</span>
                  </div>
                ) : null}
              </div>

              <div className="tbl-scroll max-h-80 overflow-auto">
                <table className="tbl tbl--zebra tbl-dense tbl--sticky w-full">
                  <thead>
                    <tr>
                      <th>Params</th>
                      <th className="text-right">Trades</th>
                      <th className="text-right">Net P&amp;L</th>
                      <th className="text-right">Return</th>
                      <th className="text-right">Win rate</th>
                      <th className="text-right">PF</th>
                      <th className="text-right">Max DD</th>
                      <th className="text-right">Sharpe</th>
                      <th className="text-right">Costs</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedRows.slice(0, 120).map((row, i) => (
                      <tr key={`${JSON.stringify(row.params)}-${i}`}>
                        <td className="whitespace-nowrap font-mono text-[10px] text-ink">
                          {Object.entries(row.params)
                            .map(([k, v]) => `${k}=${v}`)
                            .join(' ')}
                        </td>
                        <td className="col-num">{fmtInt(row.trade_count)}</td>
                        <td className={`col-num ${toneClass(row.net_profit)}`}>{fmtMoney(row.net_profit)}</td>
                        <td className={`col-num ${toneClass(row.total_return_pct)}`}>{fmtPct(row.total_return_pct)}</td>
                        <td className="col-num">{fmtPct(row.win_rate_pct)}</td>
                        <td className="col-num">{fmt(row.profit_factor, 2)}</td>
                        <td className="col-num text-down-strong">{fmtPct(row.max_drawdown_pct)}</td>
                        <td className="col-num">{fmt(row.sharpe_annualized, 2)}</td>
                        <td className="col-num text-warn-strong">{fmtMoney(row.total_costs)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {result.rows.length > 120 ? (
                <p className="faint text-[10px]">Showing the top 120 of {fmtInt(result.rows.length)} rows.</p>
              ) : null}
              {result.rows.some((r) => r.insufficient_trades) ? (
                <p className="faint text-[10px]">
                  Rows with fewer than {fmtInt(result.min_trades)} trades are pushed to the bottom: a high score on a
                  tiny sample is noise.
                </p>
              ) : null}
            </>
          ) : null}
        </div>
      </section>

      <section className="card">
        <div className="card-hd">
          <h3 className="card-title">Walk-forward validation</h3>
          <span className="badge badge-sm b-info">
            <ShieldCheck size={10} /> out-of-sample
          </span>
        </div>
        <div className="card-bd flex flex-col gap-2">
          <p className="sg-note">
            Splits the window into folds, picks parameters on each training slice, then measures only the untouched
            test slice. Purge bars drop the boundary so a trade cannot straddle train and test.
          </p>

          <div className="grid gap-2 sm:grid-cols-3">
            <label className="field">
              <span className="field-l">Objective</span>
              <select className="input w-full" value={objective} onChange={(e) => setObjective(e.target.value)}>
                {OBJECTIVES.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-l">Folds</span>
              <input
                type="number"
                className="input w-full"
                value={folds}
                min={2}
                max={12}
                onChange={(e) => setFolds(Math.max(2, Math.min(12, Number(e.target.value) || 2)))}
              />
            </label>
            <label className="field">
              <span className="field-l">Purge bars</span>
              <input
                type="number"
                className="input w-full"
                value={purge}
                min={0}
                max={500}
                onChange={(e) => setPurge(Math.max(0, Number(e.target.value) || 0))}
              />
            </label>
          </div>

          <button
            type="button"
            className="btn w-fit"
            disabled={wfLoading || !meta}
            onClick={() => onRunWalkForward(objective, folds, purge, parsedOverrides())}
          >
            <Play size={12} /> {wfLoading ? 'Running folds…' : 'Run walk-forward'}
          </button>

          {wfError ? <p className="notice notice--down text-[11px]">{wfError}</p> : null}

          {walkForward ? (
            <>
              <div className="kpis">
                <div className="kpi">
                  <span className="kpi-l">Test trades (pooled)</span>
                  <span className="kpi-v num">{fmtInt(walkForward.pooled.test_trades)}</span>
                </div>
                <div className="kpi">
                  <span className="kpi-l">Test net P&amp;L</span>
                  <span className={`kpi-v num ${toneClass(walkForward.pooled.test_net_profit)}`}>
                    {fmtMoney(walkForward.pooled.test_net_profit)}
                  </span>
                </div>
                <div className="kpi">
                  <span className="kpi-l">Mean train objective</span>
                  <span className="kpi-v num">{fmt(walkForward.pooled.mean_train_objective, 3)}</span>
                </div>
                <div className="kpi">
                  <span className="kpi-l">Mean test objective</span>
                  <span className="kpi-v num">{fmt(walkForward.pooled.mean_test_objective, 3)}</span>
                </div>
                <div className="kpi" title="Mean(train) − mean(test). A large positive gap is in-sample optimism.">
                  <span className="kpi-l">Optimism gap</span>
                  <span className={`kpi-v num ${toneClass(-(walkForward.in_sample_optimism ?? 0))}`}>
                    {fmt(walkForward.in_sample_optimism, 3)}
                  </span>
                </div>
              </div>

              <div className="tbl-wrap">
                <table className="tbl tbl--zebra tbl-dense w-full">
                  <thead>
                    <tr>
                      <th>Fold</th>
                      <th>Train bars</th>
                      <th>Test bars</th>
                      <th>Selected params</th>
                      <th className="text-right">Test trades</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {walkForward.fold_reports.map((f) => (
                      <tr key={f.fold}>
                        <td className="num">{f.fold}</td>
                        <td className="col-num">{fmtInt(f.train_bars)}</td>
                        <td className="col-num">{fmtInt(f.test_bars)}</td>
                        <td className="font-mono text-[10px] text-ink-2">
                          {f.selected_params ? JSON.stringify(f.selected_params) : '—'}
                        </td>
                        <td className="col-num">{f.test_trades === undefined ? '—' : fmtInt(f.test_trades)}</td>
                        <td>
                          {f.skipped ? (
                            <span className="badge badge-sm b-warn" title={f.skip_reason}>
                              skipped
                            </span>
                          ) : f.test_error ? (
                            <span className="badge badge-sm b-bear" title={f.test_error}>
                              error
                            </span>
                          ) : (
                            <span className="badge badge-sm b-bull">ok</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <details className="sg-sect">
                <summary className="micro-label cursor-pointer">Leakage audit</summary>
                <pre className="sg-scroll mt-1 max-h-40 overflow-auto rounded-md border border-border-subtle bg-surface-subtle p-2 font-mono text-[10px] text-ink-2">
                  {JSON.stringify(walkForward.leakage_audit, null, 2)}
                </pre>
              </details>

              {walkForward.warnings?.length ? (
                <div className="notice notice--warn">
                  <ul className="list-disc pl-4 text-[10px]">
                    {walkForward.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          ) : null}
        </div>
      </section>
    </div>
  );
}
