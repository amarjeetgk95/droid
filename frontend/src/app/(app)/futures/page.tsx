'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { FuturesOverview } from '@/lib/types';
import { FuturesHeader } from '@/components/futures/FuturesHeader';
import { TermStructureCard } from '@/components/futures/TermStructureCard';
import { OIBuildupMatrix } from '@/components/futures/OIBuildupMatrix';
import { RolloverTracker } from '@/components/futures/RolloverTracker';
import { Layers, Activity, RefreshCw } from 'lucide-react';

export default function FuturesPage() {
  const [selectedSymbol, setSelectedSymbol] = useState<string>('NIFTY');
  const [overview, setOverview] = useState<FuturesOverview | null>(null);
  const [activeTab, setActiveTab] = useState<'all' | 'term' | 'buildup' | 'rollover'>('all');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    const fetchFutures = async () => {
      try {
        const res = await api.getFuturesOverview(selectedSymbol);
        if (!isMounted) return;
        setOverview(res.data);
        setError(null);
      } catch (err) {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : 'Failed to fetch futures data');
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchFutures();
    const interval = setInterval(fetchFutures, 5000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [selectedSymbol]);

  return (
    <div className="space-y-4">
      {/* Top Header & Core Metrics */}
      <FuturesHeader
        overview={overview}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={(sym) => setSelectedSymbol(sym)}
        autoRefresh={true}
        onToggleRefresh={() => {}}
      />

      {/* Tabs Filter */}
      <div className="flex items-center gap-2 border-b border-border pb-2">
        <button
          onClick={() => setActiveTab('all')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
            activeTab === 'all'
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
          }`}
        >
          Comprehensive Dashboard
        </button>

        <button
          onClick={() => setActiveTab('term')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
            activeTab === 'term'
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          Term Structure & Basis
        </button>

        <button
          onClick={() => setActiveTab('buildup')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
            activeTab === 'buildup'
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
          }`}
        >
          <Activity className="w-3.5 h-3.5" />
          OI Buildup Engine
        </button>

        <button
          onClick={() => setActiveTab('rollover')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
            activeTab === 'rollover'
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
          }`}
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Rollover Tracker
        </button>
      </div>

      {/* Main Content Area */}
      {error ? (
        <div className="p-8 text-center bg-card border border-destructive/20 rounded-xl text-destructive">
          <p className="font-semibold text-sm">Error loading futures analytics</p>
          <p className="text-xs mt-1 opacity-80">{error}</p>
        </div>
      ) : loading && !overview ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center text-muted-foreground animate-pulse">
          Modeling futures term structure and calculating cost of carry...
        </div>
      ) : (
        <div className="space-y-4">
          {(activeTab === 'all' || activeTab === 'term') && (
            <TermStructureCard termStructure={overview?.term_structure || null} />
          )}

          {(activeTab === 'all' || activeTab === 'buildup') && (
            <OIBuildupMatrix
              buildup={overview?.buildup || null}
              allTrackedBuildups={overview?.all_tracked_buildups || []}
            />
          )}

          {(activeTab === 'all' || activeTab === 'rollover') && (
            <RolloverTracker rollover={overview?.rollover || null} />
          )}
        </div>
      )}
    </div>
  );
}
