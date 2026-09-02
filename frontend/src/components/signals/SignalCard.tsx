'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { api } from '@/lib/api';
import { Calendar, Clock, Target, TrendingUp, TrendingDown, Zap, CheckCircle2 } from 'lucide-react';

export type SignalDTO = {
  signal_id: string;
  instrument_id: string;
  display_name?: string;
  engine?: string;
  strategy?: string;
  status: string;
  direction: string;
  setup_type?: string;
  candle_timeframe?: string;
  trigger_level?: string | null;
  price?: string | null;
  price_formatted?: string | null;
  confidence?: number | null;
  breakout_pressure?: number | null;
  false_breakout_risk?: number | null;
  breakout_quality?: number | null;
  ttl_ms?: number;
  created_at_utc?: number;
  expires_at_utc?: number;
  fsm_state?: string;
  short_horizon?: any;
  continuation?: any;
  paper_order?: any;
  session?: string;
  data_health?: string;
};

function StatusBadge({ status }: { status: string }) {
  const s = status.toUpperCase();
  if (s === 'CONFIRMED') return <Badge className="bg-emerald-500 text-white border-emerald-600">CONFIRMED</Badge>;
  if (s === 'TRIGGERED') return <Badge className="bg-amber-500 text-black border-amber-600">TRIGGERED</Badge>;
  if (s.includes('POSSIBLE')) return <Badge className="bg-sky-500 text-white border-sky-600">{s}</Badge>;
  if (s === 'WATCH') return <Badge className="bg-amber-400 text-black">WATCH</Badge>;
  if (s === 'EXPIRED') return <Badge variant="outline" className="border-red-300 text-red-600">EXPIRED</Badge>;
  if (s === 'NO_SETUP') return <Badge variant="secondary">NO_SETUP</Badge>;
  return <Badge variant="outline">{s}</Badge>;
}

function formatSignalDateTime(tsMs?: number | null): string {
  if (!tsMs) return 'Just now';
  const d = new Date(tsMs);
  return d.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'Asia/Kolkata',
  }) + ' IST';
}

export function SignalCard({
  signal,
  onClick,
  onPaperExecuted,
}: {
  signal: SignalDTO;
  onClick?: () => void;
  onPaperExecuted?: (result: any) => void;
}) {
  const [executing, setExecuting] = useState(false);
  const [paperResult, setPaperResult] = useState<any>(signal.paper_order || null);
  const [execError, setExecError] = useState<string | null>(null);

  const isConfirmed = signal.status === 'CONFIRMED';
  const isTriggered = signal.status === 'TRIGGERED';
  const isPossible = signal.status.includes('POSSIBLE');
  const isExpired = signal.status === 'EXPIRED' || (signal.expires_at_utc ? Date.now() > signal.expires_at_utc : false);
  const isNoSetup = signal.status === 'NO_SETUP';

  const borderClass = isExpired
    ? 'border-border bg-muted/30 opacity-60'
    : isConfirmed
      ? 'border-emerald-500 bg-emerald-50/70 border-2'
      : isTriggered
        ? 'border-amber-400 bg-amber-50/70 border-2'
        : isPossible
          ? 'border-sky-500 bg-sky-50/70 border-2'
          : isNoSetup
            ? 'border-border bg-muted/30 opacity-75'
            : 'bg-card border-border';

  const directionColor =
    signal.direction === 'BULLISH' || signal.direction === 'LONG'
      ? 'text-emerald-600'
      : signal.direction === 'BEARISH' || signal.direction === 'SHORT'
        ? 'text-red-600'
        : 'text-muted-foreground';

  const ttlRemaining = signal.expires_at_utc ? Math.max(0, signal.expires_at_utc - Date.now()) : null;
  const ttlSec = ttlRemaining !== null ? (ttlRemaining / 1000).toFixed(1) : null;
  const timeStr = formatSignalDateTime(signal.created_at_utc);

  const handleExecutePaper = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setExecuting(true);
    setExecError(null);
    try {
      const res = await api.executeSignalPaper(signal.signal_id);
      if (res && res.paper_order) {
        setPaperResult(res.paper_order);
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
      className={`p-4 space-y-2.5 cursor-pointer hover:shadow-md transition-shadow ${borderClass}`}
      onClick={onClick}
    >
      <div className="flex justify-between items-start gap-2">
        <div>
          <div className="font-bold text-sm flex items-center gap-1.5 flex-wrap">
            {signal.display_name || signal.instrument_id}{' '}
            <span className="font-mono text-xs text-muted-foreground">{signal.instrument_id}</span>
            {signal.candle_timeframe && (
              <span className="text-[11px] font-mono bg-secondary px-1.5 py-0.5 rounded border">{signal.candle_timeframe}</span>
            )}
            <span className="text-[11px] font-mono text-muted-foreground flex items-center gap-1 ml-1 bg-background/80 px-1.5 py-0.5 rounded border">
              <Calendar className="w-3 h-3 text-primary" /> {timeStr}
            </span>
          </div>
          <div className="text-xs font-mono text-muted-foreground mt-0.5">
            {signal.price_formatted ? `Price ${signal.price_formatted}` : ''}
            {signal.session ? ` • Session ${signal.session}` : ''}
            {signal.data_health ? ` • ${signal.data_health}` : ''}
            {signal.engine ? ` • ${signal.engine}` : ''}
          </div>
        </div>
        <StatusBadge status={signal.status} />
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Direction</span>
          <span className={`font-bold flex items-center gap-1 ${directionColor}`}>
            {signal.direction === 'BULLISH' || signal.direction === 'LONG' ? <TrendingUp className="w-3 h-3" /> : null}
            {signal.direction === 'BEARISH' || signal.direction === 'SHORT' ? <TrendingDown className="w-3 h-3" /> : null}
            {signal.direction}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Strategy</span>
          <span className="font-mono font-medium">{signal.strategy || 'BREAKOUT'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Trigger</span>
          <span className="font-mono font-bold">{signal.trigger_level || '—'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Confidence</span>
          <span className="font-mono font-bold">{signal.confidence != null ? `${signal.confidence}%` : '—'}</span>
        </div>
        {signal.breakout_pressure != null && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Pressure</span>
            <span className="font-mono">{signal.breakout_pressure}/100</span>
          </div>
        )}
        {signal.false_breakout_risk != null && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">False Risk</span>
            <span className={`font-mono ${Number(signal.false_breakout_risk) > 60 ? 'text-red-600 font-bold' : ''}`}>{signal.false_breakout_risk}/100</span>
          </div>
        )}
      </div>

      {signal.short_horizon && signal.short_horizon.entry_zone && (
        <div className="text-[11px] font-mono bg-secondary/50 rounded p-1.5 border">
          <span className="text-muted-foreground">10m Entry:</span>{' '}
          {Array.isArray(signal.short_horizon.entry_zone) ? `${signal.short_horizon.entry_zone[0]}–${signal.short_horizon.entry_zone[1]}` : signal.short_horizon.entry_zone}{' '}
          <span className="text-muted-foreground">Stop:</span> {signal.short_horizon.stop_loss || '—'}
        </div>
      )}

      {/* Paper Trading Status & 1-Click Action */}
      <div className="pt-1 flex items-center justify-between gap-2 border-t text-xs">
        {paperResult ? (
          <div className="flex items-center gap-1.5 text-emerald-700 font-mono text-[11px] bg-emerald-100/70 border border-emerald-300 rounded px-2 py-0.5">
            <CheckCircle2 className="w-3.5 h-3.5" /> Paper: {paperResult.side} {paperResult.quantity} @ ₹{paperResult.fill_price ? Number(paperResult.fill_price).toLocaleString('en-IN') : '—'} ({paperResult.order_id})
          </div>
        ) : (
          !isNoSetup && !isExpired && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border-emerald-300 font-medium"
              onClick={handleExecutePaper}
              disabled={executing}
            >
              <Zap className="w-3 h-3 mr-1 text-emerald-600" />
              {executing ? 'Executing…' : '⚡ Paper Trade'}
            </Button>
          )
        )}
        {execError && <span className="text-[10px] text-destructive">{execError}</span>}
      </div>

      <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-1">
        <span className="flex items-center gap-1">
          <Clock className="w-3 h-3" />
          TTL {signal.ttl_ms ? `${signal.ttl_ms / 1000}s` : '5s'}
          {ttlSec !== null && !isExpired && !isNoSetup ? ` • ${ttlSec}s left` : ''}
          {isExpired ? ' • EXPIRED' : ''}
        </span>
        <span className="font-mono text-[10px]">{signal.signal_id.slice(0, 8)}…</span>
      </div>
    </Card>
  );
}
