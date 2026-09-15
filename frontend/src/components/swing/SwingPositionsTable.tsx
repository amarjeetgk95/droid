'use client';

import { useState } from 'react';
import { Shield, Clock, TrendingUp, XCircle, ArrowUpRight, ArrowDownRight, AlertTriangle, Layers, Zap } from 'lucide-react';
import type { SwingPositionDTO } from '@/lib/api/swing';

export type SwingPositionsTableProps = {
  positions: SwingPositionDTO[];
  closedPositions?: SwingPositionDTO[];
  onExitPosition?: (positionId: string, exitPremium: number, exitReason?: string) => Promise<any>;
};

const EXIT_REASONS = [
  { value: 'MANUAL_EXIT', label: 'Manual Exit' },
  { value: 'TARGET_1', label: 'Target 1 Hit (+1.5R)' },
  { value: 'TARGET_2', label: 'Target 2 Hit (+3.0R)' },
  { value: 'OPTION_STOP', label: 'Option Premium Stop Hit' },
  { value: 'UNDERLYING_STOP', label: 'Underlying Thesis Invalidation' },
  { value: 'THETA_DECAY', label: 'Excessive Theta Drag' },
  { value: 'EXPIRY_RISK', label: 'Expiry Proximity Risk (DTE <= 3)' },
  { value: 'TRAILING_STOP', label: 'Trailing Stop Breached' },
  { value: 'TIME_STOP', label: 'Mandatory 15:15 IST Time Stop' },
];

export function SwingPositionsTable({
  positions,
  closedPositions = [],
  onExitPosition,
}: SwingPositionsTableProps) {
  const [exitingId, setExitingId] = useState<string | null>(null);
  const [viewTab, setViewTab] = useState<'open' | 'closed'>('open');
  const [exitModalPos, setExitModalPos] = useState<SwingPositionDTO | null>(null);
  const [selectedExitReason, setSelectedExitReason] = useState<string>('MANUAL_EXIT');
  const [exitPremiumInput, setExitPremiumInput] = useState<number>(0);

  const openExitModal = (pos: SwingPositionDTO) => {
    setExitModalPos(pos);
    setExitPremiumInput(pos.current_premium);
    setSelectedExitReason('MANUAL_EXIT');
  };

  const handleConfirmExit = async () => {
    if (!exitModalPos || !onExitPosition) return;
    setExitingId(exitModalPos.position_id);
    try {
      await onExitPosition(exitModalPos.position_id, exitPremiumInput, selectedExitReason);
      setExitModalPos(null);
    } catch {
      // Handled by parent
    } finally {
      setExitingId(null);
    }
  };

  const getTrailingBadge = (method: string) => {
    switch (method) {
      case 'BREAK_EVEN':
        return <span className="px-1.5 py-0.5 text-[9px] font-semibold rounded bg-sky-500/10 text-sky-400 border border-sky-500/20">BREAK-EVEN</span>;
      case 'TRAILING_PREMIUM':
        return <span className="px-1.5 py-0.5 text-[9px] font-semibold rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">PEAK TRAIL</span>;
      case 'TIME_DECAY':
        return <span className="px-1.5 py-0.5 text-[9px] font-semibold rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">TIME DECAY STOP</span>;
      case 'TIME_STOP':
        return <span className="px-1.5 py-0.5 text-[9px] font-semibold rounded bg-rose-500/10 text-rose-400 border border-rose-500/20">15:15 TIME STOP</span>;
      default:
        return <span className="px-1.5 py-0.5 text-[9px] font-semibold rounded bg-muted text-muted-foreground border border-border">INITIAL STOP</span>;
    }
  };

  return (
    <>
      <div className="rounded-xl border border-border bg-card text-card-foreground shadow-xs overflow-hidden">
        {/* Table Sub-header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-border bg-muted/20">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setViewTab('open')}
              className={`px-3 py-1 text-xs font-semibold rounded-lg transition-colors ${
                viewTab === 'open'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted'
              }`}
            >
              Active Positions ({positions.length})
            </button>
            <button
              onClick={() => setViewTab('closed')}
              className={`px-3 py-1 text-xs font-semibold rounded-lg transition-colors ${
                viewTab === 'closed'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted'
              }`}
            >
              Closed History ({closedPositions.length})
            </button>
          </div>
          <span className="text-xs text-muted-foreground">
            {viewTab === 'open' ? 'Carried overnight multi-day positions with dual-layer stops' : 'Realized swing outcomes'}
          </span>
        </div>

        {/* Table Content */}
        <div className="overflow-x-auto">
          {viewTab === 'open' ? (
            positions.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground text-xs gap-2">
                <Shield className="w-8 h-8 opacity-40 text-muted-foreground" />
                <span>No open swing options positions in portfolio.</span>
                <span className="text-[11px] opacity-70">Enter setups from the Setups & Radar tab.</span>
              </div>
            ) : (
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-border/60 bg-muted/40 text-muted-foreground font-medium text-[11px]">
                    <th className="py-2.5 px-4">Contract / Strike</th>
                    <th className="py-2.5 px-3">DTE & Days</th>
                    <th className="py-2.5 px-3">Sizing & Entry</th>
                    <th className="py-2.5 px-3">Option LTP</th>
                    <th className="py-2.5 px-3">Dual-Layer Stops</th>
                    <th className="py-2.5 px-3">Targets (1.5R / 3R)</th>
                    <th className="py-2.5 px-3">Greeks at Entry</th>
                    <th className="py-2.5 px-3 text-right">P&L / Return</th>
                    <th className="py-2.5 px-4 text-center">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {positions.map((pos) => {
                    const isProfit = pos.unrealized_pnl >= 0;
                    const delta = pos.greeks_at_entry?.delta ?? 0;
                    const thetaDay = pos.greeks_at_entry?.theta_day ?? 0;
                    const isCall = pos.option_type === 'CE';
                    const isIntraday = pos.horizon === 'INTRADAY' || pos.strategy?.startsWith('INTRADAY_');

                    return (
                      <tr key={pos.position_id} className="hover:bg-muted/30 transition-colors">
                        <td className="py-3 px-4 font-semibold text-foreground">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span>{pos.underlying}</span>
                            <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded ${
                              isCall ? 'bg-emerald-500/10 text-emerald-500' : 'bg-rose-500/10 text-rose-500'
                            }`}>
                              {pos.strike} {pos.option_type}
                            </span>
                            {isIntraday ? (
                              <span className="px-1.5 py-0.5 text-[9px] font-bold rounded bg-amber-500/15 text-amber-400 border border-amber-500/30 flex items-center gap-0.5">
                                <Zap className="w-2.5 h-2.5" /> INTRADAY
                              </span>
                            ) : (
                              <span className="px-1.5 py-0.5 text-[9px] font-bold rounded bg-sky-500/15 text-sky-400 border border-sky-500/30">
                                POSITIONAL
                              </span>
                            )}
                          </div>
                          <div className="text-[10px] text-muted-foreground font-mono mt-0.5">
                            {pos.contract_symbol}
                          </div>
                        </td>

                        <td className="py-3 px-3 font-mono">
                          {isIntraday ? (
                            <>
                              <div className="flex items-center gap-1 text-amber-400 font-semibold text-[11px]">
                                <Zap className="w-3.5 h-3.5 text-amber-400" />
                                <span>Intraday (Same-Day)</span>
                              </div>
                              <div className="text-[10px] text-amber-300 font-medium">
                                Auto-exit: {pos.hard_exit_time || '15:15'} IST
                              </div>
                            </>
                          ) : (
                            <>
                              <div className="flex items-center gap-1 text-foreground">
                                <Clock className="w-3.5 h-3.5 text-muted-foreground" />
                                <span>Day {pos.days_held}</span>
                              </div>
                              <div className={`text-[10px] ${pos.dte_remaining <= 3 ? 'text-amber-500 font-semibold' : 'text-muted-foreground'}`}>
                                {pos.dte_remaining}d to exp
                              </div>
                            </>
                          )}
                        </td>

                        <td className="py-3 px-3">
                          <div className="font-mono text-foreground font-medium">
                            {pos.num_lots} {pos.num_lots === 1 ? 'lot' : 'lots'} ({pos.num_lots * pos.lot_size} qty)
                          </div>
                          <div className="text-[10px] text-muted-foreground font-mono">
                            @ ₹{pos.entry_premium.toFixed(2)}
                          </div>
                        </td>

                        <td className="py-3 px-3 font-mono font-medium text-foreground">
                          ₹{pos.current_premium.toFixed(2)}
                        </td>

                        <td className="py-3 px-3 font-mono">
                          <div className="font-semibold text-destructive">₹{pos.current_stop_premium.toFixed(2)}</div>
                          <div className="text-[10px] text-muted-foreground">Spot Inv: ₹{pos.spot_stop.toFixed(1)}</div>
                          <div className="mt-0.5">{getTrailingBadge(pos.stop_method)}</div>
                        </td>

                        <td className="py-3 px-3 text-[11px] font-mono">
                          <div className="text-emerald-500 font-semibold">T1: ₹{pos.target_1.toFixed(2)}</div>
                          <div className="text-muted-foreground">T2: ₹{pos.target_2.toFixed(2)}</div>
                        </td>

                        <td className="py-3 px-3 font-mono text-[10px] text-muted-foreground">
                          <div>Δ {delta.toFixed(2)}</div>
                          <div className="text-rose-500">Θ -₹{Math.abs(thetaDay).toFixed(1)}/d</div>
                        </td>

                        <td className="py-3 px-3 text-right">
                          <div className={`font-mono font-bold text-sm ${isProfit ? 'text-emerald-500' : 'text-rose-500'}`}>
                            {isProfit ? '+' : ''}₹{pos.unrealized_pnl.toFixed(2)}
                          </div>
                          <div className={`text-[11px] font-mono flex items-center justify-end gap-0.5 ${isProfit ? 'text-emerald-500' : 'text-rose-500'}`}>
                            {isProfit ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                            <span>{isProfit ? '+' : ''}{pos.pnl_pct.toFixed(1)}% ({pos.r_multiple.toFixed(1)}R)</span>
                          </div>
                        </td>

                        <td className="py-3 px-4 text-center">
                          <button
                            onClick={() => openExitModal(pos)}
                            disabled={exitingId === pos.position_id}
                            className="px-2.5 py-1 text-[11px] font-medium rounded-md border border-destructive/40 text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-50"
                          >
                            {exitingId === pos.position_id ? 'Closing...' : 'Close Trade'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )
          ) : (
            closedPositions.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground text-xs gap-2">
                <Shield className="w-8 h-8 opacity-40 text-muted-foreground" />
                <span>No closed swing options trades recorded yet.</span>
              </div>
            ) : (
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-border/60 bg-muted/40 text-muted-foreground font-medium text-[11px]">
                    <th className="py-2.5 px-4">Contract Symbol</th>
                    <th className="py-2.5 px-3">Days Held</th>
                    <th className="py-2.5 px-3">Entry Premium</th>
                    <th className="py-2.5 px-3">Exit Premium</th>
                    <th className="py-2.5 px-3">Exit Reason</th>
                    <th className="py-2.5 px-4 text-right">Realized P&L</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {closedPositions.map((pos) => {
                    const isProfit = pos.unrealized_pnl >= 0;
                    return (
                      <tr key={pos.position_id} className="hover:bg-muted/30 transition-colors">
                        <td className="py-3 px-4 font-semibold text-foreground">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span>{pos.contract_symbol}</span>
                            {pos.horizon === 'INTRADAY' || pos.strategy?.startsWith('INTRADAY_') ? (
                              <span className="px-1.5 py-0.5 text-[9px] font-bold rounded bg-amber-500/15 text-amber-400 border border-amber-500/30 flex items-center gap-0.5">
                                <Zap className="w-2.5 h-2.5" /> INTRADAY
                              </span>
                            ) : (
                              <span className="px-1.5 py-0.5 text-[9px] font-bold rounded bg-sky-500/15 text-sky-400 border border-sky-500/30">
                                POSITIONAL
                              </span>
                            )}
                          </div>
                          <div className="text-[10px] text-muted-foreground font-normal">{pos.strategy.replace(/_/g, ' ')}</div>
                        </td>
                        <td className="py-3 px-3 font-mono">
                          {pos.horizon === 'INTRADAY' || pos.strategy?.startsWith('INTRADAY_') ? 'Same-day (Intraday)' : `${pos.days_held} days`}
                        </td>
                        <td className="py-3 px-3 font-mono">₹{pos.entry_premium.toFixed(2)}</td>
                        <td className="py-3 px-3 font-mono">₹{(pos.close_premium || pos.current_premium).toFixed(2)}</td>
                        <td className="py-3 px-3">
                          <span className="px-2 py-0.5 text-[10px] font-semibold rounded bg-muted text-muted-foreground">
                            {pos.exit_reason || 'MANUAL_EXIT'}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right">
                          <div className={`font-mono font-bold ${isProfit ? 'text-emerald-500' : 'text-rose-500'}`}>
                            {isProfit ? '+' : ''}₹{pos.unrealized_pnl.toFixed(2)}
                          </div>
                          <div className={`text-[10px] font-mono ${isProfit ? 'text-emerald-500' : 'text-rose-500'}`}>
                            {pos.r_multiple.toFixed(1)}R
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )
          )}
        </div>
      </div>

      {/* Structured Close Modal */}
      {exitModalPos && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="relative w-full max-w-md rounded-xl border border-border bg-card text-card-foreground shadow-2xl p-5 space-y-4">
            <div>
              <h3 className="text-base font-bold text-foreground">Close Position</h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                {exitModalPos.contract_symbol} ({exitModalPos.num_lots} lots)
              </p>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-muted-foreground mb-1 font-medium">Exit Premium (₹)</label>
                <input
                  type="number"
                  step={0.05}
                  value={exitPremiumInput}
                  onChange={(e) => setExitPremiumInput(Number(e.target.value))}
                  className="w-full bg-background border border-border rounded-lg px-3 py-1.5 font-mono text-foreground"
                />
              </div>

              <div>
                <label className="block text-muted-foreground mb-1 font-medium">Exit Reason (§47 Structured Log)</label>
                <select
                  value={selectedExitReason}
                  onChange={(e) => setSelectedExitReason(e.target.value)}
                  className="w-full bg-background border border-border rounded-lg px-3 py-1.5 text-foreground text-xs"
                >
                  {EXIT_REASONS.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
              <button
                onClick={() => setExitModalPos(null)}
                className="px-3 py-1.5 text-xs font-medium rounded-lg border border-border bg-background hover:bg-muted text-foreground transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmExit}
                disabled={exitingId === exitModalPos.position_id}
                className="px-3 py-1.5 text-xs font-medium rounded-lg bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-50"
              >
                {exitingId === exitModalPos.position_id ? 'Confirming...' : 'Confirm Close'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
