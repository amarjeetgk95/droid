'use client';

import React, { useState, useEffect, useRef } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Clock,
  ListOrdered,
  CheckCircle2,
  Trash2,
  RefreshCw,
  Eye,
  Zap,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  Info,
} from 'lucide-react';
import {
  CryptoScalpExecutionRecord,
} from '@/lib/types';
import { api } from '@/lib/api';
import {
  CryptoTradeDetailModal,
  formatDetailedExitReason,
} from './CryptoTradeDetailModal';

interface CryptoScalpLedgerTableProps {
  records: CryptoScalpExecutionRecord[];
  loading?: boolean;
  onRefresh?: () => Promise<void> | void;
  onDeleteRecord?: (tradeId: string) => Promise<void> | void;
  refreshIntervalMs?: number;
}

interface FormattedLedgerTimestamp {
  localTimeStr: string;
  localDateStr: string;
  fullLocalStr: string;
  utcStr: string;
  relative: string;
}

export function formatLedgerDate(timestampUtc?: number): FormattedLedgerTimestamp {
  if (!timestampUtc) {
    return { localTimeStr: '—', localDateStr: '—', fullLocalStr: '—', utcStr: '—', relative: '—' };
  }
  const ts = timestampUtc < 1e11 ? timestampUtc * 1000 : timestampUtc;
  const date = new Date(ts);

  let localTimeStr = '';
  let localDateStr = '';
  let fullLocalStr = '';
  try {
    localTimeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true });
    localDateStr = date.toLocaleDateString([], { month: 'short', day: '2-digit' });
    fullLocalStr = `${localDateStr}, ${localTimeStr}`;
  } catch {
    fullLocalStr = date.toISOString().substring(0, 19).replace('T', ' ');
    localTimeStr = date.toISOString().substring(11, 19);
    localDateStr = date.toISOString().substring(5, 10);
  }

  const utcHours = String(date.getUTCHours()).padStart(2, '0');
  const utcMins = String(date.getUTCMinutes()).padStart(2, '0');
  const utcStr = `${utcHours}:${utcMins} UTC`;

  const now = Date.now();
  const diffSeconds = Math.max(0, Math.floor((now - ts) / 1000));
  let relative = 'Just now';
  if (diffSeconds >= 86400) {
    const days = Math.floor(diffSeconds / 86400);
    relative = `${days}d ago`;
  } else if (diffSeconds >= 3600) {
    const hrs = Math.floor(diffSeconds / 3600);
    const mins = Math.floor((diffSeconds % 3600) / 60);
    relative = mins > 0 ? `${hrs}h ${mins}m ago` : `${hrs}h ago`;
  } else if (diffSeconds >= 60) {
    relative = `${Math.floor(diffSeconds / 60)}m ago`;
  } else if (diffSeconds > 10) {
    relative = `${diffSeconds}s ago`;
  }

  return { localTimeStr, localDateStr, fullLocalStr, utcStr, relative };
}

export function CryptoScalpLedgerTable({
  records,
  loading = false,
  onRefresh,
  onDeleteRecord,
  refreshIntervalMs = 2000,
}: CryptoScalpLedgerTableProps) {
  const [selectedTrade, setSelectedTrade] = useState<CryptoScalpExecutionRecord | null>(null);
  const [filterSymbol, setFilterSymbol] = useState<string>('ALL');
  const [filterState, setFilterState] = useState<string>('ALL');
  const [filterOutcome, setFilterOutcome] = useState<string>('ALL');
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [autoRefreshMs, setAutoRefreshMs] = useState<number>(refreshIntervalMs);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  // Bulk + datewise deletion state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [bulkConfirm, setBulkConfirm] = useState<null | {
    mode: 'selected' | 'datewise';
    ids: string[];
    beforeMs?: number;
    label: string;
  }>(null);
  const [clearBeforeDate, setClearBeforeDate] = useState<string>('');

  // Background silent millisecond refresh without full-page redraw
  useEffect(() => {
    if (autoRefreshMs <= 0 || !onRefresh) return;

    const timer = setInterval(async () => {
      try {
        await onRefresh();
      } catch (e) {
        console.error('Silent ledger background refresh failed:', e);
      }
    }, autoRefreshMs);

    return () => clearInterval(timer);
  }, [autoRefreshMs, onRefresh]);

  const handleManualRefresh = async () => {
    if (!onRefresh) return;
    setIsRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setTimeout(() => setIsRefreshing(false), 300);
    }
  };

  const filteredRecords = records.filter((r) => {
    if (filterSymbol !== 'ALL' && !r.symbol.toUpperCase().includes(filterSymbol)) {
      return false;
    }
    if (filterState !== 'ALL' && r.position_state !== filterState) {
      return false;
    }
    if (filterOutcome === 'PROFIT' && (r.position_state !== 'CLOSED' || r.net_pnl_usd <= 0)) {
      return false;
    }
    if (filterOutcome === 'LOSS' && (r.position_state !== 'CLOSED' || r.net_pnl_usd >= 0)) {
      return false;
    }
    return true;
  });

  const handleDelete = async (e: React.MouseEvent, tradeId: string) => {
    e.stopPropagation();
    if (!onDeleteRecord) return;
    if (!window.confirm('Delete this trade record from the ledger?')) return;
    setDeletingId(tradeId);
    try {
      await onDeleteRecord(tradeId);
    } finally {
      setDeletingId(null);
    }
  };

  const allFilteredSelected = filteredRecords.length > 0 && filteredRecords.every((r) => selectedIds.has(r.trade_id));

  const toggleSelect = (tradeId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(tradeId)) next.delete(tradeId);
      else next.add(tradeId);
      return next;
    });
  };

  const toggleSelectAllFiltered = () => {
    if (allFilteredSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredRecords.map((r) => r.trade_id)));
    }
  };

  const openDatewiseConfirm = () => {
    if (!clearBeforeDate) return;
    const beforeMs = new Date(`${clearBeforeDate}T00:00:00`).getTime();
    setBulkConfirm({
      mode: 'datewise',
      ids: filteredRecords.filter((r) => r.created_at_utc < beforeMs).map((r) => r.trade_id),
      beforeMs,
      label: `Clear all trades older than ${clearBeforeDate}`,
    });
  };

  const handleBulkDelete = async () => {
    if (!bulkConfirm || bulkConfirm.ids.length === 0) return;
    setBulkDeleting(true);
    try {
      if (bulkConfirm.mode === 'selected') {
        await api.bulkDeleteCryptoTrades({ trade_ids: bulkConfirm.ids });
      } else {
        const stateMap: Record<string, string | undefined> = { ALL: undefined, ACTIVE: 'ACTIVE', PARTIALLY_CLOSED: 'PARTIALLY_CLOSED', CLOSED: 'CLOSED' };
        await api.bulkDeleteCryptoTrades({
          before_ms: bulkConfirm.beforeMs,
          symbol: filterSymbol !== 'ALL' ? filterSymbol : undefined,
          position_state: stateMap[filterState],
          outcome: filterOutcome !== 'ALL' ? filterOutcome : undefined,
        });
      }
      setBulkConfirm(null);
      setSelectedIds(new Set());
      setClearBeforeDate('');
      onRefresh?.();
    } catch (err: any) {
      alert(`Bulk delete failed: ${err?.message || 'Unknown error'}`);
    } finally {
      setBulkDeleting(false);
    }
  };

  // Summary calculation for the ledger
  const closedRecords = filteredRecords.filter((r) => r.position_state === 'CLOSED');
  const totalRealizedPnl = closedRecords.reduce((acc, r) => acc + (r.net_pnl_usd || 0), 0);
  const winningTrades = closedRecords.filter((r) => (r.net_pnl_usd || 0) > 0).length;
  const losingTrades = closedRecords.filter((r) => (r.net_pnl_usd || 0) < 0).length;
  const winRate = closedRecords.length > 0 ? (winningTrades / closedRecords.length) * 100 : 0;
  const activeCount = filteredRecords.filter((r) => r.position_state === 'ACTIVE' || r.position_state === 'PARTIALLY_CLOSED').length;

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-5">
      {/* 1. Header & Live Background Sync Controls */}
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 pb-4 border-b border-slate-100">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5">
            <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <ListOrdered className="w-4 h-4 text-blue-600" />
              <span>Profit & Loss Execution Ledger</span>
            </h3>

            {/* Live Millisecond Refresh Indicator */}
            {autoRefreshMs > 0 ? (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-mono font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                <span>Live Sync ({autoRefreshMs}ms)</span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-mono font-medium bg-slate-100 text-slate-600 border border-slate-200">
                <span className="h-2 w-2 rounded-full bg-slate-400"></span>
                <span>Paused</span>
              </span>
            )}
          </div>

          <p className="text-xs text-slate-500">
            Realized fills with explicit Profit & Loss attribution. Click any order row to view its full execution dossier.
          </p>
        </div>

        {/* Sync Controls & Filter Strip */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Millisecond Rate Selector */}
          <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-lg px-2 py-1">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-[10px] text-slate-500 font-mono">Sync:</span>
            <select
              value={autoRefreshMs}
              onChange={(e) => setAutoRefreshMs(Number(e.target.value))}
              className="bg-transparent text-slate-800 text-xs font-mono font-medium focus:outline-none cursor-pointer"
            >
              <option value={1000}>1000ms (1s)</option>
              <option value={2000}>2000ms (2s)</option>
              <option value={5000}>5000ms (5s)</option>
              <option value={0}>Paused</option>
            </select>
          </div>

          {/* Manual Refresh Button */}
          <button
            type="button"
            onClick={handleManualRefresh}
            disabled={isRefreshing}
            title="Instant ledger sync"
            className="p-1.5 bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-600 rounded-lg transition-colors cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-blue-600' : ''}`} />
          </button>

          <div className="h-4 w-px bg-slate-200 hidden sm:block mx-1" />

          {/* Symbol Filter */}
          <select
            value={filterSymbol}
            onChange={(e) => setFilterSymbol(e.target.value)}
            className="bg-slate-50 border border-slate-200 text-slate-700 text-xs rounded-lg px-2.5 py-1.5 focus:ring-1 focus:ring-slate-400 focus:outline-none cursor-pointer"
          >
            <option value="ALL">All Pairs</option>
            <option value="BTC">BTCUSDT</option>
            <option value="ETH">ETHUSDT</option>
          </select>

          {/* State Filter */}
          <select
            value={filterState}
            onChange={(e) => setFilterState(e.target.value)}
            className="bg-slate-50 border border-slate-200 text-slate-700 text-xs rounded-lg px-2.5 py-1.5 focus:ring-1 focus:ring-slate-400 focus:outline-none cursor-pointer"
          >
            <option value="ALL">All States</option>
            <option value="ACTIVE">ACTIVE</option>
            <option value="PARTIALLY_CLOSED">T1 HIT (50%)</option>
            <option value="CLOSED">CLOSED</option>
          </select>

          {/* Outcome Filter */}
          <select
            value={filterOutcome}
            onChange={(e) => setFilterOutcome(e.target.value)}
            className="bg-slate-50 border border-slate-200 text-slate-700 text-xs rounded-lg px-2.5 py-1.5 focus:ring-1 focus:ring-slate-400 focus:outline-none cursor-pointer"
          >
            <option value="ALL">All Outcomes</option>
            <option value="PROFIT">Profits Only</option>
            <option value="LOSS">Losses Only</option>
          </select>
        </div>
      </div>

      {/* Bulk Actions: multi-select + datewise clear */}
      <div className="bg-white border border-slate-200 rounded-xl p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-slate-500 flex items-center gap-1">
            <Trash2 className="w-3.5 h-3.5" /> Bulk:
          </span>
          <button
            type="button"
            onClick={toggleSelectAllFiltered}
            disabled={filteredRecords.length === 0}
            className="h-7 text-[11px] px-2.5 rounded-md border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-700 disabled:opacity-50 cursor-pointer"
          >
            {allFilteredSelected ? 'Deselect view' : `Select view (${filteredRecords.length})`}
          </button>
          {selectedIds.size > 0 && (
            <>
              <span className="text-[11px] font-mono font-medium bg-slate-100 text-slate-700 px-2 py-0.5 rounded-full">
                {selectedIds.size} selected
              </span>
              <button
                type="button"
                onClick={() => setBulkConfirm({ mode: 'selected', ids: Array.from(selectedIds), label: `Delete ${selectedIds.size} selected trade${selectedIds.size === 1 ? '' : 's'}` })}
                className="h-7 text-[11px] px-2.5 rounded-md bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-50 cursor-pointer inline-flex items-center gap-1"
              >
                <Trash2 className="w-3 h-3" /> Delete selected
              </button>
              <button
                type="button"
                onClick={() => setSelectedIds(new Set())}
                className="h-7 text-[11px] px-2.5 rounded-md border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 cursor-pointer"
              >
                Clear selection
              </button>
            </>
          )}
          <div className="h-4 w-px bg-slate-200 hidden sm:block mx-1" />
          <input
            type="date"
            value={clearBeforeDate}
            onChange={(e) => setClearBeforeDate(e.target.value)}
            className="h-7 rounded-md border border-slate-200 px-2 text-[11px] font-mono bg-white focus:outline-none focus:ring-1 focus:ring-slate-400"
            title="Delete everything created before this date"
          />
          <button
            type="button"
            onClick={openDatewiseConfirm}
            disabled={!clearBeforeDate}
            className="h-7 text-[11px] px-2.5 rounded-md border border-rose-200 bg-white hover:bg-rose-50 text-rose-700 disabled:opacity-50 cursor-pointer inline-flex items-center gap-1"
          >
            <Trash2 className="w-3 h-3" /> Clear older than date
          </button>
        </div>
      </div>

      {/* 2. Real-time PnL Summary Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3">
          <span className="text-[11px] font-mono text-slate-500 uppercase block">Realized Net P&L</span>
          <span
            className={`text-base font-bold font-mono mt-0.5 block ${
              totalRealizedPnl > 0 ? 'text-emerald-600' : totalRealizedPnl < 0 ? 'text-rose-600' : 'text-slate-800'
            }`}
          >
            {totalRealizedPnl > 0
              ? `+$${totalRealizedPnl.toFixed(2)} Profit`
              : totalRealizedPnl < 0
              ? `-$${Math.abs(totalRealizedPnl).toFixed(2)} Loss`
              : '$0.00 Breakeven'}
          </span>
          <span className="text-[10px] text-slate-400">Net of taker fees & slippage</span>
        </div>

        <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3">
          <span className="text-[11px] font-mono text-slate-500 uppercase block">Win Rate</span>
          <span className="text-base font-bold font-mono text-slate-900 mt-0.5 block">
            {closedRecords.length > 0 ? `${winRate.toFixed(1)}%` : '—'}
          </span>
          <span className="text-[10px] text-slate-400 font-mono">
            {winningTrades} wins / {losingTrades} losses ({closedRecords.length} closed)
          </span>
        </div>

        <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3">
          <span className="text-[11px] font-mono text-slate-500 uppercase block">Active Trades</span>
          <span className="text-base font-bold font-mono text-blue-600 mt-0.5 block">
            {activeCount} Open
          </span>
          <span className="text-[10px] text-slate-400">Mark-to-market live</span>
        </div>

        <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3">
          <span className="text-[11px] font-mono text-slate-500 uppercase block">Total Orders</span>
          <span className="text-base font-bold font-mono text-slate-900 mt-0.5 block">
            {filteredRecords.length} Fills
          </span>
          <span className="text-[10px] text-slate-400">Logged in FSM ledger</span>
        </div>
      </div>

      {/* 3. Streamlined Minimal Table */}
      {filteredRecords.length === 0 ? (
        <div className="p-10 text-center border border-dashed border-slate-200 rounded-xl text-slate-500 text-xs bg-slate-50/50">
          {loading ? 'Reconciling execution records...' : 'No execution records matching filter criteria.'}
        </div>
      ) : (
        <div className="overflow-x-auto border border-slate-200 rounded-xl">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold">
                <th className="py-2.5 px-2 w-8 text-center">
                  <input
                    type="checkbox"
                    checked={allFilteredSelected}
                    onChange={toggleSelectAllFiltered}
                    className="h-3.5 w-3.5 accent-slate-600 cursor-pointer"
                    title="Select all in current view"
                  />
                </th>
                <th className="py-2.5 px-3.5">Execution Time</th>
                <th className="py-2.5 px-3">Asset & Side</th>
                <th className="py-2.5 px-3">Strategy</th>
                <th className="py-2.5 px-3 text-right">Fills (Entry &rarr; Exit)</th>
                <th className="py-2.5 px-3.5 text-right">Realized P&L</th>
                <th className="py-2.5 px-3 text-center">Exit Reason</th>
                <th className="py-2.5 px-3 text-center">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredRecords.map((trade) => {
                const isLong = trade.direction === 'LONG';
                const isClosed = trade.position_state === 'CLOSED';
                const isPartial = trade.position_state === 'PARTIALLY_CLOSED';
                const isProfit = trade.net_pnl_usd > 0;
                const isLoss = trade.net_pnl_usd < 0;
                const { localTimeStr, localDateStr, relative: relativeTime } = formatLedgerDate(trade.created_at_utc);
                const exitDetail = formatDetailedExitReason(trade);

                 return (
                   <tr
                     key={trade.trade_id}
                     onClick={() => setSelectedTrade(trade)}
                     className="hover:bg-blue-50/40 cursor-pointer transition-colors text-slate-800 group"
                   >
                     <td className="py-2.5 px-2 text-center" onClick={(e) => e.stopPropagation()}>
                       <input
                         type="checkbox"
                         checked={selectedIds.has(trade.trade_id)}
                         onChange={() => toggleSelect(trade.trade_id)}
                         className="h-3.5 w-3.5 accent-slate-600 cursor-pointer"
                       />
                     </td>
                     {/* 1. Time Column */}
                     <td className="py-2.5 px-3.5 font-mono whitespace-nowrap">
                      <div className="flex items-center gap-1.5 font-semibold text-slate-800">
                        <Clock className="w-3 h-3 text-slate-400 group-hover:text-blue-600 transition-colors" />
                        <span>{localTimeStr}</span>
                      </div>
                      <span className="text-[10px] text-slate-400 block mt-0.5 font-mono">
                        {localDateStr} · {relativeTime}
                      </span>
                    </td>

                    {/* 2. Asset & Side */}
                    <td className="py-2.5 px-3 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-slate-900 font-mono">
                          {trade.symbol.replace('USDT', '')}
                        </span>
                        <span
                          className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-[10px] font-bold font-mono ${
                            isLong
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : 'bg-rose-50 text-rose-700 border border-rose-200'
                          }`}
                        >
                          {isLong ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                          {trade.direction}
                        </span>
                      </div>
                    </td>

                    {/* 3. Strategy & State */}
                    <td className="py-2.5 px-3 whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        <span className="text-slate-700 font-medium">
                          {trade.strategy_name || trade.strategy}
                        </span>
                        {isPartial && (
                          <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                            T1
                          </span>
                        )}
                      </div>
                    </td>

                    {/* 4. Entry -> Exit Fills */}
                    <td className="py-2.5 px-3 text-right font-mono whitespace-nowrap">
                      <span className="text-slate-800 font-medium">
                        ${trade.entry_fill_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                      <span className="text-slate-400 mx-1.5">&rarr;</span>
                      {trade.exit_price ? (
                        <span className="text-slate-900 font-bold">
                          ${trade.exit_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </span>
                      ) : (
                        <span className="text-blue-600 font-medium text-[11px]">Tracking</span>
                      )}
                    </td>

                    {/* 5. Realized P&L in Written Profit & Loss format */}
                    <td className="py-2.5 px-3.5 text-right whitespace-nowrap">
                      {isClosed ? (
                        <div className="inline-flex items-center gap-2">
                          <span
                            className={`px-2.5 py-1 rounded-full text-xs font-bold font-mono inline-flex items-center gap-1 shadow-2xs ${
                              isProfit
                                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                : isLoss
                                ? 'bg-rose-50 text-rose-700 border border-rose-200'
                                : 'bg-slate-100 text-slate-700 border border-slate-200'
                            }`}
                          >
                            {isProfit
                              ? `+$${trade.net_pnl_usd.toFixed(2)} Profit`
                              : isLoss
                              ? `-$${Math.abs(trade.net_pnl_usd).toFixed(2)} Loss`
                              : '$0.00 Breakeven'}
                          </span>
                          <span
                            className={`text-[11px] font-mono font-bold ${
                              trade.r_multiple > 0
                                ? 'text-emerald-600'
                                : trade.r_multiple < 0
                                ? 'text-rose-600'
                                : 'text-slate-400'
                            }`}
                          >
                            {trade.r_multiple >= 0 ? `+${trade.r_multiple.toFixed(2)}R` : `${trade.r_multiple.toFixed(2)}R`}
                          </span>
                        </div>
                      ) : isPartial ? (
                        <div className="inline-flex items-center gap-1.5">
                          <span className="px-2.5 py-1 rounded-full text-xs font-bold font-mono bg-amber-50 text-amber-700 border border-amber-200">
                            50% Booked
                          </span>
                          <span className="text-[11px] font-mono font-bold text-amber-600">+0.75R</span>
                        </div>
                      ) : (
                        <span className="px-2.5 py-1 rounded-full text-xs font-semibold font-mono bg-blue-50 text-blue-700 border border-blue-200">
                          Active MTM
                        </span>
                      )}
                    </td>

                    {/* 6. Exit Reason Column */}
                    <td className="py-2.5 px-3 text-center whitespace-nowrap">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium border ${exitDetail.badgeColor}`}
                        title={exitDetail.description}
                      >
                        <span>{exitDetail.title.split('(')[0].trim()}</span>
                      </span>
                    </td>

                    {/* 7. Action Column */}
                    <td className="py-2.5 px-3 text-center whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => setSelectedTrade(trade)}
                          title="View complete trade execution details"
                          className="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium bg-slate-100 text-slate-700 hover:bg-blue-50 hover:text-blue-700 hover:border-blue-200 border border-slate-200 transition-all cursor-pointer"
                        >
                          <Eye className="w-3 h-3" />
                          <span>View</span>
                        </button>

                        <button
                          type="button"
                          onClick={(e) => handleDelete(e, trade.trade_id)}
                          disabled={deletingId === trade.trade_id}
                          title="Delete this execution record"
                          className="p-1 rounded-md text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-all cursor-pointer border border-transparent hover:border-rose-200 disabled:opacity-50"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Bulk delete confirmation dialog */}
      {bulkConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-md w-full mx-4 space-y-4">
            <h3 className="text-base font-bold text-slate-900">Confirm Bulk Delete</h3>
            <p className="text-sm text-slate-600">
              {bulkConfirm.label}
            </p>
            <p className="text-xs text-slate-500">
              This will permanently remove {bulkConfirm.ids.length} trade record{bulkConfirm.ids.length === 1 ? '' : 's'} from the ledger and database.
            </p>
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setBulkConfirm(null)}
                disabled={bulkDeleting}
                className="px-4 py-2 text-sm rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 disabled:opacity-50 cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleBulkDelete}
                disabled={bulkDeleting}
                className="px-4 py-2 text-sm rounded-lg bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-50 cursor-pointer inline-flex items-center gap-1.5"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {bulkDeleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 4. Executed Order Detail Modal */}
      <CryptoTradeDetailModal
        trade={selectedTrade}
        isOpen={!!selectedTrade}
        onClose={() => setSelectedTrade(null)}
        onDeleteRecord={onDeleteRecord}
      />
    </div>
  );
}
