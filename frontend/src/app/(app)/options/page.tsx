'use client';

import { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { api } from '@/lib/api';
import { OptionChainResponse, MaxPainResult } from '@/lib/types';
import { OptionsHeader } from '@/components/options/OptionsHeader';
import { OptionChainTable } from '@/components/options/OptionChainTable';
import { PayoffChart } from '@/components/options/PayoffChart';
import { IVSmileChart } from '@/components/options/IVSmileChart';
import { Layers, Target, Activity, ShieldAlert } from 'lucide-react';

// Tab-conditional flow tracker loads only when its tab is selected.
const InstitutionalFlowTracker = dynamic(
  () => import('@/components/options/InstitutionalFlowTracker').then((m) => m.InstitutionalFlowTracker),
  { ssr: false, loading: () => <div className="bg-card border border-border rounded-xl p-5 h-48 animate-pulse" /> },
);

export default function OptionsPage() {
  const [selectedSymbol, setSelectedSymbol] = useState<string>('NIFTY');
  const [selectedExpiry, setSelectedExpiry] = useState<string>('');
  const [viewMode, setViewMode] = useState<'standard' | 'greeks'>('standard');
  const [activeTab, setActiveTab] = useState<'chain' | 'institutional_flow' | 'max_pain' | 'iv_smile'>('chain');

  const [chainData, setChainData] = useState<OptionChainResponse | null>(null);
  const [maxPainData, setMaxPainData] = useState<MaxPainResult | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Chain + MaxPain have no data dependency once the expiry is known, so
  // fetch them in parallel. When no expiry is selected yet, resolve it from
  // a single chain call first — the resulting setSelectedExpiry triggers one
  // parallel re-run (instead of the old sequential chain→maxPain waterfall
  // that ran twice per symbol change). Stale responses from rapid
  // symbol/expiry switches are dropped via isMounted.
  useEffect(() => {
    let isMounted = true;

    const run = async () => {
      try {
        if (!selectedExpiry) {
          const chainRes = await api.getOptionChain(selectedSymbol, undefined);
          if (!isMounted) return;
          setChainData(chainRes.data);

          if (chainRes.data.expiry) {
            setSelectedExpiry(chainRes.data.expiry);
          } else {
            const mpRes = await api.getMaxPain(selectedSymbol, undefined);
            if (!isMounted) return;
            setMaxPainData(mpRes.data);
          }

          setError(null);
          return;
        }

        const [chainRes, mpRes] = await Promise.all([
          api.getOptionChain(selectedSymbol, selectedExpiry),
          api.getMaxPain(selectedSymbol, selectedExpiry),
        ]);
        if (!isMounted) return;
        setChainData(chainRes.data);
        setMaxPainData(mpRes.data);

        setError(null);
      } catch (err) {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : 'Failed to fetch options data');
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    run();

    return () => {
      isMounted = false;
    };
  }, [selectedSymbol, selectedExpiry]);

  return (
    <div className="space-y-4">
      {/* Top Header & Metrics */}
      <OptionsHeader
        analytics={chainData?.analytics || null}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={(sym) => {
          setSelectedSymbol(sym);
          setSelectedExpiry('');
        }}
        selectedExpiry={selectedExpiry || chainData?.expiry || ''}
        expiries={chainData?.expiries || []}
        onSelectExpiry={(exp) => setSelectedExpiry(exp)}
        viewMode={viewMode}
        onToggleViewMode={setViewMode}
      />

      {/* Tabs Row */}
      <div className="flex items-center gap-2 border-b border-border pb-2">
        <button
          onClick={() => setActiveTab('chain')}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
            activeTab === 'chain'
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          Option Chain Ladder
        </button>

        <button
          onClick={() => setActiveTab('institutional_flow')}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
            activeTab === 'institutional_flow'
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
          }`}
        >
          <ShieldAlert className="w-3.5 h-3.5" />
          Institutional Flow &amp; OI
        </button>

        <button
          onClick={() => setActiveTab('max_pain')}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
            activeTab === 'max_pain'
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
          }`}
        >
          <Target className="w-3.5 h-3.5" />
          Max Pain Distribution
        </button>

        <button
          onClick={() => setActiveTab('iv_smile')}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
            activeTab === 'iv_smile'
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
          }`}
        >
          <Activity className="w-3.5 h-3.5" />
          IV Smile &amp; Skew
        </button>
      </div>

      {/* Main View Area */}
      {error ? (
        <div className="p-8 text-center bg-card border border-destructive/20 rounded-xl text-destructive">
          <p className="font-semibold text-sm">Error loading option chain</p>
          <p className="text-xs mt-1 opacity-80">{error}</p>
        </div>
      ) : loading && !chainData ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center text-muted-foreground animate-pulse">
          Computing Greeks and assembling option chain matrix...
        </div>
      ) : (
        <>
          {activeTab === 'chain' && (
            <OptionChainTable
              strikes={chainData?.strikes || []}
              viewMode={viewMode}
              spotPrice={chainData?.spot_price || 25000}
            />
          )}

          {activeTab === 'institutional_flow' && (
            <InstitutionalFlowTracker
              symbol={selectedSymbol}
              expiry={selectedExpiry || chainData?.expiry}
            />
          )}

          {activeTab === 'max_pain' && (
            <PayoffChart
              data={maxPainData}
              spotPrice={chainData?.spot_price || 25000}
            />
          )}

          {activeTab === 'iv_smile' && (
            <IVSmileChart
              strikes={chainData?.strikes || []}
              atmStrike={chainData?.analytics?.atm_strike || 25000}
            />
          )}
        </>
      )}
    </div>
  );
}
