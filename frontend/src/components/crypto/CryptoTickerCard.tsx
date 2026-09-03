'use client';

import React from 'react';
import { TrendingUp, TrendingDown, Activity } from 'lucide-react';
import { CryptoTicker } from '@/lib/types';

interface Props {
  ticker: CryptoTicker;
  isSelected?: boolean;
  onSelect?: (ticker: CryptoTicker) => void;
}

export function CryptoTickerCard({ ticker, isSelected, onSelect }: Props) {
  const isPositive = ticker.change_percent_24h >= 0;
  const isBtc = ticker.symbol.includes('BTC');

  // Format currency
  const formatPrice = (val: number) => {
    if (val >= 1000) return `$${val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (val >= 1) return `$${val.toFixed(2)}`;
    return `$${val.toFixed(5)}`;
  };

  const formatVolume = (val: number) => {
    if (val >= 1_000_000_000) return `$${(val / 1_000_000_000).toFixed(2)}B`;
    if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(2)}M`;
    return `$${(val / 1000).toFixed(1)}K`;
  };

  // 24h Range calculation
  const rangeMin = ticker.low_24h;
  const rangeMax = ticker.high_24h;
  const rangeDelta = rangeMax - rangeMin || 1;
  const currentPosPct = Math.min(100, Math.max(0, ((ticker.price - rangeMin) / rangeDelta) * 100));

  // Sparkline generator
  const renderSparkline = () => {
    if (!ticker.sparkline || ticker.sparkline.length < 2) return null;
    const min = Math.min(...ticker.sparkline);
    const max = Math.max(...ticker.sparkline);
    const range = max - min || 1;
    const width = 100;
    const height = 32;

    const points = ticker.sparkline.map((val, idx) => {
      const x = (idx / (ticker.sparkline.length - 1)) * width;
      const y = height - ((val - min) / range) * (height - 8) - 4;
      return `${x},${y}`;
    });

    const strokeColor = isPositive ? '#10b981' : '#f43f5e';

    return (
      <svg className="w-24 h-8 overflow-visible" viewBox={`0 0 ${width} ${height}`}>
        <path
          d={`M ${points.join(' L ')}`}
          fill="none"
          stroke={strokeColor}
          strokeWidth="2"
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
      className={`w-full text-left p-4 rounded-2xl border transition-all cursor-pointer flex flex-col justify-between relative overflow-hidden ${
        isSelected
          ? 'bg-gradient-to-br from-card to-secondary/70 border-primary shadow-md ring-2 ring-primary/20'
          : 'bg-card border-border hover:bg-secondary/40 hover:border-border/80 shadow-xs'
      }`}
    >
      {/* Top Bar: Coin badge + Sparkline */}
      <div className="flex items-start justify-between w-full">
        <div className="flex items-center gap-2.5">
          <div
            className={`w-8 h-8 rounded-xl flex items-center justify-center font-bold text-xs font-mono shadow-xs ${
              isBtc
                ? 'bg-amber-500/15 text-amber-400 border border-amber-500/25'
                : 'bg-sky-500/15 text-sky-400 border border-sky-500/25'
            }`}
          >
            {isBtc ? '₿' : 'Ξ'}
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-bold text-sm text-foreground font-mono">
                {ticker.symbol.replace('USDT', '')}
              </span>
              <span className="text-[10px] text-muted-foreground font-mono">
                /{ticker.quote_asset || 'USDT'}
              </span>
              {isSelected && (
                <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
              )}
            </div>
            <span className="text-[11px] text-muted-foreground block truncate">
              {ticker.display_name}
            </span>
          </div>
        </div>

        <div className="shrink-0">{renderSparkline()}</div>
      </div>

      {/* Center: Price & 24h Delta */}
      <div className="mt-3 flex items-baseline justify-between w-full">
        <div className="text-xl font-extrabold text-foreground font-mono tabular-nums tracking-tight">
          {formatPrice(ticker.price)}
        </div>

        <div
          className={`flex items-center gap-1 px-2.5 py-0.5 rounded-lg text-xs font-mono font-bold ${
            isPositive
              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
              : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
          }`}
        >
          {isPositive ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
          <span>{isPositive ? '+' : ''}{ticker.change_percent_24h.toFixed(2)}%</span>
        </div>
      </div>

      {/* 24h High/Low Slider */}
      <div className="mt-3 space-y-1 w-full">
        <div className="flex justify-between text-[10px] font-mono text-muted-foreground">
          <span>L: {formatPrice(ticker.low_24h)}</span>
          <span className="text-foreground/70">{currentPosPct.toFixed(0)}% Range</span>
          <span>H: {formatPrice(ticker.high_24h)}</span>
        </div>
        <div className="w-full h-1.5 bg-secondary rounded-full overflow-hidden relative">
          <div
            className="h-full bg-gradient-to-r from-rose-500 via-amber-400 to-emerald-400 rounded-full"
            style={{ width: '100%' }}
          />
          {/* Slider indicator needle */}
          <div
            className="absolute top-0 bottom-0 w-1.5 bg-foreground rounded-full shadow-xs transform -translate-x-1/2"
            style={{ left: `${currentPosPct}%` }}
          />
        </div>
      </div>

      {/* Bottom Footer: Vol + VWAP */}
      <div className="mt-3 pt-2.5 border-t border-border/60 flex items-center justify-between text-[11px] font-mono text-muted-foreground">
        <div>
          <span>Vol: </span>
          <span className="text-foreground font-semibold">{formatVolume(ticker.volume_24h_quote)}</span>
        </div>
        {ticker.vwap && (
          <div>
            <span>VWAP: </span>
            <span className="text-foreground font-semibold">{formatPrice(ticker.vwap)}</span>
          </div>
        )}
      </div>
    </button>
  );
}
