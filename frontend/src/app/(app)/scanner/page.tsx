'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { ScannedStrategy } from '@/lib/types';
import { ScannerCard } from '@/components/scanner/ScannerCard';
import { Radar, Filter, RefreshCw, Sparkles } from 'lucide-react';

export default function ScannerPage() {
  const [opportunities, setOpportunities] = useState<ScannedStrategy[]>([]);
  const [selectedOutlook, setSelectedOutlook] = useState<string>('ALL');
  const [minPop, setMinPop] = useState<number>(30);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const fetchOpportunities = async () => {
      try {
        const outlookParam = selectedOutlook === 'ALL' ? undefined : selectedOutlook;
        const res = await api.scanMarketStrategies(outlookParam, minPop);
        if (isMounted) {
          setOpportunities(res.data);
          setError(null);
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to scan strategies');
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchOpportunities();
    return () => {
      isMounted = false;
    };
  }, [selectedOutlook, minPop]);

  const handleManualRescan = () => {
    setLoading(true);
    const outlookParam = selectedOutlook === 'ALL' ? undefined : selectedOutlook;
    api.scanMarketStrategies(outlookParam, minPop)
      .then((res) => {
        setOpportunities(res.data);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to scan strategies'))
      .finally(() => setLoading(false));
  };

  const outlooks = [
    { label: 'All Opportunities', value: 'ALL' },
    { label: 'Bullish Outlook', value: 'BULLISH' },
    { label: 'Bearish Outlook', value: 'BEARISH' },
    { label: 'Rangebound / Neutral', value: 'NEUTRAL' },
    { label: 'High Volatility Expansion', value: 'HIGH_VOLATILITY' },
  ];

  return (
    <div className="space-y-4">
      {/* Header & Controls Bar */}
      <div className="bg-card border border-border rounded-xl p-4 flex flex-wrap items-center justify-between gap-3 shadow-xs">
        <div className="flex items-center gap-3">
          <div className="bg-primary/10 p-2 rounded-lg">
            <Radar className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h2 className="text-base font-bold text-foreground">Quantitative Strategy Scanner</h2>
            <p className="text-xs text-muted-foreground">
              Automated high-probability options opportunity screener across Indian index derivatives
            </p>
          </div>
        </div>

        <button
          onClick={handleManualRescan}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-secondary hover:bg-secondary/80 text-foreground text-xs font-bold transition-all cursor-pointer border border-border"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Rescan Market</span>
        </button>
      </div>

      {/* Filter Toolbar */}
      <div className="bg-card border border-border rounded-xl p-4 flex flex-wrap items-center justify-between gap-4 shadow-xs">
        {/* Outlook Pills */}
        <div className="flex flex-wrap items-center gap-2">
          {outlooks.map((item) => (
            <button
              key={item.value}
              onClick={() => setSelectedOutlook(item.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                selectedOutlook === item.value
                  ? 'bg-primary text-primary-foreground shadow-xs'
                  : 'bg-secondary hover:bg-secondary/80 text-muted-foreground hover:text-foreground'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        {/* Min POP Filter */}
        <div className="flex items-center gap-3 text-xs">
          <span className="text-muted-foreground font-medium flex items-center gap-1">
            <Filter className="w-3.5 h-3.5 text-primary" /> Min POP:
          </span>
          <input
            type="range"
            min={10}
            max={75}
            step={5}
            value={minPop}
            onChange={(e) => setMinPop(parseInt(e.target.value))}
            className="w-24 accent-primary cursor-pointer"
          />
          <span className="font-mono font-bold text-foreground">{minPop}%</span>
        </div>
      </div>

      {/* Opportunities Grid */}
      {error ? (
        <div className="p-8 text-center bg-card border border-destructive/20 rounded-xl text-destructive">
          <p className="font-semibold text-sm">Error scanning market strategies</p>
          <p className="text-xs mt-1 opacity-80">{error}</p>
        </div>
      ) : loading ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center text-muted-foreground animate-pulse">
          Scanning option chains, calculating breakevens, and ranking opportunities...
        </div>
      ) : opportunities.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center text-muted-foreground space-y-2">
          <Sparkles className="w-8 h-8 text-muted-foreground mx-auto opacity-50" />
          <p className="text-sm font-semibold">No strategies matched the current filter threshold.</p>
          <p className="text-xs opacity-75">Try lowering the Min POP slider or selecting &quot;All Opportunities&quot;.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {opportunities.map((opp) => (
            <ScannerCard key={opp.id} strategy={opp} />
          ))}
        </div>
      )}
    </div>
  );
}
