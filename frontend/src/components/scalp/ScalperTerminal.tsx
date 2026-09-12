'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Bot,
  Zap,
  ShieldCheck,
  ShieldAlert,
  Settings2,
  Volume2,
  VolumeX,
} from 'lucide-react';
import { ScalperChart } from './ScalperChart';
import { QuickScalpTicket } from './QuickScalpTicket';
import { ScalpAlertsHUD, ScalpSignalItem, AutoPilotConfig } from './ScalpAlertsHUD';
import { ActiveScalpPositions } from './ActiveScalpPositions';
import { api } from '@/lib/api';
import { VirtualPosition } from '@/lib/types';
import { useToast } from '@/components/ui/toast';

function playScalpAudio(type: 'enter' | 'panic' | 'limit') {
  try {
    const AudioCtx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);

    if (type === 'enter') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
      osc.frequency.exponentialRampToValueAtTime(880.0, ctx.currentTime + 0.15); // A5
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
      osc.start();
      osc.stop(ctx.currentTime + 0.35);
    } else if (type === 'panic') {
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(440, ctx.currentTime);
      osc.frequency.setValueAtTime(220, ctx.currentTime + 0.15);
      gain.gain.setValueAtTime(0.25, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
      osc.start();
      osc.stop(ctx.currentTime + 0.4);
    } else if (type === 'limit') {
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(370, ctx.currentTime);
      osc.frequency.setValueAtTime(290, ctx.currentTime + 0.1);
      gain.gain.setValueAtTime(0.18, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
      osc.start();
      osc.stop(ctx.currentTime + 0.25);
    }
  } catch {
    // Audio context may be restricted before user gesture
  }
}

export function ScalperTerminal() {
  const toast = useToast();
  const [underlying, setUnderlying] = useState<'NIFTY' | 'BANKNIFTY' | 'SENSEX'>('NIFTY');
  const [spotPrice, setSpotPrice] = useState<number>(24500.0);
  const [timeframe, setTimeframe] = useState<'1m' | '3m' | '5m'>('1m');
  const [positionsTrigger, setPositionsTrigger] = useState<number>(0);

  // Positions and circuit breakers state
  const [openPositions, setOpenPositions] = useState<VirtualPosition[]>([]);
  const [executedSignalIds, setExecutedSignalIds] = useState<Set<string>>(new Set());
  const [autoTradesCount, setAutoTradesCount] = useState<number>(0);
  const [isAutoExecuting, setIsAutoExecuting] = useState<boolean>(false);
  const [showSettings, setShowSettings] = useState<boolean>(false);

  // Auto-Pilot Configuration
  const [autoPilot, setAutoPilot] = useState<AutoPilotConfig>({
    enabled: false,
    minConfidence: 80,
    maxConcurrent: 2,
    maxDailyLoss: 3000,
    antiChaseTolerance: 15,
    soundAlerts: true,
  });

  const openPositionsRef = useRef(openPositions);
  openPositionsRef.current = openPositions;

  const autoPilotRef = useRef(autoPilot);
  autoPilotRef.current = autoPilot;

  const executedIdsRef = useRef(executedSignalIds);
  executedIdsRef.current = executedSignalIds;

  const fetchQuote = useCallback(async () => {
    try {
      const sym = underlying === 'NIFTY' ? 'NIFTY 50' : underlying;
      const res = await api.getQuote(sym);
      if (res.data?.ltp && res.data.ltp > 0) {
        setSpotPrice(res.data.ltp);
      }
    } catch {
      // ignore quote error
    }
  }, [underlying]);

  useEffect(() => {
    fetchQuote();
    const interval = setInterval(fetchQuote, 3000); // 3s quote refresh
    return () => clearInterval(interval);
  }, [fetchQuote]);

  const handleOrderExecuted = useCallback(() => {
    setPositionsTrigger((prev) => prev + 1);
  }, []);

  const handleExecuteSignal = useCallback(
    async (signalId: string) => {
      try {
        await api.executeSignalPaper(signalId);
        setPositionsTrigger((prev) => prev + 1);
        if (autoPilot.soundAlerts) playScalpAudio('enter');
        toast.success('Signal executed');
      } catch (err: unknown) {
        toast.error(`Execution failed: ${(err as Error)?.message || 'Unknown error'}`);
      }
    },
    [autoPilot.soundAlerts, toast]
  );

  // Auto-Pilot Execution Handler with Circuit Breakers
  const handleAutoExecuteSignal = useCallback(
    async (sig: ScalpSignalItem) => {
      const ap = autoPilotRef.current;
      const currentOpen = openPositionsRef.current;
      const execSet = executedIdsRef.current;

      // Circuit Breaker 1: Already executed
      if (execSet.has(sig.id)) return;

      // Circuit Breaker 2: Max concurrent open scalps
      if (currentOpen.length >= ap.maxConcurrent) {
        if (ap.soundAlerts) playScalpAudio('limit');
        toast.warning(
          `Auto-Pilot Paused: Max concurrent scalps (${ap.maxConcurrent}) already open.`
        );
        return;
      }

      // Circuit Breaker 3: Daily max loss cutoff
      const totalPnl = currentOpen.reduce((acc, p) => acc + (p.unrealized_pnl || 0), 0);
      if (totalPnl <= -ap.maxDailyLoss) {
        if (ap.soundAlerts) playScalpAudio('panic');
        toast.error(
          `🚨 Auto-Pilot Circuit Breaker: Daily loss limit hit (-₹${Math.abs(totalPnl).toFixed(
            0
          )}). Auto-pilot disengaged!`
        );
        setAutoPilot((prev) => ({ ...prev, enabled: false }));
        return;
      }

      try {
        setIsAutoExecuting(true);
        setExecutedSignalIds((prev) => new Set(prev).add(sig.id));

        await api.executeSignalPaper(sig.id);
        setAutoTradesCount((prev) => prev + 1);
        setPositionsTrigger((prev) => prev + 1);

        if (ap.soundAlerts) playScalpAudio('enter');
        toast.success(
          `⚡ AUTO-PILOT EXECUTED: ${sig.symbol} ${sig.direction} (${sig.strategy} • ${
            sig.confidence ?? 80
          }% Conf)`
        );
      } catch (err: unknown) {
        toast.error(`Auto-Pilot execution failed: ${(err as Error)?.message || 'Unknown error'}`);
      } finally {
        setIsAutoExecuting(false);
      }
    },
    [toast]
  );

  // Panic Square-Off Handler: Immediately disarms Auto-Pilot
  const handlePanicTriggered = useCallback(() => {
    setAutoPilot((prev) => {
      if (prev.enabled) {
        toast.warning('⚠️ Auto-Pilot Disengaged due to Emergency Square-Off');
        playScalpAudio('panic');
      }
      return { ...prev, enabled: false };
    });
  }, [toast]);

  const toggleAutoPilot = () => {
    const nextState = !autoPilot.enabled;
    setAutoPilot((prev) => ({ ...prev, enabled: nextState }));
    if (nextState) {
      if (autoPilot.soundAlerts) playScalpAudio('enter');
      toast.success('🤖 Auto-Pilot ARMED: Fast-path signals will auto-execute');
    } else {
      if (autoPilot.soundAlerts) playScalpAudio('limit');
      toast.info('Auto-Pilot Disengaged: Manual execution only');
    }
  };

  return (
    <div className="flex flex-col gap-3 min-h-[calc(100vh-120px)] select-none">
      {/* Top Auto-Pilot Command Ribbon */}
      <div className="bg-card border border-border rounded-lg p-2.5 flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* Status & Master Switch */}
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={toggleAutoPilot}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-md font-mono font-bold text-xs transition-all cursor-pointer shadow-sm ${
                autoPilot.enabled
                  ? 'bg-emerald-600 hover:bg-emerald-500 text-white ring-2 ring-emerald-400/40 animate-pulse'
                  : 'bg-secondary hover:bg-secondary/80 text-muted-foreground border border-border'
              }`}
            >
              <Bot className={`w-4 h-4 ${autoPilot.enabled ? 'text-white' : 'text-muted-foreground'}`} />
              <span>{autoPilot.enabled ? '⚡ AUTO-PILOT ARMED' : 'AUTO-PILOT STANDBY'}</span>
            </button>

            <span
              className={`px-2 py-0.5 rounded text-[11px] font-mono font-semibold border ${
                autoPilot.enabled
                  ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                  : 'bg-secondary/50 text-muted-foreground border-border/60'
              }`}
            >
              {autoPilot.enabled ? 'Hands-Free Execution ON' : 'Manual Trigger Only'}
            </span>

            {isAutoExecuting && (
              <span className="flex items-center gap-1 text-[11px] font-mono text-amber-400 animate-pulse">
                <Zap className="w-3.5 h-3.5 fill-amber-400" /> Executing setup…
              </span>
            )}
          </div>

          {/* Circuit Breakers Active Display */}
          <div className="hidden sm:flex items-center gap-2 text-[11px] font-mono text-muted-foreground bg-background/50 px-2.5 py-1 rounded border border-border/50">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Guards:</span>
            <span className="text-foreground">Max {autoPilot.maxConcurrent} Open</span>
            <span>•</span>
            <span className="text-foreground">Min {autoPilot.minConfidence}% Conf</span>
            <span>•</span>
            <span className="text-rose-400">Stop -₹{autoPilot.maxDailyLoss}</span>
            <span>•</span>
            <span className="text-foreground">Anti-Chase {autoPilot.antiChaseTolerance}pt</span>
          </div>

          {/* Controls: Audio Toggle & Settings */}
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono font-semibold px-2 py-0.5 rounded bg-secondary text-foreground">
              Auto-Fired: {autoTradesCount}
            </span>

            <button
              type="button"
              onClick={() =>
                setAutoPilot((prev) => ({ ...prev, soundAlerts: !prev.soundAlerts }))
              }
              className={`p-1.5 rounded transition-colors cursor-pointer ${
                autoPilot.soundAlerts
                  ? 'bg-secondary text-foreground hover:bg-secondary/80'
                  : 'bg-secondary/30 text-muted-foreground hover:text-foreground'
              }`}
              title={autoPilot.soundAlerts ? 'Sound alerts enabled' : 'Sound alerts muted'}
            >
              {autoPilot.soundAlerts ? (
                <Volume2 className="w-4 h-4 text-emerald-400" />
              ) : (
                <VolumeX className="w-4 h-4 text-muted-foreground" />
              )}
            </button>

            <button
              type="button"
              onClick={() => setShowSettings((prev) => !prev)}
              className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-mono transition-colors cursor-pointer ${
                showSettings
                  ? 'bg-primary text-primary-foreground font-bold'
                  : 'bg-secondary text-muted-foreground hover:text-foreground'
              }`}
            >
              <Settings2 className="w-3.5 h-3.5" />
              <span>Limits</span>
            </button>
          </div>
        </div>

        {/* Expandable Auto-Pilot Circuit Breaker Settings */}
        {showSettings && (
          <div className="pt-2 mt-1 border-t border-border/60 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-xs bg-secondary/15 p-2.5 rounded">
            <div>
              <label className="text-[10px] text-muted-foreground block font-mono mb-1">
                Min Signal Confidence ({autoPilot.minConfidence}%)
              </label>
              <input
                type="range"
                min={70}
                max={95}
                step={5}
                value={autoPilot.minConfidence}
                onChange={(e) =>
                  setAutoPilot((prev) => ({
                    ...prev,
                    minConfidence: Number(e.target.value),
                  }))
                }
                className="w-full accent-primary cursor-pointer"
              />
            </div>

            <div>
              <label className="text-[10px] text-muted-foreground block font-mono mb-1">
                Max Concurrent Scalps ({autoPilot.maxConcurrent})
              </label>
              <input
                type="range"
                min={1}
                max={4}
                step={1}
                value={autoPilot.maxConcurrent}
                onChange={(e) =>
                  setAutoPilot((prev) => ({
                    ...prev,
                    maxConcurrent: Number(e.target.value),
                  }))
                }
                className="w-full accent-primary cursor-pointer"
              />
            </div>

            <div>
              <label className="text-[10px] text-muted-foreground block font-mono mb-1">
                Daily Max Loss Limit (₹{autoPilot.maxDailyLoss})
              </label>
              <input
                type="range"
                min={1000}
                max={10000}
                step={500}
                value={autoPilot.maxDailyLoss}
                onChange={(e) =>
                  setAutoPilot((prev) => ({
                    ...prev,
                    maxDailyLoss: Number(e.target.value),
                  }))
                }
                className="w-full accent-primary cursor-pointer"
              />
            </div>

            <div>
              <label className="text-[10px] text-muted-foreground block font-mono mb-1">
                Anti-Chase Distance ({autoPilot.antiChaseTolerance} pts)
              </label>
              <input
                type="range"
                min={5}
                max={30}
                step={5}
                value={autoPilot.antiChaseTolerance}
                onChange={(e) =>
                  setAutoPilot((prev) => ({
                    ...prev,
                    antiChaseTolerance: Number(e.target.value),
                  }))
                }
                className="w-full accent-primary cursor-pointer"
              />
            </div>
          </div>
        )}
      </div>

      {/* Upper Grid: Left = 1M Chart, Right = Quick Ticket + Fast Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 flex-1 min-h-[500px]">
        {/* Main Chart Column (7 cols on lg) */}
        <div className="lg:col-span-7 xl:col-span-8 flex flex-col h-full min-h-[380px]">
          <ScalperChart
            symbol={underlying === 'NIFTY' ? 'NIFTY 50' : underlying}
            timeframe={timeframe}
            onTimeframeChange={setTimeframe}
            spotPrice={spotPrice}
          />
        </div>

        {/* Scalp Tools Column (5 cols on lg) */}
        <div className="lg:col-span-5 xl:col-span-4 flex flex-col gap-3">
          <QuickScalpTicket
            underlying={underlying}
            spotPrice={spotPrice}
            onUnderlyingChange={setUnderlying}
            onOrderPlaced={handleOrderExecuted}
          />

          <div className="flex-1 min-h-[220px]">
            <ScalpAlertsHUD
              currentSpot={spotPrice}
              onExecuteSignal={handleExecuteSignal}
              autoPilot={autoPilot}
              onAutoExecute={handleAutoExecuteSignal}
              executedSignalIds={executedSignalIds}
            />
          </div>
        </div>
      </div>

      {/* Bottom Span: Active Scalp Positions with Panic Square-Off All */}
      <div className="w-full">
        <ActiveScalpPositions
          refreshTrigger={positionsTrigger}
          onPositionsUpdated={handleOrderExecuted}
          onPositionsChange={setOpenPositions}
          onPanicTriggered={handlePanicTriggered}
        />
      </div>
    </div>
  );
}
