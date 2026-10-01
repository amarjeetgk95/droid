'use client';

import { useState } from 'react';
import { Download, Save, Trash2 } from 'lucide-react';
import type { ExperimentSummary } from '@/lib/api/indicatorResearch';
import { fmtDate, fmtInt, fmtMoney, fmtPct } from '@/lib/indicatorResearch';

type Props = {
  experiments: ExperimentSummary[];
  loading: boolean;
  error: string | null;
  notice: string | null;
  hasBacktest: boolean;
  canSave: boolean;
  onSave: (name: string, notes: string) => void;
  onDelete: (id: string) => void;
  exportUrl: (id: string, format: 'json' | 'csv') => string;
  onRefresh: () => void;
};

/**
 * Experiment persistence. Each record stores the full runnable config
 * (data window, indicators, params, rules, execution settings) plus the
 * result summary and validation verdict at save time, so a saved experiment
 * can be reproduced later — not just admired.
 */
export function ExperimentsPanel({
  experiments,
  loading,
  error,
  notice,
  hasBacktest,
  canSave,
  onSave,
  onDelete,
  exportUrl,
  onRefresh,
}: Props) {
  const [name, setName] = useState('');
  const [notes, setNotes] = useState('');
  const [confirmId, setConfirmId] = useState<string | null>(null);

  return (
    <section className="card">
      <div className="card-hd">
        <h3 className="card-title">Saved experiments</h3>
        <span className="card-meta num">{fmtInt(experiments.length)}</span>
        <button type="button" className="btn-ic ml-auto" onClick={onRefresh} title="Reload experiment list">
          Refresh
        </button>
      </div>
      <div className="card-bd flex flex-col gap-2.5">
        <div className="grid gap-2 sm:grid-cols-[1fr_2fr_auto]">
          <label className="field">
            <span className="field-l">Name</span>
            <input
              className="input w-full"
              placeholder="e.g. Fisher 9 NIFTY 5m Jan-26"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-l">Notes</span>
            <input
              className="input w-full"
              placeholder="What were you testing?"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>
          <div className="flex items-end">
            <button
              type="button"
              className="btn btn-primary"
              disabled={!canSave}
              title={hasBacktest ? 'Save the current configuration and its result summary' : 'Run a backtest first so the experiment stores a result'}
              onClick={() => {
                onSave(name, notes);
                setName('');
                setNotes('');
              }}
            >
              <Save size={12} /> Save current
            </button>
          </div>
        </div>

        {notice ? <p className="notice notice--info text-[11px]">{notice}</p> : null}
        {error ? <p className="notice notice--down text-[11px]">{error}</p> : null}
        {loading && experiments.length === 0 ? <p className="sg-note">Loading experiments…</p> : null}

        {experiments.length === 0 && !loading ? (
          <p className="sg-note">
            No saved experiments yet. A saved experiment stores the full configuration and its in-sample summary —
            it does not re-run anything.
          </p>
        ) : null}

        {experiments.length > 0 ? (
          <div className="tbl-scroll max-h-[24rem] overflow-auto">
            <table className="tbl tbl--zebra tbl-dense tbl--sticky w-full">
              <thead>
                <tr>
                  <th>Experiment</th>
                  <th>Window</th>
                  <th>Indicator</th>
                  <th className="text-right">Trades</th>
                  <th className="text-right">Net P&amp;L</th>
                  <th className="text-right">Return</th>
                  <th className="text-right">Win rate</th>
                  <th>Validation</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {experiments.map((exp) => {
                  const summary = exp.result_summary ?? {};
                  const validation = exp.validation ?? {};
                  const clean = validation.no_lookahead === true;
                  return (
                    <tr key={exp.id}>
                      <td>
                        <span className="text-[12px] font-medium text-ink">{exp.name || exp.id.slice(0, 8)}</span>
                        {exp.notes ? <span className="sg-rownote block">{exp.notes}</span> : null}
                        {exp.created_at ? <span className="faint block text-[10px]">{fmtDate(exp.created_at)}</span> : null}
                      </td>
                      <td className="text-[11px] text-ink-2">
                        {exp.instrument ?? '—'} · {exp.timeframe ?? '—'}
                        {exp.date_range?.start ? (
                          <span className="block faint">
                            {String(exp.date_range.start).slice(0, 10)} → {String(exp.date_range.end ?? '').slice(0, 10)}
                          </span>
                        ) : null}
                      </td>
                      <td className="text-[11px] text-ink-2">{exp.indicator_id ?? '—'}</td>
                      <td className="col-num">{summary.trade_count === undefined ? '—' : fmtInt(summary.trade_count as number)}</td>
                      <td className="col-num">
                        {summary.saved_without_backtest ? '—' : fmtMoney(summary.net_profit as number | null)}
                      </td>
                      <td className="col-num">{summary.saved_without_backtest ? '—' : fmtPct(summary.total_return_pct as number | null)}</td>
                      <td className="col-num">{summary.saved_without_backtest ? '—' : fmtPct(summary.win_rate_pct as number | null)}</td>
                      <td>
                        {Object.keys(validation).length === 0 ? (
                          <span className="badge badge-sm b-warn">unverified</span>
                        ) : clean ? (
                          <span className="badge badge-sm b-bull">✓ clean</span>
                        ) : (
                          <span className="badge badge-sm b-bear">failed</span>
                        )}
                      </td>
                      <td>
                        <div className="flex items-center justify-end gap-1">
                          <a className="btn-ic" href={exportUrl(exp.id, 'json')} title="Export full JSON" download>
                            <Download size={11} />
                          </a>
                          <a className="btn-ic" href={exportUrl(exp.id, 'csv')} title="Export summary CSV" download>
                            <Download size={11} className="rotate-180" />
                          </a>
                          {confirmId === exp.id ? (
                            <button
                              type="button"
                              className="btn btn-ic btn-sell"
                              onClick={() => {
                                onDelete(exp.id);
                                setConfirmId(null);
                              }}
                            >
                              confirm
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="btn-ic"
                              aria-label={`Delete ${exp.name || exp.id}`}
                              title="Delete experiment"
                              onClick={() => setConfirmId(exp.id)}
                            >
                              <Trash2 size={11} />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}

        <p className="faint text-[10px]">
          Experiments are stored as plain JSON under <span className="font-mono">data/experiments/indicator-research/</span>{' '}
          with atomic writes. A result summary is a snapshot of the moment it was saved — it is not kept up to date.
        </p>
      </div>
    </section>
  );
}
