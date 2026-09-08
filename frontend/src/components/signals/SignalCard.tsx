'use client';

import React, { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { api } from '@/lib/api';
import { safeNum, safeState, ttlLabel, formatDateTime } from '@/lib/signal-utils';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import {
  ArrowDownRight,
  ArrowUpRight,
  Calendar,
  Check,
  CheckCircle2,
  Clock,
  Crosshair,
  ExternalLink,
  Flame,
  Hourglass,
  Radio,
  Target,
  TrendingDown,
  TrendingUp,
  Trash2,
  Zap,
} from 'lucide-react';

const STAGES = [
  { id: 'DETECTED', label: 'Detected' },
  { id: 'VALIDATED', label: 'Validated' },
  { id: 'ARMED', label: 'Armed' },
  { id: 'TRIGGERED', label: 'Triggered' },
  { id: 'CONFIRMED', label: 'Confirmed' },
] as const;

function getStageIndex(state?: string): number {
  if (!state) return 2;
  const s = state.toUpperCase();
  if (s === 'DETECTED') return 0;
  if (s === 'VALIDATED') return 1;
  if (s === 'ARMED') return 2;
  if (s === 'TRIGGERED') return 3;
  if (s === 'CONFIRMED') return 4;
  if (s.includes('TARGET') || s.includes('STOP') || s.includes('TIME_STOP') || s.includes('CLOSED')) return 5;
  if (s === 'EXPIRED' || s === 'INVALIDATED') return 0;
  return 2;
}

export type SignalDTO = {
  signal_id: string;
  id?: string;
  underlying: string;
  instrument?: string;
  strategy: string;
  direction: string;
  timeframe: string;
  spot_price: number | string;
  entry_min: number | string;
  entry_max: number | string;
  trigger: number | string;
  stop_loss: number | string;
  current_stop_loss?: number | string;
  target_1: number | string;
  target_2: number | string;
  risk_points: number | string;
  risk_reward_t1: number;
  risk_reward_t2: number;
  confidence: number;
  signal_type?: string;
  is_scalp?: boolean;
  breakeven_activated?: boolean;
  time_stop_at_utc?: number | null;
  runner_time_stop_at_utc?: number | null;
  runner_ttl_seconds?: number | null;
  t1_hit?: boolean;
  t2_hit?: boolean;
  remaining_qty?: number | string;
  intended_qty?: number | string;
  confluence_breakdown?: Record<string, number>;
  rationale?: string[];
  option_contract?: {
    broker_symbol?: string;
    strike?: number;
    option_type?: string;
    lot_size?: number;
    expiry_date?: string;
    expiry_type?: string;
  };
  fsm_state: string;
  created_at_utc: number;
  created_at_str?: string;
  expires_at_utc: number;
  ttl_seconds?: number;
  distance_to_trigger_pts?: number | null;
  distance_to_trigger_pct?: number | null;
  paper_order?: any;
};

function StatusBadge({ status, isMarketClosed }: { status: string; isMarketClosed?: boolean }) {
  const s = status.toUpperCase();
  if (['DETECTED', 'VALIDATED', 'ARMED', 'CONFIRMED'].includes(s) && isMarketClosed) {
    return <Badge variant="outline" className="border-slate-500/40 text-muted-foreground bg-muted/40 font-mono text-[10px]">MARKET CLOSED</Badge>;
  }
  if (s === 'CONFIRMED') return <Badge className="bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30 font-mono text-[10px] font-bold">● CONFIRMED</Badge>;
  if (s === 'TARGET_1_HIT') return <Badge className="bg-emerald-500/20 text-emerald-600 dark:text-emerald-300 border-emerald-500/40 font-mono text-[10px] font-bold">🎯 T1 HIT • RUNNER</Badge>;
  if (s === 'TARGET_2_HIT') return <Badge className="bg-emerald-600 text-white font-mono text-[10px] font-bold">🏁 TARGET 2 HIT (+3.0R)</Badge>;
  if (s === 'STOP_LOSS_HIT') return <Badge variant="destructive" className="font-mono text-[10px]">🛑 STOP LOSS</Badge>;
  if (s === 'TIME_STOP_HIT') return <Badge variant="outline" className="border-amber-500 text-amber-600 font-mono text-[10px] font-bold">⏱️ TIME STOP</Badge>;
  if (s === 'RUNNER_TIME_STOP_HIT') return <Badge variant="outline" className="border-amber-600 text-amber-700 font-mono text-[10px] font-bold">⏱️ RUNNER STOP</Badge>;
  if (s === 'TRIGGERED') return <Badge className="bg-amber-500/15 text-amber-600 border-amber-500/30 font-mono text-[10px]">TRIGGERED</Badge>;
  if (s === 'ARMED') return <Badge className="bg-sky-500/15 text-sky-600 dark:text-sky-400 border-sky-500/30 font-mono text-[10px]">ARMED</Badge>;
  if (s === 'VALIDATED') return <Badge variant="secondary" className="font-mono text-[10px]">VALIDATED</Badge>;
  if (s === 'EXPIRED') return <Badge variant="outline" className="border-border text-muted-foreground font-mono text-[10px]">EXPIRED</Badge>;
  if (s === 'INVALIDATED') return <Badge variant="destructive" className="font-mono text-[10px]">INVALIDATED</Badge>;
  return <Badge variant="outline" className="font-mono text-[10px]">{s}</Badge>;
}

function StrategyBadge({ strategy }: { strategy: string }) {
  return (
    <Badge variant="outline" className="text-[10px] font-mono px-1.5 py-0 border-border bg-secondary/40 text-muted-foreground">
      {strategy}
    </Badge>
  );
}

export function SignalCard({
  signal,
  onInspect,
  onPaperExecuted,
  onDeleted,
  nowMs,
  cardsNowMs,
  selectMode,
  isSelected,
  onToggleSelect,
}: {
  signal: SignalDTO;
  onInspect?: (signalId: string) => void;
  onPaperExecuted?: (result: any) => void;
  onDeleted?: (signalId: string) => void;
  nowMs?: number;
  cardsNowMs?: number;
  selectMode?: boolean;
  isSelected?: boolean;
  onToggleSelect?: (id: string) => void;
}) {
  const currentNowMs = nowMs ?? cardsNowMs ?? Date.now();
  const [executing, setExecuting] = useState(false);
  const [paperResult, setPaperResult] = useState<any>(signal.paper_order || null);
  const [execError, setExecError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [armDelete, setArmDelete] = useState(false);

  const market = useOptionalMarketDataContext();
  const isMarketClosed = market?.marketStatus?.session === 'CLOSED' || market?.marketStatus?.is_trading_day === false;

  const fsm = safeState(signal.fsm_state);
  const isCall = signal.direction?.includes('CALL') || signal.direction === 'BULLISH';
  const isTargetHit = fsm.includes('TARGET');
  const isStopHit = fsm === 'STOP_LOSS_HIT';
  const isExpired = fsm === 'EXPIRED' || (
    ['DETECTED', 'VALIDATED', 'ARMED', 'CONFIRMED'].includes(fsm) && (
      (signal.expires_at_utc ? currentNowMs > signal.expires_at_utc : false) || isMarketClosed
    )
  );

  const dirColor = isCall ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400';

  const handleExecutePaper = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setExecuting(true);
    setExecError(null);
    try {
      const res = await api.executeSignalPaper(signal.signal_id);
      if (res && res.success) {
        setPaperResult(res);
        onPaperExecuted?.(res);
      }
    } catch (err: any) {
      setExecError(err.message || 'Execution failed');
    } finally {
      setExecuting(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!armDelete) {
      setArmDelete(true);
      setTimeout(() => setArmDelete(false), 3000);
      return;
    }
    setDeleting(true);
    try {
      await api.deleteSignal(signal.signal_id);
      onDeleted?.(signal.signal_id);
    } catch (err: any) {
      setExecError(err.message || 'Delete failed');
    } finally {
      setDeleting(false);
      setArmDelete(false);
    }
  };

  const spotNum = Number(signal.spot_price);
  const riskPts = Number(signal.risk_points || 0);
  const lotSize = signal.option_contract?.lot_size || 75;
  const estimatedRiskRupees = Math.round(riskPts * lotSize * 2);

  // ── Lifecycle & Temporal calculations ──
  const stageIndex = getStageIndex(fsm);

  const ttlSec = signal.ttl_seconds || (signal.is_scalp ? 180 : 300);
  const expiresAt = signal.expires_at_utc || (signal.created_at_utc ? signal.created_at_utc + (ttlSec * 1000) : 0);
  const preEntrySecRemaining = expiresAt > 0 ? Math.max(0, Math.floor((expiresAt - currentNowMs) / 1000)) : null;
  const isPreEntryExpired = preEntrySecRemaining === 0;

  const timeStopSecRemaining =
    typeof signal.time_stop_at_utc === 'number' && signal.time_stop_at_utc > 0
      ? Math.max(0, Math.floor((signal.time_stop_at_utc - currentNowMs) / 1000))
      : null;

  const runnerSecRemaining =
    typeof signal.runner_time_stop_at_utc === 'number' && signal.runner_time_stop_at_utc > 0
      ? Math.max(0, Math.floor((signal.runner_time_stop_at_utc - currentNowMs) / 1000))
      : null;

  const formatSec = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}m ${s.toString().padStart(2, '0')}s`;
  };

  let stateLabelText = fsm;
  let stateLabelStyle = 'bg-secondary text-secondary-foreground border-border';

  if (isMarketClosed && ['DETECTED', 'VALIDATED', 'ARMED', 'CONFIRMED'].includes(fsm)) {
    stateLabelText = 'MARKET CLOSED';
    stateLabelStyle = 'bg-muted text-muted-foreground border-border/80';
  } else if (fsm === 'ARMED') {
    if (isPreEntryExpired) {
      stateLabelText = 'ARMED · Window Expired';
      stateLabelStyle = 'bg-muted text-muted-foreground border-border';
    } else {
      stateLabelText = 'ARMED · Waiting Breakout';
      stateLabelStyle = 'bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-500/30';
    }
  } else if (fsm === 'VALIDATED') {
    stateLabelText = 'VALIDATED · Filters Passed';
    stateLabelStyle = 'bg-secondary text-secondary-foreground border-border';
  } else if (fsm === 'DETECTED') {
    stateLabelText = 'DETECTED · Scanning';
    stateLabelStyle = 'bg-secondary text-muted-foreground border-border';
  } else if (fsm === 'TRIGGERED') {
    stateLabelText = 'TRIGGERED · Fill Pending';
    stateLabelStyle = 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30';
  } else if (fsm === 'CONFIRMED') {
    stateLabelText = 'CONFIRMED · Position Active';
    stateLabelStyle = 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30';
  } else if (fsm === 'TARGET_1_HIT') {
    stateLabelText = 'T1 HIT · 50% Booked (Runner)';
    stateLabelStyle = 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border-emerald-500/40';
  } else if (fsm === 'TARGET_2_HIT') {
    stateLabelText = 'T2 HIT · Completed (+3.0R)';
    stateLabelStyle = 'bg-emerald-600 text-white border-emerald-600';
  } else if (fsm === 'STOP_LOSS_HIT') {
    stateLabelText = 'STOP HIT · Exited';
    stateLabelStyle = 'bg-destructive/15 text-destructive border-destructive/30';
  } else if (fsm === 'TIME_STOP_HIT') {
    stateLabelText = 'TIME STOP · Exit Triggered';
    stateLabelStyle = 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30';
  } else if (fsm === 'RUNNER_TIME_STOP_HIT') {
    stateLabelText = 'RUNNER STOP · Exited';
    stateLabelStyle = 'bg-amber-600/15 text-amber-800 dark:text-amber-400 border-amber-600/30';
  } else if (fsm === 'EXPIRED') {
    stateLabelText = 'EXPIRED · TTL Exceeded';
    stateLabelStyle = 'bg-muted text-muted-foreground border-border';
  } else if (fsm === 'INVALIDATED') {
    stateLabelText = 'INVALIDATED · Setup Void';
    stateLabelStyle = 'bg-destructive/15 text-destructive border-destructive/30';
  }

  let temporalTimerBadge = null;
  if (isMarketClosed) {
    temporalTimerBadge = (
      <span className="inline-flex items-center gap-1 font-mono text-[10px] text-muted-foreground">
        <Clock className="w-3 h-3 text-muted-foreground" />
        <span>Next: 09:15 IST</span>
      </span>
    );
  } else if (['ARMED', 'VALIDATED'].includes(fsm)) {
    if (preEntrySecRemaining !== null) {
      if (preEntrySecRemaining > 60) {
        temporalTimerBadge = (
          <span
            className="inline-flex items-center gap-1 font-mono text-[10px] font-semibold px-2 py-0.5 rounded border bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20"
            title="Pre-entry trigger window remaining before auto-expiry"
          >
            <Hourglass className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
            <span>{formatSec(preEntrySecRemaining)} left</span>
          </span>
        );
      } else if (preEntrySecRemaining > 0) {
        temporalTimerBadge = (
          <span
            className="inline-flex items-center gap-1 font-mono text-[10px] font-bold px-2 py-0.5 rounded border bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30 animate-pulse"
            title="Trigger window closing soon!"
          >
            <Hourglass className="w-3 h-3 text-rose-600 dark:text-rose-400" />
            <span>{preEntrySecRemaining}s left!</span>
          </span>
        );
      } else {
        temporalTimerBadge = (
          <span className="inline-flex items-center gap-1 font-mono text-[10px] font-semibold px-2 py-0.5 rounded border bg-muted text-muted-foreground border-border">
            <Hourglass className="w-3 h-3 text-muted-foreground" />
            <span>Window Expired</span>
          </span>
        );
      }
    }
  } else if (fsm === 'CONFIRMED') {
    if (timeStopSecRemaining !== null) {
      if (timeStopSecRemaining > 60) {
        temporalTimerBadge = (
          <span
            className="inline-flex items-center gap-1 font-mono text-[10px] font-semibold px-2 py-0.5 rounded border bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30"
            title="In-trade maximum holding time before time-stop"
          >
            <Clock className="w-3 h-3 text-amber-600" />
            <span>{formatSec(timeStopSecRemaining)} Time-Stop</span>
          </span>
        );
      } else if (timeStopSecRemaining > 0) {
        temporalTimerBadge = (
          <span
            className="inline-flex items-center gap-1 font-mono text-[10px] font-bold px-2 py-0.5 rounded border bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30 animate-pulse"
            title="Time-stop approaching"
          >
            <Clock className="w-3 h-3 text-rose-600" />
            <span>{timeStopSecRemaining}s Time-Stop</span>
          </span>
        );
      } else {
        temporalTimerBadge = (
          <span className="inline-flex items-center gap-1 font-mono text-[10px] font-bold px-2 py-0.5 rounded border bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30">
            Time-Stop Hit
          </span>
        );
      }
    }
  } else if (fsm === 'TARGET_1_HIT') {
    if (runnerSecRemaining !== null && runnerSecRemaining > 0) {
      temporalTimerBadge = (
        <span
          className="inline-flex items-center gap-1 font-mono text-[10px] font-semibold px-2 py-0.5 rounded border bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30"
          title="Runner trailing window remaining"
        >
          <Clock className="w-3 h-3 text-emerald-600" />
          <span>{formatSec(runnerSecRemaining)} Runner TTL</span>
        </span>
      );
    }
  }

  return (
    <Card
      className="p-4 space-y-3.5 cursor-pointer hover:shadow-md hover:border-primary/40 transition-all rounded-2xl border bg-card/70"
      onClick={() => onInspect?.(signal.signal_id)}
    >
      {/* Top Header: Underlying, Direction, Strategy, Expiry, FSM Status */}
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-base tracking-tight text-foreground">{signal.underlying}</span>
            <span className={`text-xs font-mono font-bold flex items-center gap-0.5 ${dirColor}`}>
              {isCall ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
              {signal.direction}
            </span>
            <StrategyBadge strategy={signal.strategy} />
            <span className="text-[10px] font-mono text-muted-foreground">
              {signal.timeframe || '5M'}
            </span>
          </div>

          <div className="text-xs font-mono text-muted-foreground flex items-center gap-2 flex-wrap">
            <span>Spot: <b className="text-foreground">₹{safeNum(signal.spot_price)}</b></span>
            {signal.option_contract?.strike && (
              <>
                <span>•</span>
                <span className="px-1.5 py-0.2 rounded bg-secondary/70 text-foreground border text-[11px] font-medium">
                  {signal.option_contract.strike} {signal.option_contract.option_type} ({signal.option_contract.lot_size} Qty/Lot)
                </span>
              </>
            )}
            {signal.option_contract?.expiry_date && (
              <span className="text-[11px] text-muted-foreground hidden sm:inline">• {signal.option_contract.expiry_date}</span>
            )}
          </div>
        </div>

        <div className="flex flex-col items-end gap-1">
          <StatusBadge status={fsm} isMarketClosed={isMarketClosed} />
          <div className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground">
            {signal.created_at_utc ? (
              <span title="Generated Date & Time (IST)" className="flex items-center gap-1">
                <Clock className="w-3 h-3 text-muted-foreground/80" />
                {formatDateTime(signal.created_at_utc)}
              </span>
            ) : null}
          </div>
        </div>
      </div>

      {/* ── FSM LIFECYCLE PROGRESSION & TEMPORAL AWARENESS ── */}
      <div className="bg-muted/30 border border-border/70 rounded-xl p-2.5 space-y-2">
        <div className="flex items-center justify-between text-[11px] flex-wrap gap-1.5">
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-muted-foreground text-[10px] uppercase tracking-wider font-semibold">
              Lifecycle:
            </span>
            <span className={`font-mono text-[10px] font-bold px-2 py-0.5 rounded border ${stateLabelStyle}`}>
              {stateLabelText}
            </span>
          </div>

          {temporalTimerBadge}
        </div>

        {/* 5-Stage Stepper */}
        <div className="flex items-center justify-between gap-1 pt-0.5">
          {STAGES.map((st, idx) => {
            const isPast = idx < stageIndex;
            const isCurrent = idx === stageIndex;

            return (
              <React.Fragment key={st.id}>
                <div className="flex flex-col items-center gap-0.5 flex-1">
                  <div
                    className={`w-4.5 h-4.5 rounded-full flex items-center justify-center text-[9px] font-mono font-bold transition-all ${
                      isPast
                        ? 'bg-emerald-600 text-white shadow-xs'
                        : isCurrent
                        ? isPreEntryExpired
                          ? 'bg-muted-foreground/60 text-white ring-2 ring-border'
                          : 'bg-amber-500 text-white ring-2 ring-amber-400/40 animate-pulse'
                        : 'bg-muted text-muted-foreground border border-border'
                    }`}
                  >
                    {isPast ? <Check className="w-2.5 h-2.5 text-white" /> : idx + 1}
                  </div>
                  <span
                    className={`text-[9px] font-mono tracking-tight ${
                      isCurrent
                        ? isPreEntryExpired
                          ? 'text-muted-foreground font-semibold'
                          : 'text-amber-600 dark:text-amber-400 font-bold'
                        : isPast
                        ? 'text-foreground/80 font-medium'
                        : 'text-muted-foreground/60'
                    }`}
                  >
                    {st.label}
                  </span>
                </div>
                {idx < STAGES.length - 1 && (
                  <div
                    className={`h-[2px] flex-1 mb-2.5 transition-all ${
                      idx < stageIndex ? 'bg-emerald-500' : 'bg-border'
                    }`}
                  />
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {/* 4-Column Clean Price Geometry Grid */}
      <div className="grid grid-cols-4 gap-2 text-xs font-mono p-2.5 rounded-xl bg-muted/40 border border-border/60">
        <div>
          <div className="text-muted-foreground text-[10px]">Stop Loss</div>
          <div className="text-destructive font-semibold mt-0.5">
            ₹{safeNum(signal.current_stop_loss ?? signal.stop_loss)}
          </div>
          <div className="text-[10px] text-muted-foreground truncate">
            {signal.breakeven_activated ? 'SL @ Cost' : `-${safeNum(riskPts, 1)} pts`}
          </div>
        </div>

        <div>
          <div className="text-muted-foreground text-[10px]">Trigger / Entry</div>
          <div className="text-foreground font-semibold mt-0.5">
            ₹{safeNum(signal.trigger)}
          </div>
          <div className="text-[10px] text-muted-foreground truncate">
            {typeof signal.distance_to_trigger_pts === 'number' && Number.isFinite(signal.distance_to_trigger_pts)
              ? signal.distance_to_trigger_pts <= 0.5 ? '⚡ In Zone' : `${signal.distance_to_trigger_pts.toFixed(1)} pts away`
              : 'Trigger Zone'}
          </div>
        </div>

        <div>
          <div className="text-muted-foreground text-[10px]">Target 1 (1.5R)</div>
          <div className="text-emerald-600 dark:text-emerald-400 font-semibold mt-0.5">
            ₹{safeNum(signal.target_1)}
          </div>
          <div className="text-[10px] text-muted-foreground truncate">Book 50%</div>
        </div>

        <div>
          <div className="text-muted-foreground text-[10px]">Target 2 (3.0R)</div>
          <div className="text-emerald-700 dark:text-emerald-300 font-semibold mt-0.5">
            ₹{safeNum(signal.target_2)}
          </div>
          <div className="text-[10px] text-muted-foreground truncate">Runner</div>
        </div>
      </div>

      {/* Paper Execution Strip (If already executed) */}
      {paperResult && (
        <div className="flex flex-col gap-1 w-full text-[11px] bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-2 font-mono">
          <div className="flex items-center justify-between text-emerald-700 dark:text-emerald-300">
            <span className="flex items-center gap-1 font-bold text-[11px]">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> Paper: {safeNum(paperResult.quantity, 0)} Qty @ ₹{safeNum(paperResult.fill_price)}
            </span>
            <span className="text-[10px] text-muted-foreground">{paperResult.order_id || ''}</span>
          </div>
          {(() => {
            const isOption = Boolean(signal.option_contract?.strike);
            const fillP = Number(paperResult.fill_price || 0);
            const trigP = Number(signal.trigger ?? signal.spot_price);
            if (!Number.isFinite(spotNum) || !Number.isFinite(trigP) || trigP <= 0) return null;
            const spotDiff = isCall ? spotNum - trigP : trigP - spotNum;
            // For options, delta is ~0.50 of spot move, or spotDiff for futures/spot
            const effectivePts = isOption ? (spotDiff * 0.5) : spotDiff;
            const qty = Number(paperResult.quantity || lotSize);
            if (!Number.isFinite(qty) || qty <= 0) return null;
            let pnl = effectivePts * qty;
            // Bound option loss to premium paid
            if (isOption && fillP > 0) {
              const maxLoss = fillP * qty;
              if (pnl < -maxLoss) pnl = -maxLoss;
            }
            const isProfit = pnl >= 0;
            return (
              <div className="flex items-center justify-between pt-1 border-t border-emerald-500/20 text-[10px]">
                <span className="text-muted-foreground flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-ping" />
                  Live Open MTM:
                </span>
                <span className={`font-bold ${isProfit ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                  {pnl >= 0 ? `+₹${pnl.toFixed(2)}` : `-₹${Math.abs(pnl).toFixed(2)}`} ({effectivePts >= 0 ? '+' : ''}{effectivePts.toFixed(1)} pts)
                </span>
              </div>
            );
          })()}
        </div>
      )}

      {/* Sizing, Logic Modal Trigger, and 1-Click Execution */}
      <div className="flex items-center justify-between pt-1 border-t text-xs font-mono">
        <div className="text-muted-foreground flex items-center gap-2 text-[11px]">
          <span>Size: <b className="text-foreground">2 Lots</b></span>
          <span>•</span>
          <span>Risk: <b className="text-destructive">₹{estimatedRiskRupees.toLocaleString('en-IN')}</b></span>
          <span>•</span>
          <span>Conf: <b className="text-primary">{safeNum(signal.confidence, 0)}%</b></span>
        </div>

        <div className="flex items-center gap-2">
          {/* Triggers the Signal Generation Pipeline Modal */}
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-[11px] gap-1 px-2.5 hover:bg-secondary border-border"
            onClick={(e) => {
              e.stopPropagation();
              onInspect?.(signal.signal_id);
            }}
            title="Inspect 6-Stage Quantitative Generation Pipeline"
          >
            <span>⚙️ View Logic ↗</span>
          </Button>

          {!paperResult && !isExpired && !isTargetHit && !isStopHit && !isMarketClosed && (
            <Button
              size="sm"
              className="h-7 text-[11px] bg-emerald-600 hover:bg-emerald-700 text-white font-medium gap-1 px-3 shadow-sm"
              onClick={handleExecutePaper}
              disabled={executing}
            >
              <Zap className="w-3 h-3" />
              {executing ? 'Executing…' : '⚡ 1-Click Paper'}
            </Button>
          )}

          <Button
            size="sm"
            variant="ghost"
            className={`h-7 w-7 p-0 ${armDelete ? 'text-destructive bg-destructive/10' : 'text-muted-foreground hover:text-destructive'}`}
            onClick={handleDelete}
            disabled={deleting}
            title={armDelete ? 'Tap again to confirm delete' : 'Delete signal'}
          >
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {execError && <span className="text-[10px] text-destructive font-mono block">{execError}</span>}
    </Card>
  );
}
