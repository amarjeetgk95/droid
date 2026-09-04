'use client';

import { useState, useEffect, useMemo } from 'react';
import { VirtualPosition } from '@/lib/types';
import { Layers, XCircle, TrendingUp, TrendingDown, ArrowUpDown, X, Minus } from 'lucide-react';

type SortKey = 'mtm' | 'pnlPct' | 'symbol';

function pnlPct(p: VirtualPosition): number {
  const cost = p.average_price * p.quantity;
  if (!cost) return 0;
  return (p.unrealized_pnl / cost) * 100;
}

export function PositionsTable({
  positions,
  onSquareOff,
  onPartialExit,
  onTrade,
  squareOffId,
}: {
  positions: VirtualPosition[];
  onSquareOff: (positionId: string) => void;
  onPartialExit?: (position: VirtualPosition, qty: number) => void;
  onTrade?: () => void;
  squareOffId?: string | null;
}) {
  const [sortKey, setSortKey] = useState<SortKey>('mtm');
  const [sortDir, setSortDir] = useState<1 | -1>(-1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [exitQty, setExitQty] = useState<number>(0);

  const openPositions = useMemo(() => {
    const list = positions.filter((p) => p.is_open);
    const sorted = [...list].sort((a, b) => {
      if (sortKey === 'symbol') return sortDir * a.symbol.localeCompare(b.symbol);
      if (sortKey === 'pnlPct') return sortDir * (pnlPct(a) - pnlPct(b));
      return sortDir * (a.unrealized_pnl - b.unrealized_pnl);
    });
    return sorted;
  }, [positions, sortKey, sortDir]);
  const closedPositions = positions.filter((p) => !p.is_open);
  const selected = openPositions.find((p) => p.position_id === selectedId) ?? null;

  useEffect(() => {
    if (selected) setExitQty(Math.max(1, Math.floor(selected.quantity / 2)));
  }, [selected?.position_id]);

  useEffect(() => {
    if (!selectedId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectedId(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedId]);

  const toggleSort = (k: SortKey) => {
    if (sortKey === k) setSortDir((d) => (d === 1 ? -1 : 1));
    else {
      setSortKey(k);
      setSortDir(k === 'symbol' ? 1 : -1);
    }
  };

  const sortLabel = (k: SortKey, label: string) => (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); toggleSort(k); }}
      className="inline-flex items-center gap-1 hover:text-foreground transition-colors cursor-pointer"
      aria-label={`Sort by ${label}`}
    >
      {label}
      <ArrowUpDown className={`w-3 h-3 ${sortKey === k ? 'text-primary' : 'opacity-40'}`} />
    </button>
  );

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">
            Active Positions ({openPositions.length})
          </h3>
        </div>
        <span className="text-[10px] text-muted-foreground font-mono hidden sm:inline">Click a row for detail + partial exit</span>
      </div>

      {openPositions.length === 0 ? (
        <div className="p-8 text-center bg-secondary/30 rounded-lg border border-border space-y-3">
          <p className="text-muted-foreground text-xs">No open positions. Place an order or execute a strategy basket to begin paper trading.</p>
          {onTrade && (
            <button
              type="button"
              onClick={onTrade}
              className="px-3 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-bold transition-all cursor-pointer"
            >
              Place First Paper Order
            </button>
          )}
        </div>
      ) : (
        <>
          {/* Desktop table */}
          <div className="overflow-x-auto hidden md:block">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="border-b border-border text-muted-foreground font-semibold">
                  <th className="py-2 px-2">{sortLabel('symbol', 'Instrument')}</th>
                  <th className="py-2 px-2">Side</th>
                  <th className="py-2 px-2">Product</th>
                  <th className="py-2 px-2 text-right">Qty</th>
                  <th className="py-2 px-2 text-right">Avg (₹)</th>
                  <th className="py-2 px-2 text-right">LTP (₹)</th>
                  <th className="py-2 px-2 text-right">{sortLabel('mtm', 'MTM P&L (₹)')}</th>
                  <th className="py-2 px-2 text-right">{sortLabel('pnlPct', 'P&L %')}</th>
                  <th className="py-2 px-2 text-right">Margin (₹)</th>
                  <th className="py-2 px-2 text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40 font-mono">
                {openPositions.map((pos) => {
                  const isPos = pos.unrealized_pnl >= 0;
                  const pct = pnlPct(pos);
                  const busy = squareOffId === pos.position_id;
                  return (
                    <tr
                      key={pos.position_id}
                      onClick={() => setSelectedId(pos.position_id)}
                      className="hover:bg-accent/30 transition-colors cursor-pointer"
                    >
                      <td className="py-2.5 px-2 font-sans font-bold text-foreground">{pos.symbol}</td>
                      <td className="py-2.5 px-2">
                        <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${pos.side === 'BUY' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'}`}>
                          {pos.side}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-muted-foreground text-[11px] font-sans">{pos.product}</td>
                      <td className="py-2.5 px-2 text-right font-bold text-foreground">{pos.quantity}</td>
                      <td className="py-2.5 px-2 text-right text-foreground">₹{pos.average_price}</td>
                      <td className="py-2.5 px-2 text-right text-foreground font-bold">₹{pos.ltp}</td>
                      <td className={`py-2.5 px-2 text-right font-black ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                        <span className="inline-flex items-center justify-end gap-1">
                          {isPos ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                          {isPos ? '+' : ''}₹{pos.unrealized_pnl.toLocaleString('en-IN')}
                        </span>
                      </td>
                      <td className={`py-2.5 px-2 text-right font-bold ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {isPos ? '+' : ''}{pct.toFixed(2)}%
                      </td>
                      <td className="py-2.5 px-2 text-right text-muted-foreground text-[11px]">₹{pos.used_margin.toLocaleString('en-IN')}</td>
                      <td className="py-2.5 px-2 text-center" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => onSquareOff(pos.position_id)}
                          disabled={busy}
                          className="px-2 py-1 bg-destructive/10 hover:bg-destructive text-destructive hover:text-destructive-foreground border border-destructive/30 rounded text-[10px] font-bold transition-all cursor-pointer items-center gap-1 mx-auto flex disabled:opacity-50"
                        >
                          <XCircle className="w-3 h-3" />
                          <span>{busy ? 'Exiting…' : 'Exit'}</span>
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="grid gap-2 md:hidden">
            {openPositions.map((pos) => {
              const isPos = pos.unrealized_pnl >= 0;
              const pct = pnlPct(pos);
              const busy = squareOffId === pos.position_id;
              return (
                <button
                  key={pos.position_id}
                  type="button"
                  onClick={() => setSelectedId(pos.position_id)}
                  className="text-left rounded-xl border border-border bg-secondary/30 p-3 space-y-1.5 cursor-pointer"
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-bold text-sm text-foreground">{pos.symbol}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${pos.side === 'BUY' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'}`}>{pos.side}</span>
                  </span>
                  <span className="flex items-center justify-between text-[11px] font-mono text-muted-foreground">
                    <span>{pos.quantity} qty @ ₹{pos.average_price} → ₹{pos.ltp}</span>
                    <span className={`font-black ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>{isPos ? '+' : ''}₹{pos.unrealized_pnl.toLocaleString('en-IN')} ({isPos ? '+' : ''}{pct.toFixed(1)}%)</span>
                  </span>
                  <span className="flex items-center justify-between text-[10px] text-muted-foreground">
                    <span>{pos.product} • Margin ₹{pos.used_margin.toLocaleString('en-IN')}</span>
                    <span className="text-primary font-bold">{busy ? 'Exiting…' : 'Tap for exit →'}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </>
      )}

      {closedPositions.length > 0 && (
        <div className="pt-2 space-y-2">
          <h4 className="text-xs font-semibold text-muted-foreground">Closed Positions ({closedPositions.length})</h4>
          <div className="divide-y divide-border/30 font-mono text-[11px]">
            {closedPositions.map((pos) => (
              <div key={pos.position_id} className="py-1.5 flex items-center justify-between">
                <span className="text-foreground font-sans font-medium">{pos.symbol} ({pos.side})</span>
                <span className={`font-bold ${pos.realized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  Realized: {pos.realized_pnl >= 0 ? '+' : ''}₹{pos.realized_pnl.toLocaleString('en-IN')}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Detail drawer with partial exit */}
      {selected && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/60" onClick={() => setSelectedId(null)} role="presentation">
          <div
            role="dialog"
            aria-modal="true"
            aria-label={`Position detail ${selected.symbol}`}
            className="w-full max-w-sm h-full bg-card border-l border-border p-5 space-y-4 overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <h3 className="font-bold text-base text-foreground">{selected.symbol}</h3>
                <p className="text-[11px] text-muted-foreground font-mono">{selected.side} • {selected.product} • {selected.quantity} qty</p>
              </div>
              <button type="button" onClick={() => setSelectedId(null)} className="text-muted-foreground hover:text-foreground cursor-pointer" aria-label="Close position detail">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="rounded-lg bg-secondary/40 border border-border p-2.5"><p className="text-[10px] text-muted-foreground font-sans">Avg</p><p className="font-bold">₹{selected.average_price}</p></div>
              <div className="rounded-lg bg-secondary/40 border border-border p-2.5"><p className="text-[10px] text-muted-foreground font-sans">LTP</p><p className="font-bold">₹{selected.ltp}</p></div>
              <div className="rounded-lg bg-secondary/40 border border-border p-2.5"><p className="text-[10px] text-muted-foreground font-sans">MTM</p><p className={`font-black ${selected.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{selected.unrealized_pnl >= 0 ? '+' : ''}₹{selected.unrealized_pnl.toLocaleString('en-IN')}</p></div>
              <div className="rounded-lg bg-secondary/40 border border-border p-2.5"><p className="text-[10px] text-muted-foreground font-sans">P&L %</p><p className={`font-black ${selected.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{pnlPct(selected).toFixed(2)}%</p></div>
              <div className="rounded-lg bg-secondary/40 border border-border p-2.5"><p className="text-[10px] text-muted-foreground font-sans">Cost</p><p className="font-bold">₹{(selected.average_price * selected.quantity).toLocaleString('en-IN')}</p></div>
              <div className="rounded-lg bg-secondary/40 border border-border p-2.5"><p className="text-[10px] text-muted-foreground font-sans">Margin</p><p className="font-bold">₹{selected.used_margin.toLocaleString('en-IN')}</p></div>
            </div>

            {onPartialExit && selected.quantity > 1 && (
              <div className="space-y-2 rounded-xl border border-border p-3">
                <p className="text-xs font-bold text-foreground flex items-center gap-1.5"><Minus className="w-3.5 h-3.5" /> Partial exit</p>
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    min={1}
                    max={selected.quantity}
                    value={Math.min(exitQty || 1, selected.quantity)}
                    onChange={(e) => setExitQty(Number(e.target.value))}
                    className="flex-1"
                    aria-label="Partial exit quantity"
                  />
                  <input
                    type="number"
                    min={1}
                    max={selected.quantity}
                    value={Math.min(exitQty || 1, selected.quantity)}
                    onChange={(e) => setExitQty(Math.max(1, Math.min(selected.quantity, Number(e.target.value) || 1)))}
                    className="w-20 bg-secondary text-xs px-2 py-1.5 rounded-lg border border-border font-mono text-center focus:outline-hidden"
                    aria-label="Exit quantity"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => onPartialExit(selected, Math.min(exitQty || 1, selected.quantity))}
                    disabled={squareOffId === selected.position_id}
                    className="flex-1 py-2 rounded-lg bg-secondary hover:bg-secondary/80 border border-border text-xs font-bold cursor-pointer disabled:opacity-50"
                  >
                    Exit {Math.min(exitQty || 1, selected.quantity)} qty
                  </button>
                  <button
                    type="button"
                    onClick={() => onSquareOff(selected.position_id)}
                    disabled={squareOffId === selected.position_id}
                    className="flex-1 py-2 rounded-lg bg-destructive hover:bg-destructive/90 text-destructive-foreground text-xs font-bold cursor-pointer disabled:opacity-50"
                  >
                    {squareOffId === selected.position_id ? 'Exiting…' : `Exit all ${selected.quantity}`}
                  </button>
                </div>
              </div>
            )}
            {(!onPartialExit || selected.quantity <= 1) && (
              <button
                type="button"
                onClick={() => onSquareOff(selected.position_id)}
                disabled={squareOffId === selected.position_id}
                className="w-full py-2.5 rounded-lg bg-destructive hover:bg-destructive/90 text-destructive-foreground text-xs font-bold cursor-pointer disabled:opacity-50"
              >
                {squareOffId === selected.position_id ? 'Exiting…' : 'Exit Position'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
