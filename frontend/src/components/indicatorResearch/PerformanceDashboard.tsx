'use client';

import type { BacktestResponse, GroupedStats, ValidationReport } from '@/lib/api/indicatorResearch';
import {
  fmt,
  fmtInt,
  fmtMoney,
  fmtPct,
  resultScopeLine,
  toneClass,
  type MetricCell,
} from '@/lib/indicatorResearch';

/**
 * The lookahead badge is deliberately loud. A pretty backtest that used future
 * bars is worse than no backtest, so the verdict is shown next to every number
 * that depends on it.
 */
export function NoLookaheadBadge({ validation, compact }: { validation: ValidationReport | null | undefined; compact?: boolean }) {
  if (!validation) {
    return (
      <span className={`badge ${compact ? 'badge-sm' : ''} b-warn`} title="Causality verification was not requested for this run">
        unverified
      </span>
    );
  }
  if (!validation.tested) {
    return (
      <span className={`badge ${compact ? 'badge-sm' : ''} b-warn`} title={validation.issues.join(' ') || 'Causality verification was not run'}>
        not verified
      </span>
    );
  }
  const pass = validation.no_lookahead && validation.repaint_free;
  return (
    <span
      className={`badge ${compact ? 'badge-sm' : ''} ${pass ? 'b-bull' : 'b-bear'}`}
      title={[
        validation.no_lookahead ? 'No lookahead: every signal only reads bars up to t' : 'LOOKAHEAD DETECTED',
        validation.repaint_free ? 'No repaint: re-deriving on truncated windows reproduces the same values' : 'REPAINT DETECTED',
        validation.issues.join(' '),
      ]
        .filter(Boolean)
        .join(' · ')}
    >
      {pass ? '✓ NO LOOKAHEAD' : '✕ VALIDATION FAILED'}
    </span>
  );
}

export function OrderFlowProvenanceBadge({
  provenance,
  recordsCount,
  compact,
}: {
  provenance?: string | null;
  recordsCount?: number | null;
  compact?: boolean;
}) {
  if (!provenance || provenance === 'UNAVAILABLE') {
    return (
      <span
        className={`badge ${compact ? 'badge-sm' : ''} b-warn`}
        title="Zero order-book/tick records in dataset — microstructure indicators fail honestly instead of synthesizing fake tape."
      >
        ORDER FLOW UNAVAILABLE
      </span>
    );
  }
  if (provenance === 'PROXY') {
    return (
      <span
        className={`badge ${compact ? 'badge-sm' : ''} b-info`}
        title="Proxy order flow estimation used for this dataset."
      >
        PROXY FLOW
      </span>
    );
  }
  return (
    <span
      className={`badge ${compact ? 'badge-sm' : ''} b-bull`}
      title={`Real order-flow trade records available (${recordsCount ? recordsCount.toLocaleString() : 'present'}).`}
    >
      REAL ORDER FLOW
    </span>
  );
}

function Metric({ cell }: { cell: MetricCell }) {
  return (
    <div className="kpi" title={cell.hint}>
      <span className="kpi-l">{cell.label}</span>
      <span className={`kpi-v num ${cell.tone ? toneClass(cell.tone === 'up' ? 1 : cell.tone === 'down' ? -1 : 0) : ''} ${cell.undefined ? 'text-ink-3' : ''}`}>
        {cell.value}
      </span>
    </div>
  );
}

function Group({ title, cells, hint }: { title: string; cells: MetricCell[]; hint?: string }) {
  return (
    <section className="card">
      <div className="card-hd">
        <h3 className="card-title">{title}</h3>
        {hint ? <span className="card-meta">{hint}</span> : null}
      </div>
      <div className="card-bd">
        <div className="kpis">
          {cells.map((c) => (
            <Metric key={c.label} cell={c} />
          ))}
        </div>
      </div>
    </section>
  );
}

export function PerformanceDashboard({ result }: { result: BacktestResponse }) {
  const m = result.metrics;
  if (!m) return null;

  const undef = new Set(m.undefined_metrics ?? []);
  const cell = (label: string, value: string, opts?: Omit<MetricCell, 'label' | 'value'>): MetricCell => ({
    label,
    value,
    undefined: undef.has(label.toLowerCase().replace(/[^a-z0-9]+/g, '_')),
    ...opts,
  });

  const returns: MetricCell[] = [
    cell('Net profit', fmtMoney(m.net_profit), { raw: m.net_profit, tone: (m.net_profit ?? 0) > 0 ? 'up' : (m.net_profit ?? 0) < 0 ? 'down' : 'flat' }),
    cell('Total return', fmtPct(m.total_return_pct), { raw: m.total_return_pct, tone: (m.total_return_pct ?? 0) >= 0 ? 'up' : 'down' }),
    cell('Annualised', fmtPct(m.annualized_return_pct), { raw: m.annualized_return_pct, hint: 'Extrapolated from the observed window — a short sample annualises noise' }),
    cell('Final equity', fmtMoney(m.final_equity), { raw: m.final_equity }),
    cell('Gross before costs', fmtMoney(m.gross_profit_before_costs), { raw: m.gross_profit_before_costs }),
    cell('Total costs', fmtMoney(m.total_costs), { raw: m.total_costs }),
    cell('Cost drag', fmtPct(m.cost_drag_pct), { raw: m.cost_drag_pct, hint: 'Share of gross profit consumed by modelled frictions' }),
    cell('Exposure', fmtPct(m.exposure_pct), { raw: m.exposure_pct, hint: 'Share of bars holding a position' }),
  ];

  const risk: MetricCell[] = [
    cell('Max drawdown', fmtPct(m.max_drawdown_pct), { raw: m.max_drawdown_pct, tone: 'down' }),
    cell('Max DD (abs)', fmtMoney(m.max_drawdown_abs), { raw: m.max_drawdown_abs, tone: 'down' }),
    cell('Max DD duration', `${fmtInt(m.max_drawdown_duration_bars)} bars`, { raw: m.max_drawdown_duration_bars }),
    cell('Sharpe (ann.)', fmt(m.sharpe_annualized, 2), { raw: m.sharpe_annualized, hint: 'Annualised from bar returns at the assumed bars-per-year' }),
    cell('Sortino (ann.)', fmt(m.sortino_annualized, 2), { raw: m.sortino_annualized }),
    cell('Calmar', fmt(m.calmar, 2), { raw: m.calmar }),
    cell('Profit factor', fmt(m.profit_factor, 2), { raw: m.profit_factor }),
    cell('Avg MAE', fmtPct(m.avg_mae_pct), { raw: m.avg_mae_pct, hint: 'Mean adverse excursion — how much heat a trade took before working' }),
    cell('Avg MFE', fmtPct(m.avg_mfe_pct), { raw: m.avg_mfe_pct, hint: 'Mean favourable excursion — the ceiling a target could have captured' }),
    cell('MFE / MAE', fmt(m.mfe_mae_ratio, 2), { raw: m.mfe_mae_ratio }),
  ];

  const quality: MetricCell[] = [
    cell('Trades', fmtInt(m.n_trades), { raw: m.n_trades, hint: 'Sample size. Everything below is meaningless on a handful of trades' }),
    cell('Win rate', fmtPct(m.win_rate_pct), { raw: m.win_rate_pct }),
    cell('Wins / losses', `${fmtInt(m.n_wins)} / ${fmtInt(m.n_losses)}`),
    cell('Expectancy', fmtMoney(m.expectancy_per_trade), { raw: m.expectancy_per_trade, tone: (m.expectancy_per_trade ?? 0) >= 0 ? 'up' : 'down' }),
    cell('Payoff ratio', fmt(m.payoff_ratio, 2), { raw: m.payoff_ratio }),
    cell('Avg win', fmtMoney(m.avg_win), { raw: m.avg_win, tone: 'up' }),
    cell('Avg loss', fmtMoney(m.avg_loss), { raw: m.avg_loss, tone: 'down' }),
    cell('Largest win', fmtMoney(m.largest_win), { raw: m.largest_win, tone: 'up' }),
    cell('Largest loss', fmtMoney(m.largest_loss), { raw: m.largest_loss, tone: 'down' }),
    cell('Max consec. wins', fmtInt(m.max_consecutive_wins), { raw: m.max_consecutive_wins }),
    cell('Max consec. losses', fmtInt(m.max_consecutive_losses), { raw: m.max_consecutive_losses }),
    cell('Bars held (avg)', fmt(m.avg_bars_held, 1), { raw: m.avg_bars_held }),
    cell('Bars held (median)', fmt(m.median_bars_held, 1), { raw: m.median_bars_held }),
    cell('Long / short', `${fmtInt(m.long_trades)} / ${fmtInt(m.short_trades)}`),
  ];

  return (
    <div className="flex flex-col gap-3">
      <div className="notice notice--info">
        <div className="flex flex-wrap items-center gap-2">
          <NoLookaheadBadge validation={result.validation} />
          <OrderFlowProvenanceBadge
            provenance={result.order_flow_provenance}
            recordsCount={result.order_flow_records_count}
          />
          <span className="text-[11px]">
            In-sample result on {resultScopeLine(result) ?? 'an unknown window'}. These numbers describe this window only —
            they are not a prediction, not out-of-sample evidence and not a profitability claim.
          </span>
        </div>
        {result.validation?.issues?.length ? (
          <ul className="mt-1 list-disc pl-4 text-[10px] text-down-strong">
            {result.validation.issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        ) : null}
      </div>

      {result.assumptions?.length ? (
        <details className="card">
          <summary className="card-hd cursor-pointer">
            <span className="card-title">How these numbers were produced</span>
            <span className="card-meta">{result.assumptions.length} assumptions</span>
          </summary>
          <div className="card-bd">
            <ul className="list-disc pl-4 text-[11px] text-ink-2">
              {result.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
            {result.validation ? (
              <div className="sg-kvlist mt-2">
                <div className="sg-kv">
                  <span className="sg-lab">Causality scope</span>
                  <span className="sg-num">{result.validation.scope ?? '—'}</span>
                </div>
                <div className="sg-kv">
                  <span className="sg-lab">Checks run</span>
                  <span className="sg-num num">
                    {result.validation.checks_run}
                    {result.validation.samples_checked?.length
                      ? ` · windows @ ${result.validation.samples_checked.join(', ')}`
                      : ''}
                  </span>
                </div>
              </div>
            ) : null}
            {undef.size > 0 ? (
              <p className="faint mt-2 text-[10px]">
                Undefined in this sample (shown as —): {[...undef].join(', ')}.
              </p>
            ) : null}
          </div>
        </details>
      ) : null}

      <Group title="Returns & costs" cells={returns} hint="after modelled frictions" />
      <Group title="Risk" cells={risk} hint="drawdown · risk-adjusted" />
      <Group title="Trade quality" cells={quality} hint={`${fmtInt(m.n_trades)} closed trades`} />

      <GroupedTable title="By volatility regime" group={result.by_regime} note="Regime is measured on the entry bar's realised volatility bucket — no future information." />
      <GroupedTable title="By time of day" group={result.by_time_of_day} note="Session time on the entry bar. A pattern here is a hypothesis, not yet evidence." />
      <GroupedTable title="By side" group={result.by_side} />

      {result.cost_summary ? (
        <section className="card">
          <div className="card-hd">
            <h3 className="card-title">Cost model applied</h3>
            <span className="card-meta">per round trip</span>
          </div>
          <div className="card-bd">
            <div className="sg-kvlist">
              {Object.entries(result.cost_summary).map(([key, value]) => (
                <div key={key} className="sg-kv">
                  <span className="sg-lab">{key.replace(/_/g, ' ')}</span>
                  <span className="sg-num num">{typeof value === 'number' ? fmt(value, 4) : String(value)}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}

function GroupedTable({ title, group, note }: { title: string; group?: GroupedStats; note?: string }) {
  const rows = group ? Object.entries(group) : [];
  if (rows.length === 0) return null;
  return (
    <section className="card">
      <div className="card-hd">
        <h3 className="card-title">{title}</h3>
        <span className="card-meta num">{rows.length} buckets</span>
      </div>
      <div className="card-bd">
        {note ? <p className="sg-note mb-1.5">{note}</p> : null}
        <div className="tbl-wrap">
          <table className="tbl tbl--zebra tbl-dense w-full">
            <thead>
              <tr>
                <th>Bucket</th>
                <th className="text-right">Trades</th>
                <th className="text-right">Win rate</th>
                <th className="text-right">Net P&amp;L</th>
                <th className="text-right">Avg net</th>
                <th className="text-right">Profit factor</th>
                <th className="text-right">Avg bars</th>
                <th className="text-right">Avg MAE</th>
                <th className="text-right">Avg MFE</th>
                <th>Sample</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([bucket, s]) => (
                <tr key={bucket}>
                  <td className="text-ink">{bucket}</td>
                  <td className="col-num">{fmtInt(s.n_trades)}</td>
                  <td className="col-num">{fmtPct(s.win_rate_pct)}</td>
                  <td className={`col-num ${toneClass(s.net_pnl)}`}>{fmtMoney(s.net_pnl)}</td>
                  <td className={`col-num ${toneClass(s.avg_net_pnl)}`}>{fmtMoney(s.avg_net_pnl)}</td>
                  <td className="col-num">{fmt(s.profit_factor, 2)}</td>
                  <td className="col-num">{fmt(s.avg_bars_held, 1)}</td>
                  <td className="col-num text-ink-2">{fmtPct(s.avg_mae_pct)}</td>
                  <td className="col-num text-ink-2">{fmtPct(s.avg_mfe_pct)}</td>
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
      </div>
    </section>
  );
}
