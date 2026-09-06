'use client';

import React, { useState } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Clock,
  Target,
  ShieldAlert,
  Copy,
  Check,
  Sparkles,
  Zap,
  Filter,
  CheckCircle2,
  Send,
  Database,
  Layers,
} from 'lucide-react';
import { CryptoScalpSignal } from '@/lib/types';

interface CryptoScalpSignalsCardProps {
  signals: CryptoScalpSignal[];
  loading: boolean;
  onRefresh: () => void;
  selectedAssetFilter?: string;
  onSelectAssetFilter?: (asset: string) => void;
}

export function CryptoScalpSignalsCard({
  signals,
  loading,
  onRefresh,
  selectedAssetFilter = 'ALL',
  onSelectAssetFilter,
}: CryptoScalpSignalsCardProps) {
  const [assetFilter, setAssetFilter] = useState<string>(selectedAssetFilter);
  const [dirFilter, setDirFilter] = useState<'ALL' | 'LONG' | 'SHORT'>('ALL');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleAssetSelect = (asset: string) => {
    setAssetFilter(asset);
    if (onSelectAssetFilter) {
      onSelectAssetFilter(asset);
    }
  };

  const handleCopyPlan = (sig: CryptoScalpSignal) => {
    const text = `⚡ CRYPTO SCALP: ${sig.direction} ${sig.symbol} (${sig.timeframe.toUpperCase()})
Strategy: ${sig.strategy_name}
Confidence: ${sig.confidence.toFixed(0)}% | R:R: 1:${sig.risk_reward_ratio.toFixed(1)}
🎯 Entry: $${sig.entry_price.toLocaleString()}
🛑 Stop Loss: $${sig.stop_loss.toLocaleString()} (-${sig.risk_percent.toFixed(2)}%)
🎯 Target 1: $${sig.target_1.toLocaleString()}
🎯 Target 2: $${sig.target_2.toLocaleString()}
Rationale: ${sig.rationale}`;

    navigator.clipboard.writeText(text);
    setCopiedId(sig.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const filteredSignals = signals.filter((s) => {
    if (assetFilter !== 'ALL' && s.asset !== assetFilter && s.symbol !== assetFilter) return false;
    if (dirFilter !== 'ALL' && s.direction !== dirFilter) return false;
    return true;
  });

  return (
    <div className="bg-card border border-border rounded-2xl p-5 shadow-sm space-y-5">
      {/* Header & Filter Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <Zap className="w-4 h-4" />
            </div>
            <h2 className="text-base font-bold tracking-tight text-foreground">
              Institutional Crypto Scalping Signals
            </h2>
            <span className="text-[10px] px-2 py-0.5 rounded-full font-mono bg-primary/10 text-primary font-bold">
              Sub-5m Micro-Cadence
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Real-time VWAP rejections, 9/21 EMA momentum crosses, perpetual funding squeezes, and L2 depth imbalance flips.
          </p>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Asset Pills */}
          <div className="flex bg-secondary/80 rounded-lg p-0.5 border border-border">
            {['ALL', 'BTC', 'ETH'].map((sym) => (
              <button
                key={sym}
                type="button"
                onClick={() => handleAssetSelect(sym)}
                className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all cursor-pointer ${
                  assetFilter === sym
                    ? 'bg-card text-foreground shadow-xs'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {sym}
              </button>
            ))}
          </div>

          {/* Direction Filter */}
          <div className="flex bg-secondary/80 rounded-lg p-0.5 border border-border">
            {(['ALL', 'LONG', 'SHORT'] as const).map((dir) => (
              <button
                key={dir}
                type="button"
                onClick={() => setDirFilter(dir)}
                className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all cursor-pointer ${
                  dirFilter === dir
                    ? dir === 'LONG'
                      ? 'bg-emerald-500 text-white shadow-xs'
                      : dir === 'SHORT'
                      ? 'bg-rose-500 text-white shadow-xs'
                      : 'bg-card text-foreground shadow-xs'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {dir}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Signals Grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="h-48 bg-secondary/40 border border-border rounded-xl animate-pulse" />
          ))}
        </div>
      ) : filteredSignals.length === 0 ? (
        <div className="p-8 text-center border border-dashed border-border rounded-xl space-y-2 bg-secondary/20">
          <Filter className="w-8 h-8 text-muted-foreground mx-auto" />
          <p className="text-sm font-semibold text-foreground">No Scalp Signals Active Right Now</p>
          <p className="text-xs text-muted-foreground max-w-md mx-auto">
            The 5 crypto scalping strategies only emit setups when strict risk-reward (≥ 1:1.3) and confluence criteria are met. Background scanning polls every 30s.
          </p>
          <button
            type="button"
            onClick={onRefresh}
            className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground rounded-lg text-xs font-semibold border border-border cursor-pointer transition-all"
          >
            <span>Scan Market Now</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredSignals.map((sig) => {
            const isLong = sig.direction === 'LONG';
            const priceDecimals = sig.entry_price > 100 ? 2 : 4;

            return (
              <div
                key={sig.id}
                className={`relative flex flex-col justify-between rounded-xl border p-4.5 transition-all bg-card/60 backdrop-blur-xs shadow-xs ${
                  isLong
                    ? 'border-emerald-500/30 hover:border-emerald-500/60 hover:shadow-emerald-500/5'
                    : 'border-rose-500/30 hover:border-rose-500/60 hover:shadow-rose-500/5'
                }`}
              >
                {/* Top Row: Direction, Symbol, Strategy & Confidence */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold font-mono tracking-wider ${
                          isLong
                            ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                            : 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                        }`}
                      >
                        {isLong ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                        {sig.direction}
                      </span>

                      <span className="font-bold text-sm text-foreground tracking-tight">
                        {sig.symbol}
                      </span>

                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-secondary text-muted-foreground border border-border">
                        {sig.timeframe.toUpperCase()}
                      </span>
                    </div>

                    {/* Confidence Meter */}
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] font-mono text-muted-foreground">Confidence:</span>
                      <span
                        className={`text-xs font-mono font-bold ${
                          sig.confidence >= 80 ? 'text-emerald-400' : 'text-amber-400'
                        }`}
                      >
                        {sig.confidence.toFixed(0)}%
                      </span>
                    </div>
                  </div>

                  {/* Strategy Badge & R:R */}
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1.5 font-medium text-foreground">
                      <Layers className="w-3.5 h-3.5 text-primary" />
                      <span>{sig.strategy_name}</span>
                    </div>
                    <span className="text-[11px] font-mono text-muted-foreground">
                      R:R <strong className="text-foreground">1:{sig.risk_reward_ratio.toFixed(1)}</strong>
                    </span>
                  </div>

                  {/* Pricing Matrix Grid */}
                  <div className="grid grid-cols-4 gap-2 bg-secondary/40 border border-border/80 rounded-lg p-2.5 text-center">
                    <div>
                      <span className="text-[9px] font-mono text-muted-foreground uppercase block">Entry</span>
                      <span className="text-xs font-mono font-bold text-foreground">
                        ${sig.entry_price.toFixed(priceDecimals)}
                      </span>
                    </div>
                    <div>
                      <span className="text-[9px] font-mono text-rose-400 uppercase block">Stop Loss</span>
                      <span className="text-xs font-mono font-bold text-rose-400">
                        ${sig.stop_loss.toFixed(priceDecimals)}
                      </span>
                      <span className="text-[8px] font-mono text-rose-400/80 block">
                        -{sig.risk_percent.toFixed(2)}%
                      </span>
                    </div>
                    <div>
                      <span className="text-[9px] font-mono text-emerald-400 uppercase block">Target 1</span>
                      <span className="text-xs font-mono font-bold text-emerald-400">
                        ${sig.target_1.toFixed(priceDecimals)}
                      </span>
                    </div>
                    <div>
                      <span className="text-[9px] font-mono text-emerald-300 uppercase block">Target 2</span>
                      <span className="text-xs font-mono font-bold text-emerald-300">
                        ${sig.target_2.toFixed(priceDecimals)}
                      </span>
                    </div>
                  </div>

                  {/* Confluence Tags */}
                  {sig.confluence_factors && sig.confluence_factors.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {sig.confluence_factors.map((factor, idx) => (
                        <span
                          key={idx}
                          className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-md bg-secondary/80 text-muted-foreground border border-border/60"
                        >
                          <CheckCircle2 className="w-2.5 h-2.5 text-emerald-400" />
                          <span>{factor}</span>
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Rationale */}
                  {sig.rationale && (
                    <p className="text-[11px] text-muted-foreground leading-relaxed italic border-l-2 border-primary/40 pl-2">
                      {sig.rationale}
                    </p>
                  )}
                </div>

                {/* Bottom Status Bar: Supabase + Telegram + Copy */}
                <div className="flex items-center justify-between pt-3 mt-3 border-t border-border/60 text-[10px] text-muted-foreground">
                  <div className="flex items-center gap-3">
                    {/* Supabase Status */}
                    <span className="inline-flex items-center gap-1 text-emerald-400">
                      <Database className="w-3 h-3" />
                      <span>Supabase Stored</span>
                    </span>

                    {/* Telegram Status */}
                    <span className="inline-flex items-center gap-1 text-blue-400">
                      <Send className="w-3 h-3" />
                      <span>Telegram Active</span>
                    </span>
                  </div>

                  {/* Copy Button */}
                  <button
                    type="button"
                    onClick={() => handleCopyPlan(sig)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-secondary hover:bg-secondary/80 text-foreground transition-all cursor-pointer border border-border"
                  >
                    {copiedId === sig.id ? (
                      <>
                        <Check className="w-3 h-3 text-emerald-400" />
                        <span className="text-emerald-400 font-semibold">Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3 h-3 text-muted-foreground" />
                        <span>Copy Plan</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
