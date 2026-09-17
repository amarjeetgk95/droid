'use client';

import React, { useRef, useState } from 'react';
import { api } from '@/lib/api';
import { Card } from '../shared/Card';
import { Gauge } from '../shared/Gauge';
import { Badge } from '../shared/Badge';
import { valueToneClass } from './riskUtils';

type RiskCheck = { name: string; passed: boolean; reason: string | null };

type RiskEvaluation = {
  result: string;
  reason: string | null;
  failed_check: string | null;
  checks: RiskCheck[];
  portfolio: { gross: string; net: string; margin_used: string };
};

type FormState = {
  instrument: string;
  side: 'BUY' | 'SELL';
  notional: string;
  margin: string;
  totalCapital: string;
  grossLimit: string;
  netLimit: string;
  marginLimitPct: string;
  drawdownLimitPct: string;
  maxConcurrent: string;
};

const INITIAL_FORM: FormState = {
  instrument: 'NIFTY',
  side: 'BUY',
  notional: '',
  margin: '',
  totalCapital: '',
  grossLimit: '',
  netLimit: '',
  marginLimitPct: '',
  drawdownLimitPct: '',
  maxConcurrent: '',
};

const INSTRUMENTS = ['NIFTY', 'BANKNIFTY', 'SENSEX', 'BTCUSD'];

function parsePositive(raw: string): number | null {
  if (raw.trim() === '') return null;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function amount(v: string): string {
  const n = Number(v);
  return Number.isFinite(n) ? `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '—';
}

/**
 * Hypothetical order evaluator for the backend portfolio-risk engine.
 *
 * This panel holds NO portfolio numbers of its own: every value rendered
 * comes from `/institutional/risk/portfolio-evaluate` for the order context
 * and limits the operator supplies. Before an evaluation exists the panel is
 * explicit that order context is required — it never shows seeded VaR/stress
 * figures.
 */
export const PortfolioRiskPanel: React.FC = () => {
  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [evaluation, setEvaluation] = useState<RiskEvaluation | null>(null);
  const [evaluatedOrder, setEvaluatedOrder] = useState<FormState | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Last-write-wins: a slow response from an earlier submit can never replace
  // the result of a newer one.
  const requestSeqRef = useRef(0);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleEvaluate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const notional = parsePositive(form.notional);
    const margin = parsePositive(form.margin);
    if (!notional) {
      setError('Enter a positive new-order notional (₹) before evaluating.');
      return;
    }
    if (!margin) {
      setError('Enter a positive new-order margin (₹) before evaluating.');
      return;
    }

    const limits: Record<string, number> = {};
    const capital = parsePositive(form.totalCapital);
    const grossLimit = parsePositive(form.grossLimit);
    const netLimit = parsePositive(form.netLimit);
    const marginLimitPct = parsePositive(form.marginLimitPct);
    const drawdownLimitPct = parsePositive(form.drawdownLimitPct);
    const maxConcurrent = parsePositive(form.maxConcurrent);
    if (capital) limits.total_capital = capital;
    if (grossLimit) limits.gross_exposure_limit = grossLimit;
    if (netLimit) limits.net_exposure_limit = netLimit;
    if (marginLimitPct) limits.margin_limit_pct = marginLimitPct;
    if (drawdownLimitPct) limits.drawdown_limit_pct = drawdownLimitPct;
    if (maxConcurrent) limits.max_concurrent_trades = Math.floor(maxConcurrent);

    const seq = ++requestSeqRef.current;
    setEvaluating(true);
    try {
      const res = await api.evaluatePortfolioRisk({
        new_order_instrument: form.instrument,
        new_order_notional: String(notional),
        new_order_margin: String(margin),
        side: form.side,
        ...(Object.keys(limits).length > 0 ? { limits } : {}),
      });
      if (seq !== requestSeqRef.current) return;
      setEvaluation(res);
      setEvaluatedOrder(form);
    } catch (err) {
      if (seq !== requestSeqRef.current) return;
      setError(err instanceof Error && err.message ? err.message : 'Evaluation failed.');
      setEvaluation(null);
      setEvaluatedOrder(null);
    } finally {
      if (seq === requestSeqRef.current) setEvaluating(false);
    }
  };

  const approved = evaluation?.result === 'APPROVED';
  const gross = evaluation ? Number(evaluation.portfolio.gross) : NaN;
  const marginUsed = evaluation ? Number(evaluation.portfolio.margin_used) : NaN;
  const capital = evaluatedOrder ? parsePositive(evaluatedOrder.totalCapital) : null;
  const marginLimitPct = evaluatedOrder ? parsePositive(evaluatedOrder.marginLimitPct) : null;
  const grossLimit = evaluatedOrder ? parsePositive(evaluatedOrder.grossLimit) : null;
  const projectedMarginPct =
    capital && Number.isFinite(marginUsed) ? (marginUsed / capital) * 100 : null;

  return (
    <Card
      title="PORTFOLIO RISK GATE — HYPOTHETICAL ORDER EVALUATION"
      subtitle="Runs the institutional portfolio-risk engine for an explicit order context; no cached portfolio figures are assumed"
    >
      <div className="space-y-4 font-mono text-xs">
        <form onSubmit={handleEvaluate} className="space-y-3" aria-label="Order risk evaluation">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <label className="block">
              <span className="text-[10px] text-ink-3 uppercase">Instrument</span>
              <select
                value={form.instrument}
                onChange={(e) => set('instrument', e.target.value)}
                className="mt-1 w-full rounded border border-border bg-surface px-2 py-1.5 text-ink"
              >
                {INSTRUMENTS.map((i) => (
                  <option key={i} value={i}>
                    {i}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="text-[10px] text-ink-3 uppercase">Side</span>
              <select
                value={form.side}
                onChange={(e) => set('side', e.target.value as FormState['side'])}
                className="mt-1 w-full rounded border border-border bg-surface px-2 py-1.5 text-ink"
              >
                <option value="BUY">BUY</option>
                <option value="SELL">SELL</option>
              </select>
            </label>

            <label className="block">
              <span className="text-[10px] text-ink-3 uppercase">Notional (₹)</span>
              <input
                type="number"
                min="0"
                step="any"
                inputMode="decimal"
                value={form.notional}
                onChange={(e) => set('notional', e.target.value)}
                placeholder="e.g. 250000"
                className="mt-1 w-full rounded border border-border bg-surface px-2 py-1.5 text-ink"
              />
            </label>

            <label className="block">
              <span className="text-[10px] text-ink-3 uppercase">Margin (₹)</span>
              <input
                type="number"
                min="0"
                step="any"
                inputMode="decimal"
                value={form.margin}
                onChange={(e) => set('margin', e.target.value)}
                placeholder="e.g. 120000"
                className="mt-1 w-full rounded border border-border bg-surface px-2 py-1.5 text-ink"
              />
            </label>
          </div>

          <details className="rounded border border-border-subtle bg-surface-subtle px-3 py-2">
            <summary className="cursor-pointer text-[11px] text-ink-2 select-none">
              Optional limits (only the ones provided are enforced by the engine)
            </summary>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 pt-3">
              <label className="block">
                <span className="text-[10px] text-ink-3 uppercase">Total capital (₹)</span>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={form.totalCapital}
                  onChange={(e) => set('totalCapital', e.target.value)}
                  className="mt-1 w-full rounded border border-border bg-surface px-2 py-1.5 text-ink"
                />
              </label>
              <label className="block">
                <span className="text-[10px] text-ink-3 uppercase">Gross exposure limit (₹)</span>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={form.grossLimit}
                  onChange={(e) => set('grossLimit', e.target.value)}
                  className="mt-1 w-full rounded border border-border bg-surface px-2 py-1.5 text-ink"
                />
              </label>
              <label className="block">
                <span className="text-[10px] text-ink-3 uppercase">Net exposure limit (₹)</span>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={form.netLimit}
                  onChange={(e) => set('netLimit', e.target.value)}
                  className="mt-1 w-full rounded border border-border bg-surface px-2 py-1.5 text-ink"
                />
              </label>
              <label className="block">
                <span className="text-[10px] text-ink-3 uppercase">Margin limit (%)</span>
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="any"
                  value={form.marginLimitPct}
                  onChange={(e) => set('marginLimitPct', e.target.value)}
                  className="mt-1 w-full rounded border border-border bg-surface px-2 py-1.5 text-ink"
                />
              </label>
              <label className="block">
                <span className="text-[10px] text-ink-3 uppercase">Drawdown limit (%)</span>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={form.drawdownLimitPct}
                  onChange={(e) => set('drawdownLimitPct', e.target.value)}
                  className="mt-1 w-full rounded border border-border bg-surface px-2 py-1.5 text-ink"
                />
              </label>
              <label className="block">
                <span className="text-[10px] text-ink-3 uppercase">Max concurrent trades</span>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={form.maxConcurrent}
                  onChange={(e) => set('maxConcurrent', e.target.value)}
                  className="mt-1 w-full rounded border border-border bg-surface px-2 py-1.5 text-ink"
                />
              </label>
            </div>
          </details>

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={evaluating}
              className="px-3 py-1.5 rounded bg-accent-wash hover:bg-accent/20 border border-accent-line text-primary font-semibold transition-all disabled:opacity-50"
            >
              {evaluating ? 'Evaluating…' : 'Evaluate Order'}
            </button>
            <span className="text-[10px] text-ink-3">
              Evaluation is synchronous and stateless — it covers the order above plus the supplied limits.
            </span>
          </div>
        </form>

        {error && (
          <p role="alert" className="p-2 rounded bg-down-wash border border-down-line text-down-strong">
            {error}
          </p>
        )}

        {!evaluation && !error && (
          <p className="p-3 rounded border border-dashed border-border-strong text-ink-3">
            Order context required — this gate is disabled until a hypothetical order is submitted.
          </p>
        )}

        {evaluation && evaluatedOrder && (
          <div className="space-y-3" aria-live="polite">
            <div className="flex flex-wrap items-center gap-3">
              <Badge variant={approved ? 'success' : 'danger'} size="sm">
                {evaluation.result}
              </Badge>
              <span className="text-ink-2">
                {evaluatedOrder.side} {evaluatedOrder.instrument} · notional{' '}
                {amount(evaluatedOrder.notional)} · margin {amount(evaluatedOrder.margin)}
              </span>
            </div>

            {evaluation.reason && (
              <p className={`font-semibold ${approved ? 'text-up-strong' : 'text-down-strong'}`}>
                {evaluation.reason}
                {evaluation.failed_check ? ` (failed check: ${evaluation.failed_check})` : ''}
              </p>
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="p-3 rounded-lg bg-surface-subtle border border-border">
                <div className="text-[10px] text-ink-3 uppercase">Projected Gross Exposure</div>
                <div className="text-base font-bold text-ink mt-0.5">{amount(evaluation.portfolio.gross)}</div>
              </div>
              <div className="p-3 rounded-lg bg-surface-subtle border border-border">
                <div className="text-[10px] text-ink-3 uppercase">Projected Net Exposure</div>
                <div className={`text-base font-bold mt-0.5 ${valueToneClass(Number(evaluation.portfolio.net))}`}>
                  {amount(evaluation.portfolio.net)}
                </div>
              </div>
              <div className="p-3 rounded-lg bg-surface-subtle border border-border">
                <div className="text-[10px] text-ink-3 uppercase">Projected Margin Used</div>
                <div className="text-base font-bold text-ink mt-0.5">{amount(evaluation.portfolio.margin_used)}</div>
              </div>
            </div>

            {grossLimit !== null && Number.isFinite(gross) && (
              <Gauge
                value={gross}
                min={0}
                max={grossLimit}
                label="Gross exposure vs limit"
                sublabel={`${amount(evaluation.portfolio.gross)} of ${amount(String(grossLimit))}`}
                thresholds={{ warning: 80, danger: 100 }}
              />
            )}

            {projectedMarginPct !== null && marginLimitPct !== null && (
              <Gauge
                value={projectedMarginPct}
                min={0}
                max={100}
                label="Projected margin utilization"
                sublabel={`${projectedMarginPct.toFixed(1)}% of capital · limit ${marginLimitPct}%`}
                thresholds={{
                  warning: Math.max(1, marginLimitPct * 0.8),
                  danger: marginLimitPct,
                }}
              />
            )}

            <div>
              <div className="text-[10px] text-ink-3 uppercase mb-1.5">
                Engine checks ({evaluation.checks.filter((c) => c.passed).length}/{evaluation.checks.length} passed)
              </div>
              <ul className="space-y-1.5">
                {evaluation.checks.map((check) => (
                  <li
                    key={check.name}
                    className={`flex items-start justify-between gap-3 p-2 rounded border ${
                      check.passed
                        ? 'bg-up-wash border-up-line'
                        : 'bg-down-wash border-down-line'
                    }`}
                  >
                    <div>
                      <div className={`font-semibold ${check.passed ? 'text-up-strong' : 'text-down-strong'}`}>
                        {check.name.replace(/_/g, ' ')}
                      </div>
                      {check.reason && <div className="text-[10px] text-ink-2 mt-0.5">{check.reason}</div>}
                    </div>
                    <span
                      className={`text-[10px] font-bold ${check.passed ? 'text-up-strong' : 'text-down-strong'}`}
                    >
                      {check.passed ? 'PASS' : 'FAIL'}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
};
