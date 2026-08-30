'use client';

import { useState, useEffect } from 'react';
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
import { Layers, ListOrdered, Send, WifiOff } from 'lucide-react';

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
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [offlineMode, setOfflineMode] = useState<boolean>(false);

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
        if (isMounted) setLoading(false);
      }
    };

    loadData();
    const interval = setInterval(loadData, 3000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  const handlePlaceOrder = async (orderPayload: OrderPayload) => {
    setLoading(true);
    try {
      if (offlineMode) {
        placeLocalOrder(orderPayload);
        setSummary(getLocalPortfolio());
        setPositions(getLocalPositions());
        setOrders(getLocalOrders());
        setActiveTab('POSITIONS');
      } else {
        try {
          await api.placePaperOrder(orderPayload);
        } catch (e) {
          if (isBackendUnreachableError(e)) {
            setOfflineMode(true);
            placeLocalOrder(orderPayload);
            setSummary(getLocalPortfolio());
            setPositions(getLocalPositions());
            setOrders(getLocalOrders());
            setActiveTab('POSITIONS');
            return;
          }
          throw e;
        }
        const [sumRes, posRes, ordRes] = await Promise.all([
          api.getPaperPortfolio(),
          api.getPaperPositions(),
          api.getPaperOrders(),
        ]);
        setSummary(sumRes.data);
        setPositions(posRes.data);
        setOrders(ordRes.data);
        setActiveTab('POSITIONS');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Order placement failed');
    } finally {
      setLoading(false);
    }
  };

  const handlePlaceBasket = async (basketPayload: BasketOrderPayload) => {
    setLoading(true);
    try {
      if (offlineMode) {
        placeLocalBasket(basketPayload);
        setSummary(getLocalPortfolio());
        setPositions(getLocalPositions());
        setOrders(getLocalOrders());
        setActiveTab('POSITIONS');
      } else {
        try {
          await api.placePaperBasket(basketPayload);
        } catch (e) {
          if (isBackendUnreachableError(e)) {
            setOfflineMode(true);
            placeLocalBasket(basketPayload);
            setSummary(getLocalPortfolio());
            setPositions(getLocalPositions());
            setOrders(getLocalOrders());
            setActiveTab('POSITIONS');
            return;
          }
          throw e;
        }
        const [sumRes, posRes, ordRes] = await Promise.all([
          api.getPaperPortfolio(),
          api.getPaperPositions(),
          api.getPaperOrders(),
        ]);
        setSummary(sumRes.data);
        setPositions(posRes.data);
        setOrders(ordRes.data);
        setActiveTab('POSITIONS');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Basket order failed');
    } finally {
      setLoading(false);
    }
  };

  const handleSquareOffPosition = async (positionId: string) => {
    setLoading(true);
    try {
      if (offlineMode) {
        squareOffLocal(positionId);
        setSummary(getLocalPortfolio());
        setPositions(getLocalPositions());
        setOrders(getLocalOrders());
      } else {
        try {
          await api.squareOffPosition(positionId);
        } catch (e) {
          if (isBackendUnreachableError(e)) {
            setOfflineMode(true);
            squareOffLocal(positionId);
            setSummary(getLocalPortfolio());
            setPositions(getLocalPositions());
            setOrders(getLocalOrders());
            return;
          }
          throw e;
        }
        const [sumRes, posRes, ordRes] = await Promise.all([
          api.getPaperPortfolio(),
          api.getPaperPositions(),
          api.getPaperOrders(),
        ]);
        setSummary(sumRes.data);
        setPositions(posRes.data);
        setOrders(ordRes.data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Square off failed');
    } finally {
      setLoading(false);
    }
  };

  const handleSquareOffAll = async () => {
    setLoading(true);
    try {
      if (offlineMode) {
        squareOffAllLocal();
        setSummary(getLocalPortfolio());
        setPositions(getLocalPositions());
        setOrders(getLocalOrders());
      } else {
        try {
          await api.squareOffAllPositions();
        } catch (e) {
          if (isBackendUnreachableError(e)) {
            setOfflineMode(true);
            squareOffAllLocal();
            setSummary(getLocalPortfolio());
            setPositions(getLocalPositions());
            setOrders(getLocalOrders());
            return;
          }
          throw e;
        }
        const [sumRes, posRes, ordRes] = await Promise.all([
          api.getPaperPortfolio(),
          api.getPaperPositions(),
          api.getPaperOrders(),
        ]);
        setSummary(sumRes.data);
        setPositions(posRes.data);
        setOrders(ordRes.data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Square off all failed');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async () => {
    setLoading(true);
    try {
      if (offlineMode) {
        setSummary(resetLocal());
        setPositions([]);
        setOrders([]);
      } else {
        try {
          const resetRes = await api.resetPaperAccount();
          setSummary(resetRes.data);
          setPositions([]);
          setOrders([]);
        } catch (e) {
          if (isBackendUnreachableError(e)) {
            setOfflineMode(true);
            setSummary(resetLocal());
            setPositions([]);
            setOrders([]);
            return;
          }
          throw e;
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed');
    } finally {
      setLoading(false);
    }
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
        loading={loading}
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
        />
      )}

      {activeTab === 'ORDERS' && (
        <OrderBookTable orders={orders} />
      )}

      {activeTab === 'TRADE' && (
        <OrderEntryTicket
          onPlaceOrder={handlePlaceOrder}
          onPlaceBasket={handlePlaceBasket}
          loading={loading}
        />
      )}
    </div>
  );
}
