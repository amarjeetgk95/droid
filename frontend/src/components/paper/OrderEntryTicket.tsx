'use client';

import { useState, useEffect } from 'react';
import { OrderPayload, BasketOrderPayload } from '@/lib/types';
import { Send, Zap, PlusCircle, Shield, AlertTriangle } from 'lucide-react';
import { getStoredSettings } from '@/lib/settings';

export function OrderEntryTicket({
  onPlaceOrder,
  onPlaceBasket,
  loading,
  prefill,
}: {
  onPlaceOrder: (order: OrderPayload) => void;
  onPlaceBasket: (basket: BasketOrderPayload) => void;
  loading: boolean;
  prefill?: OrderPayload | null;
}) {
  const [activeTab, setActiveTab] = useState<'SINGLE' | 'BASKET'>('SINGLE');
  const [executionMode, setExecutionMode] = useState<'PAPER' | 'LIVE'>('PAPER');
  const [activeBroker, setActiveBroker] = useState('fyers');

  useEffect(() => {
    try {
      const stored = getStoredSettings();
      if (stored?.broker?.provider) {
        setActiveBroker(stored.broker.provider);
      }
    } catch {}
  }, []);

  // Single order state
  const [symbol, setSymbol] = useState('NIFTY24800CE');
  const [underlying, setUnderlying] = useState('NIFTY');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [product, setProduct] = useState<'INTRADAY' | 'CARRYFORWARD'>('INTRADAY');
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET');
  const [quantity, setQuantity] = useState(75);
  const [price, setPrice] = useState(150.0);

  // Retry from Order Book: prefill ticket with the rejected order (halve qty as a starting suggestion).
  useEffect(() => {
    if (!prefill) return;
    if (prefill.symbol) setSymbol(prefill.symbol);
    if (prefill.underlying) setUnderlying(prefill.underlying);
    if (prefill.side === 'BUY' || prefill.side === 'SELL') setSide(prefill.side);
    if (prefill.product === 'INTRADAY' || prefill.product === 'CARRYFORWARD') setProduct(prefill.product);
    if (typeof prefill.quantity === 'number' && prefill.quantity > 0) {
      setQuantity(Math.max(1, Math.floor(prefill.quantity / 2)));
    }
    if (prefill.order_type === 'MARKET' || prefill.order_type === 'LIMIT') setOrderType(prefill.order_type);
    if (typeof prefill.price === 'number' && prefill.price > 0) setPrice(prefill.price);
    setActiveTab('SINGLE');
  }, [prefill]);

  const handleSingleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onPlaceOrder({
      symbol: symbol.trim().toUpperCase(),
      underlying,
      side,
      product,
      order_type: orderType,
      quantity: Number(quantity),
      price: orderType === 'MARKET' ? 0.0 : Number(price),
    });
  };

  const handlePresetStraddle = () => {
    onPlaceBasket({
      name: '9:20 Intraday Short Straddle',
      orders: [
        { symbol: `${underlying}ATMCE`, underlying, side: 'SELL', product: 'INTRADAY', quantity: 75, price: 180.0 },
        { symbol: `${underlying}ATMPE`, underlying, side: 'SELL', product: 'INTRADAY', quantity: 75, price: 175.0 },
      ],
    });
  };

  const handlePresetBullCall = () => {
    onPlaceBasket({
      name: 'Bull Call Debit Spread',
      orders: [
        { symbol: `${underlying}ATMCE`, underlying, side: 'BUY', product: 'INTRADAY', quantity: 75, price: 180.0 },
        { symbol: `${underlying}OTMCE`, underlying, side: 'SELL', product: 'INTRADAY', quantity: 75, price: 65.0 },
      ],
    });
  };

  const handlePresetIronCondor = () => {
    onPlaceBasket({
      name: 'Weekly Defined-Risk Iron Condor',
      orders: [
        { symbol: `${underlying}OTMCE`, underlying, side: 'SELL', product: 'CARRYFORWARD', quantity: 75, price: 55.0 },
        { symbol: `${underlying}OTMPE`, underlying, side: 'SELL', product: 'CARRYFORWARD', quantity: 75, price: 50.0 },
        { symbol: `${underlying}WINGCE`, underlying, side: 'BUY', product: 'CARRYFORWARD', quantity: 75, price: 15.0 },
        { symbol: `${underlying}WINGPE`, underlying, side: 'BUY', product: 'CARRYFORWARD', quantity: 75, price: 12.0 },
      ],
    });
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      {/* Sub Tabs & Live / Paper Mode Selector */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-3">
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

        <div className="flex items-center gap-1.5 bg-secondary/60 p-1 rounded-lg border border-border/60 text-[11px]">
          <button
            type="button"
            onClick={() => setExecutionMode('PAPER')}
            className={`px-2.5 py-1 rounded font-semibold transition-all cursor-pointer ${
              executionMode === 'PAPER'
                ? 'bg-background text-foreground shadow-xs'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Virtual Paper
          </button>
          <button
            type="button"
            onClick={() => setExecutionMode('LIVE')}
            className={`px-2.5 py-1 rounded font-bold transition-all cursor-pointer flex items-center gap-1 ${
              executionMode === 'LIVE'
                ? 'bg-emerald-500 text-slate-950 shadow-xs'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Shield className="w-3 h-3" />
            <span>Live {activeBroker.toUpperCase()}</span>
          </button>
        </div>
      </div>

      {executionMode === 'LIVE' && (
        <div className="p-2.5 bg-amber-500/10 border border-amber-500/25 rounded-lg text-xs text-amber-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" />
          <span>
            <strong>Live Order Routing Enabled:</strong> Orders will be submitted directly to{' '}
            <strong>{activeBroker.toUpperCase()}</strong> ({activeBroker === 'flattrade' ? 'Zero Brokerage' : 'Low Latency'}).
          </span>
        </div>
      )}

      {activeTab === 'SINGLE' ? (
        <form onSubmit={handleSingleSubmit} className="space-y-3 text-xs">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {/* Symbol */}
            <div className="space-y-1">
              <label className="text-muted-foreground font-semibold">Symbol / Strike</label>
              <input
                type="text"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-mono font-semibold focus:outline-hidden uppercase"
              />
            </div>

            {/* Underlying */}
            <div className="space-y-1">
              <label className="text-muted-foreground font-semibold">Underlying</label>
              <select
                value={underlying}
                onChange={(e) => setUnderlying(e.target.value)}
                className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-semibold focus:outline-hidden cursor-pointer"
              >
                <option value="NIFTY">NIFTY</option>
                <option value="BANKNIFTY">BANKNIFTY</option>
                <option value="FINNIFTY">FINNIFTY</option>
                <option value="SENSEX">SENSEX</option>
              </select>
            </div>

            {/* Side */}
            <div className="space-y-1">
              <label className="text-muted-foreground font-semibold">Side</label>
              <div className="grid grid-cols-2 gap-1">
                <button
                  type="button"
                  onClick={() => setSide('BUY')}
                  className={`py-1.5 rounded-lg font-bold text-xs transition-all cursor-pointer ${
                    side === 'BUY'
                      ? 'bg-emerald-500 text-white shadow-xs'
                      : 'bg-secondary text-muted-foreground hover:text-foreground'
                  }`}
                >
                  BUY
                </button>
                <button
                  type="button"
                  onClick={() => setSide('SELL')}
                  className={`py-1.5 rounded-lg font-bold text-xs transition-all cursor-pointer ${
                    side === 'SELL'
                      ? 'bg-rose-500 text-white shadow-xs'
                      : 'bg-secondary text-muted-foreground hover:text-foreground'
                  }`}
                >
                  SELL
                </button>
              </div>
            </div>

            {/* Product */}
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

            {/* Quantity */}
            <div className="space-y-1">
              <label className="text-muted-foreground font-semibold">Quantity</label>
              <input
                type="number"
                step={25}
                min={25}
                value={quantity}
                onChange={(e) => setQuantity(Number(e.target.value))}
                className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-mono font-semibold focus:outline-hidden"
              />
            </div>

            {/* Order Type */}
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

            {/* Limit Price */}
            {orderType === 'LIMIT' && (
              <div className="space-y-1">
                <label className="text-muted-foreground font-semibold">Limit Price (₹)</label>
                <input
                  type="number"
                  step="0.05"
                  value={price}
                  onChange={(e) => setPrice(Number(e.target.value))}
                  className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-mono font-semibold focus:outline-hidden"
                />
              </div>
            )}
          </div>

          <button
            type="submit"
            disabled={loading}
            className={`w-full py-2.5 rounded-lg text-white font-bold text-xs transition-all flex items-center justify-center gap-2 cursor-pointer shadow-xs disabled:opacity-50 ${
              executionMode === 'LIVE'
                ? side === 'BUY'
                  ? 'bg-emerald-600 hover:bg-emerald-500 ring-2 ring-emerald-400/40'
                  : 'bg-rose-600 hover:bg-rose-500 ring-2 ring-rose-400/40'
                : side === 'BUY'
                ? 'bg-emerald-600 hover:bg-emerald-500'
                : 'bg-rose-600 hover:bg-rose-500'
            }`}
          >
            <Send className="w-4 h-4" />
            <span>
              {executionMode === 'LIVE'
                ? `Submit LIVE ${side} Order (${activeBroker.toUpperCase()})`
                : `Place Virtual ${side} Order`}
            </span>
          </button>
        </form>
      ) : (
        /* Basket Presets */
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="bg-secondary/40 border border-border rounded-xl p-3.5 space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
              <Zap className="w-4 h-4 text-primary" />
              <span>9:20 Short Straddle</span>
            </div>
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              Sell ATM Call + Sell ATM Put. Captures theta decay.
            </p>
            <button
              onClick={handlePresetStraddle}
              disabled={loading}
              className="w-full py-2 bg-primary hover:bg-primary/90 text-primary-foreground font-bold text-xs rounded-lg transition-all flex items-center justify-center gap-1.5 cursor-pointer shadow-xs"
            >
              <PlusCircle className="w-3.5 h-3.5" />
              <span>Execute 2-Leg Straddle</span>
            </button>
          </div>

          <div className="bg-secondary/40 border border-border rounded-xl p-3.5 space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
              <Zap className="w-4 h-4 text-emerald-400" />
              <span>Bull Call Spread</span>
            </div>
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              Buy ATM Call + Sell OTM Call. Defined-risk bullish debit spread.
            </p>
            <button
              onClick={handlePresetBullCall}
              disabled={loading}
              className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs rounded-lg transition-all flex items-center justify-center gap-1.5 cursor-pointer shadow-xs"
            >
              <PlusCircle className="w-3.5 h-3.5" />
              <span>Execute 2-Leg Bull Spread</span>
            </button>
          </div>

          <div className="bg-secondary/40 border border-border rounded-xl p-3.5 space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
              <Zap className="w-4 h-4 text-purple-400" />
              <span>Iron Condor</span>
            </div>
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              Sell OTM CE/PE + Buy protective wings. 4-leg defined risk.
            </p>
            <button
              onClick={handlePresetIronCondor}
              disabled={loading}
              className="w-full py-2 bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs rounded-lg transition-all flex items-center justify-center gap-1.5 cursor-pointer shadow-xs"
            >
              <PlusCircle className="w-3.5 h-3.5" />
              <span>Execute 4-Leg Iron Condor</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
