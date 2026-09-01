'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { FIIDIIOverviewResponse } from '@/lib/types';
import { Landmark } from 'lucide-react';
import { safeNum, safeStr, safeInt } from '@/lib/utils';

export function FIIPositioningCard() {
  const [data, setData] = useState<FIIDIIOverviewResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    const loadData = async () => {
      try {
        const res = await api.getFIIDIIOverview();
        if (isMounted) {
          setData(res.data);
          setError(null);
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to fetch FII/DII data');
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    loadData();
    // Chained timeout with jitter so clients don't sync up their 60s polls.
    let timeout: ReturnType<typeof setTimeout> | null = null;
    const schedule = () => {
      timeout = setTimeout(() => {
        if (!document.hidden) loadData();
        schedule();
      }, 60000 * (0.8 + Math.random() * 0.4));
    };
    schedule();
    const onVis = () => { if (!document.hidden) loadData(); };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      isMounted = false;
      if (timeout) clearTimeout(timeout);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, []);

  if (loading && !data) {
    return (
      <div className="bg-card border border-border rounded-xl p-4 h-64 animate-pulse flex flex-col justify-between">
        <div className="h-4 bg-secondary rounded w-48" />
        <div className="h-10 bg-secondary rounded w-full" />
        <div className="h-4 bg-secondary rounded w-32" />
      </div>
    );
  }

  if (error || !data) {
    // Compact error state — never silently collapse the layout.
    return (
      <div className="bg-card border border-destructive/30 rounded-xl p-4 h-64 flex flex-col items-center justify-center gap-2">
        <Landmark className="w-6 h-6 text-destructive" />
        <p className="text-sm font-semibold text-foreground">Institutional FII / DII data unavailable</p>
        <p className="text-xs text-muted-foreground text-center max-w-xs">{error ?? 'No FII/DII data'}</p>
        <button
          onClick={() => {
            setLoading(true);
            api.getFIIDIIOverview()
              .then(res => { setData(res.data); setError(null); })
              .catch(err => setError(err instanceof Error ? err.message : 'Failed to fetch FII/DII data'))
              .finally(() => setLoading(false));
          }}
          className="text-xs px-3 py-1 rounded-md bg-secondary hover:bg-secondary/80 text-foreground transition-colors cursor-pointer"
        >
          Retry
        </button>
      </div>
    );
  }

  const isBullish = (data.institutional_sentiment || '').includes('BULLISH');
  const isBearish = (data.institutional_sentiment || '').includes('BEARISH');

  const fiiRatio = Number(data.fii_long_short_ratio);
  const fiiRatioSafe = Number.isFinite(fiiRatio) && fiiRatio > 0 ? fiiRatio : 1;
  const fiiWidth = Math.min(100, (fiiRatioSafe / (fiiRatioSafe + 1.0)) * 100);

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-xs">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
            <Landmark className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-foreground">
              Institutional FII / DII Derivatives & Cash Tracker
            </h3>
            <p className="text-[10px] text-muted-foreground">Index Futures Long/Short & Net Flow Analysis</p>
          </div>
        </div>

        <span
          className={`px-2 py-0.5 rounded text-[10px] font-extrabold border ${
            isBullish
              ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
              : isBearish
              ? 'bg-rose-500/20 text-rose-400 border-rose-500/30'
              : 'bg-secondary text-muted-foreground border-border'
          }`}
        >
          {safeStr(data.institutional_sentiment, '—').replace('_', ' ')}
        </span>
      </div>

      {/* Primary Positioning Bar: FII Long/Short Ratio */}
      <div className="space-y-1.5">
        <div className="flex justify-between text-[10px] font-bold">
          <span className="text-muted-foreground">FII Futures Long / Short Ratio</span>
          <span className="font-mono text-primary font-extrabold text-xs">
            {safeNum(fiiRatio, '—', 2)}x
          </span>
        </div>

        <div className="w-full bg-secondary h-2 rounded-full overflow-hidden flex">
          <div
            style={{ width: `${fiiWidth}%` }}
            className={isBullish ? 'bg-emerald-500' : isBearish ? 'bg-rose-500' : 'bg-primary'}
          />
        </div>
      </div>

      {/* Positioning Summary Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center text-xs">
        <div className="p-1.5 rounded-lg bg-secondary/50">
          <div className="text-[10px] text-muted-foreground">FII Net Futures</div>
          <div
            className={`text-xs font-mono font-bold mt-0.5 ${
              (data.fii_futures_net_contracts ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {(data.fii_futures_net_contracts ?? 0) > 0 ? '+' : ''}
            {safeInt(data.fii_futures_net_contracts)}
          </div>
        </div>

        <div className="p-1.5 rounded-lg bg-secondary/50">
          <div className="text-[10px] text-muted-foreground">DII Net Futures</div>
          <div
            className={`text-xs font-mono font-bold mt-0.5 ${
              (data.dii_futures_net_contracts ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {(data.dii_futures_net_contracts ?? 0) > 0 ? '+' : ''}
            {safeInt(data.dii_futures_net_contracts)}
          </div>
        </div>

        <div className="p-1.5 rounded-lg bg-secondary/50">
          <div className="text-[10px] text-muted-foreground">FII Cash Net</div>
          <div
            className={`text-xs font-mono font-bold mt-0.5 ${
              (data.fii_cash_net_crores ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {(data.fii_cash_net_crores ?? 0) > 0 ? '+' : ''}₹{safeNum(data.fii_cash_net_crores, '—', 0)} Cr
          </div>
        </div>

        <div className="p-1.5 rounded-lg bg-secondary/50">
          <div className="text-[10px] text-muted-foreground">DII Cash Net</div>
          <div
            className={`text-xs font-mono font-bold mt-0.5 ${
              (data.dii_cash_net_crores ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {(data.dii_cash_net_crores ?? 0) > 0 ? '+' : ''}₹{safeNum(data.dii_cash_net_crores, '—', 0)} Cr
          </div>
        </div>
      </div>
    </div>
  );
}
