'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { MarketRegimeOverview } from '@/lib/types';
import { RegimeBanner } from '@/components/markets/RegimeBanner';
import { KeyLevelsTable } from '@/components/markets/KeyLevelsTable';
import { IndicatorsGrid } from '@/components/markets/IndicatorsGrid';
import { VixRegimeCard } from '@/components/markets/VixRegimeCard';
import { ErrorCard } from '@/components/ui/ErrorCard';

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

  return (
    <div className="space-y-4">
      {/* Top Banner & Regime Diagnosis */}
      <RegimeBanner
        overview={overview}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={(sym) => setSelectedSymbol(sym)}
      />

      {/* Main Content Area — stacked (was duplicate tabs: all == levels+indicators+vix) */}
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
        <div className="space-y-4">
          <section aria-label="Support and resistance">
            <KeyLevelsTable keyLevels={overview?.key_levels || null} spotPrice={spotPrice} />
          </section>
          <section aria-label="Technical indicators">
            <IndicatorsGrid indicators={overview?.indicators || null} spotPrice={spotPrice} />
          </section>
          <section aria-label="Volatility regime">
            <VixRegimeCard vixInfo={overview?.vix_regime || null} />
          </section>
        </div>
      )}
    </div>
  );
}
