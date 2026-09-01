'use client';
import { useState, useEffect, Suspense, useRef } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { InstrumentSearch } from '@/components/chart-analysis/InstrumentSearch';
import { InstrumentHeader } from '@/components/chart-analysis/InstrumentHeader';
import { useChartAnalysis } from '@/hooks/useChartAnalysis';

function ChartAnalysisInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const symbolParam = searchParams.get('symbol') || '';
  const [activeTf, setActiveTf] = useState<string>('15m');
  const { data, loading, error, fetchAnalysis } = useChartAnalysis();
  const [selected, setSelected] = useState(symbolParam);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (symbolParam) {
      setSelected(symbolParam);
      fetchAnalysis(symbolParam);
    }
  }, [symbolParam]);

  // Charts removed — keep live data fetch via useChartAnalysis if needed, but no chart polling
  // Realtime data is handled via central_feed WS (1s) and MarketCards; chart polling disabled

  const handleSelect = (sym: string) => {
    setSelected(sym);
    router.push(`/chart-analysis?symbol=${encodeURIComponent(sym)}`);
    fetchAnalysis(sym);
  };

  return (
    <div className="space-y-4">
      <div className="bg-card border border-border rounded-lg p-4">
        <h1 className="text-lg font-bold mb-3">Chart Analysis & Multi-Timeframe</h1>
        <InstrumentSearch onSelect={handleSelect} initialQuery={selected} />
        {selected && <p className="text-xs text-muted-foreground mt-2">Selected: <b>{selected}</b> — preserved in URL</p>}
      </div>

      {loading && <div className="bg-card border border-border rounded p-8 text-center text-muted-foreground">Loading analysis for {selected}...</div>}
      {error && <div className="bg-destructive/10 border border-destructive/20 rounded p-4 text-destructive text-sm">{error}</div>}
      {data && (
        <>
          <InstrumentHeader data={data} />
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-amber-900 text-sm">
            Charts removed — use TradingView for candles. Realtime data fetch active via Groww Feed (1s) + Binance WS.
          </div>
          <div className="bg-card border border-border rounded-lg p-4 space-y-2">
            <h3 className="font-semibold mb-2">Data Freshness & Realtime Status</h3>
            <p className="text-sm">{data.freshness} • Updated {data.data_age_seconds}s ago • Source: {data.exchange} • Asset: {data.asset_class} • Generated {new Date(data.generated_at).toLocaleTimeString()}</p>
            <p className="text-xs text-muted-foreground">Data timestamp: {data.data_timestamp ? new Date(data.data_timestamp).toLocaleString() : '—'} • Realtime via central_feed WS 1s (Groww licensed) + Binance WS</p>
          </div>
        </>
      )}
      {!data && !loading && !selected && (
        <div className="bg-card border border-border rounded-lg p-8 text-center text-muted-foreground">
          Search for an instrument above to load its chart and multi-timeframe analysis.
        </div>
      )}
    </div>
  );
}

export default function ChartAnalysisPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center">Loading...</div>}>
      <ChartAnalysisInner />
    </Suspense>
  );
}
