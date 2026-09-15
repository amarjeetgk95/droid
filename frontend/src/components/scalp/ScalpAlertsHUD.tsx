'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Radio, AlertTriangle, CheckCircle2, Clock, Play, RefreshCw, Zap, Bot } from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/toast';
import { useScalpContext } from './ScalpContext';
import { useSmartInterval } from '@/hooks/useSmartInterval';
import { useExecutionGuard } from '@/hooks/useExecutionGuard';

export interface ScalpSignalItem {
  id: string;
  symbol: string;
  strategy: string;
  direction: string;
  trigger: number | null;
  sl: number | null;
  target: number | null;
  confidence: number | null;
  status: string;
  created_at?: string;
  ttl_seconds?: number;
}

export interface AutoPilotConfig {
  enabled: boolean;
  minConfidence: number;
  maxConcurrent: number;
  maxDailyLoss: number;
  antiChaseTolerance: number;
  soundAlerts: boolean;
}

interface ScalpAlertsHUDProps {
  currentSpot?: number | null;
  underlying?: 'NIFTY' | 'BANKNIFTY' | 'SENSEX';
  onExecuteSignal?: (signalId: string) => void;
  autoPilot?: AutoPilotConfig;
  onAutoExecute?: (signal: ScalpSignalItem) => void;
  executedSignalIds?: Set<string>;
}

const SCALP_STRATEGIES = new Set([
  'VWAP_SCALP',
  'MICRO_MOMENTUM',
  'EMA_RIBBON',
  'GAMMA_SPIKE',
  'ORB',
]);

export function ScalpAlertsHUD(props: ScalpAlertsHUDProps) {
  const toast = useToast();
  const scalpCtx = useScalpContext();

  const underlying = props.underlying || scalpCtx.underlying;
  const currentSpot = props.currentSpot !== undefined ? props.currentSpot : scalpCtx.spotPrice;
  const autoPilot = props.autoPilot || scalpCtx.autoPilot;
  const { onExecuteSignal, onAutoExecute, executedSignalIds } = props;

  const [signals, setSignals] = useState<ScalpSignalItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState<number>(() => Date.now());
  const [scanning, setScanning] = useState(false);

  const { isPending: executingSignal, execute: executeGuard } = useExecutionGuard();

  const autoPilotRef = useRef(autoPilot);
  autoPilotRef.current = autoPilot;

  const onAutoExecuteRef = useRef(onAutoExecute);
  onAutoExecuteRef.current = onAutoExecute;

  const executedIdsRef = useRef(executedSignalIds);
  executedIdsRef.current = executedSignalIds;

  const currentSpotRef = useRef(currentSpot);
  currentSpotRef.current = currentSpot;

  // TTL second ticker
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const fetchScalpSignals = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.getSignalsActive({ desk: 'SCALP' });
      const items = (res.signals || []) as unknown as ScalpSignalItem[];

      const filtered = items.filter((s) => {
        const strat = (s.strategy || '').toUpperCase();
        return SCALP_STRATEGIES.has(strat) || strat.includes('SCALP') || strat.includes('MOMENTUM');
      });
      setSignals(filtered);

      // Auto-Pilot Evaluation
      const ap = autoPilotRef.current;
      const autoExec = onAutoExecuteRef.current;
      const execSet = executedIdsRef.current;
      const spot = currentSpotRef.current;

      if (ap?.enabled && autoExec) {
        for (const sig of filtered) {
          if (execSet?.has(sig.id)) continue;

          // Check TTL
          const createdAtMs = sig.created_at ? new Date(sig.created_at).getTime() : Date.now();
          const ttlTotalSec = sig.ttl_seconds || 60;
          const elapsedSec = Math.floor((Date.now() - createdAtMs) / 1000);
          if (elapsedSec >= ttlTotalSec) continue;

          // Check Confidence
          const conf = sig.confidence ?? 80;
          if (conf < ap.minConfidence) continue;

          // Check Anti-Chase tolerance
          if (spot && sig.trigger) {
            const dist = Math.abs(spot - sig.trigger);
            if (dist > ap.antiChaseTolerance) continue;
          }

          // Trigger Auto-Execution
          autoExec(sig);
          break;
        }
      }
    } catch {
      setSignals([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const { refresh: refreshSignals } = useSmartInterval(fetchScalpSignals, 5000, {
    fireOnMount: true,
    fireOnVisible: true,
    pauseWhenHidden: true,
  });

  const handleScanNow = async () => {
    try {
      setScanning(true);
      toast.info(`Scanning 1M orderflow for momentum scalps… (${underlying})`);
      await api.autoDetectSignal({ underlying, strategy: 'VWAP_SCALP', timeframe: '1M' });
      await fetchScalpSignals();
      toast.success('Scalp scan complete');
    } catch {
      toast.error('Scan request failed');
    } finally {
      setScanning(false);
    }
  };

  const handleManualExecute = async (signalId: string) => {
    await executeGuard(async () => {
      if (onExecuteSignal) {
        onExecuteSignal(signalId);
      } else {
        await api.executeSignalPaper(signalId);
        scalpCtx.notifyOrderPlaced();
        toast.success('Signal executed');
      }
    });
  };

  return (
    <div className="flex flex-col text-xs select-none gap-2 h-full">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border/60 pb-1.5 shrink-0">
        <div className="flex items-center gap-1.5 font-bold text-foreground">
          <Radio className="w-3.5 h-3.5 text-rose-500 animate-pulse" />
          <span>Fast Scalp Radar (1M)</span>
          {autoPilot?.enabled && (
            <span className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[9px] font-mono font-semibold animate-pulse">
              <Bot className="w-3 h-3" /> AUTO-PILOT ON
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleScanNow}
            disabled={scanning}
            className="flex items-center gap-1 px-2 py-0.5 rounded bg-secondary hover:bg-secondary/80 text-[10px] font-medium text-foreground transition-colors cursor-pointer"
          >
            <Zap className={`w-3 h-3 text-amber-500 ${scanning ? 'animate-bounce' : ''}`} />
            Scan 1M
          </button>
          <button
            type="button"
            onClick={() => void refreshSignals()}
            disabled={loading}
            className="p-1 hover:bg-secondary rounded text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            title="Refresh signals"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Signals List */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-0.5">
        {signals.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-28 text-center text-muted-foreground p-3 border border-dashed border-border/60 rounded">
            <Clock className="w-5 h-5 text-muted-foreground/60 mb-1" />
            <p className="font-medium text-[11px]">No active 1M scalp setups</p>
            <p className="text-[10px] text-muted-foreground/80 mt-0.5">
              Waiting for 1-minute VWAP breakout or momentum surge. Click &quot;Scan 1M&quot; to probe.
            </p>
          </div>
        ) : (
          signals.map((sig) => {
            const createdAtMs = sig.created_at ? new Date(sig.created_at).getTime() : now;
            const ttlTotalSec = sig.ttl_seconds || 60;
            const elapsedSec = Math.floor((now - createdAtMs) / 1000);
            const remainingSec = Math.max(0, ttlTotalSec - elapsedSec);
            const isExpired = remainingSec <= 0;

            const isLong =
              sig.direction.includes('LONG') ||
              sig.direction.includes('CALL') ||
              sig.direction === 'BULLISH';
            const distPts = currentSpot && sig.trigger ? Math.abs(currentSpot - sig.trigger) : null;
            const chaseTolerance = autoPilot?.antiChaseTolerance ?? 15;
            const isChased = distPts !== null && distPts > chaseTolerance;
            const conf = sig.confidence ?? 80;

            return (
              <div
                key={sig.id}
                className={`p-2 rounded border transition-all ${
                  isExpired
                    ? 'bg-secondary/20 border-border/40 opacity-50'
                    : isLong
                      ? 'bg-emerald-500/5 border-emerald-500/30'
                      : 'bg-rose-500/5 border-rose-500/30'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`font-mono font-bold px-1 py-0.2 rounded text-[10px] ${
                        isLong
                          ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                          : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                      }`}
                    >
                      {isLong ? 'BUY CE' : 'BUY PE'}
                    </span>
                    <span className="font-bold text-foreground">{sig.symbol}</span>
                    <span className="text-[10px] text-muted-foreground font-mono">{sig.strategy}</span>
                  </div>

                  {/* Confidence Bar & TTL */}
                  <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1 font-mono text-[9px] text-muted-foreground">
                      <span>Conf:</span>
                      <div className="w-12 h-1.5 bg-secondary rounded-full overflow-hidden border border-border/50">
                        <div
                          className="h-full bg-primary rounded-full"
                          style={{ width: `${Math.min(100, Math.max(10, conf))}%` }}
                        />
                      </div>
                      <span className="text-foreground font-semibold">{conf}%</span>
                    </div>

                    <div
                      className={`flex items-center gap-1 font-mono text-[10px] font-semibold px-1.5 py-0.2 rounded ${
                        remainingSec > 30
                          ? 'bg-emerald-500/10 text-emerald-400'
                          : remainingSec > 10
                            ? 'bg-amber-500/10 text-amber-400 animate-pulse'
                            : 'bg-rose-500/10 text-rose-400'
                      }`}
                    >
                      <Clock className="w-2.5 h-2.5" />
                      <span>{remainingSec}s</span>
                    </div>
                  </div>
                </div>

                {/* Levels & Anti-Chase Check */}
                <div className="grid grid-cols-3 gap-1 my-1.5 text-[10px] font-mono bg-background/50 p-1.5 rounded border border-border/40">
                  <div>
                    <span className="text-muted-foreground block text-[9px]">Trigger</span>
                    <span className="text-foreground font-semibold">
                      {sig.trigger ? `₹${sig.trigger.toFixed(1)}` : '—'}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground block text-[9px]">SL</span>
                    <span className="text-rose-400 font-semibold">{sig.sl ? `₹${sig.sl.toFixed(1)}` : '—'}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground block text-[9px]">Target</span>
                    <span className="text-emerald-400 font-semibold">
                      {sig.target ? `₹${sig.target.toFixed(1)}` : '—'}
                    </span>
                  </div>
                </div>

                {/* Sweet Zone Proximity Pulse & Execution Button */}
                <div className="flex items-center justify-between mt-1">
                  <span
                    className={`text-[9px] font-mono flex items-center gap-1 ${
                      isChased ? 'text-amber-400' : 'text-emerald-400'
                    }`}
                  >
                    {isChased ? (
                      <>
                        <AlertTriangle className="w-2.5 h-2.5" /> Chase warning ({distPts?.toFixed(1)}pt away)
                      </>
                    ) : (
                      <span className="flex items-center gap-1 animate-pulse">
                        <CheckCircle2 className="w-2.5 h-2.5" /> Sweet zone ({distPts?.toFixed(1) || 0}pt)
                      </span>
                    )}
                  </span>

                  {executedSignalIds?.has(sig.id) ? (
                    <span className="flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 text-[10px] font-mono font-bold">
                      <CheckCircle2 className="w-2.5 h-2.5" /> Auto-Fired
                    </span>
                  ) : (
                    <button
                      type="button"
                      disabled={isExpired || executingSignal}
                      onClick={() => void handleManualExecute(sig.id)}
                      className="flex items-center gap-1 px-2 py-0.5 rounded bg-primary text-primary-foreground hover:bg-primary/90 text-[10px] font-bold transition-all disabled:opacity-30 cursor-pointer"
                    >
                      <Play className="w-2.5 h-2.5 fill-current" />
                      {executingSignal ? 'Executing…' : 'Execute'}
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
