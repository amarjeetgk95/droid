/* eslint-disable react-hooks/set-state-in-effect */
'use client';

import * as React from 'react';
import { RefreshCw, Lightbulb, TrendingUp, TrendingDown, Minus, X, Check, Sparkles } from 'lucide-react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { api } from '@/lib/api';
import type {
  HpiAnalysis, HpiStorageReport, HpiUniverse,
  PatternHitRate, PatternHitRateResponse, PatternOutcomeRecord,
} from '@/lib/types';
import { coverageStatus, biasTone } from '@/lib/historical-intelligence/labels';
import { fmtPct, fmtRatio, fmtNumber, fmtDate } from '@/lib/historical-intelligence/format';
import { Panel } from './Panel';
import { StatusPill } from './StatusPill';
import { EmptyState } from './EmptyState';
import { BiasBar } from './BiasBar';
import { Skeleton } from './Skeleton';

interface Props {
  universe: HpiUniverse | null;
  report: HpiStorageReport | null;
  refreshKey: number;
}

const BIAS_ICON: Record<string, React.ReactNode> = {
  BULLISH: <TrendingUp className="w-3 h-3" />,
  BEARISH: <TrendingDown className="w-3 h-3" />,
  NEUTRAL: <Minus className="w-3 h-3" />,
};

export function HiPatterns({ universe, report, refreshKey }: { universe: HpiUniverse | null; report: HpiStorageReport | null; refreshKey: number }) {
  const available = (report?.datasets ?? [])
    .filter((d) => d.enabled && d.records_stored > 0)
    .map((d) => d.symbol);

  const [symbol, setSymbol] = React.useState<string>('');

  React.useEffect(() => {
    if (available.length > 0 && (!symbol || !available.includes(symbol))) {
      setSymbol(available[0]);
    } else if (!symbol && universe?.derivatives.length) {
      setSymbol(universe.derivatives[0].symbol);
    }
  }, [available, symbol, universe]);

  return (
    <Panel
      title="Patterns"
      description="Similarity setups and detected-pattern outcomes"
      actions={
        symbol ? (
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="bg-secondary/50 border border-border rounded-md px-2 py-1 text-xs"
            aria-label="Select derivative"
          >
            {(universe?.derivatives ?? []).map((d) => (
              <option key={d.symbol} value={d.symbol}>{d.display_name}</option>
            ))}
          </select>
        ) : null
      }
      bare
    >
      <div className="px-4 sm:px-5 pb-4 sm:pb-5">
        <Tabs defaultValue="similarity">
          <TabsList>
            <TabsTrigger value="similarity"><Sparkles className="w-3.5 h-3.5" /> Similarity</TabsTrigger>
            <TabsTrigger value="outcomes">Outcomes & hit rates</TabsTrigger>
          </TabsList>

          <TabsContent value="similarity" className="mt-4">
            <SimilarityPanel symbol={symbol} refreshKey={refreshKey} />
          </TabsContent>

          <TabsContent value="outcomes" className="mt-4">
            <OutcomesPanel symbol={symbol} refreshKey={refreshKey} />
          </TabsContent>
        </Tabs>
      </div>
    </Panel>
  );
}

function SimilarityPanel({ symbol, refreshKey }: { symbol: string; refreshKey: number }) {
  const [analysis, setAnalysis] = React.useState<HpiAnalysis | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async (sym: string) => {
    setLoading(true); setError(null);
    try {
      const res = await api.getHpiAnalysis(sym);
      setAnalysis(res.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (symbol) load(symbol);
  }, [symbol, refreshKey, load]);

  if (loading && !analysis) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (analysis?.derivative_coverage === 'DISABLED') {
    return (
      <EmptyState
        icon={<Lightbulb className="w-5 h-5 text-amber-600" />}
        title={`${analysis.symbol} is disabled`}
        description="Enable the derivative in the Datasets section and import historical data, then come back here for similarity analysis."
      />
    );
  }

  if (analysis?.derivative_coverage === 'MISSING') {
    return (
      <EmptyState
        icon={<Lightbulb className="w-5 h-5 text-amber-600" />}
        title={`No data for ${analysis.symbol}`}
        description="Import at least one data category in the Datasets section to enable similarity analysis."
      />
    );
  }

  if (!analysis) return null;

  const cov = coverageStatus(analysis.derivative_coverage);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 text-xs">
        <Stat label="Coverage" value={analysis.historical_coverage_label} sub={`${analysis.historical_coverage_months.toFixed(1)} months`} />
        <Stat label="Similar setups" value={fmtNumber(analysis.similar_setups)} />
        <Stat label="Confidence" value={`${analysis.confidence}%`} />
        <Stat label="Derivative" value={<StatusPill tone={cov.tone} label={analysis.derivative_coverage} />} sub={analysis.missing_dataset ?? undefined} />
      </div>

      {analysis.warnings.length > 0 && (
        <ul className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-xs space-y-1">
          {analysis.warnings.map((w) => (
            <li key={w} className="text-amber-600">{w}</li>
          ))}
        </ul>
      )}

      {analysis.coverage_report.deleted_ranges.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground mb-1">Deleted ranges (never reconstructed)</p>
          <ul className="list-disc list-inside text-[11px] text-muted-foreground">
            {analysis.coverage_report.deleted_ranges.map((r) => <li key={r}>{r}</li>)}
          </ul>
        </div>
      )}

      {analysis.setups.length === 0 ? (
        <EmptyState title="No similar setups" description="Not enough historical context yet to find similar patterns." />
      ) : (
        <ul className="space-y-2">
          {analysis.setups.map((s, idx) => (
            <li key={idx} className="rounded-lg border border-border bg-background p-3">
              <div className="flex items-center gap-2 text-xs">
                <span className="font-mono font-semibold">{s.signature}</span>
                <span className="text-muted-foreground">similarity {(s.similarity * 100).toFixed(1)}%</span>
                <span className="ml-auto font-mono tabular-nums font-bold">{fmtPct(s.avg_forward_move_pct, 2, true)}</span>
              </div>
              <div className="mt-2">
                <BiasBar bullish={s.bullish_pct} neutral={s.neutral_pct} bearish={s.bearish_pct} />
              </div>
            </li>
          ))}
        </ul>
      )}

      {analysis.note && <p className="text-xs text-muted-foreground">{analysis.note}</p>}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}

function OutcomesPanel({ symbol, refreshKey }: { symbol: string; refreshKey: number }) {
  const [hitRates, setHitRates] = React.useState<PatternHitRateResponse | null>(null);
  const [outcomes, setOutcomes] = React.useState<PatternOutcomeRecord[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [hr, oc] = await Promise.all([
        api.getPatternHitRates(symbol),
        api.getPatternOutcomes(symbol, undefined, undefined, 30),
      ]);
      setHitRates(hr.data);
      setOutcomes(oc.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load outcomes');
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  React.useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [symbol, refreshKey, load]);

  const trigger = async () => {
    setBusy(true); setError(null);
    try {
      const res = await api.labelPatternOutcomes(symbol);
      setError(`Labeled ${res.data.labeled_count} new pattern outcomes.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to label outcomes');
    } finally {
      setBusy(false);
    }
  };

  if (loading && !hitRates) return <Skeleton className="h-48 w-full" />;

  const labelingRate = hitRates && hitRates.total_patterns_tracked > 0
    ? (hitRates.total_labeled_outcomes / hitRates.total_patterns_tracked) * 100
    : 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Stat label="Patterns tracked" value={String(hitRates?.total_patterns_tracked ?? 0)} />
        <Stat label="Labeled outcomes" value={String(hitRates?.total_labeled_outcomes ?? 0)} />
        <Stat label="Labeling rate" value={`${labelingRate.toFixed(1)}%`} />
        <button
          onClick={trigger}
          disabled={busy}
          className="ml-auto inline-flex items-center gap-1 px-3 py-1.5 rounded-md border border-border text-xs font-medium hover:bg-secondary disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${busy ? 'animate-spin' : ''}`} /> Label outcomes
        </button>
      </div>

      {error && <p className="text-xs text-amber-600">{error}</p>}

      {hitRates && hitRates.hit_rates.length > 0 ? (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-xs">
            <thead className="bg-muted/50 sticky top-0">
              <tr>
                <th className="text-left p-2 font-medium">Pattern</th>
                <th className="text-left p-2 font-medium">Bias</th>
                <th className="text-right p-2 font-medium">Samples</th>
                <th className="text-right p-2 font-medium">1D</th>
                <th className="text-right p-2 font-medium">3D</th>
                <th className="text-right p-2 font-medium">5D</th>
                <th className="text-right p-2 font-medium">Target hit</th>
                <th className="text-right p-2 font-medium">Dir. acc.</th>
                <th className="text-right p-2 font-medium">TF</th>
              </tr>
            </thead>
            <tbody>
              {hitRates.hit_rates.map((hr, idx) => <HitRateRow key={idx} hr={hr} />)}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          icon={<Lightbulb className="w-5 h-5 text-amber-600" />}
          title="No pattern outcomes tracked yet"
          description="Patterns get tracked automatically when detected. Click 'Label outcomes' to compute forward returns."
        />
      )}

      {outcomes.length > 0 && (
        <details className="rounded-md border border-border bg-muted/30">
          <summary className="cursor-pointer text-xs font-semibold p-3 select-none">Recent outcomes ({outcomes.length})</summary>
          <div className="overflow-x-auto border-t border-border">
            <table className="w-full text-xs">
              <thead className="bg-muted/50">
                <tr>
                  <th className="text-left p-2 font-medium">Pattern</th>
                  <th className="text-left p-2 font-medium">Bias</th>
                  <th className="text-right p-2 font-medium">Conf.</th>
                  <th className="text-right p-2 font-medium">Detected</th>
                  <th className="text-right p-2 font-medium">1D</th>
                  <th className="text-right p-2 font-medium">3D</th>
                  <th className="text-right p-2 font-medium">5D</th>
                  <th className="text-center p-2 font-medium">Hit</th>
                </tr>
              </thead>
              <tbody>
                {outcomes.slice(0, 20).map((o) => (
                  <tr key={o.id} className="border-t border-border/60 hover:bg-background/50">
                    <td className="p-2 font-mono">{o.pattern_name}</td>
                    <td className="p-2"><StatusPill tone={biasTone(o.bias)} icon={BIAS_ICON[o.bias]} label={o.bias} /></td>
                    <td className="p-2 text-right tabular-nums">{o.confidence.toFixed(0)}%</td>
                    <td className="p-2 text-right tabular-nums text-muted-foreground">{fmtDate(o.detection_timestamp)}</td>
                    <td className="p-2 text-right tabular-nums">{fmtPct(o.outcome_1d, 2, true)}</td>
                    <td className="p-2 text-right tabular-nums">{fmtPct(o.outcome_3d, 2, true)}</td>
                    <td className="p-2 text-right tabular-nums">{fmtPct(o.outcome_5d, 2, true)}</td>
                    <td className="p-2 text-center">
                      {o.hit_target_before_invalidation === true && <Check className="w-3.5 h-3.5 text-green-600 inline" />}
                      {o.hit_target_before_invalidation === false && <X className="w-3.5 h-3.5 text-red-500 inline" />}
                      {o.hit_target_before_invalidation === null && <span className="text-muted-foreground">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}

function HitRateRow({ hr }: { hr: PatternHitRate }) {
  return (
    <tr className="border-t border-border/60 hover:bg-background/50">
      <td className="p-2 font-mono">{hr.pattern_name}</td>
      <td className="p-2"><StatusPill tone={biasTone(hr.bias)} icon={BIAS_ICON[hr.bias]} label={hr.bias} /></td>
      <td className="p-2 text-right tabular-nums">{hr.sample_count}</td>
      <td className="p-2 text-right tabular-nums">{fmtPct(hr.avg_return_1d, 2, true)}</td>
      <td className="p-2 text-right tabular-nums">{fmtPct(hr.avg_return_3d, 2, true)}</td>
      <td className="p-2 text-right tabular-nums">{fmtPct(hr.avg_return_5d, 2, true)}</td>
      <td className="p-2 text-right tabular-nums">{fmtRatio(hr.hit_target_rate)}</td>
      <td className="p-2 text-right tabular-nums">{fmtRatio(hr.directional_accuracy)}</td>
      <td className="p-2 text-right tabular-nums text-muted-foreground">{hr.timeframe}</td>
    </tr>
  );
}

function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="rounded-md bg-muted/50 px-3 py-2 text-xs">
      <p className="text-[10px] text-muted-foreground">{label}</p>
      <p className="font-bold mt-0.5">{value}</p>
      {sub && <p className="text-[10px] text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}