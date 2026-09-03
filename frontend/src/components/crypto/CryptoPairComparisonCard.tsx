'use client';

import React from 'react';
import { ArrowLeftRight, TrendingUp, TrendingDown, Scale, BarChart2 } from 'lucide-react';
import { CryptoPairComparison } from '@/lib/types';

interface Props {
  comparison: CryptoPairComparison | null;
  loading?: boolean;
}

export function CryptoPairComparisonCard({ comparison, loading }: Props) {
  if (loading || !comparison) {
    return (
      <div className="bg-card border border-border rounded-xl p-4 shadow-xs h-28 flex items-center justify-center text-muted-foreground text-xs animate-pulse">
        <ArrowLeftRight className="w-4 h-4 mr-2 opacity-50" />
        <span>Loading BTC vs ETH relative strength comparison...</span>
      </div>
    );
  }

  const isEthOutperforming = comparison.relative_strength === 'ETH_OUTPERFORMING';
  const isBtcOutperforming = comparison.relative_strength === 'BTC_OUTPERFORMING';

  return (
    <div className="bg-card border border-border rounded-xl p-4 shadow-xs">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* Left: ETH/BTC Ratio */}
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20 shrink-0">
            <Scale className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-foreground">ETH / BTC Relative Strength</span>
              <span
                className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold ${
                  isEthOutperforming
                    ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                    : isBtcOutperforming
                    ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                    : 'bg-secondary text-muted-foreground'
                }`}
              >
                {isEthOutperforming ? 'ETH Leading' : isBtcOutperforming ? 'BTC Leading' : 'Neutral Spread'}
              </span>
            </div>
            <div className="flex items-baseline gap-2 mt-0.5">
              <span className="text-base font-extrabold font-mono text-foreground tabular-nums">
                {comparison.eth_btc_ratio.toFixed(5)} BTC
              </span>
              <span
                className={`text-xs font-mono font-semibold flex items-center gap-0.5 ${
                  comparison.eth_btc_change_percent_24h >= 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                {comparison.eth_btc_change_percent_24h >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                {comparison.eth_btc_change_percent_24h >= 0 ? '+' : ''}
                {comparison.eth_btc_change_percent_24h.toFixed(2)}%
              </span>
            </div>
          </div>
        </div>

        {/* Right: Comparative Barometer */}
        <div className="flex items-center gap-6 divide-x divide-border">
          {/* 24h Spread */}
          <div className="space-y-0.5">
            <span className="text-[10px] text-muted-foreground block font-mono">24H SPREAD (ETH - BTC)</span>
            <span
              className={`text-sm font-bold font-mono tabular-nums ${
                comparison.performance_spread_24h >= 0 ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              {comparison.performance_spread_24h >= 0 ? '+' : ''}
              {comparison.performance_spread_24h.toFixed(2)}%
            </span>
          </div>

          {/* Relative Volume */}
          <div className="pl-6 space-y-0.5">
            <span className="text-[10px] text-muted-foreground block font-mono">ETH/BTC VOL RATIO</span>
            <span className="text-sm font-bold font-mono text-foreground tabular-nums">
              {(comparison.relative_volume_ratio * 100).toFixed(1)}%
            </span>
          </div>

          {/* Status Badge */}
          <div className="pl-6 hidden md:block text-right">
            <span className="text-[10px] text-muted-foreground block font-mono">MARKET BAROMETER</span>
            <span className="text-xs text-foreground/80 font-mono">
              {isEthOutperforming ? 'Altcoin Risk-On' : 'Bitcoin Flight-to-Quality'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
