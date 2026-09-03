'use client';

import React from 'react';
import { Compass, DollarSign, Activity, Layers, ArrowUpRight } from 'lucide-react';
import { CryptoMarketOverview, CryptoTicker } from '@/lib/types';

interface Props {
  overview: CryptoMarketOverview | null;
  onSelectTicker?: (ticker: CryptoTicker) => void;
}

export function CryptoMarketOverviewStrip({ overview, onSelectTicker }: Props) {
  if (!overview) return null;

  const getFearGreedColor = (score: number) => {
    if (score >= 75) return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
    if (score >= 55) return 'text-green-400 bg-green-500/10 border-green-500/20';
    if (score >= 45) return 'text-amber-400 bg-amber-500/10 border-amber-500/20';
    if (score >= 25) return 'text-orange-400 bg-orange-500/10 border-orange-500/20';
    return 'text-rose-400 bg-rose-500/10 border-rose-500/20';
  };

  const formatUsd = (val: number) => {
    if (val >= 1_000_000_000_000) return `$${(val / 1_000_000_000_000).toFixed(2)}T`;
    if (val >= 1_000_000_000) return `$${(val / 1_000_000_000).toFixed(2)}B`;
    return `$${(val / 1_000_000).toFixed(2)}M`;
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4 shadow-xs">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 divide-y md:divide-y-0 md:divide-x divide-border">
        {/* 1. Fear & Greed Index */}
        <div className="flex items-center gap-3 pr-2">
          <div className="p-2.5 rounded-xl bg-primary/10 text-primary shrink-0">
            <Compass className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Fear & Greed Index</span>
              <span
                className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${getFearGreedColor(
                  overview.fear_greed_score
                )}`}
              >
                {overview.fear_greed_label} ({overview.fear_greed_score})
              </span>
            </div>
            <div className="w-36 h-2 bg-secondary rounded-full overflow-hidden mt-1.5 flex">
              <div
                className="bg-gradient-to-r from-rose-500 via-amber-400 to-emerald-500 h-full transition-all duration-700"
                style={{ width: `${overview.fear_greed_score}%` }}
              />
            </div>
          </div>
        </div>

        {/* 2. Bitcoin & Ethereum Market Dominance */}
        <div className="flex items-center gap-3 px-0 md:px-4 pt-3 md:pt-0">
          <div className="p-2.5 rounded-xl bg-amber-500/10 text-amber-400 shrink-0">
            <Activity className="w-5 h-5" />
          </div>
          <div>
            <span className="text-xs text-muted-foreground block">Market Dominance</span>
            <div className="flex items-baseline gap-2 mt-0.5">
              <span className="text-sm font-bold text-amber-400 font-mono">
                BTC: {overview.btc_dominance_pct.toFixed(1)}%
              </span>
              <span className="text-sm font-bold text-sky-400 font-mono">
                ETH: {(overview.eth_dominance_pct || 16.8).toFixed(1)}%
              </span>
            </div>
            <span className="text-[10px] text-muted-foreground block mt-0.5">
              Cap: {formatUsd(overview.total_market_cap_usd)}
            </span>
          </div>
        </div>

        {/* 3. Combined BTC + ETH 24h Volume */}
        <div className="flex items-center gap-3 px-0 md:px-4 pt-3 md:pt-0">
          <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-400 shrink-0">
            <DollarSign className="w-5 h-5" />
          </div>
          <div>
            <span className="text-xs text-muted-foreground block">BTC + ETH 24h Volume</span>
            <div className="flex items-baseline gap-2 mt-0.5">
              <span className="text-base font-bold text-foreground font-mono">
                {formatUsd(overview.combined_volume_24h_usd || overview.total_volume_24h_usd)}
              </span>
              <span className="text-[11px] text-emerald-400 font-medium font-mono">Binance Liquid</span>
            </div>
          </div>
        </div>

        {/* 4. ETH/BTC Cross-Ratio */}
        <div className="flex items-center gap-3 px-0 md:px-4 pt-3 md:pt-0">
          <div className="p-2.5 rounded-xl bg-purple-500/10 text-purple-400 shrink-0">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <span className="text-xs text-muted-foreground block">ETH / BTC Ratio</span>
            <div className="flex items-baseline gap-2 mt-0.5">
              <span className="text-base font-bold text-foreground font-mono">
                {(overview.eth_btc_ratio || 0.0306).toFixed(5)}
              </span>
              <span className="text-[10px] text-muted-foreground font-mono">BTC Price</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
