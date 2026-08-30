'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { MarketRegimeOverview } from '@/lib/types';
import { RegimeBanner } from '@/components/markets/RegimeBanner';
import { KeyLevelsTable } from '@/components/markets/KeyLevelsTable';
import { IndicatorsGrid } from '@/components/markets/IndicatorsGrid';
import { VixRegimeCard } from '@/components/markets/VixRegimeCard';
import { Compass, Layers, Gauge, Activity } from 'lucide-react';

export default function MarketsPage() {
  const [selectedSymbol, setSelectedSymbol] = useState<string>('NIFTY');
  const [overview, setOverview] = useState<MarketRegimeOverview | null>(null);
  const [activeTab, setActiveTab] = useState<'all' | 'levels' | 'indicators' | 'vix'>('all');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    const fetchRegime = async () => {
      try {
        const res = await api.getRegimeOverview(selectedSymbol);
        if (!isMounted) return;
        setOverview(res.data);
        setError(null);
      } catch (err) {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : 'Failed to fetch market regime data');
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchRegime();
    const interval = setInterval(fetchRegime, 5000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [selectedSymbol]);

  return (
    <div className="space-y-4">
      {/* Top Banner & Regime Diagnosis */}
      <RegimeBanner
        overview={overview}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={(sym) => setSelectedSymbol(sym)}
      />

      {/* Navigation Sub-Tabs */}
      <div className="flex items-center gap-2 border-b border-border pb-2">
        <button
          onClick={() => setActiveTab('all')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
            activeTab === 'all'
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
          }`}
        >
          <Compass className="w-3.5 h-3.5" />
          Comprehensive Intelligence
        </button>

        <button
          onClick={() => setActiveTab('levels')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
            activeTab === 'levels'
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          Support & Resistance Ladder
        </button>

        <button
          onClick={() => setActiveTab('indicators')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
            activeTab === 'indicators'
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
          }`}
        >
          <Gauge className="w-3.5 h-3.5" />
          Technical Indicator Suite
        </button>

        <button
          onClick={() => setActiveTab('vix')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
            activeTab === 'vix'
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
          }`}
        >
          <Activity className="w-3.5 h-3.5" />
          India VIX Volatility Regime
        </button>
      </div>

      {/* Main Content Area */}
      {error ? (
        <div className="p-8 text-center bg-card border border-destructive/20 rounded-xl text-destructive">
          <p className="font-semibold text-sm">Error loading market regime intelligence</p>
          <p className="text-xs mt-1 opacity-80">{error}</p>
        </div>
      ) : loading && !overview ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center text-muted-foreground animate-pulse">
          Diagnosing market regime and computing support/resistance pivots...
        </div>
      ) : (
        <div className="space-y-4">
          {(activeTab === 'all' || activeTab === 'levels') && (
            <KeyLevelsTable
              keyLevels={overview?.key_levels || null}
              spotPrice={overview?.spot_price || 25000}
            />
          )}

          {(activeTab === 'all' || activeTab === 'indicators') && (
            <IndicatorsGrid
              indicators={overview?.indicators || null}
              spotPrice={overview?.spot_price || 25000}
            />
          )}

          {(activeTab === 'all' || activeTab === 'vix') && (
            <VixRegimeCard vixInfo={overview?.vix_regime || null} />
          )}
        </div>
      )}
    </div>
  );
}
