'use client';

import { useState, useMemo } from 'react';
import { Zap, ShieldAlert, ArrowUpRight, ArrowDownRight, Target } from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/toast';

interface QuickScalpTicketProps {
  underlying: 'NIFTY' | 'BANKNIFTY' | 'SENSEX';
  spotPrice: number;
  onUnderlyingChange?: (u: 'NIFTY' | 'BANKNIFTY' | 'SENSEX') => void;
  onOrderPlaced?: () => void;
}

const LOT_SIZES: Record<string, number> = {
  NIFTY: 75,
  BANKNIFTY: 30,
  SENSEX: 20,
};

const STRIKE_STEPS: Record<string, number> = {
  NIFTY: 50,
  BANKNIFTY: 100,
  SENSEX: 100,
};

export function QuickScalpTicket({
  underlying,
  spotPrice,
  onUnderlyingChange,
  onOrderPlaced,
}: QuickScalpTicketProps) {
  const toast = useToast();
  const [lots, setLots] = useState<number>(1);
  const [slPoints, setSlPoints] = useState<number>(8);
  const [targetPoints, setTargetPoints] = useState<number>(16);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const lotSize = LOT_SIZES[underlying] || 50;
  const step = STRIKE_STEPS[underlying] || 50;
  const totalQuantity = lots * lotSize;

  // Calculate nearest ATM Strike
  const atmStrike = useMemo(() => {
    if (!spotPrice || spotPrice <= 0) {
      return underlying === 'NIFTY' ? 24500 : underlying === 'BANKNIFTY' ? 52000 : 80000;
    }
    return Math.round(spotPrice / step) * step;
  }, [spotPrice, step, underlying]);

  const callSymbol = `${underlying}${atmStrike}CE`;
  const putSymbol = `${underlying}${atmStrike}PE`;

  const handleExecuteScalp = async (side: 'CALL' | 'PUT') => {
    const symbol = side === 'CALL' ? callSymbol : putSymbol;
    try {
      setIsSubmitting(true);
      // Realistic default synthetic/market price fallback for paper broker
      const estimatedPrice = 120.0;
      
      const payload = {
        symbol,
        underlying,
        side: 'BUY' as const,
        order_type: 'MARKET' as const,
        product: 'INTRADAY' as const,
        quantity: totalQuantity,
        price: estimatedPrice,
        client_order_id: `scalp-${Date.now()}`,
      };

      const res = await api.placePaperOrder(payload);
      if (res.error) {
        toast.error(`Order failed: ${res.error}`);
      } else {
        toast.success(
          `⚡ SCALP FILLED: ${symbol} x ${totalQuantity} @ ₹${res.data?.fill_price?.toFixed(1) || estimatedPrice} (SL: -${slPoints}pt, TP: +${targetPoints}pt)`
        );
        onOrderPlaced?.();
      }
    } catch (err: unknown) {
      toast.error(`Execution error: ${(err as Error)?.message || 'Failed to place scalp order'}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const riskEstimateINR = totalQuantity * slPoints;
  const rewardEstimateINR = totalQuantity * targetPoints;

  return (
    <div className="flex flex-col bg-card border border-border rounded-lg p-3 select-none text-xs gap-3">
      {/* Header & Underlying Switcher */}
      <div className="flex items-center justify-between border-b border-border/60 pb-2">
        <div className="flex items-center gap-1.5 font-bold text-foreground">
          <Zap className="w-4 h-4 text-amber-500 fill-amber-500/20" />
          <span>1-Click Scalp Execution</span>
        </div>
        <div className="flex items-center gap-1 bg-secondary/80 p-0.5 rounded border border-border/50">
          {(['NIFTY', 'BANKNIFTY', 'SENSEX'] as const).map((u) => (
            <button
              key={u}
              type="button"
              onClick={() => onUnderlyingChange?.(u)}
              className={`px-1.5 py-0.5 rounded font-mono font-bold text-[10px] transition-colors ${
                underlying === u
                  ? 'bg-foreground text-background shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {u}
            </button>
          ))}
        </div>
      </div>

      {/* ATM Strikes & Lot Sizing */}
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-secondary/40 p-2 rounded border border-border/40">
          <span className="text-[10px] text-muted-foreground block">ATM Strike</span>
          <span className="font-mono font-bold text-sm text-foreground">
            {atmStrike}
          </span>
          <span className="text-[9px] text-muted-foreground block">
            Spot: {spotPrice ? `₹${spotPrice.toFixed(1)}` : '—'}
          </span>
        </div>

        <div className="bg-secondary/40 p-2 rounded border border-border/40">
          <span className="text-[10px] text-muted-foreground block">Total Qty</span>
          <span className="font-mono font-bold text-sm text-foreground">
            {totalQuantity} <span className="text-[10px] text-muted-foreground">({lots}L)</span>
          </span>
          <span className="text-[9px] text-muted-foreground block">
            1 Lot = {lotSize} Qty
          </span>
        </div>
      </div>

      {/* Quick Lot Multipliers */}
      <div className="flex items-center justify-between gap-1.5 bg-secondary/20 p-1.5 rounded border border-border/30">
        <span className="text-[10px] text-muted-foreground font-medium">Lots:</span>
        <div className="flex items-center gap-1 flex-1 justify-end">
          {[1, 2, 4, 10].map((l) => (
            <button
              key={l}
              type="button"
              onClick={() => setLots(l)}
              className={`flex-1 py-1 rounded text-center font-mono font-semibold transition-all ${
                lots === l
                  ? 'bg-amber-500 text-black shadow-xs font-bold'
                  : 'bg-secondary hover:bg-secondary/80 text-foreground'
              }`}
            >
              {l}x
            </button>
          ))}
        </div>
      </div>

      {/* Bracket Offsets (SL / TP) */}
      <div className="grid grid-cols-2 gap-2 text-[11px]">
        <div className="flex items-center justify-between bg-rose-500/5 border border-rose-500/20 px-2 py-1.5 rounded">
          <span className="text-rose-400 font-medium flex items-center gap-1">
            <ShieldAlert className="w-3 h-3" /> SL (pts)
          </span>
          <div className="flex items-center gap-1">
            <input
              type="number"
              min="2"
              max="50"
              value={slPoints}
              onChange={(e) => setSlPoints(Math.max(1, Number(e.target.value)))}
              className="w-10 text-right bg-background font-mono rounded px-1 py-0.5 border border-border"
            />
          </div>
        </div>

        <div className="flex items-center justify-between bg-emerald-500/5 border border-emerald-500/20 px-2 py-1.5 rounded">
          <span className="text-emerald-400 font-medium flex items-center gap-1">
            <Target className="w-3 h-3" /> TP (pts)
          </span>
          <div className="flex items-center gap-1">
            <input
              type="number"
              min="4"
              max="100"
              value={targetPoints}
              onChange={(e) => setTargetPoints(Math.max(2, Number(e.target.value)))}
              className="w-10 text-right bg-background font-mono rounded px-1 py-0.5 border border-border"
            />
          </div>
        </div>
      </div>

      {/* Risk / Reward Metrics */}
      <div className="flex items-center justify-between text-[10px] text-muted-foreground px-1">
        <span>Max Risk: <strong className="text-rose-400 font-mono">₹{riskEstimateINR.toLocaleString('en-IN')}</strong></span>
        <span>Target ROI: <strong className="text-emerald-400 font-mono">+₹{rewardEstimateINR.toLocaleString('en-IN')}</strong></span>
        <span>R:R <strong className="text-foreground font-mono">1:{(targetPoints / (slPoints || 1)).toFixed(1)}</strong></span>
      </div>

      {/* 1-Click Action Buttons */}
      <div className="grid grid-cols-2 gap-2 pt-1">
        <button
          type="button"
          disabled={isSubmitting}
          onClick={() => handleExecuteScalp('CALL')}
          className="flex flex-col items-center justify-center p-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] text-white font-bold transition-all shadow-md shadow-emerald-950/20 cursor-pointer disabled:opacity-50"
        >
          <div className="flex items-center gap-1 text-xs">
            <ArrowUpRight className="w-4 h-4" />
            <span>BUY CALL (CE)</span>
          </div>
          <span className="font-mono text-[10px] opacity-80 mt-0.5">
            {atmStrike} CE · Market
          </span>
        </button>

        <button
          type="button"
          disabled={isSubmitting}
          onClick={() => handleExecuteScalp('PUT')}
          className="flex flex-col items-center justify-center p-2.5 rounded-lg bg-rose-600 hover:bg-rose-500 active:scale-[0.98] text-white font-bold transition-all shadow-md shadow-rose-950/20 cursor-pointer disabled:opacity-50"
        >
          <div className="flex items-center gap-1 text-xs">
            <ArrowDownRight className="w-4 h-4" />
            <span>BUY PUT (PE)</span>
          </div>
          <span className="font-mono text-[10px] opacity-80 mt-0.5">
            {atmStrike} PE · Market
          </span>
        </button>
      </div>
    </div>
  );
}
