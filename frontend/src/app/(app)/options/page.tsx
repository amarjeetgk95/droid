'use client';

import { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { api } from '@/lib/api';
import { OptionChainResponse, MaxPainResult } from '@/lib/types';
import { OptionsHeader } from '@/components/options/OptionsHeader';
import { OptionChainTable } from '@/components/options/OptionChainTable';
import { PayoffChart } from '@/components/options/PayoffChart';
import { IVSmileChart } from '@/components/options/IVSmileChart';
import { PageTabs } from '@/components/ui/PageTabs';
import { ErrorCard } from '@/components/ui/ErrorCard';
import { deskCache } from '@/lib/useDeskCache';
import { OptionChainSkeleton } from '@/components/options/OptionChainSkeleton';
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

  const [chainData, setChainData] = useState<OptionChainResponse | null>(null);
  const [maxPainData, setMaxPainData] = useState<MaxPainResult | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchOptions = async () => {
    try {
      if (!selectedExpiry) {
        const chainRes = await api.getOptionChain(selectedSymbol, undefined);
        setChainData(chainRes.data);

        if (chainRes.data.expiry) {
          setSelectedExpiry(chainRes.data.expiry);
        } else {
          const mpRes = await api.getMaxPain(selectedSymbol, undefined);
          setMaxPainData(mpRes.data);
        }

        setError(null);
        return;
      }

      const [chainRes, mpRes] = await Promise.all([
        api.getOptionChain(selectedSymbol, selectedExpiry),
        api.getMaxPain(selectedSymbol, selectedExpiry),
      ]);
      setChainData(chainRes.data);
      setMaxPainData(mpRes.data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch options data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let isMounted = true;
    const cacheKey = `options:${selectedSymbol}:${selectedExpiry || 'default'}`;
    const cached = deskCache.get<{ chainData: any; maxPainData: any }>(cacheKey);

    if (cached) {
      setChainData(cached.data.chainData);
      setMaxPainData(cached.data.maxPainData);
      setLoading(false);
      // If cached data is still fresh (<30s), render immediately without refetch
      if (!cached.isStale) return;
    } else {
      setLoading(true);
    }

    const run = async () => {
      try {
        if (!selectedExpiry) {
          const chainRes = await api.getOptionChain(selectedSymbol, undefined);
          if (!isMounted) return;
          setChainData(chainRes.data);

          let mpData: any = null;
          if (chainRes.data.expiry) {
            setSelectedExpiry(chainRes.data.expiry);
          } else {
            const mpRes = await api.getMaxPain(selectedSymbol, undefined);
            if (!isMounted) return;
            mpData = mpRes.data;
            setMaxPainData(mpData);
          }

          deskCache.set(cacheKey, { chainData: chainRes.data, maxPainData: mpData });
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
        deskCache.set(cacheKey, { chainData: chainRes.data, maxPainData: mpRes.data });
        setError(null);
      } catch (err) {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : 'Failed to fetch options data');
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    void run();

    return () => {
      isMounted = false;
    };
  }, [selectedSymbol, selectedExpiry]);

  const spotPrice = chainData?.spot_price || 25000;

  const tabs = [
    {
      id: 'chain',
      label: 'Option Chain Ladder',
      icon: Layers,
      content: (
        <OptionChainTable
          strikes={chainData?.strikes || []}
          viewMode={viewMode}
          spotPrice={spotPrice}
        />
      ),
    },
    {
      id: 'institutional_flow',
      label: 'Institutional Flow & OI',
      icon: ShieldAlert,
      content: (
        <InstitutionalFlowTracker
          symbol={selectedSymbol}
          expiry={selectedExpiry || chainData?.expiry}
        />
      ),
    },
    {
      id: 'max_pain',
      label: 'Max Pain Distribution',
      icon: Target,
      content: (
        <PayoffChart
          data={maxPainData}
          spotPrice={spotPrice}
        />
      ),
    },
    {
      id: 'iv_smile',
      label: 'IV Smile & Skew',
      icon: Activity,
      content: (
        <IVSmileChart
          strikes={chainData?.strikes || []}
          atmStrike={chainData?.analytics?.atm_strike || 25000}
        />
      ),
    },
  ];

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

      {/* Main View Area */}
      {error ? (
        <ErrorCard
          title="Error loading option chain"
          message={error}
          mode="full-page"
          onRetry={() => {
            setLoading(true);
            void fetchOptions();
          }}
          isRetrying={loading}
        />
      ) : loading && !chainData ? (
        <OptionChainSkeleton rows={12} />
      ) : (
        <PageTabs tabs={tabs} defaultTab="chain" syncWithUrl />
      )}
    </div>
  );
}
