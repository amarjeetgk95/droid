'use client';

import React from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Zap,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  Sparkles,
  Layers,
  ShieldCheck,
  Edit2,
  Check,
  X,
  RotateCcw,
} from 'lucide-react';
import { UnderlyingSymbol, TradingHorizon, DirectionalBias } from './options-types';

interface OptionsCommandBarProps {
  underlying: UnderlyingSymbol;
  setUnderlying: (sym: UnderlyingSymbol) => void;
  horizon: TradingHorizon;
  setHorizon: (h: TradingHorizon) => void;
  direction: DirectionalBias;
  setDirection: (d: DirectionalBias) => void;
  spotPrice: number;
  currentIv: number;
  lotSize?: number;
  isCustomSpot?: boolean;
  onUpdateSpot?: (val: number) => void;
  onResetSpot?: () => void;
  loading: boolean;
  synthesizing: boolean;
  onRefresh: () => void;
  onSynthesizeAI: () => void;
}

const LOT_SIZES: Record<UnderlyingSymbol, number> = {
  NIFTY: 75,
  BANKNIFTY: 30,
  SENSEX: 10,
};

const HORIZON_LABELS: Record<TradingHorizon, { label: string; badge: string }> = {
  SCALP: { label: 'Scalp', badge: '15m' },
  INTRADAY: { label: 'Intraday', badge: 'Session' },
  SWING: { label: 'Swing', badge: '2-5d' },
  POSITIONAL: { label: 'Positional', badge: 'Expiry' },
};

export const OptionsCommandBar: React.FC<OptionsCommandBarProps> = ({
  underlying,
  setUnderlying,
  horizon,
  setHorizon,
  direction,
  setDirection,
  spotPrice,
  currentIv,
  lotSize,
  isCustomSpot,
  onUpdateSpot,
  onResetSpot,
  loading,
  synthesizing,
  onRefresh,
  onSynthesizeAI,
}) => {
  const activeLot = lotSize || LOT_SIZES[underlying] || 25;
  const [editingSpot, setEditingSpot] = React.useState<boolean>(false);
  const [spotInputValue, setSpotInputValue] = React.useState<string>(spotPrice.toString());

  React.useEffect(() => {
    setSpotInputValue(spotPrice.toString());
  }, [spotPrice, underlying]);

  const handleSpotSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const val = parseFloat(spotInputValue);
    if (!isNaN(val) && val > 0 && onUpdateSpot) {
      onUpdateSpot(val);
      setEditingSpot(false);
    }
  };
  return (
    <div className="bg-card/90 backdrop-blur-md rounded-2xl border border-border/70 shadow-sm p-4 space-y-3.5">
      {/* Top Tier: Title, Active Spot Metric, and Primary Action Toolbar */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0">
            <Zap className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight text-foreground">
                Options Intelligence
              </h1>
              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-semibold">
                v2.0 Terminal
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              Institutional Black-Scholes Greeks, path simulations, and non-blocking contradiction research.
            </p>
          </div>
        </div>

        {/* Live Asset Context Badge with Interactive Spot Editing */}
        <div className="flex flex-wrap items-center gap-2 bg-muted/40 p-1.5 px-3 rounded-xl border border-border/50 self-start lg:self-auto">
          {editingSpot ? (
            <form onSubmit={handleSpotSubmit} className="flex items-center gap-1.5">
              <span className="text-xs font-bold font-mono text-foreground">{underlying}:</span>
              <input
                type="number"
                step="5"
                value={spotInputValue}
                onChange={(e) => setSpotInputValue(e.target.value)}
                className="w-24 px-1.5 py-0.5 text-xs font-mono font-bold bg-background border border-primary rounded text-foreground focus:outline-hidden"
                autoFocus
              />
              <button
                type="submit"
                className="p-1 rounded hover:bg-emerald-500/20 text-emerald-400"
                title="Save spot price"
              >
                <Check className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setEditingSpot(false)}
                className="p-1 rounded hover:bg-rose-500/20 text-rose-400"
                title="Cancel"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </form>
          ) : spotPrice <= 0 ? (
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
              <span className="text-xs font-bold font-mono text-foreground">{underlying}:</span>
              <span className="text-xs font-mono font-bold text-rose-400 bg-rose-500/10 px-1.5 py-0.5 rounded border border-rose-500/20">
                NO DATA (BROKER OFFLINE)
              </span>
              {onUpdateSpot && (
                <button
                  type="button"
                  onClick={() => setEditingSpot(true)}
                  className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors flex items-center gap-1 text-[11px]"
                  title="Simulate a what-if price"
                >
                  <Edit2 className="w-3 h-3" />
                  <span className="hidden sm:inline">Simulate</span>
                </button>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${isCustomSpot ? 'bg-amber-400' : 'bg-emerald-500 animate-pulse'}`} />
              <span className="text-xs font-bold font-mono text-foreground">{underlying} Spot:</span>
              <span className={`text-sm font-bold font-mono ${isCustomSpot ? 'text-amber-400' : 'text-primary'}`}>
                ₹{spotPrice.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
              {isCustomSpot && (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 font-semibold">
                  SIMULATION
                </span>
              )}
              {onUpdateSpot && (
                <button
                  type="button"
                  onClick={() => setEditingSpot(true)}
                  className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  title="Edit spot price"
                >
                  <Edit2 className="w-3 h-3" />
                </button>
              )}
              {isCustomSpot && onResetSpot && (
                <button
                  type="button"
                  onClick={onResetSpot}
                  className="p-1 rounded-md text-amber-400 hover:text-amber-300 hover:bg-amber-500/10 transition-colors"
                  title="Reset to live broker feed"
                >
                  <RotateCcw className="w-3 h-3" />
                </button>
              )}
            </div>
          )}
          <span className="text-muted-foreground/40">|</span>
          <span className="text-xs font-mono text-muted-foreground">
            IV: <strong className="text-foreground">{(currentIv * 100).toFixed(1)}%</strong>
          </span>
          <span className="text-muted-foreground/40">|</span>
          <span className="text-xs font-mono text-muted-foreground">
            Lot: <strong className="text-foreground">{activeLot}</strong>
          </span>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 self-end lg:self-auto">
          <Button
            onClick={onSynthesizeAI}
            disabled={synthesizing}
            size="sm"
            className="gap-2 bg-primary hover:bg-primary/90 text-primary-foreground text-xs h-9 px-3.5 shadow-sm font-semibold transition-all"
          >
            <Sparkles className={`w-3.5 h-3.5 ${synthesizing ? 'animate-spin text-amber-300' : 'text-amber-300'}`} />
            {synthesizing ? 'Synthesizing Intelligence...' : 'Run Live AI Research'}
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={onRefresh}
            disabled={loading}
            className="gap-1.5 h-9 px-3 text-xs border-border/70 hover:bg-muted/60"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-primary' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Bottom Tier: Command Parameters Switcher (Asset, Horizon, Direction) */}
      <div className="pt-3 border-t border-border/50 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          {/* Underlying Switcher */}
          <div className="flex items-center rounded-xl bg-muted/60 p-1 border border-border/60">
            {(['NIFTY', 'BANKNIFTY', 'SENSEX'] as const).map((sym) => (
              <button
                key={sym}
                onClick={() => setUnderlying(sym)}
                className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                  underlying === sym
                    ? 'bg-card text-foreground shadow-sm border border-border/60 font-bold'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {sym}
              </button>
            ))}
          </div>

          {/* Horizon Switcher */}
          <div className="flex items-center rounded-xl bg-muted/60 p-1 border border-border/60">
            {(['SCALP', 'INTRADAY', 'SWING', 'POSITIONAL'] as const).map((h) => {
              const meta = HORIZON_LABELS[h];
              const isSelected = horizon === h;
              return (
                <button
                  key={h}
                  onClick={() => setHorizon(h)}
                  className={`px-2.5 py-1.5 text-xs font-medium rounded-lg flex items-center gap-1.5 transition-all ${
                    isSelected
                      ? 'bg-card text-foreground shadow-sm border border-border/60 font-bold'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <span>{meta.label}</span>
                  <span
                    className={`text-[10px] font-mono px-1 py-0.2 rounded ${
                      isSelected ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground'
                    }`}
                  >
                    {meta.badge}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Directional Toggle */}
          <div className="flex items-center rounded-xl bg-muted/60 p-1 border border-border/60">
            <button
              onClick={() => setDirection('BULLISH')}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-all ${
                direction === 'BULLISH'
                  ? 'bg-emerald-600 text-white shadow-sm font-bold'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <TrendingUp className="w-3.5 h-3.5" /> Call (Bullish)
            </button>
            <button
              onClick={() => setDirection('BEARISH')}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-all ${
                direction === 'BEARISH'
                  ? 'bg-rose-600 text-white shadow-sm font-bold'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <TrendingDown className="w-3.5 h-3.5" /> Put (Bearish)
            </button>
          </div>
        </div>

        {/* Regulatory & Microstructure Badges */}
        <div className="hidden sm:flex items-center gap-2 text-[11px] font-mono text-muted-foreground">
          <span className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-muted/40 border border-border/40">
            <ShieldCheck className="w-3 h-3 text-emerald-500" /> Analytical Greeks
          </span>
          <span className="px-2 py-0.5 rounded-md bg-muted/40 border border-border/40">
            Indian F&amp;O Friction (STT 0.1%, GST 18%)
          </span>
        </div>
      </div>
    </div>
  );
};
