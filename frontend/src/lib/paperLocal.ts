'use client';

import type { PortfolioSummary, VirtualPosition, VirtualOrder, OrderPayload, BasketOrderPayload } from './types';

const LS_POS = 'droid_paper_positions';
const LS_ORD = 'droid_paper_orders';
const LS_REALIZED = 'droid_paper_realized';
const INITIAL_CAPITAL = 1000000;

function isBrowser(): boolean { return typeof window !== 'undefined' && typeof localStorage !== 'undefined'; }

function loadPositions(): VirtualPosition[] {
  if (!isBrowser()) return [];
  try { return JSON.parse(localStorage.getItem(LS_POS) || '[]'); } catch { return []; }
}
function savePositions(p: VirtualPosition[]): void {
  if (!isBrowser()) return;
  localStorage.setItem(LS_POS, JSON.stringify(p));
}
function loadOrders(): VirtualOrder[] {
  if (!isBrowser()) return [];
  try { return JSON.parse(localStorage.getItem(LS_ORD) || '[]'); } catch { return []; }
}
function saveOrders(o: VirtualOrder[]): void {
  if (!isBrowser()) return;
  localStorage.setItem(LS_ORD, JSON.stringify(o));
}
function loadRealized(): number {
  if (!isBrowser()) return 0;
  return parseFloat(localStorage.getItem(LS_REALIZED) || '0') || 0;
}
function saveRealized(v: number): void {
  if (!isBrowser()) return;
  localStorage.setItem(LS_REALIZED, String(v));
}

function calcMargin(payload: OrderPayload, fill: number): number {
  const isOpt = payload.symbol.includes('CE') || payload.symbol.includes('PE');
  const isBuyOpt = payload.side === 'BUY' && isOpt;
  // BUY option: premium only, low margin; SELL option / futures: higher margin
  if (isBuyOpt) return Math.round(fill * payload.quantity * 0.2);
  if (isOpt) return Math.round(fill * payload.quantity * 0.3);
  return Math.round(fill * payload.quantity * 0.18);
}

function getFillPrice(payload: OrderPayload): number {
  return payload.price > 0 ? payload.price : 0;
}

export function isBackendUnreachableError(err: unknown): boolean {
  const msg = err instanceof Error ? err.message : String(err);
  return msg.includes('Cannot reach backend') || msg.includes('Failed to fetch') || msg.includes('NetworkError');
}

export function getLocalPortfolio(): PortfolioSummary {
  const positions = loadPositions().filter(p => p.is_open);
  const realized = loadRealized();
  const used = Math.round(positions.reduce((s, p) => s + (p.used_margin || 0), 0));
  const unreal = Math.round(positions.reduce((s, p) => s + (p.unrealized_pnl || 0), 0));
  const totalPnl = realized + unreal;
  const available = Math.max(0, INITIAL_CAPITAL + totalPnl - used);
  return {
    virtual_capital: INITIAL_CAPITAL,
    available_margin: available,
    used_margin: used,
    margin_utilization_pct: INITIAL_CAPITAL ? Math.round((used / INITIAL_CAPITAL) * 100 * 10) / 10 : 0,
    total_realized_pnl: realized,
    total_unrealized_pnl: unreal,
    total_portfolio_pnl: totalPnl,
    open_positions_count: positions.length,
  };
}

export function getLocalPositions(): VirtualPosition[] {
  return loadPositions();
}
export function getLocalOrders(): VirtualOrder[] {
  return loadOrders();
}

export function placeLocalOrder(payload: OrderPayload): VirtualOrder {
  const positions = loadPositions();
  const orders = loadOrders();
  let realized = loadRealized();
  const now = new Date().toISOString();
  const orderId = `ORD-${Math.random().toString(36).slice(2, 8).toUpperCase()}`;
  const fill = getFillPrice(payload);

  if (fill <= 0) {
    const rejected: VirtualOrder = {
      order_id: orderId, timestamp: now, symbol: payload.symbol, underlying: payload.underlying,
      side: payload.side, order_type: (payload.order_type ?? 'MARKET'), product: (payload.product ?? 'INTRADAY'),
      quantity: payload.quantity, price: payload.price, trigger_price: payload.trigger_price ?? null,
      status: 'REJECTED', fill_price: null, rejection_reason: 'Market price unavailable. Please specify an execution price or ensure live data is connected.',
    };
    orders.unshift(rejected);
    saveOrders(orders.slice(0, 100));
    return rejected;
  }

  const reqMargin = calcMargin(payload, fill);

  const portfolio = getLocalPortfolio();
  if (reqMargin > portfolio.available_margin) {
    const rejected: VirtualOrder = {
      order_id: orderId, timestamp: now, symbol: payload.symbol, underlying: payload.underlying,
      side: payload.side, order_type: (payload.order_type ?? 'MARKET'), product: (payload.product ?? 'INTRADAY'),
      quantity: payload.quantity, price: payload.price, trigger_price: payload.trigger_price ?? null,
      status: 'REJECTED', fill_price: null, rejection_reason: `Insufficient margin. Required ₹${reqMargin.toLocaleString()}, Available ₹${portfolio.available_margin.toLocaleString()}`,
    };
    orders.unshift(rejected);
    saveOrders(orders.slice(0, 100));
    return rejected;
  }

  const posId = `${payload.symbol}_${payload.product ?? 'INTRADAY'}`;
  let pos = positions.find(p => p.position_id === posId && p.is_open) || null;
  const instType = (payload.symbol.includes('CE') || payload.symbol.includes('PE')) ? (payload.side === 'BUY' ? 'OPTION_BUY' : 'OPTION_SELL') : 'FUTURES';

  if (pos) {
    if (pos.side === payload.side) {
      const totQty = pos.quantity + payload.quantity;
      const totVal = pos.quantity * pos.average_price + payload.quantity * fill;
      pos.average_price = Math.round((totVal / totQty) * 100) / 100;
      pos.quantity = totQty;
      pos.used_margin += reqMargin;
    } else {
      const closedQty = Math.min(pos.quantity, payload.quantity);
      const mult = pos.side === 'BUY' ? 1 : -1;
      const tradeRealized = (fill - pos.average_price) * closedQty * mult;
      realized += tradeRealized;
      pos.realized_pnl = (pos.realized_pnl || 0) + tradeRealized;
      if (payload.quantity >= pos.quantity) {
        pos.is_open = false;
        pos.quantity = 0;
        pos.used_margin = 0;
      } else {
        pos.quantity -= payload.quantity;
        pos.used_margin = Math.max(0, pos.used_margin - reqMargin);
      }
      saveRealized(realized);
    }
  } else {
    pos = {
      position_id: posId, symbol: payload.symbol, underlying: payload.underlying,
      instrument_type: instType, side: payload.side, product: (payload.product ?? 'INTRADAY'),
      quantity: payload.quantity, average_price: fill, ltp: fill,
      unrealized_pnl: 0, realized_pnl: 0, used_margin: reqMargin, is_open: true,
    };
    positions.push(pos!);
  }

  const order: VirtualOrder = {
    order_id: orderId, timestamp: now, symbol: payload.symbol, underlying: payload.underlying,
    side: payload.side, order_type: (payload.order_type ?? 'MARKET'), product: (payload.product ?? 'INTRADAY'),
    quantity: payload.quantity, price: payload.price, trigger_price: payload.trigger_price ?? null,
    status: 'FILLED', fill_price: fill,
  };
  orders.unshift(order);
  savePositions(positions);
  saveOrders(orders.slice(0, 100));
  saveRealized(realized);
  return order;
}

export function placeLocalBasket(payload: BasketOrderPayload): VirtualOrder[] {
  return payload.orders.map(o => placeLocalOrder(o));
}

export function squareOffLocal(positionId: string): VirtualPosition {
  const positions = loadPositions();
  const pos = positions.find(p => p.position_id === positionId);
  if (!pos || !pos.is_open) throw new Error(`Open position not found: ${positionId}`);
  const exitSide = pos.side === 'BUY' ? 'SELL' : 'BUY';
  placeLocalOrder({ symbol: pos.symbol, underlying: pos.underlying, side: exitSide as any, order_type: 'MARKET', product: pos.product, quantity: pos.quantity, price: pos.ltp });
  // reload after close
  const updated = loadPositions().find(p => p.position_id === positionId);
  if (!updated) throw new Error('Square off failed');
  return updated;
}

export function squareOffAllLocal(): VirtualPosition[] {
  const positions = loadPositions().filter(p => p.is_open);
  const closed: VirtualPosition[] = [];
  for (const p of positions) {
    try { closed.push(squareOffLocal(p.position_id)); } catch {}
  }
  return closed;
}

export function resetLocal(): PortfolioSummary {
  if (isBrowser()) {
    localStorage.removeItem(LS_POS);
    localStorage.removeItem(LS_ORD);
    localStorage.removeItem(LS_REALIZED);
  }
  return {
    virtual_capital: INITIAL_CAPITAL, available_margin: INITIAL_CAPITAL, used_margin: 0,
    margin_utilization_pct: 0, total_realized_pnl: 0, total_unrealized_pnl: 0,
    total_portfolio_pnl: 0, open_positions_count: 0,
  };
}
