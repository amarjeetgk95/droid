'use client';

import React, { useState, useEffect } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Shield,
  Activity,
  Layers,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  Info,
} from 'lucide-react';
import { InstitutionalFlowResponse, InstitutionalStrikeFlow } from '@/lib/types';
import { api } from '@/lib/api';

interface Props {
  symbol: string;
  expiry?: string;
}

export function InstitutionalFlowTracker({ symbol, expiry }: Props) {
  const [data, setData] = useState<InstitutionalFlowResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getInstitutionalFlow(symbol, expiry);
      if (res.data) {
        setData(res.data);
      } else {
        setError(res.error || 'Failed to load institutional flow');
      }
    } catch (err: any) {
      setError(err?.message || 'Error fetching flow analytics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const timer = setInterval(fetchData, 15000); // 15s refresh
    return () => clearInterval(timer);
  }, [symbol, expiry]);

  const getBuildupBadge = (type: string) => {
    switch (type) {
      case 'LONG_BUILDUP':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
            LONG BUILDUP
          </span>
        );
      case 'SHORT_COVERING':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-sky-500/15 text-sky-400 border border-sky-500/30">
            SHORT COVERING
          </span>
        );
      case 'SHORT_BUILDUP':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-destructive/15 text-destructive border border-destructive/30">
            SHORT BUILDUP
          </span>
        );
      case 'LONG_UNWINDING':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30">
            LONG UNWINDING
          </span>
        );
      default:
        return <span className="text-[10px] text-muted-foreground">—</span>;
    }
  };

  if (loading && !data) {
    return (
      <div className="p-8 rounded-xl border border-border bg-card/50 flex flex-col items-center justify-center space-y-3">
        <Activity className="w-6 h-6 text-primary animate-spin" />
        <span className="text-xs text-muted-foreground">Analyzing Options Institutional Flow...</span>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="p-4 rounded-xl border border-destructive/30 bg-destructive/10 text-xs text-destructive flex items-center justify-between">
        <span>{error}</span>
        <button
          onClick={fetchData}
          className="px-2.5 py-1 bg-destructive/20 hover:bg-destructive/30 rounded font-semibold cursor-pointer"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data) return null;

  const isBullish = data.institutional_score >= 55;
  const isBearish = data.institutional_score <= 45;

  return (
    <div className="space-y-4">
      {/* 1. Header & Composite Institutional Score Card */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-4">
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Layers className="w-4 h-4 text-primary" />
              Institutional Flow &amp; Open Interest Tracker
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Live Call/Put unwinding vs build-up and strike defense walls for <strong>{symbol}</strong>.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`px-3 py-1 rounded-full text-xs font-bold flex items-center gap-1.5 border ${
                isBullish
                  ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                  : isBearish
                  ? 'bg-destructive/15 text-destructive border-destructive/30'
                  : 'bg-amber-500/15 text-amber-400 border-amber-500/30'
              }`}
            >
              {isBullish ? (
                <ArrowUpRight className="w-3.5 h-3.5" />
              ) : isBearish ? (
                <ArrowDownRight className="w-3.5 h-3.5" />
              ) : (
                <Activity className="w-3.5 h-3.5" />
              )}
              {data.institutional_sentiment.replace('_', ' ')} ({data.institutional_score}/100)
            </span>
            <button
              onClick={fetchData}
              disabled={loading}
              title="Refresh Flow Analytics"
              className="p-1.5 rounded-lg bg-secondary hover:bg-secondary/80 text-foreground transition-colors cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-primary' : ''}`} />
            </button>
          </div>
        </div>

        {/* 2. Key Institutional Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="bg-secondary/30 border border-border/50 rounded-lg p-3">
            <span className="text-muted-foreground text-[11px] block">Key Resistance (Call Wall)</span>
            <span className="font-mono font-bold text-destructive mt-0.5 block text-sm">
              {data.call_wall_strike} CE
            </span>
            <span className="text-[10px] text-muted-foreground mt-0.5 block">Highest Call Open Interest</span>
          </div>

          <div className="bg-secondary/30 border border-border/50 rounded-lg p-3">
            <span className="text-muted-foreground text-[11px] block">Key Support (Put Floor)</span>
            <span className="font-mono font-bold text-emerald-400 mt-0.5 block text-sm">
              {data.put_floor_strike} PE
            </span>
            <span className="text-[10px] text-muted-foreground mt-0.5 block">Highest Put Open Interest</span>
          </div>

          <div className="bg-secondary/30 border border-border/50 rounded-lg p-3">
            <span className="text-muted-foreground text-[11px] block">Max Pain Strike</span>
            <span className="font-mono font-bold text-primary mt-0.5 block text-sm">
              {data.max_pain_strike}
            </span>
            <span className="text-[10px] text-muted-foreground mt-0.5 block">Lowest Payout for Option Sellers</span>
          </div>

          <div className="bg-secondary/30 border border-border/50 rounded-lg p-3">
            <span className="text-muted-foreground text-[11px] block">Put-Call Ratio (PCR)</span>
            <span className="font-mono font-bold text-foreground mt-0.5 block text-sm">
              {data.pcr_oi.toFixed(2)}
            </span>
            <span className="text-[10px] text-muted-foreground mt-0.5 block">
              {data.pcr_oi >= 1.0 ? 'Bullish (Puts > Calls)' : 'Bearish (Calls > Puts)'}
            </span>
          </div>
        </div>
      </div>

      {/* 3. Strike-by-Strike Institutional Flow Matrix */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-xs space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Shield className="w-3.5 h-3.5 text-sky-400" />
            Strike Flow Ladder (Unwinding vs Buildup)
          </h4>
          <span className="text-[10px] text-muted-foreground">Auto-updates every 15s</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-border/60 text-muted-foreground text-[11px]">
                <th className="pb-2 font-semibold">Call Action</th>
                <th className="pb-2 text-right font-semibold">Call OI Chg</th>
                <th className="pb-2 text-right font-semibold">Call OI</th>
                <th className="pb-2 text-center font-bold text-foreground">STRIKE</th>
                <th className="pb-2 text-left font-semibold">Put OI</th>
                <th className="pb-2 text-left font-semibold">Put OI Chg</th>
                <th className="pb-2 text-right font-semibold">Put Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/30">
              {data.strike_flows.map((row) => (
                <tr
                  key={row.strike}
                  className={`hover:bg-secondary/30 transition-colors ${
                    row.is_atm ? 'bg-primary/5 font-bold' : ''
                  }`}
                >
                  <td className="py-2">{getBuildupBadge(row.call_buildup)}</td>
                  <td
                    className={`py-2 text-right ${
                      row.call_oi_change >= 0 ? 'text-destructive' : 'text-emerald-400'
                    }`}
                  >
                    {row.call_oi_change >= 0 ? `+${row.call_oi_change.toLocaleString()}` : row.call_oi_change.toLocaleString()}
                  </td>
                  <td className="py-2 text-right text-muted-foreground">
                    {row.call_oi.toLocaleString()}
                  </td>
                  <td className="py-2 text-center">
                    <span
                      className={`inline-block px-2 py-0.5 rounded text-xs ${
                        row.is_atm
                          ? 'bg-primary text-primary-foreground font-bold'
                          : row.strike === data.call_wall_strike
                          ? 'bg-destructive/20 text-destructive font-bold'
                          : row.strike === data.put_floor_strike
                          ? 'bg-emerald-500/20 text-emerald-400 font-bold'
                          : 'text-foreground'
                      }`}
                    >
                      {row.strike}
                    </span>
                  </td>
                  <td className="py-2 text-left text-muted-foreground">
                    {row.put_oi.toLocaleString()}
                  </td>
                  <td
                    className={`py-2 text-left ${
                      row.put_oi_change >= 0 ? 'text-emerald-400' : 'text-destructive'
                    }`}
                  >
                    {row.put_oi_change >= 0 ? `+${row.put_oi_change.toLocaleString()}` : row.put_oi_change.toLocaleString()}
                  </td>
                  <td className="py-2 text-right">{getBuildupBadge(row.put_buildup)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
