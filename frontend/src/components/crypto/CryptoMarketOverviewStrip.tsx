'use client';

import React from 'react';
import { Compass, TrendingUp, TrendingDown, DollarSign, Activity } from 'lucide-react';
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
              <span className="text-xs text-muted-foreground">Fear & Greed</span>
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

        {/* 2. Bitcoin Dominance & Market Cap */}
        <div className="flex items-center gap-3 px-0 md:px-4 pt-3 md:pt-0">
          <div className="p-2.5 rounded-xl bg-amber-500/10 text-amber-400 shrink-0">
            <Activity className="w-5 h-5" />
          </div>
          <div>
            <span className="text-xs text-muted-foreground block">BTC Market Dominance</span>
            <div className="flex items-baseline gap-2 mt-0.5">
              <span className="text-base font-bold text-foreground font-mono">
                {overview.btc_dominance_pct.toFixed(1)}%
              </span>
              <span className="text-[11px] text-muted-foreground">
                Cap: {formatUsd(overview.total_market_cap_usd)}
              </span>
            </div>
          </div>
        </div>

        {/* 3. 24h Global Volume */}
        <div className="flex items-center gap-3 px-0 md:px-4 pt-3 md:pt-0">
          <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-400 shrink-0">
            <DollarSign className="w-5 h-5" />
          </div>
          <div>
            <span className="text-xs text-muted-foreground block">Tracked 24h Spot Volume</span>
            <div className="flex items-baseline gap-2 mt-0.5">
              <span className="text-base font-bold text-foreground font-mono">
                {formatUsd(overview.total_volume_24h_usd)}
              </span>
              <span className="text-[11px] text-emerald-400 font-medium">Binance Liquidity</span>
            </div>
          </div>
        </div>

        {/* 4. Top Gainers & Movers */}
        <div className="flex flex-col justify-center px-0 md:px-4 pt-3 md:pt-0 space-y-1">
          <span className="text-[11px] text-muted-foreground block">24h Top Movers</span>
          <div className="flex flex-wrap gap-1.5">
            {overview.top_gainers.slice(0, 2).map((g) => (
              <button
                key={g.symbol}
                type="button"
                onClick={() => onSelectTicker?.(g)}
                className="flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors cursor-pointer"
              >
                <TrendingUp className="w-3 h-3" />
                <span>{g.symbol.replace('USDT', '')} +{g.change_percent_24h.toFixed(1)}%</span>
              </button>
            ))}
            {overview.top_losers.slice(0, 1).map((l) => (
              <button
                key={l.symbol}
                type="button"
                onClick={() => onSelectTicker?.(l)}
                className="flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 transition-colors cursor-pointer"
              >
                <TrendingDown className="w-3 h-3" />
                <span>{l.symbol.replace('USDT', '')} {l.change_percent_24h.toFixed(1)}%</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
