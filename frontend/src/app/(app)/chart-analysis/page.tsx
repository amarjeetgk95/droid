'use client';
import { useState, useEffect, Suspense, useRef } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { InstrumentSearch } from '@/components/chart-analysis/InstrumentSearch';
import { InstrumentHeader } from '@/components/chart-analysis/InstrumentHeader';
import { ChartNavigationBar } from '@/components/chart-analysis/ChartNavigationBar';
import { TechnicalAnalysisPanel } from '@/components/chart-analysis/TechnicalAnalysisPanel';
import { MultiTimeframePanel } from '@/components/chart-analysis/MultiTimeframePanel';
import { FNOContextPanel } from '@/components/chart-analysis/FNOContextPanel';
import { HistoricalSimilarity } from '@/components/chart-analysis/HistoricalSimilarity';
import { AIAnalysisPanel } from '@/components/chart-analysis/AIAnalysisPanel';
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

  const handleSelect = (sym: string) => {
    setSelected(sym);
    setActiveTf('15m');
    router.push(`/chart-analysis?symbol=${encodeURIComponent(sym)}`);
    fetchAnalysis(sym);
  };

  const handleTfChange = (tf: string) => {
    setActiveTf(tf);
    if (selected) fetchAnalysis(selected, tf);
  };

  return (
    <div className="space-y-4">
      {/* Refined navigation bar — from scratch */}
      <ChartNavigationBar activeTf={activeTf} onTfChange={handleTfChange} data={data} symbol={selected} loading={loading} />

      <div className="bg-card border border-border rounded-lg p-4">
        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-primary animate-pulse" aria-hidden />
          Instrument
        </h2>
        <InstrumentSearch onSelect={handleSelect} initialQuery={selected} />
        {selected && <p className="text-xs text-muted-foreground mt-2">Selected: <b>{selected}</b> — {activeTf} • preserved in URL</p>}
      </div>

      {loading && <div className="bg-card border border-border rounded p-8 text-center text-muted-foreground">Loading analysis for {selected}...</div>}
      {error && <div className="bg-destructive/10 border border-destructive/20 rounded p-4 text-destructive text-sm">{error}</div>}
      {data && (
        <>
          <InstrumentHeader data={data} />
          <TechnicalAnalysisPanel data={data} timeframe={activeTf} />
          <MultiTimeframePanel data={data} />
          <FNOContextPanel data={data} />
          <HistoricalSimilarity data={data} timeframe={activeTf} />
          <AIAnalysisPanel data={data} />
        </>
      )}
      {!data && !loading && !selected && (
        <div className="bg-card border border-border rounded-lg p-8 text-center text-muted-foreground">
          Search for an instrument above to load its technical & multi-timeframe analysis.
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
