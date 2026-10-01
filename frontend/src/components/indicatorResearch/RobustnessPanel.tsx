'use client';

import { useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  DollarSign,
  FlaskConical,
  Gauge,
  Layers,
  Loader2,
  ShieldAlert,
  Sparkles,
} from 'lucide-react';
import type { AblationResponse, RobustnessResponse } from '@/lib/api/indicatorResearch';
import { fmt, fmtInt, fmtMoney, fmtPct, toneClass } from '@/lib/indicatorResearch';

type Props = {
  robustness: RobustnessResponse | null;
  robustnessLoading: boolean;
  robustnessError: string | null;
  ablation: AblationResponse | null;
  ablationLoading: boolean;
  ablationError: string | null;
  selectedCount: number;
  onRunRobustness: () => void;
  onRunAblation: (objective?: string) => void;
};

export function RobustnessPanel({
  robustness,
  robustnessLoading,
  robustnessError,
  ablation,
  ablationLoading,
  ablationError,
  selectedCount,
  onRunRobustness,
  onRunAblation,
}: Props) {
  const [subTab, setSubTab] = useState<'perturbation' | 'ablation'>('perturbation');
  const [ablationObjective, setAblationObjective] = useState('sharpe_annualized');

  return (
    <div className="flex flex-col gap-3">
      {/* ── Sub Navigation ─────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-subtle pb-2">
        <div className="flex gap-1">
          <button
            type="button"
            className={`tab ${subTab === 'perturbation' ? 'is-active' : ''}`}
            onClick={() => setSubTab('perturbation')}
          >
            <Gauge size={13} className="mr-1 inline-block" />
            Parameter Perturbation &amp; Cost Stress
          </button>
          <button
            type="button"
            className={`tab ${subTab === 'ablation' ? 'is-active' : ''}`}
            onClick={() => setSubTab('ablation')}
          >
            <Layers size={13} className="mr-1 inline-block" />
            Multi-Indicator Component Ablation
          </button>
        </div>

        <div>
          {subTab === 'perturbation' ? (
            <button
              type="button"
              className="btn btn-primary"
              disabled={robustnessLoading}
              onClick={onRunRobustness}
            >
              {robustnessLoading ? <Loader2 size={13} className="animate-spin" /> : <FlaskConical size={13} />}
              Run Robustness Audit
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <select
                className="input py-1 text-xs"
                value={ablationObjective}
                onChange={(e) => setAblationObjective(e.target.value)}
              >
                <option value="sharpe_annualized">Sharpe (annualized)</option>
                <option value="net_profit">Net profit</option>
                <option value="win_rate_pct">Win rate %</option>
              </select>
              <button
                type="button"
                className="btn btn-primary"
                disabled={ablationLoading || selectedCount < 2}
                title={selectedCount < 2 ? 'Requires at least 2 indicators to run leave-one-out ablation' : ''}
                onClick={() => onRunAblation(ablationObjective)}
              >
                {ablationLoading ? <Loader2 size={13} className="animate-spin" /> : <Layers size={13} />}
                Run Ablation Study
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── Sub Tab 1: Perturbation & Cost Stress ───────────────────────────── */}
      {subTab === 'perturbation' ? (
        <div className="flex flex-col gap-3">
          {robustnessError ? (
            <div className="notice notice--down">
              <span>{robustnessError}</span>
            </div>
          ) : null}

          {robustness ? (
            <>
              {/* Top KPIs */}
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="kpi">
                  <span className="kpi-l">Parameter Stability Score</span>
                  <span className="kpi-v num">
                    <span
                      className={
                        robustness.stability_score >= 0.7
                          ? 'text-up-strong'
                          : robustness.stability_score >= 0.4
                          ? 'text-warn'
                          : 'text-down-strong'
                      }
                    >
                      {fmtPct(robustness.stability_score * 100, 1)}
                    </span>
                  </span>
                </div>

                <div className="kpi">
                  <span className="kpi-l">Cliff Risk</span>
                  <span className="kpi-v flex items-center gap-1.5">
                    {robustness.cliff_risk_detected ? (
                      <>
                        <ShieldAlert size={16} className="text-down-strong" />
                        <span className="text-down-strong text-sm">CLIFF RISK DETECTED (&gt;50% degradation)</span>
                      </>
                    ) : (
                      <>
                        <CheckCircle2 size={16} className="text-up-strong" />
                        <span className="text-up-strong text-sm">No Catastrophic Cliffs Detected ✓</span>
                      </>
                    )}
                  </span>
                </div>

                <div className="kpi">
                  <span className="kpi-l">Fragile Parameters</span>
                  <span className="kpi-v text-sm">
                    {robustness.fragile_parameters?.length ? (
                      <span className="text-warn">{robustness.fragile_parameters.join(', ')}</span>
                    ) : (
                      <span className="text-up-strong">None (All Robust)</span>
                    )}
                  </span>
                </div>
              </div>

              {/* Parameter Perturbation Table */}
              <section className="card">
                <div className="card-hd">
                  <div className="flex items-center gap-2">
                    <Cpu size={15} className="text-accent" />
                    <h3 className="card-title">Parameter Perturbation Neighborhood (±10%, ±20%)</h3>
                  </div>
                  <span className="card-meta num">{robustness.perturbations.length} variations tested</span>
                </div>
                <div className="card-bd overflow-x-auto">
                  <table className="table w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-border-subtle text-ink-3">
                        <th className="py-2 pr-3">Parameter</th>
                        <th className="py-2 pr-3">Base Value</th>
                        <th className="py-2 pr-3">Perturbed Value</th>
                        <th className="py-2 pr-3">Shift %</th>
                        <th className="py-2 pr-3">Sharpe</th>
                        <th className="py-2 pr-3">Sharpe Change</th>
                        <th className="py-2 pr-3">Net Profit</th>
                        <th className="py-2 pr-3">Win Rate</th>
                        <th className="py-2 pr-3">Trades</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-subtle">
                      {robustness.perturbations.map((p, idx) => (
                        <tr key={idx} className="hover:bg-surface-subtle transition-colors">
                          <td className="py-2 pr-3 font-mono font-medium">{p.param_name}</td>
                          <td className="py-2 pr-3 num">{String(p.original_value)}</td>
                          <td className="py-2 pr-3 num">{String(p.perturbed_value)}</td>
                          <td className="py-2 pr-3 num">{fmtPct(p.perturbation_pct * 100, 0)}</td>
                          <td className="py-2 pr-3 num">{fmt(p.sharpe_annualized, 2)}</td>
                          <td className={`py-2 pr-3 num ${toneClass(p.sharpe_change_pct)}`}>
                            {p.sharpe_change_pct !== null ? fmtPct(p.sharpe_change_pct) : '—'}
                          </td>
                          <td className={`py-2 pr-3 num ${toneClass(p.net_profit)}`}>
                            {fmtMoney(p.net_profit)}
                          </td>
                          <td className="py-2 pr-3 num">{fmtPct(p.win_rate_pct)}</td>
                          <td className="py-2 pr-3 num">{fmtInt(p.trade_count)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              {/* Cost Stress Table */}
              <section className="card">
                <div className="card-hd">
                  <div className="flex items-center gap-2">
                    <DollarSign size={15} className="text-accent" />
                    <h3 className="card-title">Cost Stress Testing (Indian Statutory Frictions)</h3>
                  </div>
                  <span className="card-meta">Tests survival at 1.5×, 2.0×, 3.0× regulatory costs</span>
                </div>
                <div className="card-bd overflow-x-auto">
                  <table className="table w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-border-subtle text-ink-3">
                        <th className="py-2 pr-3">Multiplier</th>
                        <th className="py-2 pr-3">Net Profit</th>
                        <th className="py-2 pr-3">Profit Factor</th>
                        <th className="py-2 pr-3">Sharpe</th>
                        <th className="py-2 pr-3">Survives Statutory Stress?</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-subtle">
                      {robustness.cost_stress_tests.map((cs) => (
                        <tr key={cs.multiplier} className="hover:bg-surface-subtle transition-colors">
                          <td className="py-2 pr-3 font-semibold num">{cs.multiplier.toFixed(1)}× Base Costs</td>
                          <td className={`py-2 pr-3 num ${toneClass(cs.net_profit)}`}>
                            {fmtMoney(cs.net_profit)}
                          </td>
                          <td className="py-2 pr-3 num">{fmt(cs.profit_factor, 2)}</td>
                          <td className="py-2 pr-3 num">{fmt(cs.sharpe_annualized, 2)}</td>
                          <td className="py-2 pr-3">
                            {cs.survives ? (
                              <span className="badge badge-sm b-bull">SURVIVES (Net Profitable) ✓</span>
                            ) : (
                              <span className="badge badge-sm b-bear">UNVIABLE (Cost Drag Negative) ✗</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          ) : (
            <div className="card">
              <div className="card-bd py-8 text-center text-ink-3">
                <p className="text-sm">Press &quot;Run Robustness Audit&quot; to test parameter neighborhood stability and cost stress survival.</p>
              </div>
            </div>
          )}
        </div>
      ) : null}

      {/* ── Sub Tab 2: Multi-Indicator Ablation ─────────────────────────────── */}
      {subTab === 'ablation' ? (
        <div className="flex flex-col gap-3">
          {selectedCount < 2 ? (
            <div className="notice notice--warn">
              <div className="flex items-center gap-1.5">
                <AlertTriangle size={14} />
                <span>Multi-indicator ablation requires selecting at least 2 indicators from the library.</span>
              </div>
            </div>
          ) : null}

          {ablationError ? (
            <div className="notice notice--down">
              <span>{ablationError}</span>
            </div>
          ) : null}

          {ablation ? (
            <>
              {/* Baseline stats */}
              <div className="grid gap-3 sm:grid-cols-4">
                <div className="kpi">
                  <span className="kpi-l">Baseline Net Profit</span>
                  <span className={`kpi-v num ${toneClass(ablation.baseline_metrics.net_profit)}`}>
                    {fmtMoney(ablation.baseline_metrics.net_profit)}
                  </span>
                </div>
                <div className="kpi">
                  <span className="kpi-l">Baseline Sharpe</span>
                  <span className="kpi-v num">{fmt(ablation.baseline_metrics.sharpe_annualized, 2)}</span>
                </div>
                <div className="kpi">
                  <span className="kpi-l">Baseline Win Rate</span>
                  <span className="kpi-v num">{fmtPct(ablation.baseline_metrics.win_rate_pct)}</span>
                </div>
                <div className="kpi">
                  <span className="kpi-l">Baseline Trades</span>
                  <span className="kpi-v num">{fmtInt(ablation.baseline_metrics.trade_count)}</span>
                </div>
              </div>

              {/* Recommendations */}
              {ablation.recommendations?.length ? (
                <div className="notice notice--info">
                  <ul className="list-disc pl-4 text-xs">
                    {ablation.recommendations.map((rec, i) => (
                      <li key={i}>{rec}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {/* Ablation Table */}
              <section className="card">
                <div className="card-hd">
                  <h3 className="card-title">Leave-One-Out Component Contribution</h3>
                  <span className="card-meta">Measures performance degradation when an indicator is ablated</span>
                </div>
                <div className="card-bd overflow-x-auto">
                  <table className="table w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-border-subtle text-ink-3">
                        <th className="py-2 pr-3">Ablated Indicator</th>
                        <th className="py-2 pr-3">Remaining Set</th>
                        <th className="py-2 pr-3">Trades</th>
                        <th className="py-2 pr-3">Sharpe</th>
                        <th className="py-2 pr-3">Δ Sharpe</th>
                        <th className="py-2 pr-3">Net Profit</th>
                        <th className="py-2 pr-3">Δ Return %</th>
                        <th className="py-2 pr-3">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-subtle">
                      {ablation.rows.map((row) => (
                        <tr key={row.removed_indicator} className="hover:bg-surface-subtle transition-colors">
                          <td className="py-2 pr-3 font-semibold text-accent-strong">{row.removed_indicator}</td>
                          <td className="py-2 pr-3 text-ink-2">{row.remaining_indicators.join(' + ')}</td>
                          <td className="py-2 pr-3 num">{fmtInt(row.trade_count)}</td>
                          <td className="py-2 pr-3 num">{fmt(row.sharpe_annualized, 2)}</td>
                          <td className={`py-2 pr-3 num ${toneClass(row.delta_sharpe)}`}>
                            {row.delta_sharpe !== null ? fmt(row.delta_sharpe, 2) : '—'}
                          </td>
                          <td className={`py-2 pr-3 num ${toneClass(row.net_profit)}`}>
                            {fmtMoney(row.net_profit)}
                          </td>
                          <td className={`py-2 pr-3 num ${toneClass(row.delta_return_pct)}`}>
                            {row.delta_return_pct !== null ? fmtPct(row.delta_return_pct) : '—'}
                          </td>
                          <td className="py-2 pr-3">
                            {row.is_redundant ? (
                              <span className="badge badge-sm b-warn">REDUNDANT (Safe to Prune)</span>
                            ) : (
                              <span className="badge badge-sm b-bull">ESSENTIAL (Carries Alpha) ✓</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          ) : (
            <div className="card">
              <div className="card-bd py-8 text-center text-ink-3">
                <p className="text-sm">
                  Select 2 or more indicators and press &quot;Run Ablation Study&quot; to test each indicator&apos;s marginal contribution.
                </p>
              </div>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
