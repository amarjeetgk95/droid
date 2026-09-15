'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  ShieldAlert,
  Radio,
  History,
  Keyboard,
  GripHorizontal,
  RefreshCw,
  Columns2,
  Maximize2,
} from 'lucide-react';
import { ActiveScalpPositions } from './ActiveScalpPositions';
import { ScalpAlertsHUD } from './ScalpAlertsHUD';
import { useScalpContext } from './ScalpContext';
import { api } from '@/lib/api';
import { VirtualOrder } from '@/lib/types';
import { useSmartInterval } from '@/hooks/useSmartInterval';

export interface TacticalDockProps {
  showHelpModal?: boolean;
  onCloseHelpModal?: () => void;
  onOpenHelpModal?: () => void;
}

export function TacticalDock({
  showHelpModal = false,
  onCloseHelpModal,
  onOpenHelpModal,
}: TacticalDockProps) {
  const { openPositions } = useScalpContext();
  const [activeTab, setActiveTab] = useState<'positions' | 'radar' | 'trades'>('positions');
  const [rightTab, setRightTab] = useState<'radar' | 'trades'>('radar');
  const [isSplitView, setIsSplitView] = useState<boolean>(true);
  const [dockHeight, setDockHeight] = useState<number>(220);
  const [isResizing, setIsResizing] = useState(false);

  // Trade Log State
  const [recentTrades, setRecentTrades] = useState<VirtualOrder[]>([]);
  const [tradesLoading, setTradesLoading] = useState(false);

  const fetchRecentTrades = useCallback(async () => {
    try {
      setTradesLoading(true);
      const res = await api.getPaperOrders();
      const orders = (res.data || []) as VirtualOrder[];
      const sorted = orders
        .filter((o) => o.status === 'FILLED' || o.status === 'REJECTED')
        .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
        .slice(0, 10);
      setRecentTrades(sorted);
    } catch {
      // ignore poll error
    } finally {
      setTradesLoading(false);
    }
  }, []);

  // Poll trades when Trade Log is active (in either split or single tab mode)
  const shouldPollTrades = isSplitView ? rightTab === 'trades' : activeTab === 'trades';
  useSmartInterval(fetchRecentTrades, shouldPollTrades ? 4000 : null, {
    fireOnMount: true,
    fireOnVisible: true,
    pauseWhenHidden: true,
  });

  // Resizing logic with drag handle
  const startYRef = useRef<number>(0);
  const startHeightRef = useRef<number>(dockHeight);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
    startYRef.current = e.clientY;
    startHeightRef.current = dockHeight;
  }, [dockHeight]);

  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      const deltaY = startYRef.current - e.clientY;
      const newHeight = Math.min(420, Math.max(140, startHeightRef.current + deltaY));
      setDockHeight(newHeight);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing]);

  const totalUnrealized = openPositions.reduce((acc, p) => acc + (p.unrealized_pnl || 0), 0);

  // Render Trade Log Table
  const renderTradeLog = () => (
    <div className="flex flex-col gap-1.5 font-mono text-xs h-full">
      <div className="flex items-center justify-between border-b border-border/40 pb-1 text-[10px] text-muted-foreground shrink-0">
        <span>Recent Filled Orders (Last 10)</span>
        <button
          type="button"
          onClick={fetchRecentTrades}
          disabled={tradesLoading}
          className="inline-flex items-center gap-1 hover:text-foreground transition-colors cursor-pointer"
        >
          <RefreshCw className={`w-2.5 h-2.5 ${tradesLoading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {recentTrades.length === 0 ? (
        <div className="flex items-center justify-center h-full text-muted-foreground text-[11px] border border-dashed border-border/60 rounded">
          No executed trades logged in current session
        </div>
      ) : (
        <div className="overflow-x-auto overflow-y-auto flex-1 min-h-0">
          <table className="w-full text-[10.5px] border-collapse">
            <thead>
              <tr className="border-b border-border/30 text-muted-foreground text-[9.5px] text-left sticky top-0 bg-card">
                <th className="py-1 px-1.5">Time</th>
                <th className="py-1 px-1.5">Symbol</th>
                <th className="py-1 px-1.5">Side</th>
                <th className="py-1 px-1.5">Qty</th>
                <th className="py-1 px-1.5">Fill Price</th>
                <th className="py-1 px-1.5">Status</th>
              </tr>
            </thead>
            <tbody>
              {recentTrades.map((t) => {
                const timeStr = t.filled_at || t.timestamp
                  ? new Date(t.filled_at || t.timestamp).toLocaleTimeString('en-IN', {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                      hour12: false,
                    })
                  : '—';

                return (
                  <tr
                    key={t.order_id}
                    className="border-b border-border/20 hover:bg-secondary/20 transition-colors"
                  >
                    <td className="py-1 px-1.5 text-muted-foreground">{timeStr}</td>
                    <td className="py-1 px-1.5 font-bold text-foreground">{t.symbol}</td>
                    <td className="py-1 px-1.5">
                      <span
                        className={`px-1 rounded text-[9px] font-bold ${
                          t.side === 'BUY'
                            ? 'bg-emerald-500/20 text-emerald-400'
                            : 'bg-rose-500/20 text-rose-400'
                        }`}
                      >
                        {t.side}
                      </span>
                    </td>
                    <td className="py-1 px-1.5 text-foreground">{t.quantity}</td>
                    <td className="py-1 px-1.5 font-bold text-foreground">
                      {t.fill_price && t.fill_price > 0 ? `₹${t.fill_price.toFixed(1)}` : 'MKT'}
                    </td>
                    <td className="py-1 px-1.5">
                      <span
                        className={`px-1 rounded text-[9px] font-semibold ${
                          t.status === 'FILLED'
                            ? 'bg-emerald-500/20 text-emerald-400'
                            : 'bg-amber-500/20 text-amber-400'
                        }`}
                      >
                        {t.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );

  return (
    <>
      <div
        style={{ height: `${dockHeight}px` }}
        className="shrink-0 bg-card border border-border rounded-lg flex flex-col overflow-hidden shadow-xs relative select-none"
      >
        {/* Resize Handle */}
        <div
          onMouseDown={handleMouseDown}
          className={`h-1.5 w-full flex items-center justify-center cursor-row-resize bg-secondary/20 hover:bg-secondary/60 transition-colors ${
            isResizing ? 'bg-primary/30' : ''
          }`}
          title="Drag to resize dock height"
        >
          <GripHorizontal className="w-4 h-2 text-muted-foreground/60" />
        </div>

        {/* Dock Control Bar */}
        <div className="flex items-center justify-between border-b border-border/60 px-2.5 py-1 bg-secondary/30 shrink-0">
          {/* Left Controls */}
          <div className="flex items-center gap-1 font-mono text-[11px]">
            {isSplitView ? (
              <div className="flex items-center gap-2">
                <span className="font-bold text-foreground flex items-center gap-1.5 text-xs">
                  <ShieldAlert className="w-3.5 h-3.5 text-amber-500" />
                  <span>Positions ({openPositions.length})</span>
                  {totalUnrealized !== 0 && (
                    <span
                      className={`px-1.5 py-0.2 rounded text-[10px] font-bold ${
                        totalUnrealized > 0
                          ? 'bg-emerald-500/20 text-emerald-400'
                          : 'bg-rose-500/20 text-rose-400'
                      }`}
                    >
                      {totalUnrealized >= 0 ? '+' : ''}₹{totalUnrealized.toFixed(0)}
                    </span>
                  )}
                </span>
              </div>
            ) : (
              /* Tab list for single tab mode */
              <div className="flex items-center gap-1" role="tablist">
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === 'positions'}
                  onClick={() => setActiveTab('positions')}
                  className={`flex items-center gap-1.5 px-2 py-0.5 rounded font-bold transition-colors cursor-pointer ${
                    activeTab === 'positions'
                      ? 'bg-foreground text-background shadow-xs'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <ShieldAlert className="w-3.5 h-3.5" />
                  <span>Positions ({openPositions.length})</span>
                  {totalUnrealized !== 0 && (
                    <span
                      className={`px-1 rounded text-[10px] font-bold ${
                        totalUnrealized > 0
                          ? 'bg-emerald-500/20 text-emerald-400'
                          : 'bg-rose-500/20 text-rose-400'
                      }`}
                    >
                      {totalUnrealized >= 0 ? '+' : ''}₹{totalUnrealized.toFixed(0)}
                    </span>
                  )}
                </button>

                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === 'radar'}
                  onClick={() => setActiveTab('radar')}
                  className={`flex items-center gap-1.5 px-2 py-0.5 rounded font-bold transition-colors cursor-pointer ${
                    activeTab === 'radar'
                      ? 'bg-foreground text-background shadow-xs'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <Radio className="w-3.5 h-3.5 text-rose-500 animate-pulse" />
                  <span>Radar</span>
                </button>

                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === 'trades'}
                  onClick={() => setActiveTab('trades')}
                  className={`flex items-center gap-1.5 px-2 py-0.5 rounded font-bold transition-colors cursor-pointer ${
                    activeTab === 'trades'
                      ? 'bg-foreground text-background shadow-xs'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <History className="w-3.5 h-3.5" />
                  <span>Trade Log</span>
                </button>
              </div>
            )}
          </div>

          {/* Right Controls */}
          <div className="flex items-center gap-2 font-mono text-[10.5px]">
            {/* View Mode Toggle: Split Deck vs Tabs */}
            <button
              type="button"
              onClick={() => setIsSplitView(!isSplitView)}
              className="hidden md:flex items-center gap-1 px-2 py-0.5 rounded bg-secondary/80 hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              title={isSplitView ? 'Switch to single tabbed view' : 'Switch to dual-pane split view'}
            >
              {isSplitView ? (
                <>
                  <Maximize2 className="w-3 h-3" />
                  <span>Single Tab</span>
                </>
              ) : (
                <>
                  <Columns2 className="w-3 h-3 text-primary" />
                  <span>Dual Deck</span>
                </>
              )}
            </button>

            <button
              type="button"
              onClick={onOpenHelpModal}
              className="flex items-center gap-1 px-1.5 py-0.5 rounded text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors cursor-pointer"
              title="Hotkeys reference (?)"
            >
              <Keyboard className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Keys</span>
            </button>
          </div>
        </div>

        {/* Tab Content Panel */}
        <div className="flex-1 min-h-0 p-2 overflow-hidden">
          {isSplitView ? (
            /* DUAL-PANE DESK: Left 50% Positions | Right 50% Radar/Trades */
            <div className="grid grid-cols-1 md:grid-cols-12 gap-3 h-full min-h-0">
              {/* Left 6-cols: Positions */}
              <div className="md:col-span-6 flex flex-col h-full min-h-0 md:border-r md:border-border/50 md:pr-2.5 overflow-y-auto">
                <ActiveScalpPositions />
              </div>

              {/* Right 6-cols: Live Radar / Trade Log */}
              <div className="md:col-span-6 flex flex-col h-full min-h-0 md:pl-0.5 overflow-hidden">
                <div className="flex items-center justify-between border-b border-border/40 pb-1 mb-1.5 shrink-0">
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => setRightTab('radar')}
                      className={`flex items-center gap-1 px-2 py-0.5 rounded font-bold font-mono text-[10.5px] transition-colors cursor-pointer ${
                        rightTab === 'radar'
                          ? 'bg-foreground text-background shadow-xs'
                          : 'text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      <Radio className="w-3 h-3 text-rose-500 animate-pulse" />
                      <span>Live Radar (1M)</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setRightTab('trades')}
                      className={`flex items-center gap-1 px-2 py-0.5 rounded font-bold font-mono text-[10.5px] transition-colors cursor-pointer ${
                        rightTab === 'trades'
                          ? 'bg-foreground text-background shadow-xs'
                          : 'text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      <History className="w-3 h-3" />
                      <span>Trade Log</span>
                    </button>
                  </div>
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto">
                  {rightTab === 'radar' && <ScalpAlertsHUD />}
                  {rightTab === 'trades' && renderTradeLog()}
                </div>
              </div>
            </div>
          ) : (
            /* SINGLE-PANE VIEW */
            <div className="h-full min-h-0 overflow-y-auto">
              {activeTab === 'positions' && <ActiveScalpPositions />}
              {activeTab === 'radar' && <ScalpAlertsHUD />}
              {activeTab === 'trades' && renderTradeLog()}
            </div>
          )}
        </div>
      </div>

      {/* Floating Hotkeys Help Modal */}
      {showHelpModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-card border border-border shadow-2xl rounded-xl max-w-md w-full p-4 flex flex-col gap-3 font-mono text-xs animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-border/60 pb-2">
              <span className="font-bold text-foreground text-sm flex items-center gap-1.5">
                <Keyboard className="w-4 h-4 text-primary" /> Scalper Hotkeys Reference
              </span>
              <button
                type="button"
                onClick={onCloseHelpModal}
                className="text-muted-foreground hover:text-foreground text-sm cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div className="p-2 rounded bg-secondary/40 border border-border/50">
                <span className="text-[10px] text-muted-foreground block">BUY CALL (CE)</span>
                <span className="font-bold text-emerald-400 text-sm">Key: C</span>
                <span className="text-[9.5px] text-muted-foreground block mt-0.5">Market order with selected CE</span>
              </div>
              <div className="p-2 rounded bg-secondary/40 border border-border/50">
                <span className="text-[10px] text-muted-foreground block">BUY PUT (PE)</span>
                <span className="font-bold text-rose-400 text-sm">Key: P</span>
                <span className="text-[9.5px] text-muted-foreground block mt-0.5">Market order with selected PE</span>
              </div>
              <div className="p-2 rounded bg-secondary/40 border border-border/50">
                <span className="text-[10px] text-muted-foreground block">LOT SIZES</span>
                <span className="font-bold text-foreground text-sm">Keys: 1, 2, 3, 4</span>
                <span className="text-[9.5px] text-muted-foreground block mt-0.5">1x, 2x, 4x, 10x multiplier</span>
              </div>
              <div className="p-2 rounded bg-secondary/40 border border-border/50">
                <span className="text-[10px] text-muted-foreground block">FULLSCREEN MODE</span>
                <span className="font-bold text-amber-400 text-sm">Key: F</span>
                <span className="text-[9.5px] text-muted-foreground block mt-0.5">Toggle Theater / Fullscreen</span>
              </div>
              <div className="p-2 rounded bg-secondary/40 border border-rose-500/30">
                <span className="text-[10px] text-rose-400 block font-bold">EMERGENCY EXIT</span>
                <span className="font-bold text-rose-400 text-sm">Shift + Esc</span>
                <span className="text-[9.5px] text-muted-foreground block mt-0.5">Panic square-off all positions</span>
              </div>
            </div>

            <div className="flex justify-end pt-1">
              <button
                type="button"
                onClick={onCloseHelpModal}
                className="px-3 py-1 rounded bg-secondary hover:bg-secondary/80 text-foreground font-semibold cursor-pointer text-xs"
              >
                Close (Esc)
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
