'use client';

import React, { useEffect, useState, memo } from 'react';
import { Gauge, Clock, Flame, PieChart, Info } from 'lucide-react';
import { CryptoDerivatives } from '@/lib/types';

interface Props {
  derivatives: CryptoDerivatives | null;
  loading?: boolean;
  isLive?: boolean;
  fundingLive?: boolean;
}

function CryptoDerivativesCardInner({ derivatives, loading, isLive, fundingLive }: Props) {
  const [countdown, setCountdown] = useState<number>(0);

  useEffect(() => {
    if (derivatives) {
      setCountdown(derivatives.countdown_seconds);
    }
  }, [derivatives?.countdown_seconds]);

  // Live timer tick - isolated to countdown only, does not flash whole card
  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const formatCountdown = (secs: number) => {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const formatUsd = (val: number) => {
    if (val >= 1_000_000_000) return `$${(val / 1_000_000_000).toFixed(2)}B`;
    if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(2)}M`;
    return `$${val.toLocaleString()}`;
  };

  if (loading || !derivatives) {
    return (
      <div className="bg-card border border-border rounded-xl p-4 shadow-xs h-[420px] flex flex-col justify-center items-center text-muted-foreground text-xs animate-pulse">
        <Gauge className="w-6 h-6 mb-2 opacity-50" />
        <span>Loading Binance Futures derivatives data...</span>
      </div>
    );
  }

  const isFundingPositive = derivatives.funding_rate >= 0;

  return (
    <div className="bg-card border border-border rounded-xl p-4 shadow-xs flex flex-col justify-between h-[420px]">
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Flame className="w-3.5 h-3.5 text-amber-500" />
            <span>Futures & Derivatives Flow</span>
            {isLive || fundingLive ? (
              <span className="ml-1 flex items-center gap-1 text-[9px] font-mono px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <span className="w-1 h-1 rounded-full bg-emerald-400 animate-pulse" /> LIVE {fundingLive ? 'Funding @1s' : ''}
              </span>
            ) : null}
          </h3>
          <span className="text-[10px] font-mono text-muted-foreground bg-secondary px-2 py-0.5 rounded flex items-center gap-1">
            Binance USDT-M {fundingLive && <span className="w-1 h-1 bg-emerald-400 rounded-full animate-pulse" />}
          </span>
        </div>

        {/* 1. Funding Rate Block - stable, no flash on price tick */}
        <div className="bg-secondary/40 border border-border rounded-xl p-3 mb-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-muted-foreground flex items-center gap-1">
              <span>8H Funding Rate</span>
              <Info className="w-3 h-3 text-muted-foreground/60" />
            </span>
            <div className="flex items-center gap-1 text-[11px] font-mono text-muted-foreground">
              <Clock className="w-3 h-3 text-primary" />
              <span>Next in: <strong className="text-foreground tabular-nums">{formatCountdown(countdown)}</strong></span>
            </div>
          </div>

          <div className="mt-2 flex items-baseline justify-between">
            <div
              className={`text-xl font-bold font-mono tabular-nums transition-colors duration-300 ${
                isFundingPositive ? 'text-emerald-400' : 'text-rose-400'
              } ${fundingLive ? 'animate-none' : ''}`}
              title={fundingLive ? 'Realtime via Binance markPrice@1s WS' : 'Via REST polling'}
            >
              {isFundingPositive ? '+' : ''}
              {derivatives.funding_rate_percent.toFixed(4)}% {fundingLive && <span className="text-[10px] align-middle opacity-70">● live</span>}
            </div>
            <span
              className={`text-[10px] px-2 py-0.5 rounded font-medium ${
                isFundingPositive ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
              }`}
            >
              {isFundingPositive ? 'Longs Pay Shorts' : 'Shorts Pay Longs'}
            </span>
          </div>
        </div>

        {/* 2. Open Interest Block - uses tabular-nums to prevent width jitter */}
        <div className="grid grid-cols-2 gap-2 mb-3">
          <div className="bg-secondary/30 border border-border rounded-lg p-2.5">
            <span className="text-[10px] text-muted-foreground block">Open Interest (USD)</span>
            <span className="text-sm font-bold text-foreground font-mono mt-0.5 block tabular-nums">
              {formatUsd(derivatives.open_interest_usd)}
            </span>
          </div>

          <div className="bg-secondary/30 border border-border rounded-lg p-2.5">
            <span className="text-[10px] text-muted-foreground block">Mark vs Index Price</span>
            <span className="text-xs font-semibold text-foreground font-mono mt-0.5 block truncate tabular-nums">
              ${derivatives.mark_price.toLocaleString()}
            </span>
          </div>
        </div>

        {/* 3. Long vs Short Accounts Ratio - stable bar, no flash */}
        <div className="bg-secondary/30 border border-border rounded-xl p-3 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground text-[11px] flex items-center gap-1">
              <PieChart className="w-3 h-3 text-primary" />
              <span>Global Long / Short Ratio</span>
            </span>
            <span className="font-bold text-foreground font-mono tabular-nums">{derivatives.long_short_ratio.toFixed(2)}</span>
          </div>

          <div className="w-full h-3 bg-secondary rounded-full overflow-hidden flex">
            <div
              className="bg-emerald-500 h-full transition-all duration-700 ease-out"
              style={{ width: `${derivatives.long_percentage}%` }}
            />
            <div
              className="bg-rose-500 h-full transition-all duration-700 ease-out"
              style={{ width: `${derivatives.short_percentage}%` }}
            />
          </div>

          <div className="flex justify-between text-[11px] font-mono">
            <span className="text-emerald-400 font-semibold tabular-nums">{derivatives.long_percentage.toFixed(1)}% Long</span>
            <span className="text-rose-400 font-semibold tabular-nums">{derivatives.short_percentage.toFixed(1)}% Short</span>
          </div>
        </div>
      </div>

      <div className="text-[10px] text-muted-foreground flex justify-between border-t border-border pt-2 mt-1">
        <span>Settlement: UTC 00:00 / 08:00 / 16:00 {fundingLive ? '· funding WS realtime' : '· REST 15s'}</span>
        <span>Perpetuals {isLive ? '●' : ''}</span>
      </div>
    </div>
  );
}

export const CryptoDerivativesCard = memo(CryptoDerivativesCardInner);
