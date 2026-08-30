'use client';

import React, { memo, useMemo } from 'react';
import { Layers, ArrowDownUp } from 'lucide-react';
import { CryptoOrderBook as OrderBookType } from '@/lib/types';

interface Props {
  orderbook: OrderBookType | null;
  loading?: boolean;
  isLive?: boolean;
  streamState?: string;
}

function CryptoOrderBookInner({ orderbook, loading, isLive, streamState }: Props) {
  if (loading || !orderbook) {
    return (
      <div className="bg-card border border-border rounded-xl p-4 shadow-xs h-[420px] flex flex-col justify-center items-center text-muted-foreground text-xs animate-pulse">
        <Layers className="w-6 h-6 mb-2 opacity-50" />
        <span>Loading Binance live order book depth...</span>
      </div>
    );
  }

  // Calculate max cumulative volume for background bars - memoize to prevent flicker on spread-only updates
  const { maxTotal, displayAsks, displayBids } = useMemo(() => {
    const maxBidTotal = orderbook.bids.length > 0 ? orderbook.bids[orderbook.bids.length - 1].total : 1;
    const maxAskTotal = orderbook.asks.length > 0 ? orderbook.asks[orderbook.asks.length - 1].total : 1;
    const maxT = Math.max(maxBidTotal, maxAskTotal, 1);
    return {
      maxTotal: maxT,
      displayAsks: [...orderbook.asks].slice(0, 8).reverse(),
      displayBids: [...orderbook.bids].slice(0, 8),
    };
  }, [orderbook.bids, orderbook.asks]);

  const formatNum = (val: number, decimals: number = 2) => {
    return val.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4 shadow-xs flex flex-col justify-between h-[420px]">
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-primary" />
            <span>Order Book Depth</span>
            {isLive ? (
              <span className="ml-1 flex items-center gap-1 text-[9px] font-mono px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <span className="w-1 h-1 rounded-full bg-emerald-400 animate-pulse" /> LIVE
              </span>
            ) : streamState === 'CONNECTING' || streamState === 'RECONNECTING' ? (
              <span className="ml-1 text-[9px] font-mono px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">SYNCING</span>
            ) : null}
          </h3>
          <span className="text-[10px] font-mono text-muted-foreground bg-secondary px-2 py-0.5 rounded">
            {orderbook.symbol}
          </span>
        </div>

        {/* Table Header */}
        <div className="grid grid-cols-3 text-[10px] font-mono text-muted-foreground border-b border-border pb-1.5 px-1">
          <span>PRICE (USDT)</span>
          <span className="text-right">SIZE</span>
          <span className="text-right">TOTAL ($)</span>
        </div>

        {/* Asks (Sell Orders - Red) - stable keys by price only to avoid remount flash on qty tick */}
        <div className="space-y-0.5 my-1">
          {displayAsks.map((level) => {
            const depthPct = Math.min(100, (level.total / maxTotal) * 100);
            return (
              <div
                key={`ask-${level.price}`}
                className="relative grid grid-cols-3 text-[11px] font-mono py-0.5 px-1 hover:bg-rose-500/10"
              >
                <div
                  className="absolute right-0 top-0 bottom-0 bg-rose-500/10 pointer-events-none rounded-r transition-all duration-500"
                  style={{ width: `${depthPct}%` }}
                />
                <span className="text-rose-400 font-semibold relative z-10 tabular-nums">{formatNum(level.price, 2)}</span>
                <span className="text-muted-foreground text-right relative z-10 tabular-nums">{formatNum(level.quantity, 4)}</span>
                <span className="text-foreground/80 text-right relative z-10 tabular-nums">{formatNum(level.total, 0)}</span>
              </div>
            );
          })}
        </div>

        {/* Spread Divider - tabular-nums prevents width jitter/flash on rapid price changes */}
        <div className="py-2 px-2 my-1 bg-secondary/60 border-y border-border flex items-center justify-between text-xs font-mono">
          <div className="flex items-center gap-1.5 text-muted-foreground text-[11px]">
            <ArrowDownUp className="w-3 h-3 text-primary" />
            <span>Spread</span>
          </div>
          <div className="flex items-center gap-2 tabular-nums">
            <span className="font-semibold text-foreground font-mono">{formatNum(orderbook.spread, 2)} USDT</span>
            <span className="text-[10px] text-muted-foreground">({orderbook.spread_percent.toFixed(3)}%)</span>
          </div>
        </div>

        {/* Bids (Buy Orders - Green) - stable keys by price */}
        <div className="space-y-0.5 my-1">
          {displayBids.map((level) => {
            const depthPct = Math.min(100, (level.total / maxTotal) * 100);
            return (
              <div
                key={`bid-${level.price}`}
                className="relative grid grid-cols-3 text-[11px] font-mono py-0.5 px-1 hover:bg-emerald-500/10"
              >
                <div
                  className="absolute right-0 top-0 bottom-0 bg-emerald-500/10 pointer-events-none rounded-r transition-all duration-500"
                  style={{ width: `${depthPct}%` }}
                />
                <span className="text-emerald-400 font-semibold relative z-10 tabular-nums">{formatNum(level.price, 2)}</span>
                <span className="text-muted-foreground text-right relative z-10 tabular-nums">{formatNum(level.quantity, 4)}</span>
                <span className="text-foreground/80 text-right relative z-10 tabular-nums">{formatNum(level.total, 0)}</span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="text-[10px] text-muted-foreground flex justify-between border-t border-border pt-2 mt-1">
        <span>Source: Binance L2 Depth {isLive ? '· WS @100ms realtime' : '· REST snapshot'}</span>
        <span className="tabular-nums">{new Date(orderbook.timestamp).toLocaleTimeString()} {isLive ? '●' : ''}</span>
      </div>
    </div>
  );
}

export const CryptoOrderBook = memo(CryptoOrderBookInner);
