'use client';

import React, { memo, useMemo } from 'react';
import { Layers, ArrowDownUp, AlertTriangle } from 'lucide-react';
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
      <div className="bg-card border border-border rounded-xl p-4 shadow-xs h-[450px] flex flex-col justify-center items-center text-muted-foreground text-xs animate-pulse">
        <Layers className="w-6 h-6 mb-2 opacity-50" />
        <span>Loading synchronized L2 depth ladder...</span>
      </div>
    );
  }

  const isBtcCross = orderbook.symbol.includes('BTC') && !orderbook.symbol.endsWith('USDT');
  const decimals = isBtcCross ? 5 : 2;

  // Calculate cumulative notional for background depth bars
  const { maxTotal, displayAsks, displayBids } = useMemo(() => {
    const askItems = orderbook.asks || [];
    const bidItems = orderbook.bids || [];
    const maxBidTotal = bidItems.length > 0 ? (bidItems[bidItems.length - 1].cumulative_notional || bidItems[bidItems.length - 1].total || 1) : 1;
    const maxAskTotal = askItems.length > 0 ? (askItems[askItems.length - 1].cumulative_notional || askItems[askItems.length - 1].total || 1) : 1;
    const maxT = Math.max(maxBidTotal, maxAskTotal, 1);
    return {
      maxTotal: maxT,
      displayAsks: [...askItems].slice(0, 8).reverse(),
      displayBids: [...bidItems].slice(0, 8),
    };
  }, [orderbook.bids, orderbook.asks]);

  const formatNum = (val: number, dec: number = decimals) => {
    return val.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
  };

  const formatUsd = (val: number) => {
    if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(2)}M`;
    if (val >= 1000) return `$${(val / 1000).toFixed(1)}K`;
    return `$${val.toFixed(0)}`;
  };

  const bidDepth = orderbook.bid_depth_total || (orderbook.bids.length > 0 ? (orderbook.bids[orderbook.bids.length - 1].cumulative_notional || orderbook.bids[orderbook.bids.length - 1].total || 0) : 0);
  const askDepth = orderbook.ask_depth_total || (orderbook.asks.length > 0 ? (orderbook.asks[orderbook.asks.length - 1].cumulative_notional || orderbook.asks[orderbook.asks.length - 1].total || 0) : 0);
  const totalDepth = bidDepth + askDepth;
  const bidRatioPct = totalDepth > 0 ? Math.round((bidDepth / totalDepth) * 100) : 50;

  const seqStatus = orderbook.sequence_status || 'ACTIVE';

  return (
    <div className="bg-card border border-border rounded-xl p-4 shadow-xs flex flex-col justify-between h-[450px]">
      <div>
        {/* Header with sequence status */}
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-primary" />
            <span>L2 Order Book Depth</span>
            {seqStatus === 'GAP_DETECTED' ? (
              <span className="ml-1 flex items-center gap-0.5 text-[9px] font-mono px-1.5 py-0.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20">
                <AlertTriangle className="w-2.5 h-2.5" /> GAP RESYNC
              </span>
            ) : isLive || seqStatus === 'ACTIVE' ? (
              <span className="ml-1 flex items-center gap-1 text-[9px] font-mono px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <span className="w-1 h-1 rounded-full bg-emerald-400 animate-pulse" /> LIVE
              </span>
            ) : (
              <span className="ml-1 text-[9px] font-mono px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
                SYNCING
              </span>
            )}
          </h3>
          <span className="text-[10px] font-mono text-muted-foreground bg-secondary px-2 py-0.5 rounded">
            {orderbook.symbol}
          </span>
        </div>

        {/* Depth Imbalance Barometer */}
        <div className="mb-2.5 p-2 bg-secondary/40 rounded-lg border border-border/60">
          <div className="flex justify-between text-[10px] font-mono text-muted-foreground mb-1">
            <span className="text-emerald-400 font-semibold">Bids: {formatUsd(bidDepth)} ({bidRatioPct}%)</span>
            <span className="text-rose-400 font-semibold">Asks: {formatUsd(askDepth)} ({100 - bidRatioPct}%)</span>
          </div>
          <div className="w-full h-1.5 bg-secondary rounded-full overflow-hidden flex">
            <div
              className="bg-emerald-500 h-full transition-all duration-300"
              style={{ width: `${bidRatioPct}%` }}
            />
            <div
              className="bg-rose-500 h-full transition-all duration-300"
              style={{ width: `${100 - bidRatioPct}%` }}
            />
          </div>
        </div>

        {/* Table Header */}
        <div className="grid grid-cols-3 text-[10px] font-mono text-muted-foreground border-b border-border pb-1 px-1">
          <span>PRICE ({isBtcCross ? 'BTC' : 'USDT'})</span>
          <span className="text-right">SIZE</span>
          <span className="text-right">TOTAL ($)</span>
        </div>

        {/* Asks (Sell Orders - Red) */}
        <div className="space-y-0.5 my-1">
          {displayAsks.map((level) => {
            const tot = level.cumulative_notional || level.total || 0;
            const depthPct = Math.min(100, (tot / maxTotal) * 100);
            return (
              <div
                key={`ask-${level.price}`}
                className="relative grid grid-cols-3 text-[11px] font-mono py-0.5 px-1 hover:bg-rose-500/10"
              >
                <div
                  className="absolute right-0 top-0 bottom-0 bg-rose-500/10 pointer-events-none rounded-r transition-all duration-300"
                  style={{ width: `${depthPct}%` }}
                />
                <span className="text-rose-400 font-semibold relative z-10 tabular-nums">{formatNum(level.price)}</span>
                <span className="text-muted-foreground text-right relative z-10 tabular-nums">{level.quantity.toFixed(4)}</span>
                <span className="text-foreground/80 text-right relative z-10 tabular-nums">{formatUsd(tot)}</span>
              </div>
            );
          })}
        </div>

        {/* Spread Divider */}
        <div className="py-1.5 px-2 my-1 bg-secondary/70 border-y border-border flex items-center justify-between text-xs font-mono">
          <div className="flex items-center gap-1.5 text-muted-foreground text-[11px]">
            <ArrowDownUp className="w-3 h-3 text-primary" />
            <span>Spread</span>
          </div>
          <div className="flex items-center gap-2 tabular-nums">
            <span className="font-semibold text-foreground font-mono">{formatNum(orderbook.spread)} {isBtcCross ? 'BTC' : 'USDT'}</span>
            <span className="text-[10px] text-muted-foreground">({orderbook.spread_percent.toFixed(3)}%)</span>
          </div>
        </div>

        {/* Bids (Buy Orders - Green) */}
        <div className="space-y-0.5 my-1">
          {displayBids.map((level) => {
            const tot = level.cumulative_notional || level.total || 0;
            const depthPct = Math.min(100, (tot / maxTotal) * 100);
            return (
              <div
                key={`bid-${level.price}`}
                className="relative grid grid-cols-3 text-[11px] font-mono py-0.5 px-1 hover:bg-emerald-500/10"
              >
                <div
                  className="absolute right-0 top-0 bottom-0 bg-emerald-500/10 pointer-events-none rounded-r transition-all duration-300"
                  style={{ width: `${depthPct}%` }}
                />
                <span className="text-emerald-400 font-semibold relative z-10 tabular-nums">{formatNum(level.price)}</span>
                <span className="text-muted-foreground text-right relative z-10 tabular-nums">{level.quantity.toFixed(4)}</span>
                <span className="text-foreground/80 text-right relative z-10 tabular-nums">{formatUsd(tot)}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer */}
      <div className="text-[10px] text-muted-foreground flex justify-between border-t border-border pt-2 mt-1">
        <span>Binance Depth @100ms {isLive ? '· Sequence Verified' : '· Snapshot'}</span>
        <span className="tabular-nums font-mono">{new Date(orderbook.timestamp).toLocaleTimeString()}</span>
      </div>
    </div>
  );
}

export const CryptoOrderBook = memo(CryptoOrderBookInner);
