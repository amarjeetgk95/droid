'use client';
import { useState, useEffect, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { InstrumentSearch } from '@/components/chart-analysis/InstrumentSearch';
import { InstrumentHeader } from '@/components/chart-analysis/InstrumentHeader';
import { ForecastChart } from '@/components/chart-analysis/ForecastChart';
import { TimeframeForecast } from '@/components/chart-analysis/TimeframeForecast';
import { MultiTimeframePanel } from '@/components/chart-analysis/MultiTimeframePanel';
import { TechnicalAnalysisPanel } from '@/components/chart-analysis/TechnicalAnalysisPanel';
import { FNOContextPanel } from '@/components/chart-analysis/FNOContextPanel';
import { HistoricalSimilarity } from '@/components/chart-analysis/HistoricalSimilarity';
import { ForecastSummary } from '@/components/chart-analysis/ForecastSummary';
import { AIAnalysisPanel } from '@/components/chart-analysis/AIAnalysisPanel';
import { useChartAnalysis } from '@/hooks/useChartAnalysis';

function ChartAnalysisInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const symbolParam = searchParams.get('symbol') || '';
  const [activeTf, setActiveTf] = useState<string>('15m');
  const { data, loading, error, fetchAnalysis } = useChartAnalysis();
  const [selected, setSelected] = useState(symbolParam);

  useEffect(() => {
    if (symbolParam) {
      setSelected(symbolParam);
      fetchAnalysis(symbolParam);
    }
  }, [symbolParam]);

  const handleSelect = (sym: string) => {
    setSelected(sym);
    router.push(`/chart-analysis?symbol=${encodeURIComponent(sym)}`);
    fetchAnalysis(sym);
  };

  return (
    <div className="space-y-4">
      <div className="bg-card border border-border rounded-lg p-4">
        <h1 className="text-lg font-bold mb-3">Chart Forecast & Multi-Timeframe Analysis</h1>
        <InstrumentSearch onSelect={handleSelect} initialQuery={selected} />
        {selected && <p className="text-xs text-muted-foreground mt-2">Selected: <b>{selected}</b> — preserved in URL</p>}
      </div>

      {loading && <div className="bg-card border border-border rounded p-8 text-center text-muted-foreground">Loading analysis for {selected}...</div>}
      {error && <div className="bg-destructive/10 border border-destructive/20 rounded p-4 text-destructive text-sm">{error}</div>}
      {data && (
        <>
          <InstrumentHeader data={data} />
          <div className="flex gap-2">
            {['1m','5m','15m','1h'].map(tf => (
              <button key={tf} onClick={() => setActiveTf(tf)} className={`px-3 py-1 rounded text-sm border ${activeTf===tf?'bg-primary text-primary-foreground':'bg-card border-border'}`}>{tf}</button>
            ))}
          </div>
          <ForecastChart data={data} />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <TimeframeForecast data={data} />
            <MultiTimeframePanel data={data} />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <TechnicalAnalysisPanel data={data} timeframe={activeTf} />
            <FNOContextPanel data={data} />
          </div>
          <ForecastSummary data={data} />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <HistoricalSimilarity data={data} timeframe={activeTf} />
            <AIAnalysisPanel data={data} />
          </div>
          <div className="bg-card border border-border rounded-lg p-4">
            <h3 className="font-semibold mb-2">Data Freshness</h3>
            <p className="text-sm">{data.freshness} • Updated {data.data_age_seconds}s ago • Source: {data.exchange} • Asset: {data.asset_class}</p>
          </div>
        </>
      )}
      {!data && !loading && !selected && (
        <div className="bg-card border border-border rounded-lg p-8 text-center text-muted-foreground">
          Search for an instrument above to load its chart and multi-timeframe forecast.
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
