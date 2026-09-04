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
  }, [applySnapshot]);

  const refreshFromLocal = useCallback(() => {
    applySnapshot(getLocalPortfolio(), getLocalPositions(), getLocalOrders());
  }, [applySnapshot]);

  // Polling data - resilient: falls back to localStorage when backend unreachable (deployed site without Cloud Run)
  useEffect(() => {
    let isMounted = true;

    const loadData = async () => {
      try {
        const [sumRes, posRes, ordRes] = await Promise.all([
          api.getPaperPortfolio(),
          api.getPaperPositions(),
          api.getPaperOrders(),
        ]);
        if (isMounted) {
          setSummary(sumRes.data);
          setPositions(posRes.data);
          setOrders(ordRes.data);
          setOfflineMode(false);
          setError(null);
        }
      } catch (err) {
        if (isBackendUnreachableError(err)) {
          // Backend not reachable (e.g. Render cold start) -> use browser-local paper trading
          if (isMounted) {
            setSummary(getLocalPortfolio());
            setPositions(getLocalPositions());
            setOrders(getLocalOrders());
            setOfflineMode(true);
            setError(null);
          }
        } else if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to load paper trading data');
        }
      } finally {
        if (isMounted) setInitialLoading(false);
      }
    };

    loadData();
    let timeout: ReturnType<typeof setTimeout> | null = null;
    const schedule = () => {
      const jittered = 30000 * (0.8 + Math.random() * 0.4);
      timeout = setTimeout(async () => {
        if (!document.hidden) await loadData();
        schedule();
      }, jittered);
    };
    schedule();
    const onVis = () => { if (!document.hidden) void loadData(); };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      isMounted = false;
      if (timeout) clearTimeout(timeout);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, []);

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

  const handleRetryOrder = (order: VirtualOrder) => {
    setPrefillOrder({
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
        <div className="flex items-center gap-2 px-3 py-2 bg-amber-500/10 border border-amber-500/20 rounded-lg text-amber-700 text-xs font-medium">
          <WifiOff className="w-4 h-4" />
          <span>Offline demo mode — backend unreachable, paper trading runs in browser storage (localStorage). Orders persist locally until you clear site data.</span>
        </div>
      )}
      {/* Portfolio Summary Banner */}
      <PortfolioBanner
        summary={summary}
        onSquareOffAll={handleSquareOffAll}
        onReset={handleReset}
        loading={initialLoading}
        busyAction={busyAction}
      />

      {/* Navigation Sub-Tabs */}
      <div className="flex items-center gap-2 border-b border-border pb-2">
        <button
          onClick={() => setActiveTab('POSITIONS')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
            activeTab === 'POSITIONS'
              ? 'bg-primary text-primary-foreground shadow-xs'
              : 'bg-secondary text-muted-foreground hover:text-foreground'
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          <span>Positions ({positions.filter((p) => p.is_open).length})</span>
        </button>

        <button
          onClick={() => setActiveTab('ORDERS')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
            activeTab === 'ORDERS'
              ? 'bg-primary text-primary-foreground shadow-xs'
              : 'bg-secondary text-muted-foreground hover:text-foreground'
          }`}
        >
          <ListOrdered className="w-3.5 h-3.5" />
          <span>Order Book ({orders.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('TRADE')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
            activeTab === 'TRADE'
              ? 'bg-primary text-primary-foreground shadow-xs'
              : 'bg-secondary text-muted-foreground hover:text-foreground'
          }`}
        >
          <Send className="w-3.5 h-3.5" />
          <span>Place Order / Baskets</span>
        </button>
      </div>

      {/* Main Tab Content */}
      {error && (
        <div className="p-4 bg-destructive/10 border border-destructive/20 rounded-xl text-destructive text-xs font-semibold">
          {error}
        </div>
      )}

      {activeTab === 'POSITIONS' && (
        <PositionsTable
          positions={positions}
          onSquareOff={handleSquareOffPosition}
          squareOffId={squareOffId}
        />
      )}

      {activeTab === 'ORDERS' && (
        <OrderBookTable orders={orders} onRetry={handleRetryOrder} />
      )}

      {activeTab === 'TRADE' && (
        <OrderEntryTicket
          onPlaceOrder={handlePlaceOrder}
          onPlaceBasket={handlePlaceBasket}
          loading={placing}
          prefill={prefillOrder}
        />
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
