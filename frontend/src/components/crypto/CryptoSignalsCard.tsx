'use client';

import React, { useState } from 'react';
import { Radio, ArrowUpRight, ArrowDownRight, ShieldAlert, Target, Sparkles, Check, Layers, Clock, TrendingUp } from 'lucide-react';
import { CryptoSignal } from '@/lib/types';
import { formatDateTime } from '@/lib/signal-utils';

interface Props {
  signals: CryptoSignal[];
  loading?: boolean;
  selectedAsset?: string;
  onSelectAsset?: (asset: string) => void;
}

export function CryptoSignalsCard({ signals, loading, selectedAsset, onSelectAsset }: Props) {
  const [filter, setFilter] = useState<'ALL' | 'BTC' | 'ETH'>('ALL');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const filteredSignals = signals.filter((s) => {
    if (filter === 'ALL') return true;
    return s.asset === filter;
  });

  const handleCopy = (sig: CryptoSignal) => {
    const text = `[DROID QUANT SIGNAL] ${sig.direction} ${sig.symbol}\nDate & Time: ${formatDateTime(sig.timestamp)}\nStrategy: ${sig.strategy_name}\nEntry: $${sig.entry_price}\nTarget 1: $${sig.target_1}\nTarget 2: $${sig.target_2}\nStop Loss: $${sig.stop_loss}\nR:R: ${sig.risk_reward_ratio}\nConfidence: ${sig.confidence}%\nTimeframe: ${sig.timeframe}`;
    navigator.clipboard?.writeText(text);
    setCopiedId(sig.id);
    setTimeout(() => setCopiedId(null), 2500);
  };

  const formatPrice = (val: number) => {
    if (val >= 1000) return `$${val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (val >= 1) return `$${val.toFixed(2)}`;
    return `$${val.toFixed(5)}`;
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4 shadow-xs space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <Radio className="w-4 h-4 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-bold text-foreground">
                Institutional Quant Signals
              </h3>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 font-bold">
                {signals.length} Active
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Automated setups derived from L2 depth walls, funding rate squeezes, and basis skew.
            </p>
          </div>
        </div>

        {/* Filter Pills */}
        <div className="flex bg-secondary rounded-lg p-0.5 border border-border self-start sm:self-auto">
          {(['ALL', 'BTC', 'ETH'] as const).map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => setFilter(opt)}
              className={`px-2.5 py-1 text-[11px] font-mono font-semibold rounded-md transition-all cursor-pointer ${
                filter === opt
                  ? 'bg-card text-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {opt}
            </button>
          ))}
        </div>
      </div>

      {/* Loading state */}
      {loading && signals.length === 0 ? (
        <div className="h-44 flex items-center justify-center text-xs text-muted-foreground animate-pulse">
          <Radio className="w-4 h-4 mr-2 opacity-50" />
          <span>Synthesizing real-time order-book & derivatives flow...</span>
        </div>
      ) : filteredSignals.length === 0 ? (
        <div className="h-32 flex flex-col items-center justify-center text-xs text-muted-foreground border border-dashed border-border rounded-xl p-4 text-center">
          <ShieldAlert className="w-6 h-6 mb-1 text-muted-foreground/60" />
          <span>No active signal threshold breached for {filter}. Order book and funding currently in neutral equilibrium.</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {filteredSignals.map((sig) => {
            const isLong = sig.direction === 'LONG';
            const isCopied = copiedId === sig.id;

            return (
              <div
                key={sig.id}
                className="bg-secondary/30 border border-border hover:border-border/80 transition-all rounded-xl p-3.5 flex flex-col justify-between space-y-3 relative overflow-hidden"
              >
                {/* Accent Top Border */}
                <div
                  className={`absolute top-0 left-0 right-0 h-1 ${
                    isLong ? 'bg-emerald-500' : 'bg-rose-500'
                  }`}
                />

                {/* Top Row: Coin & Strategy */}
                <div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`text-xs font-mono font-extrabold px-2 py-0.5 rounded ${
                          isLong
                            ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/25'
                            : 'bg-rose-500/15 text-rose-400 border border-rose-500/25'
                        }`}
                      >
                        {isLong ? '▲ BUY / LONG' : '▼ SELL / SHORT'}
                      </span>
                      <span className="text-xs font-bold text-foreground font-mono">
                        {sig.symbol}
                      </span>
                      <span className="text-[10px] text-muted-foreground font-mono">
                        · {sig.timeframe}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-card text-primary border border-border font-bold">
                        {sig.confidence}% Conviction
                      </span>
                    </div>
                  </div>

                  <h4 className="text-xs font-semibold text-foreground mt-2 flex items-center gap-1">
                    <span>{sig.strategy_name}</span>
                  </h4>

                  <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed line-clamp-2">
                    {sig.rationale}
                  </p>
                </div>

                {/* Quantitative Levels Grid */}
                <div className="grid grid-cols-4 gap-1.5 bg-card/60 p-2 rounded-lg border border-border/60 text-[10px] font-mono">
                  <div>
                    <span className="text-muted-foreground block text-[9px]">ENTRY</span>
                    <span className="font-bold text-foreground tabular-nums">{formatPrice(sig.entry_price)}</span>
                  </div>
                  <div>
                    <span className="text-rose-400 block text-[9px]">STOP LOSS</span>
                    <span className="font-bold text-rose-400 tabular-nums">{formatPrice(sig.stop_loss)}</span>
                  </div>
                  <div>
                    <span className="text-emerald-400 block text-[9px]">TARGET 1</span>
                    <span className="font-bold text-emerald-400 tabular-nums">{formatPrice(sig.target_1)}</span>
                  </div>
                  <div>
                    <span className="text-emerald-300 block text-[9px]">R:R RATIO</span>
                    <span className="font-bold text-emerald-300 tabular-nums">1 : {sig.risk_reward_ratio}</span>
                  </div>
                </div>

                {/* Confluence Badges & Actions */}
                <div className="space-y-2 pt-1">
                  <div className="flex flex-wrap gap-1">
                    {sig.confluence_factors.map((factor, idx) => (
                      <span
                        key={idx}
                        className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-secondary text-muted-foreground border border-border"
                      >
                        ✓ {factor}
                      </span>
                    ))}
                  </div>

                  <div className="flex items-center justify-between pt-1 border-t border-border/40 text-[11px]">
                    <span className="text-[10px] font-mono text-muted-foreground" title="Signal Date & Time (IST)">
                      {formatDateTime(sig.timestamp)}
                    </span>

                    <button
                      type="button"
                      onClick={() => handleCopy(sig)}
                      className="px-2.5 py-1 rounded bg-secondary hover:bg-secondary/80 text-foreground font-mono text-[10px] font-semibold transition-all cursor-pointer border border-border flex items-center gap-1"
                    >
                      {isCopied ? <Check className="w-3 h-3 text-emerald-400" /> : <ArrowUpRight className="w-3 h-3" />}
                      <span>{isCopied ? 'Copied!' : 'Copy Plan'}</span>
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
