'use client';

import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import {
  Zap,
  ShieldAlert,
  ArrowUpRight,
  ArrowDownRight,
  Target,
  Minus,
  Plus,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/toast';
import { calculateStrikeForSide, StrikeOffset } from './autoPilotGuard';
import { useScalpContext } from './ScalpContext';
import { useOptionQuotes } from '@/hooks/useOptionQuotes';
import { useMarginPreview } from '@/hooks/useMarginPreview';
import { useExecutionGuard } from '@/hooks/useExecutionGuard';
import { useScalpKeyboard } from '@/hooks/useScalpKeyboard';

interface QuickScalpTicketProps {
  onBracketChange?: (slPts: number, tpPts: number) => void;
  onToggleHelp?: () => void;
}

const LOT_SIZES: Record<string, number> = {
  NIFTY: 75,
  BANKNIFTY: 30,
  SENSEX: 10,
};

const STRIKE_STEPS: Record<string, number> = {
  NIFTY: 50,
  BANKNIFTY: 100,
  SENSEX: 100,
};

const CONFIRM_LOTS_THRESHOLD = 4;
const CONFIRM_TIMEOUT_MS = 5000;

function clampInt(v: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(v)) return fallback;
  return Math.min(max, Math.max(min, Math.round(v)));
}

function fmtCompact(n: number | null) {
  if (n == null || !Number.isFinite(n)) return '—';
  if (n >= 10000000) return `${(n / 10000000).toFixed(2)}Cr`;
  if (n >= 100000) return `${(n / 100000).toFixed(2)}L`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return Math.round(n).toString();
}

export function QuickScalpTicket({ onBracketChange, onToggleHelp }: QuickScalpTicketProps) {
  const toast = useToast();
  const {
    underlying,
    setUnderlying,
    spotPrice,
    spotAgeSec,
    spotStale,
    refreshSpot,
    notifyOrderPlaced,
    panicSquareOff,
    toggleFullscreen,
  } = useScalpContext();

  const [lots, setLots] = useState<number>(1);
  const [slPoints, setSlPoints] = useState<number>(8);
  const [targetPoints, setTargetPoints] = useState<number>(16);
  const [strikeOffset, setStrikeOffset] = useState<StrikeOffset>('ATM');

  // Confirmation state
  const [confirmSide, setConfirmSide] = useState<'CALL' | 'PUT' | null>(null);
  const [confirmSecondsLeft, setConfirmSecondsLeft] = useState<number>(0);
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { isPending: isSubmitting, execute } = useExecutionGuard();

  const lotSize = LOT_SIZES[underlying] || 25;
  const step = STRIKE_STEPS[underlying] || 50;
  const totalQuantity = lots * lotSize;

  // Strikes
  const atmStrike = useMemo(() => {
    if (!spotPrice || spotPrice <= 0) return 0;
    return Math.round(spotPrice / step) * step;
  }, [spotPrice, step]);

  const ceStrike = useMemo(() => {
    return calculateStrikeForSide(spotPrice, step, strikeOffset, 'CE');
  }, [spotPrice, step, strikeOffset]);

  const peStrike = useMemo(() => {
    return calculateStrikeForSide(spotPrice, step, strikeOffset, 'PE');
  }, [spotPrice, step, strikeOffset]);

  const callSymbol = ceStrike > 0 ? `${underlying}${ceStrike}CE` : '—';
  const putSymbol = peStrike > 0 ? `${underlying}${peStrike}PE` : '—';
  const noLiveSpot = !spotPrice || spotPrice <= 0 || atmStrike <= 0;

  // ATM flip proximity warning (within 5 pts of flip threshold)
  const flipNear = useMemo(() => {
    if (noLiveSpot) return false;
    const upperFlip = atmStrike + step / 2;
    const lowerFlip = atmStrike - step / 2;
    const dist = Math.min(upperFlip - spotPrice, spotPrice - lowerFlip);
    return dist <= 5;
  }, [noLiveSpot, atmStrike, step, spotPrice]);

  // Option quotes hook
  const {
    quotes,
    quoteError,
    quoteAgeSec,
    quotesStale,
    ceSpread,
    peSpread,
    refresh: refreshQuotes,
  } = useOptionQuotes(underlying, ceStrike, peStrike);

  // Margin preview hook
  const hasCe = quotes.ceLtp != null && quotes.ceLtp > 0;
  const hasPe = quotes.peLtp != null && quotes.peLtp > 0;
  const refPrice = hasCe ? quotes.ceLtp : hasPe ? quotes.peLtp : null;
  const refSymbol = hasCe ? callSymbol : hasPe ? putSymbol : null;
  const marginInfo = useMarginPreview(underlying, refSymbol, totalQuantity, refPrice);

  // Lift bracket SL/TP
  useEffect(() => {
    onBracketChange?.(slPoints, targetPoints);
  }, [slPoints, targetPoints, onBracketChange]);

  // Confirmation timeout helper
  const clearConfirm = useCallback(() => {
    setConfirmSide(null);
    setConfirmSecondsLeft(0);
    if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
    if (countdownIntervalRef.current) clearInterval(countdownIntervalRef.current);
  }, []);

  useEffect(() => {
    return () => clearConfirm();
  }, [clearConfirm]);

  const armConfirm = useCallback((side: 'CALL' | 'PUT') => {
    clearConfirm();
    setConfirmSide(side);
    setConfirmSecondsLeft(5);

    countdownIntervalRef.current = setInterval(() => {
      setConfirmSecondsLeft((s) => {
        if (s <= 1) {
          clearConfirm();
          return 0;
        }
        return s - 1;
      });
    }, 1000);

    confirmTimerRef.current = setTimeout(() => {
      clearConfirm();
    }, CONFIRM_TIMEOUT_MS);
  }, [clearConfirm]);

  const needsConfirm = useCallback(
    (side: 'CALL' | 'PUT'): boolean => {
      if (lots >= CONFIRM_LOTS_THRESHOLD) return true;
      const ltp = side === 'CALL' ? quotes.ceLtp : quotes.peLtp;
      if (ltp == null || !(ltp > 0)) return true;
      const wide = side === 'CALL' ? ceSpread.wide : peSpread.wide;
      return wide;
    },
    [lots, quotes.ceLtp, quotes.peLtp, ceSpread.wide, peSpread.wide]
  );

  const handleExecuteScalp = useCallback(
    async (side: 'CALL' | 'PUT') => {
      if (noLiveSpot) {
        toast.error('No live spot quote — click retry spot to refresh');
        return;
      }

      if (needsConfirm(side) && confirmSide !== side) {
        armConfirm(side);
        return;
      }

      clearConfirm();
      const symbol = side === 'CALL' ? callSymbol : putSymbol;

      await execute(async () => {
        const payload = {
          symbol,
          underlying,
          side: 'BUY' as const,
          order_type: 'MARKET' as const,
          product: 'INTRADAY' as const,
          quantity: totalQuantity,
          client_order_id: `scalp-${Date.now()}`,
        };

        const res = await api.placePaperOrder(payload);
        if (res.error) {
          toast.error(`Order failed: ${res.error}`);
        } else {
          const fillPx = res.data?.fill_price;
          toast.success(
            fillPx && fillPx > 0
              ? `FILLED: ${symbol} x ${totalQuantity} @ ₹${fillPx.toFixed(1)} (SL: -${slPoints}pt, TP: +${targetPoints}pt)`
              : `Order placed: ${symbol} x ${totalQuantity}`
          );
          notifyOrderPlaced();
          void refreshQuotes();
        }
      });
    },
    [
      noLiveSpot,
      needsConfirm,
      confirmSide,
      clearConfirm,
      callSymbol,
      putSymbol,
      execute,
      underlying,
      totalQuantity,
      slPoints,
      targetPoints,
      toast,
      notifyOrderPlaced,
      refreshQuotes,
      armConfirm,
    ]
  );

  // Single global keyboard wiring
  useScalpKeyboard({
    onBuyCall: () => void handleExecuteScalp('CALL'),
    onBuyPut: () => void handleExecuteScalp('PUT'),
    onSetLots: (l) => {
      setLots(l);
      clearConfirm();
    },
    onPanicSquareOff: () => void panicSquareOff(),
    onToggleHelp,
    onToggleFullscreen: toggleFullscreen,
  });

  // Risk / reward calculations
  const riskEstimateINR = totalQuantity * slPoints;
  const rewardEstimateINR = totalQuantity * targetPoints;
  const estPremRisk = useMemo(() => {
    const delta = quotes.ceDelta || quotes.peDelta;
    if (delta && Number.isFinite(delta) && Math.abs(delta) > 0) {
      return totalQuantity * slPoints * Math.abs(delta);
    }
    return null;
  }, [totalQuantity, slPoints, quotes.ceDelta, quotes.peDelta]);

  // Render option quote strip
  const renderQuoteChip = (
    label: string,
    strike: number,
    ltp: number | null,
    delta: number | null,
    oi: number | null,
    spread: number | null,
    wide: boolean,
    side: 'CALL' | 'PUT'
  ) => {
    const isCall = side === 'CALL';
    return (
      <div className="flex items-center justify-between gap-1.5 bg-background/60 border border-border/50 rounded px-2 py-1.5 transition-colors">
        <div className="flex items-center gap-1.5 min-w-0">
          <span
            className={`font-mono font-black text-[10px] px-1.5 py-0.5 rounded ${
              isCall ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
            }`}
          >
            {label} {strike || ''}
          </span>
          <span className="font-mono text-[9px] text-muted-foreground hidden sm:inline">
            {delta != null ? `Δ ${delta.toFixed(2)}` : 'Δ —'}
          </span>
          {spread != null && (
            <span
              className={`text-[9px] font-mono px-1 rounded ${
                wide ? 'bg-amber-500/20 text-amber-400' : 'text-muted-foreground'
              }`}
            >
              spd {spread.toFixed(1)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`font-mono font-bold text-xs ${
              ltp && ltp > 0 ? (isCall ? 'text-emerald-400' : 'text-rose-400') : 'text-muted-foreground'
            }`}
          >
            {ltp && ltp > 0 ? `₹${ltp.toFixed(1)}` : 'MKT'}
          </span>
          <span className="font-mono text-[9px] text-muted-foreground">
            {oi != null ? `OI ${fmtCompact(oi)}` : ''}
          </span>
        </div>
      </div>
    );
  };

  const fireBlocked = isSubmitting || noLiveSpot;

  return (
    <div className="flex flex-col bg-card border border-border rounded-lg p-2.5 select-none text-xs gap-2">
      {/* Header & Underlying Switcher */}
      <div className="flex items-center justify-between gap-2 border-b border-border/60 pb-1.5">
        <div className="flex items-center gap-1.5 font-bold text-foreground">
          <Zap className="w-3.5 h-3.5 text-amber-500 fill-amber-500/20" />
          <span className="text-[11.5px]">1-Click Execution</span>
        </div>
        <div className="flex items-center gap-1 bg-secondary/80 p-0.5 rounded border border-border/50">
          {(['NIFTY', 'BANKNIFTY', 'SENSEX'] as const).map((u) => (
            <button
              key={u}
              type="button"
              onClick={() => {
                setUnderlying(u);
                clearConfirm();
              }}
              className={`px-1.5 py-0.5 rounded font-mono font-bold text-[10px] transition-colors cursor-pointer ${
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

      {/* Strike Matrix Selector with ATM Flip Proximity Callout */}
      <div className="flex flex-col gap-1 bg-secondary/30 p-1.5 rounded border border-border/40">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1">
            Strike Matrix
            {flipNear && (
              <span className="text-amber-400 text-[9px] font-mono flex items-center gap-0.5 bg-amber-500/15 px-1 rounded animate-pulse">
                <AlertTriangle className="w-2.5 h-2.5" /> ATM FLIP NEAR
              </span>
            )}
          </span>
          <span className="text-[10px] font-mono text-foreground font-semibold">
            CE {ceStrike || '—'} · PE {peStrike || '—'}
          </span>
        </div>

        {/* Compact Horizontal Segmented Selector */}
        <div className="grid grid-cols-3 gap-1 bg-secondary/60 p-0.5 rounded border border-border/40">
          {(['ITM', 'ATM', 'OTM'] as const).map((offset) => (
            <button
              key={offset}
              type="button"
              onClick={() => {
                setStrikeOffset(offset);
                clearConfirm();
              }}
              className={`py-1 rounded text-center font-mono font-bold text-[10px] transition-all cursor-pointer ${
                strikeOffset === offset
                  ? 'bg-amber-500 text-black shadow-xs font-black'
                  : 'text-muted-foreground hover:text-foreground hover:bg-secondary/70'
              }`}
            >
              {offset === 'ATM' ? '★ ATM' : offset === 'ITM' ? 'ITM -1' : 'OTM +1'}
            </button>
          ))}
        </div>
      </div>

      {/* Lot Sizing */}
      <div className="flex items-center justify-between gap-1.5 bg-secondary/20 p-1.5 rounded border border-border/30">
        <span className="text-[10px] text-muted-foreground font-medium whitespace-nowrap">Lots:</span>
        <div className="flex items-center gap-1 flex-1 justify-end">
          {[1, 2, 4, 10].map((l) => {
            const dangerous = l >= 10;
            return (
              <button
                key={l}
                type="button"
                disabled={isSubmitting}
                onClick={() => {
                  setLots(l);
                  clearConfirm();
                }}
                className={`flex-1 py-1 rounded text-center font-mono font-semibold transition-all cursor-pointer disabled:opacity-50 ${
                  lots === l
                    ? dangerous
                      ? 'bg-rose-500 text-white shadow-xs font-bold'
                      : 'bg-amber-500 text-black shadow-xs font-bold'
                    : dangerous
                      ? 'bg-secondary text-rose-400 border border-rose-500/40 hover:bg-rose-500/10'
                      : 'bg-secondary hover:bg-secondary/80 text-foreground'
                }`}
              >
                {l}x
              </button>
            );
          })}
        </div>
        <span className="font-mono text-[10px] text-foreground font-semibold whitespace-nowrap pl-1">
          {totalQuantity}q
        </span>
      </div>

      {/* Option Depth Chips */}
      <div className="flex flex-col gap-1">
        {renderQuoteChip(
          'CE',
          ceStrike,
          quotes.ceLtp,
          quotes.ceDelta,
          quotes.ceOi,
          ceSpread.spread,
          ceSpread.wide,
          'CALL'
        )}
        {renderQuoteChip(
          'PE',
          peStrike,
          quotes.peLtp,
          quotes.peDelta,
          quotes.peOi,
          peSpread.spread,
          peSpread.wide,
          'PUT'
        )}

        {/* Spot/Quote freshness banner if degraded */}
        {noLiveSpot ? (
          <div className="flex items-center justify-between gap-2 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[10px]">
            <span className="text-amber-300 font-mono">Waiting for live spot</span>
            <button
              type="button"
              onClick={refreshSpot}
              className="px-1.5 py-0.5 rounded bg-amber-500 text-black font-bold font-mono text-[10px] hover:bg-amber-400"
            >
              Retry spot
            </button>
          </div>
        ) : spotStale || quotesStale ? (
          <div className="flex items-center justify-between text-[9px] font-mono text-amber-400/90 px-1">
            <span>Data age: spot {spotAgeSec || 0}s · chain {quoteAgeSec || 0}s</span>
            <button
              type="button"
              onClick={() => {
                void refreshSpot();
                void refreshQuotes();
              }}
              className="inline-flex items-center gap-0.5 text-muted-foreground hover:text-foreground"
            >
              <RefreshCw className="w-2.5 h-2.5" /> refresh
            </button>
          </div>
        ) : null}

        {quoteError && (
          <span className="text-[10px] text-rose-400 font-mono">{quoteError}</span>
        )}
      </div>

      {/* SL & TP Brackets */}
      <div className="grid grid-cols-2 gap-1.5 text-[11px]">
        {/* SL */}
        <div className="flex flex-col gap-1 bg-rose-500/5 border border-rose-500/20 p-1.5 rounded">
          <div className="flex items-center justify-between">
            <span className="text-rose-400 font-bold text-[10px] flex items-center gap-1">
              <ShieldAlert className="w-3 h-3" /> SL (pts)
            </span>
            <div className="flex items-center gap-0.5">
              <button
                type="button"
                onClick={() => setSlPoints((v) => clampInt(v - 1, 2, 50, 8))}
                className="w-5 h-5 flex items-center justify-center rounded hover:bg-rose-500/20 text-muted-foreground hover:text-foreground cursor-pointer"
              >
                <Minus className="w-3 h-3" />
              </button>
              <span className="w-6 text-center font-mono font-bold text-xs text-foreground">
                {slPoints}
              </span>
              <button
                type="button"
                onClick={() => setSlPoints((v) => clampInt(v + 1, 2, 50, 8))}
                className="w-5 h-5 flex items-center justify-center rounded hover:bg-rose-500/20 text-muted-foreground hover:text-foreground cursor-pointer"
              >
                <Plus className="w-3 h-3" />
              </button>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {[5, 8, 12, 20].map((pt) => (
              <button
                key={pt}
                type="button"
                onClick={() => setSlPoints(pt)}
                className={`flex-1 py-0.5 rounded text-[9px] font-mono font-bold transition-all cursor-pointer ${
                  slPoints === pt
                    ? 'bg-rose-500 text-white shadow-xs'
                    : 'bg-secondary/60 text-muted-foreground hover:text-foreground'
                }`}
              >
                {pt}p
              </button>
            ))}
          </div>
        </div>

        {/* TP */}
        <div className="flex flex-col gap-1 bg-emerald-500/5 border border-emerald-500/20 p-1.5 rounded">
          <div className="flex items-center justify-between">
            <span className="text-emerald-400 font-bold text-[10px] flex items-center gap-1">
              <Target className="w-3 h-3" /> TP (pts)
            </span>
            <div className="flex items-center gap-0.5">
              <button
                type="button"
                onClick={() => setTargetPoints((v) => clampInt(v - 2, 4, 100, 16))}
                className="w-5 h-5 flex items-center justify-center rounded hover:bg-emerald-500/20 text-muted-foreground hover:text-foreground cursor-pointer"
              >
                <Minus className="w-3 h-3" />
              </button>
              <span className="w-6 text-center font-mono font-bold text-xs text-foreground">
                {targetPoints}
              </span>
              <button
                type="button"
                onClick={() => setTargetPoints((v) => clampInt(v + 2, 4, 100, 16))}
                className="w-5 h-5 flex items-center justify-center rounded hover:bg-emerald-500/20 text-muted-foreground hover:text-foreground cursor-pointer"
              >
                <Plus className="w-3 h-3" />
              </button>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {[10, 16, 25, 40].map((pt) => (
              <button
                key={pt}
                type="button"
                onClick={() => setTargetPoints(pt)}
                className={`flex-1 py-0.5 rounded text-[9px] font-mono font-bold transition-all cursor-pointer ${
                  targetPoints === pt
                    ? 'bg-emerald-600 text-white shadow-xs'
                    : 'bg-secondary/60 text-muted-foreground hover:text-foreground'
                }`}
              >
                {pt}p
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Risk / Reward Metrics & Surfaced Premium Risk */}
      <div className="flex items-center justify-between text-[10px] text-muted-foreground px-0.5 font-mono">
        <span>
          Risk <strong className="text-rose-400">-₹{riskEstimateINR.toLocaleString('en-IN')}</strong>
          {estPremRisk != null && (
            <span className="text-[9px] text-muted-foreground/80 block">
              Prem ₹{Math.round(estPremRisk).toLocaleString('en-IN')}
            </span>
          )}
        </span>
        <span>
          Target <strong className="text-emerald-400">+₹{rewardEstimateINR.toLocaleString('en-IN')}</strong>
        </span>
        <span>
          R:R <strong className="text-foreground">1:{(targetPoints / (slPoints || 1)).toFixed(1)}</strong>
        </span>
        {marginInfo ? (
          <span className={marginInfo.affordable ? 'text-muted-foreground' : 'text-rose-400 font-bold'}>
            Margin ₹{marginInfo.required.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
          </span>
        ) : null}
      </div>

      {/* 1-Click Action Buttons with Inline Countdown Confirmation */}
      <div className="grid grid-cols-2 gap-2 pt-0.5">
        {/* BUY CALL */}
        <button
          type="button"
          disabled={fireBlocked}
          onClick={() => void handleExecuteScalp('CALL')}
          className={`flex flex-col items-center justify-center py-2 px-2 rounded-lg font-bold transition-all shadow-md cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
            confirmSide === 'CALL'
              ? 'bg-amber-500 hover:bg-amber-400 text-black shadow-amber-950/20 ring-2 ring-amber-400'
              : 'bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] text-white shadow-emerald-950/20'
          }`}
        >
          <div className="flex items-center gap-1.5 text-xs font-black">
            <ArrowUpRight className="w-4 h-4" />
            <span>
              {confirmSide === 'CALL'
                ? `CONFIRM BUY CE (${confirmSecondsLeft}s)`
                : isSubmitting
                  ? 'SUBMITTING…'
                  : 'BUY CALL (CE)'}
            </span>
            <kbd className="text-[9px] font-mono bg-black/20 px-1 rounded opacity-80">C</kbd>
          </div>
          <span className="font-mono text-[10px] opacity-85 mt-0.5">
            {noLiveSpot
              ? 'WAITING SPOT'
              : quotes.ceLtp && quotes.ceLtp > 0
                ? `${ceStrike} CE · ₹${quotes.ceLtp.toFixed(1)}`
                : `${ceStrike} CE · MKT`}
          </span>
        </button>

        {/* BUY PUT */}
        <button
          type="button"
          disabled={fireBlocked}
          onClick={() => void handleExecuteScalp('PUT')}
          className={`flex flex-col items-center justify-center py-2 px-2 rounded-lg font-bold transition-all shadow-md cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
            confirmSide === 'PUT'
              ? 'bg-amber-500 hover:bg-amber-400 text-black shadow-amber-950/20 ring-2 ring-amber-400'
              : 'bg-rose-600 hover:bg-rose-500 active:scale-[0.98] text-white shadow-rose-950/20'
          }`}
        >
          <div className="flex items-center gap-1.5 text-xs font-black">
            <ArrowDownRight className="w-4 h-4" />
            <span>
              {confirmSide === 'PUT'
                ? `CONFIRM BUY PE (${confirmSecondsLeft}s)`
                : isSubmitting
                  ? 'SUBMITTING…'
                  : 'BUY PUT (PE)'}
            </span>
            <kbd className="text-[9px] font-mono bg-black/20 px-1 rounded opacity-80">P</kbd>
          </div>
          <span className="font-mono text-[10px] opacity-85 mt-0.5">
            {noLiveSpot
              ? 'WAITING SPOT'
              : quotes.peLtp && quotes.peLtp > 0
                ? `${peStrike} PE · ₹${quotes.peLtp.toFixed(1)}`
                : `${peStrike} PE · MKT`}
          </span>
        </button>
      </div>

      <p className="text-[9px] text-muted-foreground/70 font-mono text-center -mt-0.5">
        Keys: C = CE · P = PE · 1-4 = Lots · F = Full · Shift+Esc = Panic · ? = Help
      </p>
    </div>
  );
}
