'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { api } from '@/lib/api';
import { safeNum, formatDateTime } from '@/lib/signal-utils';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import {
  ArrowDownRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  Clock,
  Crosshair,
  Hourglass,
  Target,
  Trash2,
  Zap,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';

const STAGES = [
  { id: 'DETECTED', label: 'D' },
  { id: 'VALIDATED', label: 'V' },
  { id: 'ARMED', label: 'A' },
  { id: 'TRIGGERED', label: 'T' },
  { id: 'CONFIRMED', label: 'C' },
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

function stageColor(idx: number, current: number, preEntryExpired: boolean): string {
  if (idx < current) return 'bg-emerald-600 text-white';
  if (idx === current) {
    if (preEntryExpired) return 'bg-muted-foreground/60 text-white ring-2 ring-border';
    return 'bg-amber-500 text-white ring-2 ring-amber-400/40';
  }
  return 'bg-muted text-muted-foreground border border-border';
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

export function SignalCard({
  signal,
  onInspect,
  onPaperExecuted,
  onDeleted,
  selectMode,
  isSelected,
  onToggleSelect,
}: {
  signal: SignalDTO;
  onInspect?: (signalId: string) => void;
  onPaperExecuted?: (result: any) => void;
  onDeleted?: (signalId: string) => void;
  selectMode?: boolean;
  isSelected?: boolean;
  onToggleSelect?: (id: string) => void;
}) {
  const router = useRouter();
  const [executing, setExecuting] = useState(false);
  const [paperResult, setPaperResult] = useState<any>(signal.paper_order || null);
  const [execError, setExecError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [armDelete, setArmDelete] = useState(false);
  const [levelsOpen, setLevelsOpen] = useState(false);
  const [nowMs, setNowMs] = useState(Date.now());
  const [toast, setToast] = useState<{ msg: string } | null>(null);

  const showToast = useCallback((msg: string) => {
    setToast({ msg });
    setTimeout(() => setToast(null), 5000);
  }, []);

  const market = useOptionalMarketDataContext();
  const isMarketClosed = market?.marketStatus?.session === 'CLOSED' || market?.marketStatus?.is_trading_day === false;

  const fsm = signal.fsm_state?.toUpperCase() || 'UNKNOWN';
  const isCall = signal.direction?.includes('CALL') || signal.direction === 'BULLISH';
  const isTargetHit = fsm.includes('TARGET');
  const isStopHit = fsm === 'STOP_LOSS_HIT';
  const isExpired = fsm === 'EXPIRED' || (
    ['DETECTED', 'VALIDATED', 'ARMED', 'CONFIRMED'].includes(fsm) && (
      (signal.expires_at_utc ? nowMs > signal.expires_at_utc : false) || isMarketClosed
    )
  );

  const dirColor = isCall ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400';
  const dirBg = isCall ? 'bg-emerald-500/10' : 'bg-rose-500/10';

  const handleExecutePaper = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setExecuting(true);
    setExecError(null);
    try {
      const res = await api.executeSignalPaper(signal.signal_id);
      if (res && res.success) {
        setPaperResult(res);
        onPaperExecuted?.(res);
        showToast(`Paper trade placed — ${res.lots || 2} Lots @ ₹${safeNum(res.fill_price)}. View in Paper Trading →`);
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

  const stageIndex = getStageIndex(fsm);
  const preEntryExpired = fsm === 'ARMED' && signal.expires_at_utc ? nowMs > signal.expires_at_utc : false;

  const ttlSec = signal.ttl_seconds || (signal.is_scalp ? 180 : 300);
  const expiresAt = signal.expires_at_utc || (signal.created_at_utc ? signal.created_at_utc + (ttlSec * 1000) : 0);
  const preEntrySecRemaining = expiresAt > 0 ? Math.max(0, Math.floor((expiresAt - nowMs) / 1000)) : null;

  const timeStopSecRemaining =
    typeof signal.time_stop_at_utc === 'number' && signal.time_stop_at_utc > 0
      ? Math.max(0, Math.floor((signal.time_stop_at_utc - nowMs) / 1000))
      : null;

  const formatSec = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}m ${s.toString().padStart(2, '0')}s`;
  };

  // ── Local card timer: each card updates only itself ──
  useEffect(() => {
    const tick = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(tick);
  }, []);

  let ttlBadge = null;
  if (isMarketClosed) {
    ttlBadge = (
      <span className="inline-flex items-center gap-1 font-mono text-[10px] text-muted-foreground px-1.5 py-0.5 rounded bg-muted/50">
        <Clock className="w-3 h-3" />
        <span>Next: 09:15</span>
      </span>
    );
  } else if (['ARMED', 'VALIDATED'].includes(fsm) && preEntrySecRemaining !== null) {
    if (preEntrySecRemaining > 60) {
      ttlBadge = (
        <span className="inline-flex items-center gap-1 font-mono text-[10px] font-semibold px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/20">
          <Hourglass className="w-3 h-3 text-emerald-600" />
          {formatSec(preEntrySecRemaining)}
        </span>
      );
    } else if (preEntrySecRemaining > 0) {
      ttlBadge = (
        <span className="inline-flex items-center gap-1 font-mono text-[10px] font-bold px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-700 dark:text-rose-300 border border-rose-500/30 animate-pulse">
          <Hourglass className="w-3 h-3 text-rose-600" />
          {preEntrySecRemaining}s!
        </span>
      );
    } else {
      ttlBadge = (
        <span className="inline-flex items-center gap-1 font-mono text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground border border-border">
          Expired
        </span>
      );
    }
  } else if (fsm === 'CONFIRMED' && timeStopSecRemaining !== null) {
    if (timeStopSecRemaining > 60) {
      ttlBadge = (
        <span className="inline-flex items-center gap-1 font-mono text-[10px] font-semibold px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-500/20">
          <Clock className="w-3 h-3 text-amber-600" />
          {formatSec(timeStopSecRemaining)}
        </span>
      );
    } else if (timeStopSecRemaining > 0) {
      ttlBadge = (
        <span className="inline-flex items-center gap-1 font-mono text-[10px] font-bold px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-700 dark:text-rose-300 border border-rose-500/30 animate-pulse">
          <Clock className="w-3 h-3 text-rose-600" />
          {timeStopSecRemaining}s
        </span>
      );
    }
  } else if (fsm === 'TARGET_1_HIT') {
    const runnerSecRemaining =
      typeof signal.runner_time_stop_at_utc === 'number' && signal.runner_time_stop_at_utc > 0
        ? Math.max(0, Math.floor((signal.runner_time_stop_at_utc - nowMs) / 1000))
        : null;
    if (runnerSecRemaining !== null && runnerSecRemaining > 0) {
      ttlBadge = (
        <span className="inline-flex items-center gap-1 font-mono text-[10px] font-semibold px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/20">
          <Clock className="w-3 h-3 text-emerald-600" />
          {formatSec(runnerSecRemaining)}
        </span>
      );
    }
  }

  const riskPtsNum = Number(signal.risk_points || 0);
  const slNum = Number(signal.current_stop_loss ?? signal.stop_loss);
  const triggerNum = Number(signal.trigger);
  const t1Num = Number(signal.target_1);
  const t2Num = Number(signal.target_2);

  return (
    <Card
      className={`p-3 space-y-2.5 cursor-pointer hover:shadow-md hover:border-primary/40 transition-all rounded-2xl border bg-card/70 ${isSelected ? 'ring-2 ring-primary border-primary' : ''}`}
      onClick={() => onInspect?.(signal.signal_id)}
    >
      {toast && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-2 text-[11px] font-mono text-emerald-700 dark:text-emerald-300 flex items-center justify-between gap-2">
          <span className="truncate">{toast.msg}</span>
          <button
            onClick={(e) => {
              e.stopPropagation();
              router.push('/paper-trading');
            }}
            className="shrink-0 font-bold underline underline-offset-2 hover:no-underline cursor-pointer"
            aria-label="Go to paper trading page"
          >
            View in Paper Trading →
          </button>
        </div>
      )}
      {/* ── Layer 1: Identity Bar ── */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          <span className="font-bold text-sm tracking-tight text-foreground truncate">{signal.underlying}</span>
          <span className={`text-xs font-mono font-bold flex items-center gap-0.5 px-1.5 py-0.5 rounded ${dirBg} ${dirColor}`}>
            {isCall ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
            {signal.direction}
          </span>
          <Badge variant="outline" className="text-[10px] font-mono px-1.5 py-0 border-border bg-secondary/40 text-muted-foreground">
            {signal.strategy}
          </Badge>
          <span className="text-[10px] font-mono text-muted-foreground">{signal.timeframe || '5M'}</span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {selectMode && (
            <div
              className={`w-4 h-4 rounded border flex items-center justify-center cursor-pointer ${isSelected ? 'bg-primary border-primary' : 'border-border'}`}
              onClick={(e) => {
                e.stopPropagation();
                onToggleSelect?.(signal.signal_id || signal.id || '');
              }}
            >
              {isSelected && <Check className="w-3 h-3 text-white" />}
            </div>
          )}
          {ttlBadge}
        </div>
      </div>

      {/* ── Layer 2: Price Geometry (collapsible) ── */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          setLevelsOpen(!levelsOpen);
        }}
        className="w-full flex items-center justify-between text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors"
        aria-expanded={levelsOpen}
      >
        <span className="flex items-center gap-1.5">
          <Crosshair className="w-3 h-3" />
          {levelsOpen ? 'Hide' : 'Show'} Levels
        </span>
        <span className="text-[10px]">
          SL {safeNum(slNum)} → T1 {safeNum(t1Num)} (1:{safeNum(signal.risk_reward_t2 ?? 3.0, 1)}R)
        </span>
        {levelsOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>

      {levelsOpen && (
        <div className="grid grid-cols-4 gap-2 text-[11px] font-mono p-2.5 rounded-xl bg-muted/40 border border-border/60 animate-in fade-in slide-in-from-top-1 duration-200">
          <div>
            <div className="text-muted-foreground text-[10px]">Stop Loss</div>
            <div className="text-destructive font-semibold mt-0.5">₹{safeNum(slNum)}</div>
            <div className="text-[10px] text-muted-foreground">
              {signal.breakeven_activated ? 'SL @ Cost' : `-${safeNum(riskPtsNum, 1)} pts`}
            </div>
          </div>
          <div>
            <div className="text-muted-foreground text-[10px]">Trigger</div>
            <div className="text-foreground font-semibold mt-0.5">₹{safeNum(triggerNum)}</div>
            <div className="text-[10px] text-muted-foreground truncate">
              {typeof signal.distance_to_trigger_pts === 'number' && Number.isFinite(signal.distance_to_trigger_pts)
                ? signal.distance_to_trigger_pts <= 0.5 ? '⚡ In Zone' : `${signal.distance_to_trigger_pts.toFixed(1)} pts`
                : '—'}
            </div>
          </div>
          <div>
            <div className="text-muted-foreground text-[10px]">Target 1</div>
            <div className="text-emerald-600 dark:text-emerald-400 font-semibold mt-0.5">₹{safeNum(t1Num)}</div>
            <div className="text-[10px] text-muted-foreground">1.5R</div>
          </div>
          <div>
            <div className="text-muted-foreground text-[10px]">Target 2</div>
            <div className="text-emerald-700 dark:text-emerald-300 font-semibold mt-0.5">₹{safeNum(t2Num)}</div>
            <div className="text-[10px] text-muted-foreground">3.0R</div>
          </div>
        </div>
      )}

      {/* ── Layer 3: Lifecycle + Actions ── */}
      <div className="flex items-center justify-between pt-1 border-t">
        <div className="flex items-center gap-2">
          {/* 5-stage stepper */}
          <div className="flex items-center gap-0.5">
            {STAGES.map((st, idx) => {
              const isPast = idx < stageIndex;
              const isCurrent = idx === stageIndex;
              return (
                <div
                  key={st.id}
                  className={`w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-mono font-bold transition-all ${stageColor(idx, stageIndex, preEntryExpired)}`}
                  title={st.id}
                >
                  {isPast ? <Check className="w-2.5 h-2.5 text-white" /> : st.label}
                </div>
              );
            })}
          </div>
          {fsm !== 'CONFIRMED' && fsm !== 'TARGET_1_HIT' && fsm !== 'TARGET_2_HIT' && fsm !== 'STOP_LOSS_HIT' && (
            <span className="text-[10px] font-mono text-muted-foreground hidden sm:inline">
              {fsm}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
            onClick={(e) => {
              e.stopPropagation();
              onInspect?.(signal.signal_id);
            }}
            title="Inspect signal logic"
            aria-label={`Inspect ${signal.underlying} signal`}
          >
            <Crosshair className="w-3.5 h-3.5" />
          </Button>

          {!paperResult && !isExpired && !isTargetHit && !isStopHit && !isMarketClosed && (
            <Button
              size="sm"
              className="h-7 text-[11px] bg-emerald-600 hover:bg-emerald-700 text-white font-medium gap-1 px-2.5 shadow-sm"
              onClick={handleExecutePaper}
              disabled={executing}
            >
              <Zap className="w-3 h-3" />
              {executing ? '…' : 'Paper'}
            </Button>
          )}

          <Button
            size="sm"
            variant="ghost"
            className={`h-7 w-7 p-0 ${armDelete ? 'text-destructive bg-destructive/10' : 'text-muted-foreground hover:text-destructive'}`}
            onClick={handleDelete}
            disabled={deleting}
            title={armDelete ? 'Confirm delete' : 'Delete signal'}
            aria-label={armDelete ? 'Confirm delete signal' : 'Delete signal'}
          >
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

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
            const effectivePts = isOption ? (spotDiff * 0.5) : spotDiff;
            const qty = Number(paperResult.quantity || lotSize);
            if (!Number.isFinite(qty) || qty <= 0) return null;
            let pnl = effectivePts * qty;
            if (isOption && fillP > 0) {
              const maxLoss = fillP * qty;
              if (pnl < -maxLoss) pnl = -maxLoss;
            }
            const isProfit = pnl >= 0;
            return (
              <div className="flex items-center justify-between pt-1 border-t border-emerald-500/20 text-[10px]">
                <span className="text-muted-foreground flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-ping" />
                  Live MTM:
                </span>
                <span className={`font-bold ${isProfit ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                  {pnl >= 0 ? `+₹${pnl.toFixed(2)}` : `-₹${Math.abs(pnl).toFixed(2)}`}
                </span>
              </div>
            );
          })()}
        </div>
      )}

      {execError && <span className="text-[10px] text-destructive font-mono block">{execError}</span>}
    </Card>
  );
}
