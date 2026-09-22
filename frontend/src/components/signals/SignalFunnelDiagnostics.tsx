'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Filter,
  Layers,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react';
import { api } from '@/lib/api';
import type { SignalFunnelData } from '@/lib/api/signals';
import { errorMessage } from '@/lib/errors';

interface SignalFunnelDiagnosticsProps {
  initialInstrument?: string;
  onRefreshParent?: () => void;
  standalone?: boolean;
}

/**
 * Percentage from two measured counts. Null when either side is missing or the
 * denominator is zero (0/0 has no measurement) — callers render "No data".
 */
function ratePct(num: number | null, den: number | null): string | null {
  if (num === null || den === null || !Number.isFinite(num) || !Number.isFinite(den) || den <= 0) {
    return null;
  }
  return ((num / den) * 100).toFixed(1);
}

/** Counts render "No data" when unmeasured; a measured 0 still renders 0. */
function countText(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'No data';
  return value.toLocaleString();
}

function numOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function SignalFunnelDiagnostics({
  initialInstrument,
  onRefreshParent,
  standalone = false,
}: SignalFunnelDiagnosticsProps) {
  const [data, setData] = useState<SignalFunnelData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showRawRejections, setShowRawRejections] = useState(false);
  const [selectedStrategy, setSelectedStrategy] = useState<string>('ALL');

  const fetchFunnel = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getFunnelAnalytics({
        strategy: selectedStrategy === 'ALL' ? undefined : selectedStrategy,
        underlying: initialInstrument && initialInstrument !== 'ALL' ? initialInstrument : undefined,
      });
      setData(res);
    } catch (err) {
      setError(errorMessage(err, 'Failed to load signal funnel diagnostics'));
    } finally {
      setLoading(false);
    }
  }, [initialInstrument, selectedStrategy]);

  useEffect(() => {
    void fetchFunnel();
  }, [fetchFunnel]);

  const stages = data?.stages;
  const blockers = data?.top_blockers ?? [];
  const strategies = data?.strategy_performance ?? [];
  const rawRejections = data?.raw_rejections ?? [];

  // null = payload/stage missing; 0 = a measured zero. The two never conflate.
  const evalCount = numOrNull(stages ? stages.evaluated : data?.opportunities_evaluated);
  const candCount = numOrNull(stages ? stages.candidates : data?.total_candidates_found);
  const qualCount = numOrNull(stages ? stages.strategy_qualified : null);
  const riskCount = numOrNull(stages ? stages.risk_passed : null);
  const confCount = numOrNull(stages ? stages.confirmed : data?.total_confirmed);

  const candRate = ratePct(candCount, evalCount);
  const qualRate = ratePct(qualCount, candCount);
  const riskRate = ratePct(riskCount, qualCount);
  const confRate = ratePct(confCount, riskCount);
  const conversionPct =
    typeof data?.conversion_rate_pct === 'number' && Number.isFinite(data.conversion_rate_pct)
      ? data.conversion_rate_pct
      : null;

  const formatIST = (isoString?: string) => {
    if (!isoString) return '—';
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString('en-IN', {
        timeZone: 'Asia/Kolkata',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return isoString;
    }
  };

  return (
    <div className={`flex flex-col gap-3 ${standalone ? '' : 'panel p-4'}`}>
      {/* ── Top Bar ────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-wash text-accent">
            <Activity size={18} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-ink">
                Signal Funnel &amp; Gate Rejection Diagnostics
              </h3>
              <span className="badge b-neut text-[10px]">
                {data?.date ? `Session ${data.date}` : data ? 'Today' : 'No data'}
              </span>
            </div>
            <p className="text-[11px] text-ink-2">
              Real-time quantitative audit of opportunity scanning, gate pass rates, and primary blockers.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-[11px] text-ink-3">
            Tracking since: <b className="font-semibold text-ink">{formatIST(data?.data_since)} IST</b>
          </span>
          <button
            type="button"
            className="btn btn-ic text-xs"
            disabled={loading}
            onClick={() => {
              void fetchFunnel();
              onRefreshParent?.();
            }}
            title="Refresh funnel telemetry"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {error ? <div className="sg-err text-xs">{error}</div> : null}

      {/* ── Metric Strip ───────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-6">
        <div className="stat rounded-lg border border-border bg-surface p-2.5 shadow-sm">
          <div className="stat-l text-[10px] uppercase tracking-wider">Evaluated</div>
          <div className="mono mt-1 text-lg font-bold text-ink">{countText(evalCount)}</div>
          <div className="text-[10px] text-ink-3">opportunities</div>
        </div>

        <div className="stat rounded-lg border border-border bg-surface p-2.5 shadow-sm">
          <div className="stat-l text-[10px] uppercase tracking-wider">Candidates</div>
          <div className="mono mt-1 text-lg font-bold text-warn-ink">{countText(candCount)}</div>
          <div className="text-[10px] text-ink-3">
            {candRate !== null ? `${candRate}% detection` : 'No data'}
          </div>
        </div>

        <div className="stat rounded-lg border border-border bg-surface p-2.5 shadow-sm">
          <div className="stat-l text-[10px] uppercase tracking-wider">Strategy Qualified</div>
          <div className="mono mt-1 text-lg font-bold text-accent">{countText(qualCount)}</div>
          <div className="text-[10px] text-ink-3">
            {qualRate !== null ? `${qualRate}% pre-qual` : 'No data'}
          </div>
        </div>

        <div className="stat rounded-lg border border-border bg-surface p-2.5 shadow-sm">
          <div className="stat-l text-[10px] uppercase tracking-wider">Risk Cleared</div>
          <div className="mono mt-1 text-lg font-bold text-accent">{countText(riskCount)}</div>
          <div className="text-[10px] text-ink-3">
            {riskRate !== null ? `${riskRate}% risk accept` : 'No data'}
          </div>
        </div>

        <div className="stat rounded-lg border border-border bg-surface p-2.5 shadow-sm">
          <div className="stat-l text-[10px] uppercase tracking-wider">Confirmed</div>
          <div className="mono mt-1 text-lg font-bold text-up-strong">{countText(confCount)}</div>
          <div className="text-[10px] text-ink-3">
            {confRate !== null ? `${confRate}% registration` : 'No data'}
          </div>
        </div>

        <div className="stat rounded-lg border border-border bg-surface p-2.5 shadow-sm">
          <div className="stat-l text-[10px] uppercase tracking-wider">Funnel Conversion</div>
          <div className="mono mt-1 text-lg font-bold text-ink">
            {conversionPct !== null ? `${conversionPct}%` : 'No data'}
          </div>
          <div className="text-[10px] text-ink-3">candidate → signal</div>
        </div>
      </div>

      {/* ── Funnel Stage Visual Stepper ─────────────────────── */}
      <div className="rounded-lg border border-border bg-surface p-3 shadow-sm">
        <div className="mb-2 flex items-center justify-between text-[11px] font-semibold text-ink-2">
          <span className="flex items-center gap-1.5 uppercase tracking-wider">
            <Filter size={12} className="text-accent" />
            Scanner Pipeline Drop-Off Funnel
          </span>
          <span className="mono text-ink-3">
            {confCount !== null && candCount !== null
              ? `Conversion: ${confCount} / ${candCount} candidates${
                  conversionPct !== null ? ` (${conversionPct}%)` : ' (rate n/a)'
                }`
              : 'Conversion: No data'}
          </span>
        </div>

        <div className="grid grid-cols-5 gap-2">
          <div className="flex flex-col gap-1 rounded-md border border-border bg-surface-subtle p-2 border-l-3 border-l-border-strong">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">1. Evaluated</span>
            <span className="mono text-xs font-bold text-ink">{countText(evalCount)}</span>
            <span className="text-[9px] text-ink-3">
              {evalCount !== null ? '100% of scans' : 'No data'}
            </span>
          </div>

          <div className="flex flex-col gap-1 rounded-md border border-border bg-surface-subtle p-2 border-l-3 border-l-warn">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">2. Detected</span>
            <span className="mono text-xs font-bold text-warn-ink">{countText(candCount)}</span>
            <span className="text-[9px] text-ink-3">
              {candRate !== null ? `${candRate}% of eval` : 'No data'}
            </span>
          </div>

          <div className="flex flex-col gap-1 rounded-md border border-border bg-surface-subtle p-2 border-l-3 border-l-accent">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">3. Pre-Qual</span>
            <span className="mono text-xs font-bold text-accent">{countText(qualCount)}</span>
            <span className="text-[9px] text-ink-3">
              {qualRate !== null ? `${qualRate}% of detected` : 'No data'}
            </span>
          </div>

          <div className="flex flex-col gap-1 rounded-md border border-border bg-surface-subtle p-2 border-l-3 border-l-accent">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">4. Risk Accepted</span>
            <span className="mono text-xs font-bold text-accent">{countText(riskCount)}</span>
            <span className="text-[9px] text-ink-3">
              {riskRate !== null ? `${riskRate}% of qual` : 'No data'}
            </span>
          </div>

          <div className="flex flex-col gap-1 rounded-md border border-border bg-surface-subtle p-2 border-l-3 border-l-up">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">5. Confirmed FSM</span>
            <span className="mono text-xs font-bold text-up-strong">{countText(confCount)}</span>
            <span className="text-[9px] text-ink-3">
              {confRate !== null ? `${confRate}% of risk` : 'No data'}
            </span>
          </div>
        </div>
      </div>

      {/* ── Two-Column Breakdown: Primary Blockers vs Strategies ──── */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-12">
        {/* Left: Primary Gate Blockers */}
        <div className="rounded-lg border border-border bg-surface p-3.5 shadow-sm lg:col-span-6">
          <div className="mb-3 flex items-center justify-between border-b border-border pb-2">
            <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-ink">
              <ShieldAlert size={14} className="text-warn-strong" />
              Primary Gate Blockers
            </span>
            <span className="text-[11px] text-ink-3">
              {data === null ? 'No data' : `${blockers.length} filter categories`}
            </span>
          </div>

          {data === null ? (
            <div className="flex h-36 flex-col items-center justify-center text-center text-xs text-ink-3">
              <AlertTriangle size={22} className="mb-1.5 text-warn-strong" />
              <span className="font-medium text-ink-2">No data — blocker telemetry unavailable.</span>
            </div>
          ) : blockers.length === 0 ? (
            <div className="flex h-36 flex-col items-center justify-center text-center text-xs text-ink-3">
              <CheckCircle2 size={22} className="mb-1.5 text-up" />
              <span className="font-medium text-ink-2">No gate rejections recorded in active session.</span>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {blockers.map((b) => (
                <div key={b.name} className="flex flex-col gap-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-ink">{b.name}</span>
                    <span className="mono text-xs text-ink-2">
                      <b className="font-bold text-ink">{b.count}</b> ({b.percentage}%)
                    </span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-inset">
                    <div
                      className="h-full rounded-full bg-warn transition-all duration-300"
                      style={{ width: `${Math.min(100, Math.max(4, b.percentage))}%` }}
                    />
                  </div>
                  <span className="text-[10px] text-ink-3 leading-tight">{b.description}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: Strategy Contribution Table */}
        <div className="rounded-lg border border-border bg-surface p-3.5 shadow-sm lg:col-span-6">
          <div className="mb-3 flex items-center justify-between border-b border-border pb-2">
            <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-ink">
              <BarChart3 size={14} className="text-accent" />
              Strategy Contribution Matrix
            </span>
            <span className="badge b-neut text-[10px]">
              {data === null
                ? 'No data'
                : `${strategies.filter((s) => s.enabled).length} Active Strategies`}
            </span>
          </div>

          {data === null ? (
            <p className="text-xs text-ink-3">No data — strategy performance unavailable.</p>
          ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border text-[10px] font-semibold uppercase tracking-wider text-ink-3">
                  <th className="pb-2 font-semibold">Strategy</th>
                  <th className="pb-2 text-center font-semibold">Desk</th>
                  <th className="pb-2 text-right font-semibold">Candidates</th>
                  <th className="pb-2 text-right font-semibold">Risk Ok</th>
                  <th className="pb-2 text-right font-semibold">Signals</th>
                  <th className="pb-2 text-right font-semibold">Win %</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle font-mono text-[11px]">
                {strategies.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-3 text-center font-sans text-ink-3">
                      No data — no strategy rows measured.
                    </td>
                  </tr>
                ) : null}
                {strategies.map((strat) => {
                  const isActive = strat.enabled;
                  return (
                    <tr
                      key={strat.strategy}
                      className={isActive ? 'hover:bg-hover' : 'opacity-40 hover:bg-hover'}
                    >
                      <td className="py-2 font-sans font-semibold text-ink">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`h-2 w-2 rounded-full ${
                              isActive ? 'bg-up' : 'bg-border-strong'
                            }`}
                          />
                          <span className="truncate max-w-[140px]" title={strat.strategy}>
                            {strat.strategy}
                          </span>
                        </div>
                      </td>
                      <td className="py-2 text-center font-sans">
                        <span
                          className={`badge ${
                            strat.desk === 'SCALP' ? 'b-warn' : 'b-neut'
                          } text-[9px] px-1.5 py-0 font-bold`}
                        >
                          {strat.desk}
                        </span>
                      </td>
                      <td className="py-2 text-right text-ink-2">{strat.candidates}</td>
                      <td className="py-2 text-right text-ink-2">{strat.risk_passed}</td>
                      <td className="py-2 text-right font-bold text-up-strong">{strat.confirmed}</td>
                      <td className="py-2 text-right text-ink-2">
                        {strat.total_trades > 0 ? `${strat.win_rate_pct.toFixed(0)}%` : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          )}
        </div>
      </div>

      {/* ── Collapsible Raw Rejection Codes ───────────────────── */}
      {rawRejections.length > 0 ? (
        <div className="rounded-lg border border-border bg-surface p-3 shadow-sm">
          <button
            type="button"
            className="flex w-full items-center justify-between text-xs font-semibold uppercase tracking-wider text-ink-2 hover:text-ink transition-colors"
            onClick={() => setShowRawRejections((prev) => !prev)}
          >
            <span className="flex items-center gap-1.5">
              <Layers size={13} className="text-accent" />
              Senior Quant Rejection Telemetry ({rawRejections.length} active codes)
            </span>
            {showRawRejections ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {showRawRejections ? (
            <div className="mt-3 grid grid-cols-1 gap-1.5 font-mono text-[11px] sm:grid-cols-2 lg:grid-cols-3">
              {rawRejections.map((item) => (
                <div
                  key={item.code}
                  className="flex items-center justify-between rounded border border-border bg-surface-subtle px-2.5 py-1.5"
                >
                  <span className="truncate text-ink-2" title={item.code}>
                    {item.code}
                  </span>
                  <span className="badge b-warn ml-2 font-mono font-bold text-[10px] px-1.5 py-0">
                    {item.count}
                  </span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
