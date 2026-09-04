'use client';

import { useState, useEffect, useMemo } from 'react';
import { OrderPayload, BasketOrderPayload } from '@/lib/types';
import { Send, Zap, PlusCircle, MinusCircle, Plus, Minus } from 'lucide-react';
import { api } from '@/lib/api';
import { lotSizeFor, estimateMarginLocal, buildOptionSymbol } from '@/lib/paperLots';

type BasketLeg = {
  id: number;
  symbol: string;
  underlying: string;
  side: 'BUY' | 'SELL';
  product: 'INTRADAY' | 'CARRYFORWARD';
  quantity: number;
  price: number;
};

let legId = 0;
const nextLegId = () => ++legId;

function parseSymbol(symbol: string): { strike: number | null; optionType: 'CE' | 'PE' } {
  const s = (symbol || '').toUpperCase();
  const optionType = s.endsWith('PE') ? 'PE' : s.endsWith('CE') ? 'CE' : 'CE';
  const m = s.match(/(\d{3,6})\s*(CE|PE)?$/);
  return { strike: m ? Number(m[1]) : null, optionType: (m?.[2] as 'CE' | 'PE') || optionType };
}

export function OrderEntryTicket({
  onPlaceOrder,
  onPlaceBasket,
  loading,
  prefill,
  availableMargin,
}: {
  onPlaceOrder: (order: OrderPayload) => void;
  onPlaceBasket: (basket: BasketOrderPayload) => void;
  loading: boolean;
  prefill?: OrderPayload | null;
  availableMargin?: number;
}) {
  const [activeTab, setActiveTab] = useState<'SINGLE' | 'BASKET'>('SINGLE');

  // Single order builder state — symbol is derived, never free-typed.
  const [underlying, setUnderlying] = useState('NIFTY');
  const [optionType, setOptionType] = useState<'CE' | 'PE'>('CE');
  const [strike, setStrike] = useState(24800);
  const [lots, setLots] = useState(1);
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [product, setProduct] = useState<'INTRADAY' | 'CARRYFORWARD'>('INTRADAY');
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET');
  const [price, setPrice] = useState(150.0);
  const [customSymbol, setCustomSymbol] = useState<string | null>(null);

  const lotSize = lotSizeFor(underlying);
  const quantity = Math.max(lotSize, lots * lotSize);
  const symbol = customSymbol ?? buildOptionSymbol(underlying, strike, optionType);
  const fillPrice = orderType === 'MARKET' ? 0 : Number(price);

  // Retry from Order Book: prefill builder (halve qty as a starting suggestion).
  useEffect(() => {
    if (!prefill) return;
    if (prefill.underlying) {
      setUnderlying(prefill.underlying);
      const parsed = parseSymbol(prefill.symbol);
      if (parsed.strike) setStrike(parsed.strike);
      setOptionType(parsed.optionType);
      setCustomSymbol(null);
      const ls = lotSizeFor(prefill.underlying);
      if (typeof prefill.quantity === 'number' && prefill.quantity > 0) {
        setLots(Math.max(1, Math.floor(prefill.quantity / 2 / ls)));
      }
    } else if (prefill.symbol) {
      setCustomSymbol(prefill.symbol.toUpperCase());
    }
    if (prefill.side === 'BUY' || prefill.side === 'SELL') setSide(prefill.side);
    if (prefill.product === 'INTRADAY' || prefill.product === 'CARRYFORWARD') setProduct(prefill.product);
    if (prefill.order_type === 'MARKET' || prefill.order_type === 'LIMIT') setOrderType(prefill.order_type);
    if (typeof prefill.price === 'number' && prefill.price > 0) setPrice(prefill.price);
    setActiveTab('SINGLE');
  }, [prefill]);

  // Keep strike step aligned with underlying (NIFTY 50, BANKNIFTY 100, SENSEX 100).
  const strikeStep = underlying === 'NIFTY' ? 50 : 100;

  // Instant local estimate + authoritative backend check (debounced, best-effort).
  const localEst = useMemo(
    () => estimateMarginLocal({ symbol, underlying, side, price: orderType === 'LIMIT' ? Number(price) : 150, quantity }),
    [symbol, underlying, side, orderType, price, quantity],
  );
  const [serverMargin, setServerMargin] = useState<number | null>(null);
  useEffect(() => {
    setServerMargin(null);
    const t = setTimeout(async () => {
      try {
        const res = await api.previewPaperMargin({
          symbol,
          underlying,
          side,
          quantity,
          price: orderType === 'LIMIT' ? Number(price) : 150,
        });
        setServerMargin(res.data.required_margin);
      } catch {
        // Offline / backend down — local estimate stands.
      }
    }, 600);
    return () => clearTimeout(t);
  }, [symbol, underlying, side, quantity, price, orderType]);

  const requiredMargin = serverMargin ?? localEst.requiredMargin;
  const premium = orderType === 'LIMIT' ? Math.round(Number(price) * quantity * 100) / 100 : localEst.premium;
  const avail = availableMargin ?? null;
  const affordable = avail === null ? true : requiredMargin <= avail;
  const invalidStrike = !Number.isFinite(strike) || strike <= 0;
  const invalidPrice = orderType === 'LIMIT' && (!Number.isFinite(Number(price)) || Number(price) <= 0);
  const canSubmit = !loading && !invalidStrike && !invalidPrice && affordable;

  const handleSingleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    onPlaceOrder({
      symbol,
      underlying,
      side,
      product,
      order_type: orderType,
      quantity,
      price: orderType === 'MARKET' ? 0.0 : Number(price),
    });
  };

  // Editable basket legs
  const [legs, setLegs] = useState<BasketLeg[]>([]);
  const [basketName, setBasketName] = useState('Custom Basket');
  const updateLeg = (id: number, patch: Partial<BasketLeg>) =>
    setLegs((prev) => prev.map((l) => (l.id === id ? { ...l, ...patch } : l)));
  const removeLeg = (id: number) => setLegs((prev) => prev.filter((l) => l.id !== id));
  const addLeg = () =>
    setLegs((prev) => [
      ...prev,
      { id: nextLegId(), symbol: buildOptionSymbol(underlying, strike, 'CE'), underlying, side: 'BUY', product: 'INTRADAY', quantity: lotSizeFor(underlying), price: 100 },
    ]);

  const presetLegs = (name: string, mk: () => Omit<BasketLeg, 'id'>[]) => {
    setBasketName(name);
    setLegs(mk().map((l) => ({ ...l, id: nextLegId() })));
  };
  const handlePresetStraddle = () =>
    presetLegs('9:20 Intraday Short Straddle', () => {
      const ls = lotSizeFor(underlying);
      return [
        { symbol: buildOptionSymbol(underlying, strike, 'CE'), underlying, side: 'SELL', product: 'INTRADAY', quantity: ls, price: 180.0 },
        { symbol: buildOptionSymbol(underlying, strike, 'PE'), underlying, side: 'SELL', product: 'INTRADAY', quantity: ls, price: 175.0 },
      ];
    });
  const handlePresetBullCall = () =>
    presetLegs('Bull Call Debit Spread', () => {
      const ls = lotSizeFor(underlying);
      return [
        { symbol: buildOptionSymbol(underlying, strike, 'CE'), underlying, side: 'BUY', product: 'INTRADAY', quantity: ls, price: 180.0 },
        { symbol: buildOptionSymbol(underlying, strike + strikeStep * 2, 'CE'), underlying, side: 'SELL', product: 'INTRADAY', quantity: ls, price: 65.0 },
      ];
    });
  const handlePresetIronCondor = () =>
    presetLegs('Weekly Defined-Risk Iron Condor', () => {
      const ls = lotSizeFor(underlying);
      return [
        { symbol: buildOptionSymbol(underlying, strike + strikeStep * 2, 'CE'), underlying, side: 'SELL', product: 'CARRYFORWARD', quantity: ls, price: 55.0 },
        { symbol: buildOptionSymbol(underlying, strike - strikeStep * 2, 'PE'), underlying, side: 'SELL', product: 'CARRYFORWARD', quantity: ls, price: 50.0 },
        { symbol: buildOptionSymbol(underlying, strike + strikeStep * 4, 'CE'), underlying, side: 'BUY', product: 'CARRYFORWARD', quantity: ls, price: 15.0 },
        { symbol: buildOptionSymbol(underlying, strike - strikeStep * 4, 'PE'), underlying, side: 'BUY', product: 'CARRYFORWARD', quantity: ls, price: 12.0 },
      ];
    });

  const basketTotal = useMemo(
    () =>
      legs.reduce(
        (s, l) => s + estimateMarginLocal({ symbol: l.symbol, underlying: l.underlying, side: l.side, price: l.price, quantity: l.quantity }).requiredMargin,
        0,
      ),
    [legs],
  );
  const basketAffordable = avail === null ? true : basketTotal <= avail;

  const handleBasketSubmit = () => {
    if (loading || legs.length === 0 || !basketAffordable) return;
    onPlaceBasket({
      name: basketName,
      orders: legs.map((l) => ({
        symbol: l.symbol.trim().toUpperCase(),
        underlying: l.underlying,
        side: l.side,
        product: l.product,
        quantity: Number(l.quantity),
        price: Number(l.price),
      })),
    });
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setActiveTab('SINGLE')}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              activeTab === 'SINGLE'
                ? 'bg-primary text-primary-foreground shadow-xs'
                : 'bg-secondary text-muted-foreground hover:text-foreground'
            }`}
          >
            Single Order Ticket
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('BASKET')}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              activeTab === 'BASKET'
                ? 'bg-primary text-primary-foreground shadow-xs'
                : 'bg-secondary text-muted-foreground hover:text-foreground'
            }`}
          >
            1-Click Strategy Baskets
          </button>
        </div>
        <span className="text-[11px] font-semibold text-muted-foreground bg-secondary/60 border border-border/60 px-2.5 py-1 rounded-lg">
          Virtual Paper
        </span>
      </div>

      {activeTab === 'SINGLE' ? (
        <form onSubmit={handleSingleSubmit} className="space-y-3 text-xs">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="space-y-1">
              <label className="text-muted-foreground font-semibold">Underlying</label>
              <select
                value={underlying}
                onChange={(e) => { setUnderlying(e.target.value); setCustomSymbol(null); }}
                className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-semibold focus:outline-hidden cursor-pointer"
              >
                <option value="NIFTY">NIFTY (lot 75)</option>
                <option value="BANKNIFTY">BANKNIFTY (lot 30)</option>
                <option value="FINNIFTY">FINNIFTY (lot 65)</option>
                <option value="SENSEX">SENSEX (lot 10)</option>
              </select>
            </div>

            <div className="space-y-1">
              <label className="text-muted-foreground font-semibold">Strike</label>
              <div className="flex gap-1">
                <button type="button" onClick={() => setStrike((s) => s - strikeStep)} className="px-2 rounded-lg bg-secondary border border-border hover:text-foreground text-muted-foreground cursor-pointer" aria-label="Decrease strike">
                  <Minus className="w-3 h-3" />
                </button>
                <input
                  type="number"
                  step={strikeStep}
                  min={1}
                  value={strike}
                  onChange={(e) => { setStrike(Number(e.target.value)); setCustomSymbol(null); }}
                  className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-mono font-semibold focus:outline-hidden"
                />
                <button type="button" onClick={() => setStrike((s) => s + strikeStep)} className="px-2 rounded-lg bg-secondary border border-border hover:text-foreground text-muted-foreground cursor-pointer" aria-label="Increase strike">
                  <Plus className="w-3 h-3" />
                </button>
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-muted-foreground font-semibold">Option</label>
              <div className="grid grid-cols-2 gap-1">
                {(['CE', 'PE'] as const).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => { setOptionType(t); setCustomSymbol(null); }}
                    className={`py-1.5 rounded-lg font-bold text-xs transition-all cursor-pointer ${optionType === t ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-muted-foreground font-semibold">Side</label>
              <div className="grid grid-cols-2 gap-1">
                <button
                  type="button"
                  onClick={() => setSide('BUY')}
                  className={`py-1.5 rounded-lg font-bold text-xs transition-all cursor-pointer ${side === 'BUY' ? 'bg-emerald-500 text-white shadow-xs' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}
                >
                  BUY
                </button>
                <button
                  type="button"
                  onClick={() => setSide('SELL')}
                  className={`py-1.5 rounded-lg font-bold text-xs transition-all cursor-pointer ${side === 'SELL' ? 'bg-rose-500 text-white shadow-xs' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}
                >
                  SELL
                </button>
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-muted-foreground font-semibold">Lots (1 lot = {lotSize})</label>
              <div className="flex gap-1">
                <button type="button" onClick={() => setLots((l) => Math.max(1, l - 1))} className="px-2 rounded-lg bg-secondary border border-border text-muted-foreground hover:text-foreground cursor-pointer" aria-label="Decrease lots">
                  <Minus className="w-3 h-3" />
                </button>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={lots}
                  onChange={(e) => setLots(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
                  className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-mono font-semibold focus:outline-hidden text-center"
                />
                <button type="button" onClick={() => setLots((l) => Math.min(20, l + 1))} className="px-2 rounded-lg bg-secondary border border-border text-muted-foreground hover:text-foreground cursor-pointer" aria-label="Increase lots">
                  <Plus className="w-3 h-3" />
                </button>
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-muted-foreground font-semibold">Product</label>
              <select
                value={product}
                onChange={(e) => setProduct(e.target.value as 'INTRADAY' | 'CARRYFORWARD')}
                className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-semibold focus:outline-hidden cursor-pointer"
              >
                <option value="INTRADAY">MIS (Intraday)</option>
                <option value="CARRYFORWARD">NRML (Overnight)</option>
              </select>
            </div>

            <div className="space-y-1">
              <label className="text-muted-foreground font-semibold">Order Type</label>
              <select
                value={orderType}
                onChange={(e) => setOrderType(e.target.value as 'MARKET' | 'LIMIT')}
                className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-semibold focus:outline-hidden cursor-pointer"
              >
                <option value="MARKET">Market</option>
                <option value="LIMIT">Limit</option>
              </select>
            </div>

            {orderType === 'LIMIT' && (
              <div className="space-y-1">
                <label className="text-muted-foreground font-semibold">Limit Price (₹)</label>
                <input
                  type="number"
                  step="0.05"
                  min={0.05}
                  value={price}
                  onChange={(e) => setPrice(Number(e.target.value))}
                  className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-mono font-semibold focus:outline-hidden"
                />
              </div>
            )}
          </div>

          {/* Derived contract + cost preview — no more free-typed symbols */}
          <div className={`rounded-lg border px-3 py-2 font-mono text-[11px] flex flex-col sm:flex-row sm:items-center justify-between gap-2 ${affordable ? 'bg-secondary/40 border-border' : 'bg-destructive/10 border-destructive/30'}`}>
            <span className="font-bold text-foreground">{symbol} <span className="text-muted-foreground font-sans">× {quantity} qty ({lots} lot{lots > 1 ? 's' : ''})</span></span>
            <span className="text-muted-foreground">
              {side === 'BUY' && optionType ? <span>Premium ≈ ₹{premium.toLocaleString('en-IN')} • </span> : null}
              Margin <strong className={affordable ? 'text-foreground' : 'text-destructive'}>₹{requiredMargin.toLocaleString('en-IN')}</strong>
              {avail !== null && <span> • Avail ₹{avail.toLocaleString('en-IN')}</span>}
              {!affordable && <span className="text-destructive font-bold"> • exceeds margin</span>}
            </span>
          </div>
          {invalidStrike && <p className="text-[11px] text-destructive font-semibold">Enter a valid strike price.</p>}

          <button
            type="submit"
            disabled={!canSubmit}
            className={`w-full py-2.5 rounded-lg text-white font-bold text-xs transition-all flex items-center justify-center gap-2 cursor-pointer shadow-xs disabled:opacity-50 ${side === 'BUY' ? 'bg-emerald-600 hover:bg-emerald-500' : 'bg-rose-600 hover:bg-rose-500'}`}
          >
            <Send className="w-4 h-4" />
            <span>{loading ? 'Placing…' : `Place Virtual ${side} Order • ${lots} lot${lots > 1 ? 's' : ''}`}</span>
          </button>
        </form>
      ) : (
        <div className="space-y-3 text-xs">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="bg-secondary/40 border border-border rounded-xl p-3.5 space-y-2">
              <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                <Zap className="w-4 h-4 text-primary" />
                <span>9:20 Short Straddle</span>
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">Sell ATM Call + Sell ATM Put at {strike}.</p>
              <button type="button" onClick={handlePresetStraddle} disabled={loading} className="w-full py-2 bg-primary hover:bg-primary/90 text-primary-foreground font-bold text-xs rounded-lg transition-all flex items-center justify-center gap-1.5 cursor-pointer shadow-xs disabled:opacity-50">
                <PlusCircle className="w-3.5 h-3.5" /><span>Load 2-Leg Straddle</span>
              </button>
            </div>
            <div className="bg-secondary/40 border border-border rounded-xl p-3.5 space-y-2">
              <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                <Zap className="w-4 h-4 text-emerald-400" /><span>Bull Call Spread</span>
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">Buy ATM Call + Sell OTM Call.</p>
              <button type="button" onClick={handlePresetBullCall} disabled={loading} className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs rounded-lg transition-all flex items-center justify-center gap-1.5 cursor-pointer shadow-xs disabled:opacity-50">
                <PlusCircle className="w-3.5 h-3.5" /><span>Load Bull Spread</span>
              </button>
            </div>
            <div className="bg-secondary/40 border border-border rounded-xl p-3.5 space-y-2">
              <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                <Zap className="w-4 h-4 text-purple-400" /><span>Iron Condor</span>
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">4-leg defined risk around {strike}.</p>
              <button type="button" onClick={handlePresetIronCondor} disabled={loading} className="w-full py-2 bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs rounded-lg transition-all flex items-center justify-center gap-1.5 cursor-pointer shadow-xs disabled:opacity-50">
                <PlusCircle className="w-3.5 h-3.5" /><span>Load Iron Condor</span>
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <input
              value={basketName}
              onChange={(e) => setBasketName(e.target.value)}
              className="flex-1 bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-semibold focus:outline-hidden"
              placeholder="Basket name"
              aria-label="Basket name"
            />
            <button type="button" onClick={addLeg} className="px-2.5 py-1.5 rounded-lg bg-secondary border border-border text-[11px] font-bold hover:text-foreground text-muted-foreground cursor-pointer flex items-center gap-1">
              <Plus className="w-3 h-3" /> Add leg
            </button>
          </div>

          {legs.length === 0 ? (
            <p className="text-[11px] text-muted-foreground bg-secondary/30 border border-border rounded-lg p-3 text-center">Load a preset or add legs to build an editable basket. Prices are limit prices per leg.</p>
          ) : (
            <div className="space-y-2">
              {legs.map((l) => (
                <div key={l.id} className="grid grid-cols-2 sm:grid-cols-6 gap-2 items-end bg-secondary/30 border border-border rounded-lg p-2.5">
                  <div className="col-span-2 space-y-1">
                    <label className="text-muted-foreground font-semibold text-[10px]">Symbol</label>
                    <input value={l.symbol} onChange={(e) => updateLeg(l.id, { symbol: e.target.value.toUpperCase() })} className="w-full bg-background text-[11px] px-2 py-1.5 rounded-lg border border-border font-mono font-semibold uppercase focus:outline-hidden" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-muted-foreground font-semibold text-[10px]">Side</label>
                    <select value={l.side} onChange={(e) => updateLeg(l.id, { side: e.target.value as 'BUY' | 'SELL' })} className="w-full bg-background text-[11px] px-2 py-1.5 rounded-lg border border-border font-bold cursor-pointer">
                      <option value="BUY">BUY</option>
                      <option value="SELL">SELL</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-muted-foreground font-semibold text-[10px]">Qty</label>
                    <input type="number" min={1} value={l.quantity} onChange={(e) => updateLeg(l.id, { quantity: Math.max(1, Number(e.target.value) || 1) })} className="w-full bg-background text-[11px] px-2 py-1.5 rounded-lg border border-border font-mono focus:outline-hidden" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-muted-foreground font-semibold text-[10px]">Price ₹</label>
                    <input type="number" min={0.05} step={0.05} value={l.price} onChange={(e) => updateLeg(l.id, { price: Number(e.target.value) })} className="w-full bg-background text-[11px] px-2 py-1.5 rounded-lg border border-border font-mono focus:outline-hidden" />
                  </div>
                  <button type="button" onClick={() => removeLeg(l.id)} className="flex items-center justify-center gap-1 py-1.5 rounded-lg text-destructive hover:bg-destructive/10 border border-transparent hover:border-destructive/30 text-[11px] font-bold cursor-pointer" aria-label={`Remove ${l.symbol}`}>
                    <MinusCircle className="w-3.5 h-3.5" /> Remove
                  </button>
                </div>
              ))}
              <div className={`rounded-lg border px-3 py-2 font-mono text-[11px] flex items-center justify-between ${basketAffordable ? 'bg-secondary/40 border-border' : 'bg-destructive/10 border-destructive/30'}`}>
                <span className="text-muted-foreground font-sans font-semibold">{legs.length} legs • {basketName}</span>
                <span>Est. margin <strong className={basketAffordable ? 'text-foreground' : 'text-destructive'}>₹{Math.round(basketTotal).toLocaleString('en-IN')}</strong>{avail !== null && <span className="text-muted-foreground"> • Avail ₹{avail.toLocaleString('en-IN')}</span>}</span>
              </div>
              <button
                type="button"
                onClick={handleBasketSubmit}
                disabled={loading || legs.length === 0 || !basketAffordable}
                className="w-full py-2.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-bold text-xs transition-all cursor-pointer disabled:opacity-50"
              >
                {loading ? 'Executing…' : `Execute ${legs.length}-Leg Basket${basketAffordable ? '' : ' • exceeds margin'}`}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
