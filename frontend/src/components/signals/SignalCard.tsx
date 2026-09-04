'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { api } from '@/lib/api';
import { safeNum, safeState, ttlLabel } from '@/lib/signal-utils';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import {
  ArrowDownRight,
  ArrowUpRight,
  Calendar,
  CheckCircle2,
  Clock,
  Crosshair,
  ExternalLink,
  Flame,
  Radio,
  Target,
  TrendingDown,
  TrendingUp,
  Trash2,
  Zap,
} from 'lucide-react';

export type SignalDTO = {
  signal_id: string;
  underlying: string;
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
  expires_at_utc: number;
  ttl_seconds?: number;
  distance_to_trigger_pts?: number | null;
  distance_to_trigger_pct?: number | null;
  paper_order?: any;
};

function StatusBadge({ status, isMarketClosed }: { status: string; isMarketClosed?: boolean }) {
  const s = status.toUpperCase();
  if (['DETECTED', 'VALIDATED', 'ARMED', 'CONFIRMED'].includes(s) && isMarketClosed) {
    return <Badge variant="outline" className="border-slate-500/40 text-muted-foreground bg-muted/40">MARKET CLOSED</Badge>;
  }
  if (s === 'CONFIRMED') return <Badge className="bg-emerald-500 text-white border-emerald-600 animate-pulse">CONFIRMED</Badge>;
  if (s === 'TARGET_1_HIT') return <Badge className="bg-emerald-600 text-white font-bold">🎯 T1 HIT • RUNNER ACTIVE</Badge>;
  if (s === 'TARGET_2_HIT') return <Badge className="bg-emerald-700 text-white font-bold">🏁 TARGET 2 HIT (+3.0R)</Badge>;
  if (s === 'STOP_LOSS_HIT') return <Badge variant="destructive">🛑 STOP LOSS HIT</Badge>;
  if (s === 'TIME_STOP_HIT') return <Badge variant="outline" className="border-amber-500 text-amber-600 font-bold">⏱️ TIME STOP HIT</Badge>;
  if (s === 'RUNNER_TIME_STOP_HIT') return <Badge variant="outline" className="border-amber-600 text-amber-700 font-bold">⏱️ RUNNER TIME STOP</Badge>;
  if (s === 'TRIGGERED') return <Badge className="bg-amber-500 text-black border-amber-600">TRIGGERED</Badge>;
  if (s === 'ARMED') return <Badge className="bg-sky-500 text-white border-sky-600">ARMED</Badge>;
  if (s === 'VALIDATED') return <Badge variant="secondary">VALIDATED</Badge>;
  if (s === 'EXPIRED') return <Badge variant="outline" className="border-red-300 text-red-600">EXPIRED</Badge>;
  if (s === 'INVALIDATED') return <Badge variant="destructive">INVALIDATED</Badge>;
  return <Badge variant="outline">{s}</Badge>;
}

function StrategyBadge({ strategy }: { strategy: string }) {
  const colors: Record<string, string> = {
    BREAKOUT: 'bg-indigo-500/10 text-indigo-700 border-indigo-500/20',
    MEAN_REVERSION: 'bg-purple-500/10 text-purple-700 border-purple-500/20',
    TREND_PULLBACK: 'bg-blue-500/10 text-blue-700 border-blue-500/20',
    GAMMA_SQUEEZE: 'bg-amber-500/10 text-amber-700 border-amber-500/20',
    ORB: 'bg-emerald-500/10 text-emerald-700 border-emerald-500/20',
    VWAP_SCALP: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20 font-bold',
    MICRO_MOMENTUM: 'bg-amber-500/10 text-amber-600 border-amber-500/20 font-bold',
    EMA_RIBBON: 'bg-cyan-500/10 text-cyan-600 border-cyan-500/20 font-bold',
    GAMMA_SPIKE: 'bg-rose-500/10 text-rose-600 border-rose-500/20 font-bold',
  };
  return <Badge variant="outline" className={`text-[10px] font-mono ${colors[strategy] || ''}`}>{strategy}</Badge>;
}

export function SignalCard({
  signal,
  onInspect,
  onPaperExecuted,
  onDeleted,
  nowMs,
}: {
  signal: SignalDTO;
  onInspect?: (signalId: string) => void;
  onPaperExecuted?: (result: any) => void;
  onDeleted?: (signalId: string) => void;
  /**
   * Shared page-level clock (ms). The signals page owns ONE 1s ticker and
   * passes it to every card — cards must NOT create their own timers
   * (100 cards = 1 timer, not 100).
   */
  nowMs: number;
}) {
  const [executing, setExecuting] = useState(false);
  const [paperResult, setPaperResult] = useState<any>(signal.paper_order || null);
  const [execError, setExecError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [armDelete, setArmDelete] = useState(false);

  const market = useOptionalMarketDataContext();
  const isMarketClosed = market?.marketStatus?.session === 'CLOSED' || market?.marketStatus?.is_trading_day === false;

  const fsm = safeState(signal.fsm_state);
  const isCall = signal.direction?.includes('CALL') || signal.direction === 'BULLISH';
  const isConfirmed = fsm === 'CONFIRMED';
  const isTargetHit = fsm.includes('TARGET');
  const isStopHit = fsm === 'STOP_LOSS_HIT';
  const isExpired = fsm === 'EXPIRED' || (
    ['DETECTED', 'VALIDATED', 'ARMED', 'CONFIRMED'].includes(fsm) && (
      (signal.expires_at_utc ? nowMs > signal.expires_at_utc : false) || isMarketClosed
    )
  );

  const borderClass = isTargetHit
    ? 'border-emerald-500 bg-emerald-50/70 border-2'
    : isStopHit
      ? 'border-destructive/60 bg-destructive/10 border-2'
      : isConfirmed && !isMarketClosed
        ? 'border-emerald-500 bg-emerald-50/50 border-2'
        : isExpired || isMarketClosed
          ? 'border-border bg-muted/30 opacity-70'
          : 'bg-card border-border hover:border-primary/50';

  const dirColor = isCall ? 'text-emerald-600' : 'text-red-600';

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

  // Trigger-gap edge check (mirrors backend trigger_gate): gap < min ⇒ born-triggered noise.
  const triggerEdge = (() => {
    const spotP = Number(signal.spot_price);
    const trigP = Number(signal.trigger);
    const riskP = Number(signal.risk_points);
    if (!Number.isFinite(spotP) || !Number.isFinite(trigP) || spotP <= 0 || trigP <= 0) return null;
    const gap = Math.abs(trigP - spotP);
    const minGap = Math.max(spotP * 0.0005, (Number.isFinite(riskP) ? Math.abs(riskP) : 0) * 0.1, 0.1);
    return { gap, minGap, noEdge: gap < minGap };
  })();

  return (
    <Card
      className={`p-4 space-y-3 cursor-pointer hover:shadow-lg transition-all rounded-xl ${borderClass}`}
      onClick={() => onInspect?.(signal.signal_id)}
    >
      {/* Top Header */}
      <div className="flex justify-between items-start gap-2">
        <div className="space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-base tracking-tight">{signal.underlying}</span>
            <StrategyBadge strategy={signal.strategy} />
            {signal.is_scalp || signal.signal_type === 'SCALP' ? (
              <Badge className="bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30 text-[10px] font-bold">
                ⚡ {signal.timeframe || '1M'} SCALP
              </Badge>
            ) : (
              <Badge variant="secondary" className="text-[10px] font-mono">
                {signal.timeframe || '5M'}
              </Badge>
            )}
            {signal.breakeven_activated && (
              <Badge className="bg-emerald-500/15 text-emerald-600 border-emerald-500/30 text-[10px] font-mono font-bold">
                🛡️ SL @ COST
              </Badge>
            )}
            <span className={`text-xs font-bold flex items-center gap-0.5 ${dirColor}`}>
              {isCall ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
              {signal.direction}
            </span>
          </div>

          <div className="text-xs font-mono text-muted-foreground flex items-center gap-2">
            <span>Spot ₹{safeNum(signal.spot_price)}</span>
            {signal.option_contract?.strike && (
              <span className="bg-secondary/60 px-1.5 py-0.5 rounded text-[11px] border">
                {signal.option_contract.strike} {signal.option_contract.option_type} ({signal.option_contract.lot_size} lot)
              </span>
            )}
          </div>
        </div>

        <StatusBadge status={fsm} isMarketClosed={isMarketClosed} />
      </div>

      {/* Two-Clock Lifecycle Banner (§6, §20) */}
      {fsm === 'TARGET_1_HIT' ? (
        <div className="flex items-center justify-between text-[11px] font-mono px-2.5 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-700 dark:text-emerald-300">
          <span className="flex items-center gap-1 font-semibold">
            🎯 50% Profit Booked • Runner Mode Active
          </span>
          <span className="font-bold flex items-center gap-1">
            <Clock className="w-3 h-3 text-emerald-600" />
            {signal.runner_time_stop_at_utc
              ? `${Math.max(0, Math.round((signal.runner_time_stop_at_utc - nowMs) / 1000))}s Runner TTL`
              : 'Runner Clock'}
          </span>
        </div>
      ) : fsm === 'CONFIRMED' && (signal.is_scalp || signal.signal_type === 'SCALP') ? (
        <div className="flex items-center justify-between text-[11px] font-mono px-2.5 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-700 dark:text-amber-300">
          <span className="flex items-center gap-1 font-semibold">
            ⚡ High-Frequency Scalp Active
          </span>
          <span className="font-bold flex items-center gap-1">
            <Clock className="w-3 h-3 text-amber-600" />
            {ttlLabel(signal, nowMs)}
          </span>
        </div>
      ) : null}

      {/* Live Distance to Trigger Banner */}
      {typeof signal.distance_to_trigger_pts === 'number' && Number.isFinite(signal.distance_to_trigger_pts) && !isExpired && !isTargetHit && !isStopHit && fsm !== 'CONFIRMED' && (
        <div className="flex items-center justify-between text-[11px] font-mono px-2.5 py-1.5 rounded-lg bg-secondary/40 border">
          <span className="text-muted-foreground flex items-center gap-1">
            <Crosshair className="w-3.5 h-3.5 text-primary" /> Trigger Level: <span className="font-bold text-foreground">₹{safeNum(signal.trigger)}</span>
          </span>
          <span className={`font-bold ${typeof signal.distance_to_trigger_pct === 'number' && signal.distance_to_trigger_pct <= 0.1 ? 'text-emerald-600 animate-pulse' : 'text-primary'}`}>
            {signal.distance_to_trigger_pts > 0 ? `${signal.distance_to_trigger_pts.toFixed(1)} pts (${safeNum(signal.distance_to_trigger_pct)}%) away` : '⚡ Trigger Zone'}
          </span>
        </div>
      )}
      {triggerEdge?.noEdge && !isExpired && !isTargetHit && !isStopHit && (
        <div className="text-[10px] font-mono px-2.5 py-1.5 rounded-lg bg-destructive/10 border border-destructive/30 text-destructive font-bold">
          NO EDGE — trigger {triggerEdge.gap.toFixed(1)}pts from spot (needs ≥ {triggerEdge.minGap.toFixed(1)}pts). Born-triggered noise.
        </div>
      )}

      {/* Target & Stop Loss Progress Bar */}
      <div className="space-y-1 pt-1">
        <div className="flex justify-between text-[11px] font-mono text-muted-foreground">
          <span className="text-destructive font-semibold">
            SL ₹{safeNum(signal.current_stop_loss ?? signal.stop_loss)}
            {signal.breakeven_activated && ' (Cost)'}
          </span>
          <span className="text-emerald-600 font-semibold">T1 ₹{safeNum(signal.target_1)} (1.5R)</span>
          <span className="text-emerald-700 font-bold">T2 ₹{safeNum(signal.target_2)} (3.0R)</span>
        </div>
        <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden flex">
          <div className="h-full bg-destructive/60 w-1/4" title="Stop Loss Zone" />
          <div className="h-full bg-primary/40 w-1/4" title="Entry Zone" />
          <div className="h-full bg-emerald-400 w-1/4" title="Target 1" />
          <div className="h-full bg-emerald-600 w-1/4" title="Target 2" />
        </div>
      </div>

      {/* Confluence & Confidence Footer */}
      <div className="grid grid-cols-2 gap-2 text-xs pt-1 border-t">
        <div className="flex justify-between items-center">
          <span className="text-muted-foreground text-[11px]">Confidence</span>
          <span className="font-mono font-bold text-primary">{safeNum(signal.confidence, 1)}%</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-muted-foreground text-[11px]">Risk:Reward</span>
          <span className="font-mono font-bold text-emerald-600">1:{safeNum(signal.risk_reward_t2 ?? 3.0, 1)} R:R</span>
        </div>
      </div>
      {(signal as { data_quality?: string }).data_quality === 'DEGRADED' && (
        <p className="text-[10px] text-amber-600 font-mono">⚠ Live price degraded — distance/TTL may be stale</p>
      )}

      {/* Paper Trading Status & 1-Click Action */}
      <div className="pt-2 flex items-center justify-between gap-2 border-t text-xs">
        {paperResult ? (
          <div className="flex flex-col gap-1 w-full text-[11px] bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-2 font-mono">
            <div className="flex items-center justify-between text-emerald-700 dark:text-emerald-300">
              <span className="flex items-center gap-1 font-bold text-[11px]">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> Paper: {safeNum(paperResult.quantity, 0)} Qty @ ₹{safeNum(paperResult.fill_price)}
              </span>
              <span className="text-[10px] text-muted-foreground">{paperResult.order_id || ''}</span>
            </div>
            {(() => {
              const spotP = Number(signal.spot_price);
              const trigP = Number(signal.trigger ?? signal.spot_price);
              if (!Number.isFinite(spotP) || !Number.isFinite(trigP) || trigP <= 0) return null;
              const isBull = signal.direction?.includes('CALL') || signal.direction === 'BULLISH';
              const pts = isBull ? spotP - trigP : trigP - spotP;
              const qty = Number(paperResult.quantity || 75);
              if (!Number.isFinite(qty) || qty <= 0) return null;
              const pnl = pts * qty;
              const isProfit = pnl >= 0;
              return (
                <div className="flex items-center justify-between pt-1 border-t border-emerald-500/20 text-[10px]">
                  <span className="text-muted-foreground flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-ping" />
                    Live MTM:
                  </span>
                  <span className={`font-bold ${isProfit ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                    {pnl >= 0 ? `+₹${pnl.toFixed(2)}` : `-₹${Math.abs(pnl).toFixed(2)}`} ({pts >= 0 ? '+' : ''}{pts.toFixed(1)} pts)
                  </span>
                </div>
              );
            })()}
          </div>
        ) : (
          <div className="flex items-center justify-between w-full gap-2">
            {!isExpired && !isTargetHit && !isStopHit ? (
              isMarketClosed ? (
                <Badge variant="outline" className="h-7 text-[10px] font-mono text-muted-foreground border-border bg-muted/30">
                  Market Closed
                </Badge>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 text-xs bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border-emerald-300 font-semibold gap-1.5"
                  onClick={handleExecutePaper}
                  disabled={executing}
                >
                  <Zap className="w-3.5 h-3.5 text-emerald-600" />
                  {executing ? 'Executing…' : '⚡ 1-Click Paper Order'}
                </Button>
              )
            ) : (
              <span className="text-[11px] font-mono text-muted-foreground">
                {isMarketClosed ? 'Market Closed' : isExpired ? 'Expired' : isTargetHit ? 'Target Completed' : isStopHit ? 'Stop Hit' : ''}
              </span>
            )}
            <div className="flex items-center gap-1">
              <Button
                size="sm"
                variant="ghost"
                className="h-8 text-xs text-muted-foreground hover:text-foreground gap-1"
                onClick={(e) => {
                  e.stopPropagation();
                  onInspect?.(signal.signal_id);
                }}
              >
                Inspect <ExternalLink className="w-3 h-3" />
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className={`h-8 w-8 p-0 ${armDelete ? 'text-destructive bg-destructive/10' : 'text-muted-foreground hover:text-destructive'}`}
                onClick={handleDelete}
                disabled={deleting}
                title={armDelete ? 'Tap again to confirm delete' : 'Delete signal'}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>
        )}
        {execError && <span className="text-[10px] text-destructive">{execError}</span>}
      </div>
    </Card>
  );
}
