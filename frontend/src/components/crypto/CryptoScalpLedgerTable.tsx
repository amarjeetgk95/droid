'use client';

import React, { useState } from 'react';
import {
  TrendingUp,
  TrendingDown,
  ChevronDown,
  ChevronUp,
  Clock,
  ListOrdered,
  FileText,
  DollarSign,
  CheckCircle2,
  Percent,
} from 'lucide-react';
import {
  CryptoScalpExecutionRecord,
} from '@/lib/types';

interface CryptoScalpLedgerTableProps {
  records: CryptoScalpExecutionRecord[];
  loading?: boolean;
  onRefresh?: () => void;
}

export function CryptoScalpLedgerTable({
  records,
  loading = false,
  onRefresh,
}: CryptoScalpLedgerTableProps) {
  const [expandedTradeId, setExpandedTradeId] = useState<string | null>(null);
  const [filterSymbol, setFilterSymbol] = useState<string>('ALL');
  const [filterState, setFilterState] = useState<string>('ALL');

  const filteredRecords = records.filter((r) => {
    if (filterSymbol !== 'ALL' && !r.symbol.toUpperCase().includes(filterSymbol)) {
      return false;
    }
    if (filterState !== 'ALL' && r.position_state !== filterState) {
      return false;
    }
    return true;
  });

  const toggleExpand = (tradeId: string) => {
    setExpandedTradeId((prev) => (prev === tradeId ? null : tradeId));
  };

  // Quick summary calculation for the ledger
  const closedRecords = filteredRecords.filter((r) => r.position_state === 'CLOSED');
  const totalRealizedPnl = closedRecords.reduce((acc, r) => acc + (r.net_pnl_usd || 0), 0);
  const winningTrades = closedRecords.filter((r) => (r.net_pnl_usd || 0) > 0).length;
  const winRate = closedRecords.length > 0 ? (winningTrades / closedRecords.length) * 100 : 0;
  const activeCount = filteredRecords.filter((r) => r.position_state === 'ACTIVE' || r.position_state === 'PARTIALLY_CLOSED').length;

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-5">
      {/* 1. Header & Filters */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
        <div className="space-y-0.5">
          <h3 className="text-base font-semibold text-slate-900 flex items-center gap-2">
            <ListOrdered className="w-4 h-4 text-slate-700" />
            <span>Profit & Loss Execution Ledger</span>
          </h3>
          <p className="text-xs text-slate-500">
            Realized fills, slippage drag, taker fees, and chronological audit ledger.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
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
            <option value="PARTIALLY_CLOSED">PARTIALLY_CLOSED (T1)</option>
            <option value="CLOSED">CLOSED</option>
          </select>
        </div>
      </div>

      {/* 2. Real-time PnL Summary Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3">
          <span className="text-[11px] font-mono text-slate-500 uppercase block">Realized Net P&L</span>
          <span
            className={`text-base font-bold font-mono mt-0.5 block ${
              totalRealizedPnl >= 0 ? 'text-emerald-600' : 'text-rose-600'
            }`}
          >
            {totalRealizedPnl >= 0 ? `+$${totalRealizedPnl.toFixed(2)}` : `-$${Math.abs(totalRealizedPnl).toFixed(2)}`}
          </span>
          <span className="text-[10px] text-slate-400">Net of fees & slippage</span>
        </div>

        <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3">
          <span className="text-[11px] font-mono text-slate-500 uppercase block">Win Rate</span>
          <span className="text-base font-bold font-mono text-slate-900 mt-0.5 block">
            {closedRecords.length > 0 ? `${winRate.toFixed(1)}%` : '—'}
          </span>
          <span className="text-[10px] text-slate-400">
            {winningTrades} wins / {closedRecords.length} completed
          </span>
        </div>

        <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3">
          <span className="text-[11px] font-mono text-slate-500 uppercase block">Active Trades</span>
          <span className="text-base font-bold font-mono text-blue-600 mt-0.5 block">
            {activeCount} Active
          </span>
          <span className="text-[10px] text-slate-400">Currently open positions</span>
        </div>

        <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3">
          <span className="text-[11px] font-mono text-slate-500 uppercase block">Total Executions</span>
          <span className="text-base font-bold font-mono text-slate-900 mt-0.5 block">
            {filteredRecords.length} Fills
          </span>
          <span className="text-[10px] text-slate-400">Logged in FSM ledger</span>
        </div>
      </div>

      {/* 3. Detailed Ledger Table */}
      {filteredRecords.length === 0 ? (
        <div className="p-10 text-center border border-dashed border-slate-200 rounded-xl text-slate-500 text-xs bg-slate-50/50">
          {loading ? 'Reconciling execution records...' : 'No execution records matching filter criteria.'}
        </div>
      ) : (
        <div className="overflow-x-auto border border-slate-200 rounded-xl">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold">
                <th className="py-2.5 px-3">Trade ID</th>
                <th className="py-2.5 px-3">Asset</th>
                <th className="py-2.5 px-3">Direction</th>
                <th className="py-2.5 px-3">Strategy</th>
                <th className="py-2.5 px-3">State</th>
                <th className="py-2.5 px-3 text-right">Entry Fill</th>
                <th className="py-2.5 px-3 text-right">Exit Price</th>
                <th className="py-2.5 px-3 text-center">Exit Reason</th>
                <th className="py-2.5 px-3 text-right">Realized R</th>
                <th className="py-2.5 px-3 text-right">Net P&L ($)</th>
                <th className="py-2.5 px-3 text-right">Duration</th>
                <th className="py-2.5 px-2 text-center">Audit</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredRecords.map((trade) => {
                const isLong = trade.direction === 'LONG';
                const isExpanded = expandedTradeId === trade.trade_id;
                const isProfitable = trade.net_pnl_usd > 0;

                return (
                  <React.Fragment key={trade.trade_id}>
                    <tr
                      onClick={() => toggleExpand(trade.trade_id)}
                      className="hover:bg-slate-50/80 cursor-pointer transition-colors text-slate-800"
                    >
                      <td className="py-2.5 px-3 font-mono font-medium text-slate-700">
                        #{trade.trade_id.slice(-6).toUpperCase()}
                      </td>

                      <td className="py-2.5 px-3 font-semibold text-slate-900">
                        {trade.symbol.replace('USDT', '')}
                      </td>

                      <td className="py-2.5 px-3">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold font-mono ${
                            isLong
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : 'bg-rose-50 text-rose-700 border border-rose-200'
                          }`}
                        >
                          {isLong ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                          {trade.direction}
                        </span>
                      </td>

                      <td className="py-2.5 px-3 text-slate-600 font-medium">
                        {trade.strategy_name || trade.strategy}
                      </td>

                      <td className="py-2.5 px-3">
                        {trade.position_state === 'ACTIVE' && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
                            ACTIVE
                          </span>
                        )}
                        {trade.position_state === 'PARTIALLY_CLOSED' && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                            T1 HIT (50%)
                          </span>
                        )}
                        {trade.position_state === 'CLOSED' && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 text-slate-700 border border-slate-200">
                            CLOSED
                          </span>
                        )}
                      </td>

                      <td className="py-2.5 px-3 text-right font-mono text-slate-800">
                        ${trade.entry_fill_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </td>

                      <td className="py-2.5 px-3 text-right font-mono text-slate-800">
                        {trade.exit_price ? (
                          `$${trade.exit_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>

                      <td className="py-2.5 px-3 text-center">
                        {trade.exit_reason ? (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-700 border border-slate-200">
                            {trade.exit_reason}
                          </span>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>

                      <td className={`py-2.5 px-3 text-right font-mono font-bold ${trade.r_multiple >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                        {trade.position_state === 'CLOSED' ? (
                          trade.r_multiple > 0 ? `+${trade.r_multiple.toFixed(2)}R` : `${trade.r_multiple.toFixed(2)}R`
                        ) : trade.position_state === 'PARTIALLY_CLOSED' ? (
                          <span className="text-amber-600">+0.75R (T1)</span>
                        ) : (
                          <span className="text-slate-400">0.0R</span>
                        )}
                      </td>

                      <td className={`py-2.5 px-3 text-right font-bold font-mono ${isProfitable ? 'text-emerald-600' : trade.net_pnl_usd < 0 ? 'text-rose-600' : 'text-slate-600'}`}>
                        {trade.position_state === 'CLOSED' ? (
                          trade.net_pnl_usd >= 0 ? `+$${trade.net_pnl_usd.toFixed(2)}` : `-$${Math.abs(trade.net_pnl_usd).toFixed(2)}`
                        ) : (
                          <span className="text-blue-600 font-semibold">Active</span>
                        )}
                      </td>

                      <td className="py-2.5 px-3 text-right text-slate-500 font-mono">
                        {trade.duration_str}
                      </td>

                      <td className="py-2.5 px-2 text-center text-slate-400">
                        {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                      </td>
                    </tr>

                    {/* Expandable Audit Trail Row */}
                    {isExpanded && (
                      <tr className="bg-slate-50/80 border-b border-slate-200">
                        <td colSpan={12} className="p-4 space-y-3">
                          <div className="flex flex-wrap items-center justify-between text-xs text-slate-600 border-b border-slate-200 pb-2 gap-2">
                            <span className="font-semibold text-slate-800 flex items-center gap-1.5">
                              <FileText className="w-3.5 h-3.5 text-blue-600" />
                              <span>Execution Audit Trail ({trade.events?.length || 0} events)</span>
                            </span>
                            <div className="flex items-center gap-4 text-[11px] font-mono">
                              <span>Theoretical: <strong>{trade.theoretical_r}R</strong></span>
                              <span>Realized: <strong>{trade.r_multiple}R</strong></span>
                              <span>Drag: <strong className="text-amber-600">-{trade.execution_drag_r}R</strong></span>
                              <span>Fees: <strong>${trade.fees_usd.toFixed(2)}</strong></span>
                              <span>Slippage: <strong>${trade.slippage_usd.toFixed(2)}</strong></span>
                            </div>
                          </div>

                          {/* Event Timeline */}
                          <div className="space-y-2">
                            {trade.events && trade.events.length > 0 ? (
                              trade.events.map((ev, idx) => (
                                <div
                                  key={ev.event_id || idx}
                                  className="flex flex-wrap items-center justify-between p-2.5 bg-white rounded-lg border border-slate-200 text-xs shadow-2xs gap-2"
                                >
                                  <div className="flex items-center gap-3">
                                    <span className="font-mono text-[11px] text-slate-500">
                                      {new Date(ev.timestamp_ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                                    </span>
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
                                      {ev.event_type}
                                    </span>
                                    <span className="text-slate-800">
                                      Fill: <strong className="font-mono">${ev.fill_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}</strong>
                                    </span>
                                    <span className="text-slate-500">
                                      Qty: <strong className="font-mono">{ev.quantity}</strong>
                                    </span>
                                  </div>

                                  <div className="flex items-center gap-4">
                                    <span className="text-slate-500 text-[11px]">
                                      Fee: ${ev.fee_usd.toFixed(3)} | Slip: ${ev.slippage_usd.toFixed(3)}
                                    </span>
                                    <span
                                      className={`font-bold font-mono text-xs ${
                                        ev.net_pnl_usd > 0 ? 'text-emerald-600' : ev.net_pnl_usd < 0 ? 'text-rose-600' : 'text-slate-600'
                                      }`}
                                    >
                                      {ev.net_pnl_usd !== 0 ? (ev.net_pnl_usd > 0 ? `+$${ev.net_pnl_usd.toFixed(2)}` : `-$${Math.abs(ev.net_pnl_usd).toFixed(2)}`) : '$0.00'}
                                    </span>
                                    <span className="text-[10px] text-slate-400 font-mono">
                                      {ev.state_before} &rarr; {ev.state_after}
                                    </span>
                                  </div>
                                </div>
                              ))
                            ) : (
                              <div className="text-slate-400 text-xs italic">No granular events logged for this trade.</div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
