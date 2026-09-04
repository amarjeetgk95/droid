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
}: {
  signal: SignalDTO;
  onInspect?: (signalId: string) => void;
  onPaperExecuted?: (result: any) => void;
  onDeleted?: (signalId: string) => void;
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
  const isTargetHit = fsm.includes('TARGET');
  const isStopHit = fsm === 'STOP_LOSS_HIT';
  const isExpired = fsm === 'EXPIRED' || (
    ['DETECTED', 'VALIDATED', 'ARMED', 'CONFIRMED'].includes(fsm) && (
      (signal.expires_at_utc ? nowMs > signal.expires_at_utc : false) || isMarketClosed
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
          <span className="text-[10px] font-mono text-muted-foreground">
            TTL: {ttlLabel(signal, nowMs)}
          </span>
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
            const trigP = Number(signal.trigger ?? signal.spot_price);
            if (!Number.isFinite(spotNum) || !Number.isFinite(trigP) || trigP <= 0) return null;
            const pts = isCall ? spotNum - trigP : trigP - spotNum;
            const qty = Number(paperResult.quantity || lotSize);
            if (!Number.isFinite(qty) || qty <= 0) return null;
            const pnl = pts * qty;
            const isProfit = pnl >= 0;
            return (
              <div className="flex items-center justify-between pt-1 border-t border-emerald-500/20 text-[10px]">
                <span className="text-muted-foreground flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-ping" />
                  Live Open MTM:
                </span>
                <span className={`font-bold ${isProfit ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                  {pnl >= 0 ? `+₹${pnl.toFixed(2)}` : `-₹${Math.abs(pnl).toFixed(2)}`} ({pts >= 0 ? '+' : ''}{pts.toFixed(1)} pts)
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
