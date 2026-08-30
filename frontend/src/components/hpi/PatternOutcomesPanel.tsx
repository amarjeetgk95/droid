'use client';

import { useEffect, useState } from 'react';
import { RefreshCw, AlertTriangle, Lightbulb, TrendingUp, TrendingDown, Minus, Target, X, Check } from 'lucide-react';
import { api } from '@/lib/api';
import type { PatternHitRate, PatternHitRateResponse, PatternOutcomeRecord } from '@/lib/types';

const BIAS_COLORS: Record<string, string> = {
  BULLISH: 'text-green-600 bg-green-500/10',
  BEARISH: 'text-red-500 bg-red-500/10',
  NEUTRAL: 'text-amber-600 bg-amber-500/10',
};

const BIAS_ICONS: Record<string, React.ReactNode> = {
  BULLISH: <TrendingUp className="w-3.5 h-3.5" />,
  BEARISH: <TrendingDown className="w-3.5 h-3.5" />,
  NEUTRAL: <Minus className="w-3.5 h-3.5" />,
};

interface Props {
  symbol: string;
  refreshKey?: number;
}

export function PatternOutcomesPanel({ symbol, refreshKey }: Props) {
  const [hitRates, setHitRates] = useState<PatternHitRateResponse | null>(null);
  const [outcomes, setOutcomes] = useState<PatternOutcomeRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingOutcomes, setLoadingOutcomes] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'hit-rates' | 'outcomes'>('hit-rates');

  const loadHitRates = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getPatternHitRates(symbol);
      setHitRates(res.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load hit rates');
    } finally {
      setLoading(false);
    }
  };

  const loadOutcomes = async () => {
    setLoadingOutcomes(true);
    try {
      const res = await api.getPatternOutcomes(symbol, undefined, undefined, 30);
      setOutcomes(res.data);
    } catch (err) {
      console.error('Failed to load outcomes:', err);
    } finally {
      setLoadingOutcomes(false);
    }
  };

  const triggerLabeling = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.labelPatternOutcomes(symbol);
      setError(`Labeled ${res.data.labeled_count} patterns`);
      setTimeout(() => setError(null), 3000);
      loadHitRates();
      loadOutcomes();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to label outcomes');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHitRates();
    loadOutcomes();
  }, [symbol, refreshKey]);

  const formatPct = (val: number | null | undefined) => {
    if (val === null || val === undefined) return '—';
    return `${val > 0 ? '+' : ''}${val.toFixed(2)}%`;
  };

  const formatRate = (val: number | null | undefined) => {
    if (val === null || val === undefined) return '—';
    return `${(val * 100).toFixed(1)}%`;
  };

  const getBiasClass = (bias: string) => BIAS_COLORS[bias] || 'text-muted-foreground bg-muted/50';

  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-base font-bold">Pattern Outcomes — {symbol}</h2>
        <div className="ml-auto flex items-center gap-1.5">
          <button
            onClick={loadHitRates}
            className="p-1.5 rounded-md border border-border hover:bg-secondary"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={triggerLabeling}
            disabled={loading}
            className="px-2 py-1 rounded-md border border-border hover:bg-secondary text-xs font-medium"
            title="Label outcomes now (on-demand)"
          >
            Label Outcomes
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-3 text-xs text-amber-600 flex items-center gap-1 bg-amber-500/5 border border-amber-500/30 rounded-lg p-2">
          <AlertTriangle className="w-3.5 h-3.5" />
          {error}
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex gap-1 mb-3 border-b border-border">
        <button
          onClick={() => setActiveTab('hit-rates')}
          className={`px-3 py-1.5 text-xs font-medium rounded-t transition-colors ${
            activeTab === 'hit-rates' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-secondary/50'
          }`}
        >
          Hit Rates ({hitRates?.hit_rates.length ?? 0})
        </button>
        <button
          onClick={() => setActiveTab('outcomes')}
          className={`px-3 py-1.5 text-xs font-medium rounded-t transition-colors ${
            activeTab === 'outcomes' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-secondary/50'
          }`}
        >
          Recent Outcomes ({outcomes.length})
        </button>
      </div>

      {/* Hit Rates Tab */}
      {activeTab === 'hit-rates' && (
        <div>
          {loading && !hitRates && <p className="text-xs text-muted-foreground">Loading…</p>}

          {!loading && hitRates && hitRates.hit_rates.length === 0 && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-center">
              <Lightbulb className="w-4 h-4 mx-auto mb-1 text-amber-600" />
              <p className="font-semibold text-amber-600">No pattern outcomes tracked yet</p>
              <p className="text-muted-foreground mt-1">
                Patterns are automatically tracked when detected. Click "Label Outcomes" to compute
                forward returns for existing unlabeled patterns, or run pattern scans to accumulate data.
              </p>
            </div>
          )}

          {!loading && hitRates && hitRates.hit_rates.length > 0 && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3 text-xs">
                <div className="bg-muted rounded p-2">
                  <div className="text-[10px] text-muted-foreground">Patterns Tracked</div>
                  <div className="font-bold">{hitRates.total_patterns_tracked}</div>
                </div>
                <div className="bg-muted rounded p-2">
                  <div className="text-[10px] text-muted-foreground">Labeled Outcomes</div>
                  <div className="font-bold">{hitRates.total_labeled_outcomes}</div>
                </div>
                <div className="bg-muted rounded p-2">
                  <div className="text-[10px] text-muted-foreground">Labeling Rate</div>
                  <div className="font-bold">
                    {hitRates.total_patterns_tracked > 0
                      ? `${((hitRates.total_labeled_outcomes / hitRates.total_patterns_tracked) * 100).toFixed(1)}%`
                      : '0%'}
                  </div>
                </div>
                <div className="bg-muted rounded p-2">
                  <div className="text-[10px] text-muted-foreground">Symbols</div>
                  <div className="font-bold">{hitRates.symbol}</div>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-[11px]">
                  <thead>
                    <tr className="text-left text-muted-foreground border-b border-border">
                      <th className="pb-1 pr-3">Pattern</th>
                      <th className="pb-1 pr-3 text-right">Bias</th>
                      <th className="pb-1 pr-3 text-right">Samples</th>
                      <th className="pb-1 pr-3 text-right">1D Avg</th>
                      <th className="pb-1 pr-3 text-right">3D Avg</th>
                      <th className="pb-1 pr-3 text-right">5D Avg</th>
                      <th className="pb-1 pr-3 text-right">Target Hit</th>
                      <th className="pb-1 pr-3 text-right">Dir. Acc.</th>
                      <th className="pb-1 text-right">Timeframe</th>
                    </tr>
                  </thead>
                  <tbody>
                    {hitRates.hit_rates.map((hr, idx) => (
                      <tr key={idx} className="border-b border-border/50 hover:bg-muted/50">
                        <td className="py-1.5 pr-3 font-mono text-sm">
                          {hr.pattern_name}
                          <span className="ml-1.5 px-1 text-[9px] rounded bg-muted/50 text-muted-foreground">
                            {hr.pattern_type}
                          </span>
                        </td>
                        <td className="py-1.5 pr-3 text-right">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${getBiasClass(hr.bias)} flex items-center gap-1 justify-end`}>
                            {BIAS_ICONS[hr.bias] || ''}
                            {hr.bias}
                          </span>
                        </td>
                        <td className="py-1.5 pr-3 text-right font-mono">{hr.sample_count}</td>
                        <td className="py-1.5 pr-3 text-right font-mono">
                          {formatPct(hr.avg_return_1d)}
                          {hr.stddev_return_1d !== null && hr.stddev_return_1d !== undefined && (
                            <span className="ml-1 text-[9px] text-muted-foreground">±{hr.stddev_return_1d.toFixed(2)}%</span>
                          )}
                        </td>
                        <td className="py-1.5 pr-3 text-right font-mono">{formatPct(hr.avg_return_3d)}</td>
                        <td className="py-1.5 pr-3 text-right font-mono">{formatPct(hr.avg_return_5d)}</td>
                        <td className="py-1.5 pr-3 text-right font-mono">
                          {formatRate(hr.hit_target_rate)}
                          <Target className="w-3 h-3 ml-1 inline-block text-muted-foreground" />
                        </td>
                        <td className="py-1.5 pr-3 text-right font-mono">{formatRate(hr.directional_accuracy)}</td>
                        <td className="py-1.5 text-right text-muted-foreground font-mono">{hr.timeframe}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {/* Recent Outcomes Tab */}
      {activeTab === 'outcomes' && (
        <div>
          {loadingOutcomes && <p className="text-xs text-muted-foreground">Loading…</p>}

          {!loadingOutcomes && outcomes.length === 0 && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-center">
              <Lightbulb className="w-4 h-4 mx-auto mb-1 text-amber-600" />
              <p className="font-semibold text-amber-600">No labeled outcomes yet</p>
              <p className="text-muted-foreground mt-1">
                Run "Label Outcomes" to compute forward returns for tracked patterns.
              </p>
            </div>
          )}

          {!loadingOutcomes && outcomes.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-left text-muted-foreground border-b border-border">
                    <th className="pb-1 pr-3">Pattern</th>
                    <th className="pb-1 pr-3 text-right">Bias</th>
                    <th className="pb-1 pr-3 text-right">Conf.</th>
                    <th className="pb-1 pr-3 text-right">Detected</th>
                    <th className="pb-1 pr-3 text-right">Trigger</th>
                    <th className="pb-1 pr-3 text-right">Target</th>
                    <th className="pb-1 pr-3 text-right">Invalid.</th>
                    <th className="pb-1 pr-3 text-right">1D</th>
                    <th className="pb-1 pr-3 text-right">3D</th>
                    <th className="pb-1 pr-3 text-right">5D</th>
                    <th className="pb-1 pr-3 text-right">Target Hit</th>
                    <th className="pb-1 text-right">TF</th>
                  </tr>
                </thead>
                <tbody>
                  {outcomes.map((o, idx) => (
                    <tr key={idx} className="border-b border-border/50 hover:bg-muted/50">
                      <td className="py-1.5 pr-3 font-mono text-sm">
                        {o.pattern_name}
                      </td>
                      <td className="py-1.5 pr-3 text-right">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${getBiasClass(o.bias)} flex items-center gap-1 justify-end`}>
                          {BIAS_ICONS[o.bias] || ''}
                          {o.bias}
                        </span>
                      </td>
                      <td className="py-1.5 pr-3 text-right font-mono">{o.confidence.toFixed(0)}%</td>
                      <td className="py-1.5 pr-3 text-right text-muted-foreground font-mono">
                        {new Date(o.detection_timestamp).toLocaleDateString()}
                      </td>
                      <td className="py-1.5 pr-3 text-right font-mono">{o.trigger_price.toFixed(2)}</td>
                      <td className="py-1.5 pr-3 text-right font-mono">{o.target_level.toFixed(2)}</td>
                      <td className="py-1.5 pr-3 text-right font-mono">{o.invalidation_level.toFixed(2)}</td>
                      <td className="py-1.5 pr-3 text-right font-mono">
                        {o.outcome_1d !== null && o.outcome_1d !== undefined
                          ? formatPct(o.outcome_1d)
                          : <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="py-1.5 pr-3 text-right font-mono">
                        {o.outcome_3d !== null && o.outcome_3d !== undefined
                          ? formatPct(o.outcome_3d)
                          : <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="py-1.5 pr-3 text-right font-mono">
                        {o.outcome_5d !== null && o.outcome_5d !== undefined
                          ? formatPct(o.outcome_5d)
                          : <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="py-1.5 pr-3 text-right">
                        {o.hit_target_before_invalidation === true && <Check className="w-4 h-4 mx-auto text-green-600" />}
                        {o.hit_target_before_invalidation === false && <X className="w-4 h-4 mx-auto text-red-500" />}
                        {o.hit_target_before_invalidation === null && o.outcome_labeled_at && <span className="text-muted-foreground">—</span>}
                        {o.hit_target_before_invalidation === null && !o.outcome_labeled_at && <span className="text-muted-foreground">pending</span>}
                      </td>
                      <td className="py-1.5 text-right text-muted-foreground font-mono">{o.timeframe}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}