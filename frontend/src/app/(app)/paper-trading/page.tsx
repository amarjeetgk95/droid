'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '@/lib/api';
import {
  PortfolioSummary,
  VirtualPosition,
  VirtualOrder,
  OrderPayload,
  BasketOrderPayload,
} from '@/lib/types';
import {
  isBackendUnreachableError,
  getLocalPortfolio,
  getLocalPositions,
  getLocalOrders,
  placeLocalOrder,
  placeLocalBasket,
  squareOffLocal,
  squareOffAllLocal,
  resetLocal,
} from '@/lib/paperLocal';
import { PortfolioBanner } from '@/components/paper/PortfolioBanner';
import { PositionsTable } from '@/components/paper/PositionsTable';
import { OrderBookTable } from '@/components/paper/OrderBookTable';
import { OrderEntryTicket } from '@/components/paper/OrderEntryTicket';
import { PageTabs } from '@/components/ui/PageTabs';
import { ErrorCard } from '@/components/ui/ErrorCard';
import { Layers, ListOrdered, Send, WifiOff, CheckCircle2, AlertTriangle, X } from 'lucide-react';

type Toast = {
  id: number;
  kind: 'success' | 'error';
  msg: string;
  action?: 'view-positions' | 'view-orders';
};

export default function PaperTradingPage() {
  const [activeTab, setActiveTab] = useState<'POSITIONS' | 'ORDERS' | 'TRADE'>('POSITIONS');
  const [summary, setSummary] = useState<PortfolioSummary>({
    virtual_capital: 1000000,
    available_margin: 1000000,
    used_margin: 0,
    margin_utilization_pct: 0,
    total_realized_pnl: 0,
    total_unrealized_pnl: 0,
    total_portfolio_pnl: 0,
    open_positions_count: 0,
  });

  const [positions, setPositions] = useState<VirtualPosition[]>([]);
  const [orders, setOrders] = useState<VirtualOrder[]>([]);
  // Per-action loading: initial fetch vs order placement vs per-row square-off vs banner actions.
  const [initialLoading, setInitialLoading] = useState<boolean>(true);
  const [placing, setPlacing] = useState<boolean>(false);
  const [squareOffId, setSquareOffId] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<'square-off-all' | 'reset' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [offlineMode, setOfflineMode] = useState<boolean>(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [prefillOrder, setPrefillOrder] = useState<OrderPayload | null>(null);
  const [lastUpdatedMs, setLastUpdatedMs] = useState<number | null>(null);
  const [nowMs, setNowMs] = useState<number>(() => Date.now());
  const [pnlHistory, setPnlHistory] = useState<number[]>([]);
  const toastId = useRef(0);

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const pushToast = useCallback((kind: Toast['kind'], msg: string, action?: Toast['action']) => {
    const id = ++toastId.current;
    setToasts((prev) => [...prev.slice(-3), { id, kind, msg, action }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  const applySnapshot = useCallback(
    (s: PortfolioSummary, p: VirtualPosition[], o: VirtualOrder[]) => {
      setSummary(s);
      setPositions(p);
      setOrders(o);
      setPnlHistory((prev) => {
        if (prev.length > 0 && prev[prev.length - 1] === s.total_portfolio_pnl) return prev;
        return [...prev.slice(-29), s.total_portfolio_pnl];
      });
    },
    [],
  );

  const refreshFromBackend = useCallback(async () => {
    const [sumRes, posRes, ordRes] = await Promise.all([
      api.getPaperPortfolio(),
      api.getPaperPositions(),
      api.getPaperOrders(),
    ]);
    applySnapshot(sumRes.data, posRes.data, ordRes.data);
    setLastUpdatedMs(Date.now());
  }, [applySnapshot]);

  const refreshFromLocal = useCallback(() => {
    applySnapshot(getLocalPortfolio(), getLocalPositions(), getLocalOrders());
    setLastUpdatedMs(Date.now());
  }, [applySnapshot]);

  // Polling: fast lane (portfolio+positions ~10s for live MTM) + slow lane (orders 15s).
  // Falls back to localStorage when backend unreachable. Pauses when tab hidden.
  useEffect(() => {
    let isMounted = true;

    const loadFast = async () => {
      try {
        const [sumRes, posRes] = await Promise.all([
          api.getPaperPortfolio(),
          api.getPaperPositions(),
        ]);
        if (isMounted) {
          setSummary(sumRes.data);
          setPositions(posRes.data);
          setOfflineMode(false);
          setError(null);
          setLastUpdatedMs(Date.now());
        }
      } catch (err) {
        if (isBackendUnreachableError(err)) {
          if (isMounted) {
            setSummary(getLocalPortfolio());
            setPositions(getLocalPositions());
            setOfflineMode(true);
            setError(null);
            setLastUpdatedMs(Date.now());
          }
        } else if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to load paper trading data');
        }
      } finally {
        if (isMounted) setInitialLoading(false);
      }
    };

    const loadSlow = async () => {
      try {
        const ordRes = await api.getPaperOrders();
        if (isMounted) setOrders(ordRes.data);
      } catch (err) {
        if (isBackendUnreachableError(err)) {
          if (isMounted) {
            setOrders(getLocalOrders());
            setOfflineMode(true);
          }
        }
      }
    };

    const loadAll = async () => {
      await loadFast();
      await loadSlow();
    };

    loadAll();
    let fastTimer: ReturnType<typeof setTimeout> | null = null;
    let slowTimer: ReturnType<typeof setTimeout> | null = null;
    const scheduleFast = () => {
      const jittered = 10000 * (0.8 + Math.random() * 0.4);
      fastTimer = setTimeout(async () => {
        if (!document.hidden) await loadFast();
        scheduleFast();
      }, jittered);
    };
    const scheduleSlow = () => {
      const jittered = 15000 * (0.8 + Math.random() * 0.4);
      slowTimer = setTimeout(async () => {
        if (!document.hidden) await loadSlow();
        scheduleSlow();
      }, jittered);
    };
    scheduleFast();
    scheduleSlow();
    // Tick every 5s so "Updated Xs ago" stays honest without refetching.
    const clockTimer = setInterval(() => setNowMs(Date.now()), 5000);
    const onVis = () => { if (!document.hidden) void loadFast(); };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      isMounted = false;
      if (fastTimer) clearTimeout(fastTimer);
      if (slowTimer) clearTimeout(slowTimer);
      clearInterval(clockTimer);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, []);

  const retryBackend = async () => {
    try {
      await refreshFromBackend();
      setOfflineMode(false);
      setLastUpdatedMs(Date.now());
      pushToast('success', 'Backend reachable — live paper data restored.');
    } catch {
      pushToast('error', 'Backend still unreachable — staying in offline mode.');
    }
  };

  const updatedAgoSecs = lastUpdatedMs ? Math.max(0, Math.round((nowMs - lastUpdatedMs) / 1000)) : null;
  const feedStale = offlineMode || updatedAgoSecs === null || updatedAgoSecs > 30;

  const handlePlaceOrder = async (orderPayload: OrderPayload) => {
    setPlacing(true);
    try {
      if (offlineMode) {
        const placed = placeLocalOrder(orderPayload);
        refreshFromLocal();
        if (placed.status === 'REJECTED') {
          pushToast('error', placed.rejection_reason || 'Order rejected.', 'view-orders');
          setActiveTab('ORDERS');
        } else {
          pushToast('success', `Virtual ${placed.side} ${placed.quantity} ${placed.symbol} @ ₹${placed.fill_price}`, 'view-positions');
        }
        return;
      }
      try {
        const res = await api.placePaperOrder(orderPayload);
        await refreshFromBackend();
        const placed = res.data;
        if (placed?.status === 'REJECTED') {
          pushToast('error', placed.rejection_reason || 'Order rejected.', 'view-orders');
          setActiveTab('ORDERS');
        } else if (placed) {
          pushToast('success', `Virtual ${placed.side} ${placed.quantity} ${placed.symbol} @ ₹${placed.fill_price}`, 'view-positions');
        } else {
          pushToast('success', 'Virtual order placed.', 'view-positions');
        }
      } catch (e) {
        if (isBackendUnreachableError(e)) {
          setOfflineMode(true);
          const placed = placeLocalOrder(orderPayload);
          refreshFromLocal();
          if (placed.status === 'REJECTED') {
            pushToast('error', placed.rejection_reason || 'Order rejected.', 'view-orders');
            setActiveTab('ORDERS');
          } else {
            pushToast('success', `Virtual ${placed.side} ${placed.quantity} ${placed.symbol} @ ₹${placed.fill_price} (offline)`, 'view-positions');
          }
          return;
        }
        throw e;
      }
    } catch (err) {
      pushToast('error', err instanceof Error ? err.message : 'Order placement failed');
    } finally {
      setPlacing(false);
    }
  };

  const handlePlaceBasket = async (basketPayload: BasketOrderPayload) => {
    setPlacing(true);
    try {
      if (offlineMode) {
        const placed = placeLocalBasket(basketPayload);
        refreshFromLocal();
        const rejected = placed.filter((o) => o.status === 'REJECTED').length;
        if (rejected > 0) {
          pushToast('error', `${placed.length - rejected}/${placed.length} legs filled, ${rejected} rejected.`, 'view-orders');
          setActiveTab('ORDERS');
        } else {
          pushToast('success', `${placed.length}-leg basket executed.`, 'view-positions');
        }
        return;
      }
      try {
        const res = await api.placePaperBasket(basketPayload);
        await refreshFromBackend();
        const placed: VirtualOrder[] = res.data || [];
        const rejected = placed.filter((o) => o.status === 'REJECTED').length;
        if (rejected > 0) {
          pushToast('error', `${placed.length - rejected}/${placed.length} legs filled, ${rejected} rejected.`, 'view-orders');
          setActiveTab('ORDERS');
        } else {
          pushToast('success', `${placed.length}-leg basket executed.`, 'view-positions');
        }
      } catch (e) {
        if (isBackendUnreachableError(e)) {
          setOfflineMode(true);
          const placed = placeLocalBasket(basketPayload);
          refreshFromLocal();
          pushToast('success', `${placed.length}-leg basket executed (offline).`, 'view-positions');
          return;
        }
        throw e;
      }
    } catch (err) {
      pushToast('error', err instanceof Error ? err.message : 'Basket order failed');
    } finally {
      setPlacing(false);
    }
  };

  const handleSquareOffPosition = async (positionId: string) => {
    setSquareOffId(positionId);
    try {
      if (offlineMode) {
        squareOffLocal(positionId);
        refreshFromLocal();
        pushToast('success', 'Position squared off.');
      } else {
        try {
          await api.squareOffPosition(positionId);
        } catch (e) {
          if (isBackendUnreachableError(e)) {
            setOfflineMode(true);
            squareOffLocal(positionId);
            refreshFromLocal();
            pushToast('success', 'Position squared off (offline).');
            return;
          }
          throw e;
        }
        await refreshFromBackend();
        pushToast('success', 'Position squared off.');
      }
    } catch (err) {
      pushToast('error', err instanceof Error ? err.message : 'Square off failed');
    } finally {
      setSquareOffId(null);
    }
  };

  const handleSquareOffAll = async () => {
    setBusyAction('square-off-all');
    try {
      if (offlineMode) {
        squareOffAllLocal();
        refreshFromLocal();
        pushToast('success', 'All positions squared off.');
      } else {
        try {
          await api.squareOffAllPositions();
        } catch (e) {
          if (isBackendUnreachableError(e)) {
            setOfflineMode(true);
            squareOffAllLocal();
            refreshFromLocal();
            pushToast('success', 'All positions squared off (offline).');
            return;
          }
          throw e;
        }
        await refreshFromBackend();
        pushToast('success', 'All positions squared off.');
      }
    } catch (err) {
      pushToast('error', err instanceof Error ? err.message : 'Square off all failed');
    } finally {
      setBusyAction(null);
    }
  };

  const handleReset = async () => {
    setBusyAction('reset');
    try {
      if (offlineMode) {
        setSummary(resetLocal());
        setPositions([]);
        setOrders([]);
        pushToast('success', 'Virtual account reset.');
      } else {
        try {
          const resetRes = await api.resetPaperAccount();
          setSummary(resetRes.data);
          setPositions([]);
          setOrders([]);
          pushToast('success', 'Virtual account reset.');
        } catch (e) {
          if (isBackendUnreachableError(e)) {
            setOfflineMode(true);
            setSummary(resetLocal());
            setPositions([]);
            setOrders([]);
            pushToast('success', 'Virtual account reset (offline).');
            return;
          }
          throw e;
        }
      }
    } catch (err) {
      pushToast('error', err instanceof Error ? err.message : 'Reset failed');
    } finally {
      setBusyAction(null);
    }
  };

  const handlePartialExit = async (position: VirtualPosition, qty: number) => {
    const exitSide = position.side === 'BUY' ? 'SELL' : 'BUY';
    const payload: OrderPayload = {
      symbol: position.symbol,
      underlying: position.underlying,
      side: exitSide,
      order_type: 'MARKET',
      product: position.product,
      quantity: qty,
      price: 0,
    };
    setSquareOffId(position.position_id);
    try {
      if (offlineMode) {
        placeLocalOrder(payload);
        refreshFromLocal();
        pushToast('success', `Exited ${qty}/${position.quantity} ${position.symbol}.`);
      } else {
        try {
          await api.placePaperOrder(payload);
        } catch (e) {
          if (isBackendUnreachableError(e)) {
            setOfflineMode(true);
            placeLocalOrder(payload);
            refreshFromLocal();
            pushToast('success', `Exited ${qty}/${position.quantity} ${position.symbol} (offline).`);
            return;
          }
          throw e;
        }
        await refreshFromBackend();
        pushToast('success', `Exited ${qty}/${position.quantity} ${position.symbol}.`);
      }
    } catch (err) {
      pushToast('error', err instanceof Error ? err.message : 'Partial exit failed');
    } finally {
      setSquareOffId(null);
    }
  };

  const downloadCsv = (filename: string, rows: (string | number | null | undefined)[][]) => {
    const esc = (v: string | number | null | undefined) => {
      const s = v === null || v === undefined ? '' : String(v);
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const csv = rows.map((r) => r.map(esc).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleExportPositions = () => {
    downloadCsv(`paper-positions-${new Date().toISOString().slice(0, 10)}.csv`, [
      ['position_id', 'symbol', 'underlying', 'side', 'product', 'quantity', 'avg', 'ltp', 'unrealized', 'realized', 'margin', 'is_open'],
      ...positions.map((p) => [p.position_id, p.symbol, p.underlying, p.side, p.product, p.quantity, p.average_price, p.ltp, p.unrealized_pnl, p.realized_pnl, p.used_margin, p.is_open ? 'OPEN' : 'CLOSED']),
    ]);
    pushToast('success', 'Positions exported to CSV.');
  };

  const handleExportOrders = () => {
    downloadCsv(`paper-orders-${new Date().toISOString().slice(0, 10)}.csv`, [
      ['order_id', 'timestamp', 'symbol', 'underlying', 'side', 'product', 'qty', 'price', 'fill_price', 'status', 'rejection_reason'],
      ...orders.map((o) => [o.order_id, o.timestamp, o.symbol, o.underlying, o.side, o.product, o.quantity, o.price, o.fill_price ?? '', o.status, o.rejection_reason ?? '']),
    ]);
    pushToast('success', 'Order book exported to CSV.');
  };

  const handleRetryOrder = (order: VirtualOrder) => {    setPrefillOrder({
      symbol: order.symbol,
      underlying: order.underlying,
      side: order.side,
      product: order.product,
      order_type: order.order_type === 'LIMIT' ? 'LIMIT' : 'MARKET',
      quantity: order.quantity,
      price: order.price > 0 ? order.price : 0,
      trigger_price: order.trigger_price ?? null,
    });
    setActiveTab('TRADE');
  };

  return (
    <div className="space-y-4">
      {offlineMode && (
        <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-amber-500/10 border border-amber-500/20 rounded-lg text-amber-700 text-xs font-medium">
          <span className="flex items-center gap-2">
            <WifiOff className="w-4 h-4" />
            <span>Offline demo mode — backend unreachable, paper trading runs in browser storage (localStorage). Orders persist locally until you clear site data.</span>
          </span>
          <button
            type="button"
            onClick={retryBackend}
            className="px-2.5 py-1 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/30 text-[11px] font-bold transition-all cursor-pointer"
          >
            Retry Backend
          </button>
        </div>
      )}
      {/* Portfolio Summary Banner */}
      <PortfolioBanner
        summary={summary}
        onSquareOffAll={handleSquareOffAll}
        onReset={handleReset}
        loading={initialLoading}
        busyAction={busyAction}
        pnlSpark={pnlHistory}
        onExportOrders={handleExportOrders}
        onExportPositions={handleExportPositions}
      />

      {/* Freshness & Navigation Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-1">
        <div className="flex-1 min-w-[280px]">
          <PageTabs
            tabs={[
              {
                id: 'POSITIONS',
                label: 'Positions',
                icon: Layers,
                badge: positions.filter((p) => p.is_open).length,
                content: initialLoading ? (
                  <div className="bg-card border border-border rounded-xl p-4 space-y-2 shadow-xs" aria-label="Loading positions">
                    {[0, 1, 2].map((i) => (
                      <div key={i} className="h-10 rounded-lg bg-secondary/60 animate-pulse" />
                    ))}
                  </div>
                ) : (
                  <PositionsTable
                    positions={positions}
                    onSquareOff={handleSquareOffPosition}
                    onPartialExit={handlePartialExit}
                    onTrade={() => setActiveTab('TRADE')}
                    squareOffId={squareOffId}
                  />
                ),
              },
              {
                id: 'ORDERS',
                label: 'Order Book',
                icon: ListOrdered,
                badge: orders.length,
                content: <OrderBookTable orders={orders} onRetry={handleRetryOrder} />,
              },
              {
                id: 'TRADE',
                label: 'Place Order / Baskets',
                icon: Send,
                content: (
                  <OrderEntryTicket
                    onPlaceOrder={handlePlaceOrder}
                    onPlaceBasket={handlePlaceBasket}
                    loading={placing}
                    prefill={prefillOrder}
                    availableMargin={summary.available_margin}
                  />
                ),
              },
            ]}
            activeTab={activeTab}
            onTabChange={(tabId) => setActiveTab(tabId as 'POSITIONS' | 'ORDERS' | 'TRADE')}
          />
        </div>

        {/* Freshness indicator — MTM is only trustworthy when fresh */}
        <span className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground self-start mt-1.5" title="Portfolio+positions refresh every ~5s, orders every ~15s">
          <span className={`h-1.5 w-1.5 rounded-full ${feedStale ? 'bg-amber-500' : 'bg-emerald-500 animate-pulse'}`} />
          {offlineMode ? 'OFFLINE • local' : feedStale ? 'STALE' : 'LIVE'}
          {updatedAgoSecs !== null && <span>• {updatedAgoSecs}s ago</span>}
        </span>
      </div>

      {error && (
        <ErrorCard title="Portfolio synchronization issue" message={error} mode="banner" />
      )}

      {/* Toasts — success/error feedback without blocking the page */}
      <div aria-live="polite" className="fixed bottom-4 right-4 z-50 w-[320px] max-w-[calc(100vw-2rem)] space-y-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`flex items-start gap-2 rounded-lg border bg-card p-3 shadow-lg text-xs ${
              t.kind === 'success' ? 'border-emerald-500/30' : 'border-destructive/30'
            }`}
          >
            {t.kind === 'success' ? (
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-500" />
            ) : (
              <AlertTriangle className="w-4 h-4 shrink-0 text-destructive" />
            )}
            <div className="flex-1 space-y-1">
              <p className="font-semibold text-foreground leading-snug">{t.msg}</p>
              {t.action === 'view-positions' && (
                <button
                  type="button"
                  onClick={() => { setActiveTab('POSITIONS'); dismissToast(t.id); }}
                  className="text-[11px] font-bold text-primary hover:underline cursor-pointer"
                >
                  View Positions
                </button>
              )}
              {t.action === 'view-orders' && (
                <button
                  type="button"
                  onClick={() => { setActiveTab('ORDERS'); dismissToast(t.id); }}
                  className="text-[11px] font-bold text-primary hover:underline cursor-pointer"
                >
                  View Order Book
                </button>
              )}
            </div>
            <button
              type="button"
              onClick={() => dismissToast(t.id)}
              className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              aria-label="Dismiss notification"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
