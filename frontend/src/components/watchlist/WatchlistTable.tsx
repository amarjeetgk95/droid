'use client';

import { useState } from 'react';
import { WatchlistItem } from '@/lib/types';
import { Bookmark, Plus, Trash2, TrendingUp, TrendingDown } from 'lucide-react';

export function WatchlistTable({
  items,
  selectedSymbol,
  onSelectSymbol,
  onAddSymbol,
  onRemoveSymbol,
}: {
  items: WatchlistItem[];
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  onAddSymbol: (symbol: string) => void;
  onRemoveSymbol: (symbol: string) => void;
}) {
  const [newSymbol, setNewSymbol] = useState('');

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSymbol.trim()) return;
    onAddSymbol(newSymbol.trim().toUpperCase());
    setNewSymbol('');
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Bookmark className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">Market Watchlist ({items.length})</h3>
        </div>

        {/* Quick Add Symbol Input */}
        <form onSubmit={handleAdd} className="flex items-center gap-1.5">
          <input
            type="text"
            placeholder="Add symbol e.g. TCS"
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value)}
            className="bg-secondary text-xs px-2.5 py-1 rounded-lg border border-border text-foreground focus:outline-hidden w-36 uppercase font-semibold"
          />
          <button
            type="submit"
            className="p-1.5 bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg transition-all cursor-pointer"
            title="Add Symbol"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </form>
      </div>

      {/* Watchlist Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left border-collapse">
          <thead>
            <tr className="border-b border-border text-muted-foreground font-semibold">
              <th className="py-2 px-2">Symbol</th>
              <th className="py-2 px-2 text-right">LTP (₹)</th>
              <th className="py-2 px-2 text-right">Change</th>
              <th className="py-2 px-2">Active Pattern</th>
              <th className="py-2 px-2">Regime State</th>
              <th className="py-2 px-2 text-center">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40 font-mono">
            {items.map((item) => {
              const isSelected = selectedSymbol.toUpperCase().includes(item.symbol.toUpperCase()) || item.symbol.toUpperCase().includes(selectedSymbol.toUpperCase());
              const isPositive = item.change >= 0;
              return (
                <tr
                  key={item.symbol}
                  onClick={() => onSelectSymbol(item.symbol)}
                  className={`hover:bg-accent/40 cursor-pointer transition-colors ${
                    isSelected ? 'bg-primary/10' : ''
                  }`}
                >
                  <td className="py-2.5 px-2 font-sans font-bold text-foreground">
                    {item.display_name || item.symbol}
                  </td>
                  <td className="py-2.5 px-2 text-right font-bold text-foreground">
                    ₹{item.ltp.toLocaleString('en-IN')}
                  </td>
                  <td className={`py-2.5 px-2 text-right font-bold flex items-center justify-end gap-1 ${
                    isPositive ? 'text-emerald-400' : 'text-rose-400'
                  }`}>
                    {isPositive ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                    {isPositive ? '+' : ''}{item.change.toFixed(2)} ({item.change_percent.toFixed(2)}%)
                  </td>
                  <td className="py-2.5 px-2 font-sans">
                    {item.active_pattern ? (
                      <span className="text-[10px] px-2 py-0.5 rounded font-bold bg-primary/20 text-primary border border-primary/30">
                        {item.active_pattern}
                      </span>
                    ) : (
                      <span className="text-muted-foreground text-[11px]">Consolidation</span>
                    )}
                  </td>
                  <td className="py-2.5 px-2 font-sans">
                    <span className="text-[11px] text-muted-foreground">
                      {item.regime_state?.replace(/_/g, ' ') || '---'}
                    </span>
                  </td>
                  <td className="py-2.5 px-2 text-center">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onRemoveSymbol(item.symbol);
                      }}
                      className="p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors cursor-pointer"
                      title="Remove from Watchlist"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
