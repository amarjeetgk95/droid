'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { api } from '@/lib/api';
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
  target_1: number | string;
  target_2: number | string;
  risk_points: number | string;
  risk_reward_t1: number;
  risk_reward_t2: number;
  confidence: number;
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

function StatusBadge({ status }: { status: string }) {
  const s = status.toUpperCase();
  if (s === 'CONFIRMED') return <Badge className="bg-emerald-500 text-white border-emerald-600 animate-pulse">CONFIRMED</Badge>;
  if (s === 'TARGET_1_HIT') return <Badge className="bg-emerald-600 text-white font-bold">🎯 TARGET 1 HIT (+1.5R)</Badge>;
  if (s === 'TARGET_2_HIT') return <Badge className="bg-emerald-700 text-white font-bold">🏁 TARGET 2 HIT (+3.0R)</Badge>;
  if (s === 'STOP_LOSS_HIT') return <Badge variant="destructive">🛑 STOP LOSS HIT</Badge>;
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
  };
  return <Badge variant="outline" className={`text-[10px] font-mono ${colors[strategy] || ''}`}>{strategy}</Badge>;
}

export function SignalCard({
  signal,
  onInspect,
  onPaperExecuted,
}: {
  signal: SignalDTO;
  onInspect?: (signalId: string) => void;
  onPaperExecuted?: (result: any) => void;
}) {
  const [executing, setExecuting] = useState(false);
  const [paperResult, setPaperResult] = useState<any>(signal.paper_order || null);
  const [execError, setExecError] = useState<string | null>(null);

  const isCall = signal.direction?.includes('CALL') || signal.direction === 'BULLISH';
  const isConfirmed = signal.fsm_state === 'CONFIRMED';
  const isTargetHit = signal.fsm_state.includes('TARGET');
  const isStopHit = signal.fsm_state === 'STOP_LOSS_HIT';
  const isExpired = signal.fsm_state === 'EXPIRED' || (signal.expires_at_utc ? Date.now() > signal.expires_at_utc : false);

  const borderClass = isTargetHit
    ? 'border-emerald-500 bg-emerald-50/70 border-2'
    : isStopHit
      ? 'border-destructive/60 bg-destructive/10 border-2'
      : isConfirmed
        ? 'border-emerald-500 bg-emerald-50/50 border-2'
        : isExpired
          ? 'border-border bg-muted/30 opacity-60'
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
            <Badge variant="secondary" className="text-[10px] font-mono">
              {signal.timeframe || '5M'}
            </Badge>
            <span className={`text-xs font-bold flex items-center gap-0.5 ${dirColor}`}>
              {isCall ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
              {signal.direction}
            </span>
          </div>

          <div className="text-xs font-mono text-muted-foreground flex items-center gap-2">
            <span>Spot ₹{Number(signal.spot_price).toLocaleString('en-IN')}</span>
            {signal.option_contract?.strike && (
              <span className="bg-secondary/60 px-1.5 py-0.5 rounded text-[11px] border">
                {signal.option_contract.strike} {signal.option_contract.option_type} ({signal.option_contract.lot_size} lot)
              </span>
            )}
          </div>
        </div>

        <StatusBadge status={signal.fsm_state} />
      </div>

      {/* Live Distance to Trigger Banner */}
      {signal.distance_to_trigger_pts !== null && signal.distance_to_trigger_pts !== undefined && !isExpired && !isTargetHit && !isStopHit && (
        <div className="flex items-center justify-between text-[11px] font-mono px-2.5 py-1.5 rounded-lg bg-secondary/40 border">
          <span className="text-muted-foreground flex items-center gap-1">
            <Crosshair className="w-3.5 h-3.5 text-primary" /> Trigger Level: <span className="font-bold text-foreground">₹{Number(signal.trigger).toLocaleString('en-IN')}</span>
          </span>
          <span className={`font-bold ${signal.distance_to_trigger_pct! <= 0.1 ? 'text-emerald-600 animate-pulse' : 'text-primary'}`}>
            {signal.distance_to_trigger_pts > 0 ? `${signal.distance_to_trigger_pts.toFixed(1)} pts (${signal.distance_to_trigger_pct}%) away` : '⚡ Trigger Zone'}
          </span>
        </div>
      )}

      {/* Target & Stop Loss Progress Bar */}
      <div className="space-y-1 pt-1">
        <div className="flex justify-between text-[11px] font-mono text-muted-foreground">
          <span className="text-destructive font-semibold">SL ₹{Number(signal.stop_loss).toLocaleString('en-IN')}</span>
          <span className="text-emerald-600 font-semibold">T1 ₹{Number(signal.target_1).toLocaleString('en-IN')} (1.5R)</span>
          <span className="text-emerald-700 font-bold">T2 ₹{Number(signal.target_2).toLocaleString('en-IN')} (3.0R)</span>
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
          <span className="font-mono font-bold text-primary">{signal.confidence}%</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-muted-foreground text-[11px]">Risk:Reward</span>
          <span className="font-mono font-bold text-emerald-600">1:{signal.risk_reward_t2 || 3.0} R:R</span>
        </div>
      </div>

      {/* Paper Trading Status & 1-Click Action */}
      <div className="pt-2 flex items-center justify-between gap-2 border-t text-xs">
        {paperResult ? (
          <div className="flex items-center gap-1.5 text-emerald-700 font-mono text-[11px] bg-emerald-100/70 border border-emerald-300 rounded-lg px-2.5 py-1 w-full justify-between">
            <span className="flex items-center gap-1 font-bold">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> Paper: {paperResult.side} {paperResult.quantity} Qty @ ₹{Number(paperResult.fill_price).toLocaleString('en-IN')}
            </span>
            <span className="text-[10px] text-muted-foreground font-mono">{paperResult.order_id}</span>
          </div>
        ) : (
          !isExpired && !isTargetHit && !isStopHit && (
            <div className="flex items-center justify-between w-full gap-2">
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
            </div>
          )
        )}
        {execError && <span className="text-[10px] text-destructive">{execError}</span>}
      </div>
    </Card>
  );
}
