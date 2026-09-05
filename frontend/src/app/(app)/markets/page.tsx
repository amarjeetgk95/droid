'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { MarketRegimeOverview } from '@/lib/types';
import { RegimeBanner } from '@/components/markets/RegimeBanner';
import { KeyLevelsTable } from '@/components/markets/KeyLevelsTable';
import { IndicatorsGrid } from '@/components/markets/IndicatorsGrid';
import { VixRegimeCard } from '@/components/markets/VixRegimeCard';
import { PageTabs } from '@/components/ui/PageTabs';
import { ErrorCard } from '@/components/ui/ErrorCard';
import { Compass, Layers, Gauge, Activity } from 'lucide-react';

export default function MarketsPage() {
  const [selectedSymbol, setSelectedSymbol] = useState<string>('NIFTY');
  const [overview, setOverview] = useState<MarketRegimeOverview | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRegime = async () => {
    if (typeof document !== 'undefined' && document.hidden) return;
    try {
      const res = await api.getRegimeOverview(selectedSymbol);
      setOverview(res.data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch market regime data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let isMounted = true;
    let timeout: ReturnType<typeof setTimeout> | null = null;

    setLoading(true);
    void fetchRegime();

    const schedule = () => {
      const jittered = 30000 * (0.8 + Math.random() * 0.4);
      timeout = setTimeout(async () => {
        if (!isMounted) return;
        await fetchRegime();
        schedule();
      }, jittered);
    };
    schedule();
    const onVis = () => { if (!document.hidden) void fetchRegime(); };
    document.addEventListener('visibilitychange', onVis);

    return () => {
      isMounted = false;
      if (timeout) clearTimeout(timeout);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [selectedSymbol]);

  const spotPrice = overview?.spot_price || 25000;

  const tabs = [
    {
      id: 'all',
      label: 'Comprehensive Intelligence',
      icon: Compass,
      content: (
        <div className="space-y-4">
          <KeyLevelsTable keyLevels={overview?.key_levels || null} spotPrice={spotPrice} />
          <IndicatorsGrid indicators={overview?.indicators || null} spotPrice={spotPrice} />
          <VixRegimeCard vixInfo={overview?.vix_regime || null} />
        </div>
      ),
    },
    {
      id: 'levels',
      label: 'Support & Resistance Ladder',
      icon: Layers,
      content: (
        <KeyLevelsTable keyLevels={overview?.key_levels || null} spotPrice={spotPrice} />
      ),
    },
    {
      id: 'indicators',
      label: 'Technical Indicator Suite',
      icon: Gauge,
      content: (
        <IndicatorsGrid indicators={overview?.indicators || null} spotPrice={spotPrice} />
      ),
    },
    {
      id: 'vix',
      label: 'India VIX Volatility Regime',
      icon: Activity,
      content: (
        <VixRegimeCard vixInfo={overview?.vix_regime || null} />
      ),
    },
  ];

  return (
    <div className="space-y-4">
      {/* Top Banner & Regime Diagnosis */}
      <RegimeBanner
        overview={overview}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={(sym) => setSelectedSymbol(sym)}
      />

      {/* Main Content Area */}
      {error ? (
        <ErrorCard
          title="Error loading market regime intelligence"
          message={error}
          mode="full-page"
          onRetry={() => {
            setLoading(true);
            void fetchRegime();
          }}
          isRetrying={loading}
        />
      ) : loading && !overview ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center text-muted-foreground animate-pulse">
          Diagnosing market regime and computing support/resistance pivots...
        </div>
      ) : (
        <PageTabs tabs={tabs} defaultTab="all" syncWithUrl />
      )}
    </div>
  );
}
