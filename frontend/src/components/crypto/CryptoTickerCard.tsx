'use client';

import React from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { CryptoTicker } from '@/lib/types';

interface Props {
  ticker: CryptoTicker;
  isSelected?: boolean;
  onSelect?: (ticker: CryptoTicker) => void;
}

export function CryptoTickerCard({ ticker, isSelected, onSelect }: Props) {
  const isPositive = ticker.change_percent_24h >= 0;

  // Format currency
  const formatPrice = (val: number) => {
    if (val >= 1000) return `$${val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (val >= 1) return `$${val.toFixed(2)}`;
    return `$${val.toFixed(4)}`;
  };

  const formatVolume = (val: number) => {
    if (val >= 1_000_000_000) return `$${(val / 1_000_000_000).toFixed(2)}B`;
    if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(2)}M`;
    return `$${(val / 1000).toFixed(1)}K`;
  };

  // Sparkline path generator
  const renderSparkline = () => {
    if (!ticker.sparkline || ticker.sparkline.length < 2) return null;
    const min = Math.min(...ticker.sparkline);
    const max = Math.max(...ticker.sparkline);
    const range = max - min || 1;
    const width = 80;
    const height = 28;

    const points = ticker.sparkline.map((val, idx) => {
      const x = (idx / (ticker.sparkline.length - 1)) * width;
      const y = height - ((val - min) / range) * (height - 6) - 3;
      return `${x},${y}`;
    });

    const pathD = `M ${points.join(' L ')}`;

    return (
      <svg className="w-20 h-7 overflow-visible" viewBox={`0 0 ${width} ${height}`}>
        <path
          d={pathD}
          fill="none"
          stroke={isPositive ? '#10b981' : '#f43f5e'}
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  };

  return (
    <button
      type="button"
      onClick={() => onSelect?.(ticker)}
      className={`w-full text-left p-3.5 rounded-xl border transition-all cursor-pointer flex flex-col justify-between ${
        isSelected
          ? 'bg-primary/10 border-primary ring-2 ring-primary/20 shadow-sm'
          : 'bg-card border-border hover:bg-secondary/40 hover:border-border/80'
      }`}
    >
      <div className="flex items-start justify-between w-full">
        <div>
          <div className="flex items-center gap-1.5">
            <span className="font-bold text-xs text-foreground font-mono">{ticker.symbol.replace('USDT', '')}</span>
            <span className="text-[10px] text-muted-foreground">/USDT</span>
          </div>
          <span className="text-[11px] text-muted-foreground block truncate max-w-[100px]">{ticker.display_name}</span>
        </div>
        <div className="shrink-0">{renderSparkline()}</div>
      </div>

      <div className="mt-3 flex items-end justify-between w-full">
        <div>
          <div className="text-sm font-bold text-foreground font-mono">{formatPrice(ticker.price)}</div>
          <div className="text-[10px] text-muted-foreground font-mono">Vol: {formatVolume(ticker.volume_24h_quote)}</div>
        </div>

        <div
          className={`flex items-center gap-0.5 px-2 py-0.5 rounded text-[11px] font-mono font-semibold ${
            isPositive ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
          }`}
        >
          {isPositive ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
          <span>{isPositive ? '+' : ''}{ticker.change_percent_24h.toFixed(2)}%</span>
        </div>
      </div>
    </button>
  );
}
