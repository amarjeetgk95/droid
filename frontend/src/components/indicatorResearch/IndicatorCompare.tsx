'use client';

import { useEffect, useMemo, useState } from 'react';
import { GitCompareArrows, Play } from 'lucide-react';
import type { CompareResponse, IndicatorMetadata } from '@/lib/api/indicatorResearch';
import { fmt, fmtInt, fmtMoney, fmtPct, toneClass } from '@/lib/indicatorResearch';

const OBJECTIVES = ['net_profit', 'profit_factor', 'sharpe_annualized', 'total_return_pct'];

type Props = {
  metas: IndicatorMetadata[];
  result: CompareResponse | null;
  loading: boolean;
  error: string | null;
  presetIds: string[];
  onRun: (ids: string[], objective: string, useDefaultRules: boolean) => void;
};

export function IndicatorCompare({ metas, result, loading, error, presetIds, onRun }: Props) {
  const [selected, setSelected] = useState<string[]>(presetIds);
  const [objective, setObjective] = useState('net_profit');
  const [useDefaults, setUseDefaults] = useState(true);

  useEffect(() => {
    setSelected((prev) => (prev.length > 0 ? prev : presetIds));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetIds.join(',')]);

  const grouped = useMemo(() => {
    const map = new Map<string, IndicatorMetadata[]>();
    for (const meta of metas) {
      const list = map.get(meta.category) ?? [];
      list.push(meta);
      map.set(meta.category, list);
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [metas]);

  const toggle = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  return (
    <div className="flex flex-col gap-3">
      <section className="card">
        <div className="card-hd">
          <h3 className="card-title">Compare indicators</h3>
          <span className="card-meta">same window · same costs · same execution</span>
        </div>
        <div className="card-bd flex flex-col gap-2">
          <p className="sg-note">
            Each indicator is backtested on the identical data window and cost model, but with{' '}
            <b>its own</b> signal rules — so this ranks rule sets, not indicators in the abstract. Treat it as an
            in-sample screen.
          </p>

          <div className="grid gap-2 sm:grid-cols-2">
            <label className="field">
              <span className="field-l">Objective</span>
              <select className="input w-full" value={objective} onChange={(e) => setObjective(e.target.value)}>
                {OBJECTIVES.map((o) => (
                  <option key={o} value={o}>
                    {o.replace(/_/g, ' ')}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-end gap-1.5 pb-1">
              <input
                type="checkbox"
                className="h-3.5 w-3.5 accent-[var(--ds-accent)]"
                checked={useDefaults}
                onChange={(e) => setUseDefaults(e.target.checked)}
              />
              <span className="text-[11px] text-ink-2">Use each indicator&rsquo;s own default rules</span>
            </label>
          </div>

          <div className="sg-scroll max-h-52 overflow-y-auto rounded-md border border-border-subtle p-2">
            {grouped.map(([cat, list]) => (
              <div key={cat} className="mb-1.5">
                <span className="micro-label">{cat}</span>
                <div className="flex flex-wrap gap-x-3 gap-y-1">
                  {list.map((meta) => (
                    <label key={meta.id} className="flex items-center gap-1.5">
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5 accent-[var(--ds-accent)]"
                        checked={selected.includes(meta.id)}
                        onChange={() => toggle(meta.id)}
                      />
                      <span className="text-[11px] text-ink-2">{meta.name}</span>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              className="btn btn-primary w-fit"
              disabled={loading || selected.length === 0}
              onClick={() => onRun(selected, objective, useDefaults)}
            >
              <Play size={12} /> {loading ? 'Comparing…' : `Compare ${selected.length}`}
            </button>
            <button type="button" className="btn btn-ic" onClick={() => setSelected([])} disabled={selected.length === 0}>
              Clear
            </button>
          </div>

          {error ? <p className="notice notice--down text-[11px]">{error}</p> : null}
        </div>
      </section>

      {result ? (
        <section className="card">
          <div className="card-hd">
            <h3 className="card-title">
              <GitCompareArrows size={13} className="mr-1 inline" />
              Results · {result.objective.replace(/_/g, ' ')}
            </h3>
            <span className="badge badge-sm b-warn">in-sample</span>
          </div>
          <div className="card-bd flex flex-col gap-2">
            <p className="sg-note">
              {result.comparable_count} of {result.rows.length} indicators produced comparable results on this window.
            </p>
            <div className="tbl-scroll max-h-[30rem] overflow-auto">
              <table className="tbl tbl--zebra tbl-dense tbl--sticky w-full">
                <thead>
                  <tr>
                    <th>Indicator</th>
                    <th>Category</th>
                    <th className="text-right">Trades</th>
                    <th className="text-right">Net P&amp;L</th>
                    <th className="text-right">Return</th>
                    <th className="text-right">Win rate</th>
                    <th className="text-right">PF</th>
                    <th className="text-right">Max DD</th>
                    <th className="text-right">Sharpe</th>
                    <th>Lookahead</th>
                    <th>Rules</th>
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row) => (
                    <tr key={row.indicator_id}>
                      <td className="text-ink">{row.name ?? row.indicator_id}</td>
                      <td className="text-ink-3">{row.category ?? '—'}</td>
                      <td className="col-num">{row.trade_count === undefined ? '—' : fmtInt(row.trade_count)}</td>
                      <td className={`col-num ${toneClass(row.net_profit)}`}>{fmtMoney(row.net_profit)}</td>
                      <td className={`col-num ${toneClass(row.total_return_pct)}`}>{fmtPct(row.total_return_pct)}</td>
                      <td className="col-num">{fmtPct(row.win_rate_pct)}</td>
                      <td className="col-num">{fmt(row.profit_factor, 2)}</td>
                      <td className="col-num text-down-strong">{fmtPct(row.max_drawdown_pct)}</td>
                      <td className="col-num">{fmt(row.sharpe_annualized, 2)}</td>
                      <td>
                        {row.comparable ? (
                          <span className={`badge badge-sm ${row.no_lookahead ? 'b-bull' : 'b-bear'}`}>
                            {row.no_lookahead ? 'clean' : 'failed'}
                          </span>
                        ) : (
                          <span className="badge badge-sm b-warn" title={row.reason ?? undefined}>
                            n/a
                          </span>
                        )}
                      </td>
                      <td className="max-w-[16rem] text-[10px] text-ink-3" title={`${row.long_rule ?? ''} / ${row.short_rule ?? ''}`}>
                        <span className="block truncate">{row.long_rule ?? '—'}</span>
                        <span className="block truncate opacity-70">{row.short_rule ?? '—'}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {result.note ? <p className="faint text-[10px]">{result.note}</p> : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}
