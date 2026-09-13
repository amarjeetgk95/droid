'use client';

import { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { Zap, ShieldAlert, ArrowUpRight, ArrowDownRight, Target, Minus, Plus } from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/toast';

interface QuickScalpTicketProps {
  underlying: 'NIFTY' | 'BANKNIFTY' | 'SENSEX';
  spotPrice: number;
  /** Epoch ms of the last successful spot fetch — drives staleness even when price is flat. */
  spotUpdatedAt?: number | null;
  onUnderlyingChange?: (u: 'NIFTY' | 'BANKNIFTY' | 'SENSEX') => void;
  onOrderPlaced?: () => void;
  onBracketChange?: (slPts: number, tpPts: number) => void;
  onRetrySpot?: () => void;
}

// Aligned with backend contract_master (NIFTY 25, BANKNIFTY 15, SENSEX 10).
const LOT_SIZES: Record<string, number> = {
  NIFTY: 25,
  BANKNIFTY: 15,
  SENSEX: 10,
};

const STRIKE_STEPS: Record<string, number> = {
  NIFTY: 50,
  BANKNIFTY: 100,
  SENSEX: 100,
};

const CONFIRM_LOTS_THRESHOLD = 4;
const QUOTE_STALE_SEC = 15;
const CONFIRM_TIMEOUT_MS = 5000;

interface AtmQuotes {
  ceLtp: number | null;
  peLtp: number | null;
  ceBid: number | null;
  ceAsk: number | null;
  peBid: number | null;
  peAsk: number | null;
  ceIv: number | null;
  peIv: number | null;
  ceDelta: number | null;
  peDelta: number | null;
  ceOi: number | null;
  peOi: number | null;
  expiry: string | null;
  fetchedAt: number | null;
}

const EMPTY_QUOTES: AtmQuotes = {
  ceLtp: null, peLtp: null,
  ceBid: null, ceAsk: null, peBid: null, peAsk: null,
  ceIv: null, peIv: null, ceDelta: null, peDelta: null,
  ceOi: null, peOi: null, expiry: null, fetchedAt: null,
};

function clampInt(v: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(v)) return fallback;
  return Math.min(max, Math.max(min, Math.round(v)));
}

export function QuickScalpTicket({
  underlying,
  spotPrice,
  spotUpdatedAt,
  onUnderlyingChange,
  onOrderPlaced,
  onBracketChange,
  onRetrySpot,
}: QuickScalpTicketProps) {
  const toast = useToast();
  const [lots, setLots] = useState<number>(1);
  const [slPoints, setSlPoints] = useState<number>(8);
  const [targetPoints, setTargetPoints] = useState<number>(16);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [quotes, setQuotes] = useState<AtmQuotes>(EMPTY_QUOTES);
  const [quoteError, setQuoteError] = useState<string | null>(null);
  const [marginInfo, setMarginInfo] = useState<{ required: number; affordable: boolean } | null>(null);
  const [confirmSide, setConfirmSide] = useState<'CALL' | 'PUT' | null>(null);
  const [confirmLots, setConfirmLots] = useState<number>(0);
  const [nowMs, setNowMs] = useState(() => Date.now());

  const requestIdRef = useRef(0);
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const submittingRef = useRef(false);
  const lastSpotRef = useRef<{ price: number; at: number }>({ price: spotPrice, at: Date.now() });

  const lotSize = LOT_SIZES[underlying] || 50;
  const step = STRIKE_STEPS[underlying] || 50;
  const totalQuantity = lots * lotSize;

  // Track spot freshness from the parent's successful fetch timestamp so a
  // flat market (same LTP across polls) doesn't falsely read as stale.
  useEffect(() => {
    if (Number.isFinite(spotPrice) && spotPrice > 0) {
      if (typeof spotUpdatedAt === 'number' && Number.isFinite(spotUpdatedAt) && spotUpdatedAt > 0) {
        lastSpotRef.current = { price: spotPrice, at: spotUpdatedAt };
      } else if (spotPrice !== lastSpotRef.current.price) {
        lastSpotRef.current = { price: spotPrice, at: Date.now() };
      }
    }
  }, [spotPrice, spotUpdatedAt]);
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const spotAgeSec = useMemo(() => {
    if (!Number.isFinite(spotPrice) || spotPrice <= 0) return null;
    return Math.max(0, Math.floor((nowMs - lastSpotRef.current.at) / 1000));
  }, [nowMs, spotPrice]);

  // Calculate nearest ATM Strike — FYERS spot only, never hardcoded fallback.
  const atmStrike = useMemo(() => {
    if (!spotPrice || spotPrice <= 0) {
      return 0;
    }
    return Math.round(spotPrice / step) * step;
  }, [spotPrice, step]);

  const callSymbol = atmStrike > 0 ? `${underlying}${atmStrike}CE` : '—';
  const putSymbol = atmStrike > 0 ? `${underlying}${atmStrike}PE` : '—';
  const noLiveSpot = !spotPrice || spotPrice <= 0 || atmStrike <= 0;

  // Distance to the half-step boundary where ATM flips.
  const flipDistance = useMemo(() => {
    if (noLiveSpot) return null;
    const upperFlip = atmStrike + step / 2;
    const lowerFlip = atmStrike - step / 2;
    return Math.min(upperFlip - spotPrice, spotPrice - lowerFlip);
  }, [noLiveSpot, atmStrike, step, spotPrice]);

  // Lift bracket to parent (chart overlay) without feedback loops.
  useEffect(() => {
    onBracketChange?.(slPoints, targetPoints);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slPoints, targetPoints]);

  // Live ATM option quotes from the chain (LTP + bid/ask + greeks + OI).
  const fetchAtmQuotes = useCallback(async () => {
    if (typeof document !== 'undefined' && document.hidden) return;
    if (!atmStrike || atmStrike <= 0) return;
    const reqId = ++requestIdRef.current;
    try {
      const res = await api.getOptionChain(underlying);
      if (reqId !== requestIdRef.current) return;
      if (res.error) {
        setQuoteError(res.error);
        return;
      }
      const chain = res.data;
      const strikes = chain?.strikes || [];
      if (strikes.length === 0) {
        setQuoteError('Empty option chain');
        return;
      }
      let best = strikes[0];
      let bestDist = Math.abs((best?.strike ?? 0) - atmStrike);
      for (const row of strikes) {
        const d = Math.abs(row.strike - atmStrike);
        if (d < bestDist) {
          best = row;
          bestDist = d;
        }
      }
      setQuotes({
        ceLtp: best?.call?.ltp ?? null,
        peLtp: best?.put?.ltp ?? null,
        ceBid: best?.call?.bid ?? null,
        ceAsk: best?.call?.ask ?? null,
        peBid: best?.put?.bid ?? null,
        peAsk: best?.put?.ask ?? null,
        ceIv: best?.call?.greeks?.iv ?? null,
        peIv: best?.put?.greeks?.iv ?? null,
        ceDelta: best?.call?.greeks?.delta ?? null,
        peDelta: best?.put?.greeks?.delta ?? null,
        ceOi: best?.call?.open_interest ?? null,
        peOi: best?.put?.open_interest ?? null,
        expiry: chain?.expiry ?? null,
        fetchedAt: Date.now(),
      });
      setQuoteError(null);
    } catch (err: unknown) {
      if (reqId !== requestIdRef.current) return;
      setQuoteError((err as Error)?.message || 'Option chain unavailable');
    }
  }, [atmStrike, underlying]);

  useEffect(() => {
    setQuotes(EMPTY_QUOTES);
    setQuoteError(null);
    setConfirmSide(null);
    fetchAtmQuotes();
    const interval = setInterval(fetchAtmQuotes, 5000);
    const onVisible = () => {
      if (!document.hidden) fetchAtmQuotes();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [fetchAtmQuotes]);

  useEffect(() => {
    return () => {
      if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
    };
  }, []);

  const quoteAgeSec = quotes.fetchedAt != null ? Math.max(0, Math.floor((nowMs - quotes.fetchedAt) / 1000)) : null;
  const quotesStale = quoteAgeSec == null || quoteAgeSec > QUOTE_STALE_SEC;

  const spreadFor = (bid: number | null, ask: number | null, ltp: number | null) => {
    if (bid == null || ask == null || ltp == null) return { spread: null as number | null, wide: false, missing: true };
    if (!(bid > 0) || !(ask > 0) || !(ltp > 0) || ask < bid) return { spread: null, wide: true, missing: false };
    const spread = ask - bid;
    const wide = spread > Math.max(1.5, ltp * 0.03);
    return { spread, wide, missing: false };
  };
  const ceSpread = spreadFor(quotes.ceBid, quotes.ceAsk, quotes.ceLtp);
  const peSpread = spreadFor(quotes.peBid, quotes.peAsk, quotes.peLtp);

  // Margin preview (debounced, advisory only — never blocks).
  // Uses the side that actually has a quote so CE/PE estimates match.
  useEffect(() => {
    if (!atmStrike || totalQuantity <= 0) {
      setMarginInfo(null);
      return;
    }
    const hasCe = quotes.ceLtp != null && quotes.ceLtp > 0;
    const hasPe = quotes.peLtp != null && quotes.peLtp > 0;
    const refPrice = hasCe ? quotes.ceLtp : hasPe ? quotes.peLtp : null;
    const refSymbol = hasCe ? callSymbol : hasPe ? putSymbol : null;
    if (refPrice == null || refSymbol == null) {
      setMarginInfo(null);
      return;
    }
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const res = await api.previewPaperMargin({
          symbol: refSymbol,
          underlying,
          side: 'BUY',
          quantity: totalQuantity,
          price: refPrice,
        });
        if (cancelled) return;
        if (!res.error && res.data) {
          setMarginInfo({ required: res.data.required_margin, affordable: res.data.affordable });
        }
      } catch {
        if (!cancelled) setMarginInfo(null);
      }
    }, 600);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [atmStrike, totalQuantity, quotes.ceLtp, quotes.peLtp, callSymbol, putSymbol, underlying]);

  const armConfirm = (side: 'CALL' | 'PUT') => {
    setConfirmSide(side);
    setConfirmLots(lots);
    if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
    confirmTimerRef.current = setTimeout(() => {
      setConfirmSide(null);
    }, CONFIRM_TIMEOUT_MS);
  };

  const needsConfirm = (side: 'CALL' | 'PUT'): boolean => {
    if (lots >= CONFIRM_LOTS_THRESHOLD) return true;
    const ltp = side === 'CALL' ? quotes.ceLtp : quotes.peLtp;
    if (ltp == null || !(ltp > 0)) return true; // no quote: confirm blind fire, backend validates
    const wide = side === 'CALL' ? ceSpread.wide : peSpread.wide;
    return wide;
  };

  const handleExecuteScalp = async (side: 'CALL' | 'PUT') => {
    if (submittingRef.current || isSubmitting) return;
    if (noLiveSpot) {
      toast.error('No live spot — tap Retry spot, no synthetic price fallback');
      return;
    }
    // Fat-finger guard: large lots, wide spread, or missing quote need a second tap.
    if (needsConfirm(side) && (confirmSide !== side || confirmLots !== lots)) {
      armConfirm(side);
      const ltp = side === 'CALL' ? quotes.ceLtp : quotes.peLtp;
      const reason =
        lots >= CONFIRM_LOTS_THRESHOLD
          ? `${lots}x size`
          : ltp == null || !(ltp > 0)
            ? 'no live quote (backend will validate)'
            : 'wide spread';
      toast.warning(`Confirm ${side} (${reason}): tap again within 5s to fire ${totalQuantity} qty`);
      return;
    }
    setConfirmSide(null);
    const symbol = side === 'CALL' ? callSymbol : putSymbol;
    try {
      submittingRef.current = true;
      setIsSubmitting(true);
      // Truth-of-Wall: MARKET order with no client price — backend fills from live chain.
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
            ? `SCALP FILLED: ${symbol} x ${totalQuantity} @ ₹${fillPx.toFixed(1)} (SL: -${slPoints}pt, TP: +${targetPoints}pt)`
            : `Order placed: ${symbol} x ${totalQuantity} — awaiting live fill (no synthetic price)`
        );
        onOrderPlaced?.();
        fetchAtmQuotes();
      }
    } catch (err: unknown) {
      toast.error(`Execution error: ${(err as Error)?.message || 'Failed to place scalp order'}`);
    } finally {
      submittingRef.current = false;
      setIsSubmitting(false);
    }
  };

  // Keyboard fast-path (C/P). Ignored while typing so SL/TP edits are safe.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === 'c' || k === 'p') {
        e.preventDefault();
        handleExecuteScalp(k === 'c' ? 'CALL' : 'PUT');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lots, confirmSide, confirmLots, noLiveSpot, quotes.ceLtp, quotes.peLtp, callSymbol, putSymbol, slPoints, targetPoints, isSubmitting]);

  const riskEstimateINR = totalQuantity * slPoints;
  const rewardEstimateINR = totalQuantity * targetPoints;
  const estPremRisk = (delta: number | null) =>
    delta != null && Number.isFinite(delta) && Math.abs(delta) > 0
      ? totalQuantity * slPoints * Math.abs(delta)
      : null;
  const cePremRisk = estPremRisk(quotes.ceDelta);
  const pePremRisk = estPremRisk(quotes.peDelta);

  const fmtCompact = (n: number | null) => {
    if (n == null || !Number.isFinite(n)) return '—';
    if (n >= 10000000) return `${(n / 10000000).toFixed(2)}Cr`;
    if (n >= 100000) return `${(n / 100000).toFixed(2)}L`;
    if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
    return Math.round(n).toString();
  };

  const quoteChip = (label: string, ltp: number | null, iv: number | null, delta: number | null, oi: number | null) => (
    <div className="flex items-center justify-between gap-2 bg-background/50 border border-border/40 rounded px-2 py-1">
      <span className="font-mono font-bold text-[10px] text-muted-foreground">{label}</span>
      <span className={`font-mono font-bold text-xs ${ltp && ltp > 0 ? 'text-foreground' : 'text-rose-400'}`}>
        {ltp && ltp > 0 ? `₹${ltp.toFixed(1)}` : 'NO QUOTE'}
      </span>
      <span className="font-mono text-[9px] text-muted-foreground hidden sm:inline">
        {iv != null ? `IV ${(iv * 100).toFixed(1)}%` : 'IV —'} · {delta != null ? `Δ ${delta.toFixed(2)}` : 'Δ —'} · OI {oi != null ? fmtCompact(oi) : '—'}
      </span>
    </div>
  );

  // Controls stay interactive: lots/SL/TP/underlying always clickable.
  // Only the fire buttons need a live spot; missing option quotes downgrade
  // to tap-again confirm instead of a dead disabled button.
  const lotsDisabled = isSubmitting;
  const fireBlocked = isSubmitting || noLiveSpot;

  return (
    <div className="flex flex-col bg-card border border-border rounded-lg p-3 select-none text-xs gap-3">
      {/* Header & Underlying Switcher */}
      <div className="flex items-center justify-between gap-2 border-b border-border/60 pb-2">
        <div className="flex items-center gap-1.5 font-bold text-foreground">
          <Zap className="w-4 h-4 text-amber-500 fill-amber-500/20" />
          <span>1-Click Scalp Execution</span>
        </div>
        <div className="flex items-center gap-1 bg-secondary/80 p-0.5 rounded border border-border/50" role="tablist" aria-label="Underlying">
          {(['NIFTY', 'BANKNIFTY', 'SENSEX'] as const).map((u) => (
            <button
              key={u}
              type="button"
              role="tab"
              aria-selected={underlying === u}
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
            {atmStrike || '—'}
          </span>
          <span className="text-[9px] text-muted-foreground block">
            Spot: {spotPrice ? `₹${spotPrice.toFixed(1)}` : '—'}
            {spotAgeSec != null && spotPrice > 0 ? (
              <span className={spotAgeSec > 5 ? 'text-amber-400' : ''}> · {spotAgeSec}s ago</span>
            ) : null}
          </span>
          <span className="text-[9px] text-muted-foreground block">
            {flipDistance != null ? `ATM flips in ${flipDistance.toFixed(1)} pts` : '—'}
            {quotes.expiry ? ` · Exp ${quotes.expiry}` : ''}
          </span>
        </div>

        <div className="bg-secondary/40 p-2 rounded border border-border/40">
          <span className="text-[10px] text-muted-foreground block">Total Qty</span>
          <span className="font-mono font-bold text-sm text-foreground">
            {totalQuantity} <span className="text-[10px] text-muted-foreground font-medium">({lots} {lots === 1 ? 'lot' : 'lots'})</span>
          </span>
          <span className="text-[9px] text-muted-foreground block">
            1 lot = {lotSize} qty
          </span>
          <span className="text-[9px] block">
            {marginInfo ? (
              <span className={marginInfo.affordable ? 'text-emerald-400' : 'text-rose-400'}>
                Margin ₹{marginInfo.required.toLocaleString('en-IN', { maximumFractionDigits: 0 })}{marginInfo.affordable ? '' : ' · shortfall'}
              </span>
            ) : (
              <span className="text-muted-foreground">Margin —</span>
            )}
          </span>
        </div>
      </div>

      {/* Live option quotes — advisory, with manual retry */}
      <div className="flex flex-col gap-1">
        {quoteChip('CE', quotes.ceLtp, quotes.ceIv, quotes.ceDelta, quotes.ceOi)}
        {quoteChip('PE', quotes.peLtp, quotes.peIv, quotes.peDelta, quotes.peOi)}
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9px] font-mono px-0.5">
          <span className={ceSpread.wide ? 'text-amber-400' : 'text-muted-foreground'}>
            CE spread {ceSpread.spread != null ? `₹${ceSpread.spread.toFixed(1)}` : '—'}{ceSpread.wide ? ' · WIDE' : ''}
          </span>
          <span className={peSpread.wide ? 'text-amber-400' : 'text-muted-foreground'}>
            PE spread {peSpread.spread != null ? `₹${peSpread.spread.toFixed(1)}` : '—'}{peSpread.wide ? ' · WIDE' : ''}
          </span>
          <span className={quotesStale ? 'text-amber-400' : 'text-muted-foreground'}>
            {quoteAgeSec != null ? `quotes ${quoteAgeSec}s ago` : 'quotes —'}
          </span>
          {quoteError ? <span className="text-rose-400">· {quoteError}</span> : null}
          {(quoteError || quotes.ceLtp == null || quotes.peLtp == null) && (
            <button
              type="button"
              onClick={() => fetchAtmQuotes()}
              className="ml-auto px-1.5 py-0.5 rounded bg-secondary hover:bg-secondary/80 text-foreground border border-border/50"
            >
              Retry quotes
            </button>
          )}
        </div>
        {noLiveSpot && (
          <div className="flex items-center justify-between gap-2 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[10px]">
            <span className="text-amber-300 font-mono">Waiting for live spot — orders need ATM</span>
            {onRetrySpot && (
              <button
                type="button"
                onClick={onRetrySpot}
                className="px-1.5 py-0.5 rounded bg-amber-500 text-black font-bold font-mono text-[10px] hover:bg-amber-400"
              >
                Retry spot
              </button>
            )}
          </div>
        )}
      </div>

      {/* Quick Lot Multipliers */}
      <div className="flex items-center justify-between gap-1.5 bg-secondary/20 p-1.5 rounded border border-border/30">
        <span className="text-[10px] text-muted-foreground font-medium">Lots:</span>
        <div className="flex items-center gap-1 flex-1 justify-end" role="radiogroup" aria-label="Lots">
          {[1, 2, 4, 10].map((l) => {
            const dangerous = l >= 10;
            return (
              <button
                key={l}
                type="button"
                role="radio"
                aria-checked={lots === l}
                disabled={lotsDisabled}
                onClick={() => {
                  setLots(l);
                  setConfirmSide(null);
                }}
                title={l >= CONFIRM_LOTS_THRESHOLD ? `${l}x needs tap-again confirm` : `${l} lot${l > 1 ? 's' : ''}`}
                className={`flex-1 py-1 rounded text-center font-mono font-semibold transition-all disabled:opacity-50 ${
                  lots === l
                    ? dangerous
                      ? 'bg-rose-500 text-white shadow-xs font-bold'
                      : l >= CONFIRM_LOTS_THRESHOLD
                        ? 'bg-amber-500 text-black shadow-xs font-bold'
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
      </div>

      {/* Bracket Offsets (SL / TP) — underlying points */}
      <div className="grid grid-cols-2 gap-2 text-[11px]">
        <div className="flex items-center justify-between bg-rose-500/5 border border-rose-500/20 px-2 py-1.5 rounded">
          <span className="text-rose-400 font-medium flex items-center gap-1">
            <ShieldAlert className="w-3 h-3" /> SL (u-pts)
          </span>
          <div className="flex items-center gap-1">
            <button type="button" aria-label="Decrease stop loss" onClick={() => setSlPoints((v) => clampInt(v - 1, 2, 50, 8))} className="p-0.5 rounded hover:bg-secondary text-muted-foreground hover:text-foreground">
              <Minus className="w-3 h-3" />
            </button>
            <input
              type="number"
              min="2"
              max="50"
              value={slPoints}
              onChange={(e) => setSlPoints(clampInt(Number(e.target.value), 2, 50, 8))}
              className="w-12 text-right bg-background font-mono rounded px-1 py-0.5 border border-border"
              aria-label="Stop loss in underlying points"
            />
            <button type="button" aria-label="Increase stop loss" onClick={() => setSlPoints((v) => clampInt(v + 1, 2, 50, 8))} className="p-0.5 rounded hover:bg-secondary text-muted-foreground hover:text-foreground">
              <Plus className="w-3 h-3" />
            </button>
          </div>
        </div>

        <div className="flex items-center justify-between bg-emerald-500/5 border border-emerald-500/20 px-2 py-1.5 rounded">
          <span className="text-emerald-400 font-medium flex items-center gap-1">
            <Target className="w-3 h-3" /> TP (u-pts)
          </span>
          <div className="flex items-center gap-1">
            <button type="button" aria-label="Decrease target" onClick={() => setTargetPoints((v) => clampInt(v - 2, 4, 100, 16))} className="p-0.5 rounded hover:bg-secondary text-muted-foreground hover:text-foreground">
              <Minus className="w-3 h-3" />
            </button>
            <input
              type="number"
              min="4"
              max="100"
              value={targetPoints}
              onChange={(e) => setTargetPoints(clampInt(Number(e.target.value), 4, 100, 16))}
              className="w-12 text-right bg-background font-mono rounded px-1 py-0.5 border border-border"
              aria-label="Target in underlying points"
            />
            <button type="button" aria-label="Increase target" onClick={() => setTargetPoints((v) => clampInt(v + 2, 4, 100, 16))} className="p-0.5 rounded hover:bg-secondary text-muted-foreground hover:text-foreground">
              <Plus className="w-3 h-3" />
            </button>
          </div>
        </div>
      </div>

      {/* Risk / Reward Metrics — underlying notional + delta-adjusted premium estimate */}
      <div className="flex flex-col gap-0.5 text-[10px] text-muted-foreground px-1">
        <div className="flex items-center justify-between">
          <span title="Underlying-points notional (qty × SL). Actual option premium loss is the Δ-adjusted estimate below.">Max Risk (underlying notional): <strong className="text-rose-400 font-mono">₹{riskEstimateINR.toLocaleString('en-IN')}</strong></span>
          <span>Target ROI: <strong className="text-emerald-400 font-mono">+₹{rewardEstimateINR.toLocaleString('en-IN')}</strong></span>
          <span>R:R <strong className="text-foreground font-mono">1:{(targetPoints / (slPoints || 1)).toFixed(1)}</strong></span>
        </div>
        <div className="flex items-center justify-between font-mono text-[9px]">
          <span title="Premium moves ~delta × underlying, so actual premium risk differs from underlying notional">
            CE prem risk ≈ {cePremRisk != null ? `₹${cePremRisk.toLocaleString('en-IN', { maximumFractionDigits: 0 })}` : '—'}
          </span>
          <span>
            PE prem risk ≈ {pePremRisk != null ? `₹${pePremRisk.toLocaleString('en-IN', { maximumFractionDigits: 0 })}` : '—'}
          </span>
          <span className="text-muted-foreground/70">Δ-adjusted est.</span>
        </div>
      </div>

      {/* 1-Click Action Buttons — always clickable when spot is live; missing
          quotes fall back to tap-again confirm and backend validation */}
      <div className="grid grid-cols-2 gap-2 pt-1">
        <button
          type="button"
          disabled={fireBlocked}
          title={noLiveSpot ? 'No live spot — tap Retry spot' : 'Buy CE market (shortcut: C)'}
          onClick={() => handleExecuteScalp('CALL')}
          className={`flex flex-col items-center justify-center p-2.5 rounded-lg font-bold transition-all shadow-md cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
            confirmSide === 'CALL' && confirmLots === lots
              ? 'bg-amber-500 hover:bg-amber-400 text-black shadow-amber-950/20 animate-pulse'
              : 'bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] text-white shadow-emerald-950/20'
          }`}
        >
          <div className="flex items-center gap-1 text-xs">
            <ArrowUpRight className="w-4 h-4" />
            <span>{confirmSide === 'CALL' && confirmLots === lots ? 'CONFIRM CE?' : 'BUY CALL (CE)'}</span>
          </div>
          <span className="font-mono text-[10px] opacity-80 mt-0.5">
            {noLiveSpot ? 'NO LIVE SPOT' : !(quotes.ceLtp && quotes.ceLtp > 0) ? `${atmStrike} CE · MKT (no quote)` : `${atmStrike} CE · MKT ${quotes.ceLtp ? `₹${quotes.ceLtp.toFixed(1)}` : ''}`}
          </span>
        </button>

        <button
          type="button"
          disabled={fireBlocked}
          title={noLiveSpot ? 'No live spot — tap Retry spot' : 'Buy PE market (shortcut: P)'}
          onClick={() => handleExecuteScalp('PUT')}
          className={`flex flex-col items-center justify-center p-2.5 rounded-lg font-bold transition-all shadow-md cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
            confirmSide === 'PUT' && confirmLots === lots
              ? 'bg-amber-500 hover:bg-amber-400 text-black shadow-amber-950/20 animate-pulse'
              : 'bg-rose-600 hover:bg-rose-500 active:scale-[0.98] text-white shadow-rose-950/20'
          }`}
        >
          <div className="flex items-center gap-1 text-xs">
            <ArrowDownRight className="w-4 h-4" />
            <span>{confirmSide === 'PUT' && confirmLots === lots ? 'CONFIRM PE?' : 'BUY PUT (PE)'}</span>
          </div>
          <span className="font-mono text-[10px] opacity-80 mt-0.5">
            {noLiveSpot ? 'NO LIVE SPOT' : !(quotes.peLtp && quotes.peLtp > 0) ? `${atmStrike} PE · MKT (no quote)` : `${atmStrike} PE · MKT ${quotes.peLtp ? `₹${quotes.peLtp.toFixed(1)}` : ''}`}
          </span>
        </button>
      </div>
      <p className="text-[9px] text-muted-foreground/70 font-mono px-0.5 -mt-1">
        {isSubmitting ? 'Firing order…' : 'Keys: C = CE · P = PE · 4x/10x, wide spreads & missing quotes need tap-again.'}
      </p>
    </div>
  );
}
