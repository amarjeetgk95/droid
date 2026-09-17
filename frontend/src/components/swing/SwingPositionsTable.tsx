'use client';

import { useState } from 'react';
import {
  Shield,
  Clock,
  ArrowUpRight,
  ArrowDownRight,
  AlertCircle,
  RefreshCw,
  Zap,
} from 'lucide-react';
import type { SwingPositionDTO } from '@/lib/api/swing';
import { Modal } from '@/components/shared/Modal';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import { useToast } from '@/components/ui/toast';
import { fmtINR, fmtNum } from '@/components/ui/desk';
import {
  EXIT_REASONS,
  exitReasonLabel,
  pnlTone,
  pnlToneClass,
  signedINR,
  signedPct,
  signedR,
} from './swingUtils';

export type SwingPositionsTableProps = {
  positions: SwingPositionDTO[];
  closedPositions?: SwingPositionDTO[];
  /** Awaiting the first load — never renders "No open positions" while true. */
  loading?: boolean;
  /** A refetch is in flight over existing data. */
  refreshing?: boolean;
  /** When the marks were last fetched (positions response time). */
  marksAt?: number | null;
  /** The last positions fetch failed — marks are last known, not live. */
  stale?: boolean;
  /** Explicit error for the failing positions fetch. */
  loadError?: string | null;
  onRetry?: () => void;
  onExitPosition?: (positionId: string, exitPremium: number, exitReason?: string) => Promise<any>;
};

function isIntradayPosition(pos: SwingPositionDTO): boolean {
  return pos.horizon === 'INTRADAY' || Boolean(pos.strategy?.startsWith('INTRADAY_'));
}

export function SwingPositionsTable({
  positions,
  closedPositions = [],
  loading = false,
  refreshing = false,
  marksAt = null,
  stale = false,
  loadError = null,
  onRetry,
  onExitPosition,
}: SwingPositionsTableProps) {
  const toast = useToast();
  const [exitingId, setExitingId] = useState<string | null>(null);
  const [viewTab, setViewTab] = useState<'open' | 'closed'>('open');
  const [exitModalPos, setExitModalPos] = useState<SwingPositionDTO | null>(null);
  const [selectedExitReason, setSelectedExitReason] = useState<string>('MANUAL_EXIT');
  const [exitPremiumInput, setExitPremiumInput] = useState<number>(0);
  const [exitError, setExitError] = useState<string | null>(null);

  const initialLoading = loading && positions.length === 0 && closedPositions.length === 0;

  const openExitModal = (pos: SwingPositionDTO) => {
    setExitModalPos(pos);
    setExitPremiumInput(Number.isFinite(pos.current_premium) ? pos.current_premium : 0);
    setSelectedExitReason('MANUAL_EXIT');
    setExitError(null);
  };

  const closeExitModal = () => {
    if (exitingId !== null) return;
    setExitModalPos(null);
    setExitError(null);
  };

  const handleConfirmExit = async () => {
    if (!exitModalPos || !onExitPosition) return;
    if (!Number.isFinite(exitPremiumInput) || exitPremiumInput <= 0) {
      setExitError('Enter a positive exit premium before confirming.');
      return;
    }
    setExitingId(exitModalPos.position_id);
    setExitError(null);
    try {
      await onExitPosition(exitModalPos.position_id, exitPremiumInput, selectedExitReason);
      toast.success(
        `Position closed — ${exitModalPos.contract_symbol}`,
        `${exitReasonLabel(selectedExitReason)} · exit ${fmtINR(exitPremiumInput)}`,
      );
      setExitModalPos(null);
    } catch (err) {
      setExitError(
        err instanceof Error && err.message
          ? err.message
          : 'Close failed — the position is still open.',
      );
    } finally {
      setExitingId(null);
    }
  };

  const getTrailingBadge = (method: string) => {
    switch (method) {
      case 'BREAK_EVEN':
        return <span className="px-1.5 py-0.5 text-[9px] font-semibold rounded bg-accent/10 text-accent border border-accent/20">BREAK-EVEN</span>;
      case 'TRAILING_PREMIUM':
        // Informational, like BREAK-EVEN — it is a trailing method, not a signal.
        return <span className="px-1.5 py-0.5 text-[9px] font-semibold rounded bg-accent/10 text-accent border border-accent/20">PEAK TRAIL</span>;
      case 'TIME_DECAY':
        return <span className="px-1.5 py-0.5 text-[9px] font-semibold rounded bg-warn/10 text-warn border border-warn/20">TIME DECAY STOP</span>;
      case 'TIME_STOP':
        return <span className="px-1.5 py-0.5 text-[9px] font-semibold rounded bg-down/10 text-down border border-down/20">15:15 TIME STOP</span>;
      default:
        return <span className="px-1.5 py-0.5 text-[9px] font-semibold rounded bg-muted text-muted-foreground border border-border">INITIAL STOP</span>;
    }
  };

  return (
    <>
      <div className="rounded-xl border border-border bg-card text-card-foreground shadow-xs overflow-hidden">
        {/* Table Sub-header */}
        <div className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 border-b border-border bg-muted/20">
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
          <div className="flex items-center gap-2">
            <FreshnessClock
              state={stale ? 'STALE' : undefined}
              lastAt={marksAt}
              fetching={refreshing}
              sourceLabel="marks"
            />
            <span className="text-xs text-muted-foreground">
              {viewTab === 'open' ? 'Carried overnight multi-day positions with dual-layer stops' : 'Realized swing outcomes'}
            </span>
          </div>
        </div>

        {/* Refresh failed but old marks remain — say so instead of showing them as live. */}
        {stale && loadError && (positions.length > 0 || closedPositions.length > 0) && (
          <div role="status" className="notice notice--warn text-[11px] rounded-none border-x-0 border-t-0">
            <AlertCircle className="w-3.5 h-3.5 text-warn shrink-0" />
            <span className="flex-1">
              Positions refresh failed — showing last known marks. {loadError}
            </span>
            {onRetry && (
              <button type="button" onClick={onRetry} className="btn shrink-0">
                Retry
              </button>
            )}
          </div>
        )}

        {/* Table Content */}
        <div className="overflow-x-auto">
          {initialLoading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground text-xs gap-2">
              <RefreshCw className="w-5 h-5 animate-spin text-primary" />
              <span>Loading swing positions…</span>
            </div>
          ) : viewTab === 'open' ? (
            positions.length === 0 && loadError ? (
              <div
                role="alert"
                className="flex flex-col items-center justify-center py-12 text-muted-foreground text-xs gap-2 text-center px-4"
              >
                <AlertCircle className="w-8 h-8 text-down opacity-70" />
                <span className="text-sm font-semibold text-foreground">Open positions unavailable.</span>
                <span>{loadError}</span>
                {onRetry && (
                  <button
                    type="button"
                    onClick={onRetry}
                    className="mt-2 px-3 py-1.5 text-xs font-medium rounded-lg bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors"
                  >
                    Retry
                  </button>
                )}
              </div>
            ) : positions.length === 0 ? (
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
                    <th className="py-2.5 px-3">Option LTP (mark)</th>
                    <th className="py-2.5 px-3">Dual-Layer Stops</th>
                    <th className="py-2.5 px-3">Targets (1.5R / 3R)</th>
                    <th className="py-2.5 px-3">Greeks at Entry</th>
                    <th className="py-2.5 px-3 text-right">P&L / Return</th>
                    <th className="py-2.5 px-4 text-center">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {positions.map((pos) => {
                    const tone = pnlTone(pos.unrealized_pnl);
                    const toneClass = pnlToneClass(pos.unrealized_pnl);
                    const delta = pos.greeks_at_entry?.delta ?? 0;
                    const thetaDay = pos.greeks_at_entry?.theta_day ?? 0;
                    const isCall = pos.option_type === 'CE';
                    const isIntraday = isIntradayPosition(pos);

                    return (
                      <tr key={pos.position_id} className="hover:bg-muted/30 transition-colors">
                        <td className="py-3 px-4 font-semibold text-foreground">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span>{pos.underlying}</span>
                            <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded ${
                              isCall ? 'bg-up/10 text-up' : 'bg-down/10 text-down'
                            }`}>
                              {pos.strike} {pos.option_type}
                            </span>
                            {isIntraday ? (
                              <span className="px-1.5 py-0.5 text-[9px] font-bold rounded bg-warn/15 text-warn border border-warn/30 flex items-center gap-0.5">
                                <Zap className="w-2.5 h-2.5" /> INTRADAY
                              </span>
                            ) : (
                              <span className="px-1.5 py-0.5 text-[9px] font-bold rounded bg-accent/15 text-accent border border-accent/30">
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
                              <div className="flex items-center gap-1 text-warn font-semibold text-[11px]">
                                <Zap className="w-3.5 h-3.5 text-warn" />
                                <span>Intraday (Same-Day)</span>
                              </div>
                              <div className="text-[10px] text-warn font-medium">
                                Auto-exit: {pos.hard_exit_time || '15:15'} IST
                              </div>
                            </>
                          ) : (
                            <>
                              <div className="flex items-center gap-1 text-foreground">
                                <Clock className="w-3.5 h-3.5 text-muted-foreground" />
                                <span>Day {pos.days_held}</span>
                              </div>
                              <div className={`text-[10px] ${pos.dte_remaining <= 3 ? 'text-warn font-semibold' : 'text-muted-foreground'}`}>
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
                            @ {fmtINR(pos.entry_premium)}
                          </div>
                        </td>

                        <td className="py-3 px-3 font-mono font-medium text-foreground">
                          {fmtINR(pos.current_premium)}
                        </td>

                        <td className="py-3 px-3 font-mono">
                          <div className="font-semibold text-destructive">{fmtINR(pos.current_stop_premium)}</div>
                          <div className="text-[10px] text-muted-foreground">Spot Inv: {fmtINR(pos.spot_stop)}</div>
                          <div className="mt-0.5">{getTrailingBadge(pos.stop_method)}</div>
                        </td>

                        <td className="py-3 px-3 text-[11px] font-mono">
                          <div className="text-up font-semibold">T1: {fmtINR(pos.target_1)}</div>
                          <div className="text-muted-foreground">T2: {fmtINR(pos.target_2)}</div>
                        </td>

                        <td className="py-3 px-3 font-mono text-[10px] text-muted-foreground">
                          <div>Δ {fmtNum(delta)}</div>
                          <div className="text-down">Θ -{fmtINR(Math.abs(thetaDay))}/d</div>
                        </td>

                        <td className="py-3 px-3 text-right">
                          <div className={`font-mono font-bold text-sm ${toneClass}`}>
                            {signedINR(pos.unrealized_pnl)}
                          </div>
                          <div className={`text-[11px] font-mono flex items-center justify-end gap-0.5 ${toneClass}`}>
                            {tone === 'up' && <ArrowUpRight className="w-3 h-3" />}
                            {tone === 'down' && <ArrowDownRight className="w-3 h-3" />}
                            <span>
                              {signedPct(pos.pnl_pct, 1)} ({signedR(pos.r_multiple, 1)})
                            </span>
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
          ) : closedPositions.length === 0 && loadError ? (
            <div
              role="alert"
              className="flex flex-col items-center justify-center py-12 text-muted-foreground text-xs gap-2 text-center px-4"
            >
              <AlertCircle className="w-8 h-8 text-down opacity-70" />
              <span className="text-sm font-semibold text-foreground">Closed history unavailable.</span>
              <span>{loadError}</span>
              {onRetry && (
                <button
                  type="button"
                  onClick={onRetry}
                  className="mt-2 px-3 py-1.5 text-xs font-medium rounded-lg bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors"
                >
                  Retry
                </button>
              )}
            </div>
          ) : closedPositions.length === 0 ? (
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
                  const toneClass = pnlToneClass(pos.unrealized_pnl);
                  const isIntraday = isIntradayPosition(pos);
                  return (
                    <tr key={pos.position_id} className="hover:bg-muted/30 transition-colors">
                      <td className="py-3 px-4 font-semibold text-foreground">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span>{pos.contract_symbol}</span>
                          {isIntraday ? (
                            <span className="px-1.5 py-0.5 text-[9px] font-bold rounded bg-warn/15 text-warn border border-warn/30 flex items-center gap-0.5">
                              <Zap className="w-2.5 h-2.5" /> INTRADAY
                            </span>
                          ) : (
                            <span className="px-1.5 py-0.5 text-[9px] font-bold rounded bg-accent/15 text-accent border border-accent/30">
                              POSITIONAL
                            </span>
                          )}
                        </div>
                        <div className="text-[10px] text-muted-foreground font-normal">{pos.strategy.replace(/_/g, ' ')}</div>
                      </td>
                      <td className="py-3 px-3 font-mono">
                        {isIntraday ? 'Same-day (Intraday)' : `${pos.days_held} days`}
                      </td>
                      <td className="py-3 px-3 font-mono">{fmtINR(pos.entry_premium)}</td>
                      <td className="py-3 px-3 font-mono">
                        {fmtINR(pos.close_premium ?? pos.current_premium)}
                      </td>
                      <td className="py-3 px-3">
                        <span className="px-2 py-0.5 text-[10px] font-semibold rounded bg-muted text-muted-foreground">
                          {exitReasonLabel(pos.exit_reason)}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <div className={`font-mono font-bold ${toneClass}`}>
                          {signedINR(pos.unrealized_pnl)}
                        </div>
                        <div className={`text-[10px] font-mono ${toneClass}`}>
                          {signedR(pos.r_multiple, 1)}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Structured Close Modal — explicit confirmation with pending + error states */}
      {exitModalPos && (
        <Modal
          isOpen
          onClose={closeExitModal}
          closeDisabled={exitingId !== null}
          maxWidth="md"
          title={
            <span className="flex items-center gap-2">
              Close Position
              <span className="text-xs font-mono text-muted-foreground">
                {exitModalPos.contract_symbol} · {exitModalPos.num_lots}{' '}
                {exitModalPos.num_lots === 1 ? 'lot' : 'lots'}
              </span>
            </span>
          }
          footer={
            <>
              <button
                type="button"
                onClick={closeExitModal}
                disabled={exitingId !== null}
                className="px-3 py-1.5 text-xs font-medium rounded-lg border border-border bg-background hover:bg-muted text-foreground transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleConfirmExit()}
                disabled={exitingId !== null}
                className="px-3 py-1.5 text-xs font-medium rounded-lg bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-50"
              >
                {exitingId !== null ? 'Closing…' : 'Confirm Close'}
              </button>
            </>
          }
        >
          <div className="space-y-3 text-xs">
            <div className="rounded-md border border-border bg-secondary/40 px-3 py-2 font-mono">
              <div className="flex items-baseline justify-between gap-3 py-0.5">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Mark
                </span>
                <span className="num text-xs font-semibold text-foreground">
                  {fmtINR(exitModalPos.current_premium)}
                </span>
              </div>
              <div className="flex items-baseline justify-between gap-3 py-0.5">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Entry
                </span>
                <span className="num text-xs font-semibold text-foreground">
                  {fmtINR(exitModalPos.entry_premium)}
                </span>
              </div>
              <div className="flex items-baseline justify-between gap-3 py-0.5">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Mark quality
                </span>
                <span className="text-xs font-semibold text-foreground">
                  {stale ? 'Last known — refresh failed' : 'Fetched this session'}
                </span>
              </div>
            </div>

            <div>
              <label className="block text-muted-foreground mb-1 font-medium" htmlFor="swing-exit-premium">
                Exit Premium (₹)
              </label>
              <input
                id="swing-exit-premium"
                type="number"
                step={0.05}
                value={exitPremiumInput}
                onChange={(e) => setExitPremiumInput(Number(e.target.value))}
                className="w-full bg-background border border-border rounded-lg px-3 py-1.5 font-mono text-foreground"
              />
            </div>

            <div>
              <label className="block text-muted-foreground mb-1 font-medium" htmlFor="swing-exit-reason">
                Exit Reason (§47 Structured Log)
              </label>
              <select
                id="swing-exit-reason"
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

            {exitError && (
              <p role="alert" className="text-xs text-down font-mono">
                {exitError}
              </p>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}
