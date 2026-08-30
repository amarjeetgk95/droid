'use client';

import { useEffect, useState } from 'react';
import { RefreshCw, AlertTriangle } from 'lucide-react';
import { api } from '@/lib/api';
import type { HpiAnalysis, HpiUniverse } from '@/lib/types';

const STATUS_COLORS: Record<string, string> = {
  FULL: 'bg-green-500/10 text-green-600',
  PARTIAL: 'bg-amber-500/10 text-amber-600',
  MISSING: 'bg-red-500/10 text-red-500',
  DISABLED: 'bg-muted text-muted-foreground',
};

export function PatternAnalysisPanel({ universe, refreshKey }: { universe: HpiUniverse | null; refreshKey: number }) {
  const [symbol, setSymbol] = useState('NIFTY');
  const [analysis, setAnalysis] = useState<HpiAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const res = await api.getHpiAnalysis(symbol);
      setAnalysis(res.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [symbol, refreshKey]);

  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-base font-bold">Historical Pattern Intelligence</h2>
        <select value={symbol} onChange={(e) => setSymbol(e.target.value)}
          className="ml-auto bg-secondary/50 border border-border rounded-lg px-2 py-1 text-xs">
          {(universe?.derivatives ?? []).map((d) => <option key={d.symbol} value={d.symbol}>{d.display_name}</option>)}
        </select>
        <button onClick={load} className="p-1.5 rounded-md border border-border hover:bg-secondary" title="Refresh">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {error && <p className="text-xs text-red-500 mb-2">{error}</p>}
      {!analysis && !error && <p className="text-xs text-muted-foreground">No analysis yet.</p>}

      {analysis && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
            <div className="bg-muted rounded p-2">
              <div className="text-[10px] text-muted-foreground">Historical Coverage</div>
              <div className="font-bold text-sm">{analysis.historical_coverage_label}</div>
            </div>
            <div className="bg-muted rounded p-2">
              <div className="text-[10px] text-muted-foreground">Similar Setups</div>
              <div className="font-bold text-sm">{analysis.similar_setups.toLocaleString()}</div>
            </div>
            <div className="bg-muted rounded p-2">
              <div className="text-[10px] text-muted-foreground">Confidence</div>
              <div className="font-bold text-sm">{analysis.confidence}%</div>
            </div>
            <div className="bg-muted rounded p-2">
              <div className="text-[10px] text-muted-foreground">Derivative Coverage</div>
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${STATUS_COLORS[analysis.derivative_coverage] ?? ''}`}>
                {analysis.derivative_coverage}
              </span>
              {analysis.missing_dataset && <div className="text-[10px] text-amber-600 mt-0.5">Missing: {analysis.missing_dataset}</div>}
            </div>
          </div>

          {analysis.warnings.length > 0 && (
            <div className="mb-3 space-y-1">
              {analysis.warnings.map((w) => (
                <p key={w} className="text-xs text-amber-600 flex items-start gap-1"><AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />{w}</p>
              ))}
            </div>
          )}
          {analysis.note && <p className="text-xs text-muted-foreground mb-3">{analysis.note}</p>}

          {analysis.coverage_report.deleted_ranges.length > 0 && (
            <div className="mb-3">
              <h3 className="text-xs font-bold mb-1">Deleted ranges (never reconstructed)</h3>
              <ul className="text-[11px] text-muted-foreground list-disc list-inside">
                {analysis.coverage_report.deleted_ranges.map((r) => <li key={r}>{r}</li>)}
              </ul>
            </div>
          )}

          {analysis.setups.length > 0 && (
            <div>
              <h3 className="text-xs font-bold mb-1">Most similar historical setups</h3>
              <div className="space-y-1">
                {analysis.setups.map((s, idx) => (
                  <div key={idx} className="flex items-center gap-3 text-[11px] bg-muted/50 rounded px-2 py-1">
                    <span className="font-mono">{s.signature}</span>
                    <span className="text-muted-foreground">similarity {(s.similarity * 100).toFixed(1)}%</span>
                    <span className="ml-auto">
                      <span className="text-green-600">{s.bullish_pct}% bull</span> · <span>{s.neutral_pct}% neutral</span> · <span className="text-red-500">{s.bearish_pct}% bear</span>
                    </span>
                    <span className="text-muted-foreground">fwd {s.avg_forward_move_pct > 0 ? '+' : ''}{s.avg_forward_move_pct}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
