'use client';

import React, { useState } from 'react';
import {
  TrendingUp,
  TrendingDown,
  ChevronDown,
  ChevronUp,
  Clock,
  CheckCircle2,
  AlertCircle,
  Zap,
  ListOrdered,
  FileText,
} from 'lucide-react';
import {
  CryptoScalpExecutionRecord,
  CryptoScalpPositionState,
  CryptoScalpExitEventType,
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

  return (
    <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 space-y-4">
      {/* Header & Filter Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="space-y-0.5">
          <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <ListOrdered className="w-4 h-4 text-cyan-400" />
            <span>Paper Execution Ledger & Event Timeline</span>
          </h3>
          <p className="text-xs text-slate-400">
            Immutable audit events with half-spread fill simulation, adverse slippage, and taker fees.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Symbol Filter */}
          <select
            value={filterSymbol}
            onChange={(e) => setFilterSymbol(e.target.value)}
            className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded-lg px-2.5 py-1.5 focus:ring-1 focus:ring-cyan-400 focus:outline-none"
          >
            <option value="ALL">All Pairs</option>
            <option value="BTC">BTCUSDT</option>
            <option value="ETH">ETHUSDT</option>
          </select>

          {/* State Filter */}
          <select
            value={filterState}
            onChange={(e) => setFilterState(e.target.value)}
            className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded-lg px-2.5 py-1.5 focus:ring-1 focus:ring-cyan-400 focus:outline-none"
          >
            <option value="ALL">All States</option>
            <option value="ACTIVE">ACTIVE</option>
            <option value="PARTIALLY_CLOSED">PARTIALLY_CLOSED (T1)</option>
            <option value="CLOSED">CLOSED</option>
          </select>
        </div>
      </div>

      {/* Table */}
      {filteredRecords.length === 0 ? (
        <div className="p-8 text-center border border-dashed border-slate-800 rounded-lg text-slate-500 text-xs">
          {loading ? 'Loading execution records...' : 'No execution records matching filter criteria.'}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="py-2.5 px-3 font-medium">Trade / Time</th>
                <th className="py-2.5 px-3 font-medium">Asset & Dir</th>
                <th className="py-2.5 px-3 font-medium">Strategy</th>
                <th className="py-2.5 px-3 font-medium">State</th>
                <th className="py-2.5 px-3 font-medium text-right">Entry Fill</th>
                <th className="py-2.5 px-3 font-medium text-right">Exit Fill</th>
                <th className="py-2.5 px-3 font-medium text-center">Exit Reason</th>
                <th className="py-2.5 px-3 font-medium text-right">Realized R</th>
                <th className="py-2.5 px-3 font-medium text-right">Net P&L</th>
                <th className="py-2.5 px-3 font-medium text-right">Duration</th>
                <th className="py-2.5 px-2 text-center w-8"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {filteredRecords.map((trade) => {
                const isExpanded = expandedTradeId === trade.trade_id;
                const isLong = trade.direction === 'LONG';
                const isProfitable = trade.net_pnl_usd >= 0;
                const createdDate = new Date(trade.created_at_utc);
                const timeStr = createdDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

                return (
                  <React.Fragment key={trade.trade_id}>
                    <tr
                      onClick={() => toggleExpand(trade.trade_id)}
                      className="hover:bg-slate-800/40 cursor-pointer transition-colors"
                    >
                      <td className="py-2.5 px-3">
                        <div className="font-mono text-[11px] text-slate-300 truncate max-w-[120px]" title={trade.trade_id}>
                          {trade.trade_id.replace('trade_SCALP-', '')}
                        </div>
                        <div className="text-[10px] text-slate-500">{timeStr}</div>
                      </td>

                      <td className="py-2.5 px-3">
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-slate-200">{trade.symbol}</span>
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                              isLong
                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                            }`}
                          >
                            {trade.direction}
                          </span>
                        </div>
                      </td>

                      <td className="py-2.5 px-3">
                        <span className="text-slate-300 font-medium">{trade.strategy_name}</span>
                      </td>

                      <td className="py-2.5 px-3">
                        {trade.position_state === 'ACTIVE' && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                            ACTIVE
                          </span>
                        )}
                        {trade.position_state === 'PARTIALLY_CLOSED' && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-500/10 text-amber-300 border border-amber-500/20">
                            T1 HIT (50%)
                          </span>
                        )}
                        {trade.position_state === 'CLOSED' && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-700/50 text-slate-300 border border-slate-600">
                            CLOSED
                          </span>
                        )}
                      </td>

                      <td className="py-2.5 px-3 text-right font-mono text-slate-300">
                        ${trade.entry_fill_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </td>

                      <td className="py-2.5 px-3 text-right font-mono text-slate-300">
                        {trade.exit_price ? (
                          `$${trade.exit_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>

                      <td className="py-2.5 px-3 text-center">
                        {trade.exit_reason ? (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
                            {trade.exit_reason}
                          </span>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>

                      <td className={`py-2.5 px-3 text-right font-mono font-bold ${trade.r_multiple >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {trade.position_state === 'CLOSED' ? (
                          trade.r_multiple > 0 ? `+${trade.r_multiple.toFixed(2)}R` : `${trade.r_multiple.toFixed(2)}R`
                        ) : trade.position_state === 'PARTIALLY_CLOSED' ? (
                          <span className="text-amber-300">+0.75R (T1)</span>
                        ) : (
                          <span className="text-slate-500">0.0R</span>
                        )}
                      </td>

                      <td className={`py-2.5 px-3 text-right font-semibold ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {trade.position_state === 'CLOSED' ? (
                          trade.net_pnl_usd >= 0 ? `+$${trade.net_pnl_usd.toFixed(2)}` : `-$${Math.abs(trade.net_pnl_usd).toFixed(2)}`
                        ) : (
                          <span className="text-slate-500">Active</span>
                        )}
                      </td>

                      <td className="py-2.5 px-3 text-right text-slate-400 font-mono">
                        {trade.duration_str}
                      </td>

                      <td className="py-2.5 px-2 text-center text-slate-400">
                        {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                      </td>
                    </tr>

                    {/* Expandable Audit Trail Row */}
                    {isExpanded && (
                      <tr className="bg-slate-950/60 border-b border-slate-800">
                        <td colSpan={11} className="p-4 space-y-3">
                          <div className="flex items-center justify-between text-xs text-slate-400 border-b border-slate-800/80 pb-2">
                            <span className="font-semibold text-slate-300 flex items-center gap-1.5">
                              <FileText className="w-3.5 h-3.5 text-cyan-400" />
                              <span>Chronological Execution Audit Events ({trade.events?.length || 0})</span>
                            </span>
                            <div className="flex items-center gap-4 text-[11px]">
                              <span>Theoretical R: <strong className="text-slate-200">{trade.theoretical_r}R</strong></span>
                              <span>Realized R: <strong className="text-slate-200">{trade.r_multiple}R</strong></span>
                              <span>Drag: <strong className="text-amber-400">-{trade.execution_drag_r}R</strong></span>
                              <span>Fees: <strong className="text-slate-200">${trade.fees_usd.toFixed(2)}</strong></span>
                              <span>Slippage: <strong className="text-slate-200">${trade.slippage_usd.toFixed(2)}</strong></span>
                            </div>
                          </div>

                          {/* Event Timeline */}
                          <div className="space-y-2">
                            {trade.events && trade.events.length > 0 ? (
                              trade.events.map((ev, idx) => (
                                <div
                                  key={ev.event_id || idx}
                                  className="flex items-center justify-between p-2.5 bg-slate-900/50 rounded-lg border border-slate-800 text-xs"
                                >
                                  <div className="flex items-center gap-3">
                                    <span className="font-mono text-[11px] text-slate-500">
                                      {new Date(ev.timestamp_ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                                    </span>
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-800 text-cyan-300 border border-slate-700">
                                      {ev.event_type}
                                    </span>
                                    <span className="text-slate-300">
                                      Fill: <strong className="font-mono">${ev.fill_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}</strong>
                                    </span>
                                    <span className="text-slate-400">
                                      Qty: <strong className="font-mono">{ev.quantity}</strong>
                                    </span>
                                  </div>

                                  <div className="flex items-center gap-4">
                                    <span className="text-slate-400 text-[11px]">
                                      Fee: ${ev.fee_usd.toFixed(3)} | Slip: ${ev.slippage_usd.toFixed(3)}
                                    </span>
                                    <span
                                      className={`font-semibold text-xs ${
                                        ev.net_pnl_usd >= 0 ? 'text-emerald-400' : 'text-rose-400'
                                      }`}
                                    >
                                      {ev.net_pnl_usd !== 0 ? (ev.net_pnl_usd > 0 ? `+$${ev.net_pnl_usd.toFixed(2)}` : `-$${Math.abs(ev.net_pnl_usd).toFixed(2)}`) : '$0.00'}
                                    </span>
                                    <span className="text-[10px] text-slate-500 font-mono">
                                      {ev.state_before} &rarr; {ev.state_after}
                                    </span>
                                  </div>
                                </div>
                              ))
                            ) : (
                              <div className="text-slate-500 text-xs italic">No granular events logged for this trade.</div>
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
