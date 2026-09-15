'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { api } from '@/lib/api';
import { VirtualPosition } from '@/lib/types';
import { AutoPilotConfig } from './ScalpAlertsHUD';
import { scalpAudio } from './scalpAudio';
import { useSmartInterval } from '@/hooks/useSmartInterval';
import { useToast } from '@/components/ui/toast';

export type ScalpUnderlying = 'NIFTY' | 'BANKNIFTY' | 'SENSEX';

export interface ScalpContextValue {
  underlying: ScalpUnderlying;
  setUnderlying: (u: ScalpUnderlying) => void;

  // Spot
  spotPrice: number;
  spotUpdatedAt: number | null;
  spotAgeSec: number | null;
  spotStale: boolean;
  refreshSpot: () => Promise<void>;

  // Positions & PnL
  openPositions: VirtualPosition[];
  sessionMTM: number;
  lossUsedPct: number;
  positionsTrigger: number;
  notifyOrderPlaced: () => void;
  refreshPositions: () => Promise<void>;

  // Auto-Pilot
  autoPilot: AutoPilotConfig;
  setAutoPilot: React.Dispatch<React.SetStateAction<AutoPilotConfig>>;
  toggleAutoPilot: () => void;
  autoTradesCount: number;
  incrementAutoTradesCount: () => void;

  // Global Panic
  panicPending: boolean;
  panicSquareOff: () => Promise<void>;

  // Audio
  audioEnabled: boolean;
  setAudioEnabled: (enabled: boolean) => void;

  // Fullscreen
  isFullscreen: boolean;
  toggleFullscreen: () => void;
}

const AUTOPILOT_STORAGE_KEY = 'droid_scalp_autopilot_v1';

const DEFAULT_AUTOPILOT: AutoPilotConfig = {
  enabled: false,
  minConfidence: 80,
  maxConcurrent: 2,
  maxDailyLoss: 3000,
  antiChaseTolerance: 15,
  soundAlerts: true,
};

function loadStoredAutoPilot(): AutoPilotConfig {
  if (typeof window === 'undefined') return DEFAULT_AUTOPILOT;
  try {
    const raw = localStorage.getItem(AUTOPILOT_STORAGE_KEY);
    if (!raw) return DEFAULT_AUTOPILOT;
    const parsed = JSON.parse(raw);
    if (parsed && parsed.version === 1 && typeof parsed.config === 'object') {
      const c = parsed.config;
      return {
        enabled: Boolean(c.enabled),
        minConfidence: Math.min(95, Math.max(70, Number(c.minConfidence) || 80)),
        maxConcurrent: Math.min(4, Math.max(1, Math.round(Number(c.maxConcurrent) || 2))),
        maxDailyLoss: Math.min(50000, Math.max(500, Number(c.maxDailyLoss) || 3000)),
        antiChaseTolerance: Math.min(50, Math.max(5, Number(c.antiChaseTolerance) || 15)),
        soundAlerts: c.soundAlerts !== false,
      };
    }
  } catch {
    // fallback to defaults
  }
  return DEFAULT_AUTOPILOT;
}

function saveStoredAutoPilot(config: AutoPilotConfig) {
  if (typeof window === 'undefined') return;
  try {
    const payload = {
      version: 1,
      config: {
        enabled: config.enabled,
        minConfidence: config.minConfidence,
        maxConcurrent: config.maxConcurrent,
        maxDailyLoss: config.maxDailyLoss,
        antiChaseTolerance: config.antiChaseTolerance,
        soundAlerts: config.soundAlerts,
      },
    };
    localStorage.setItem(AUTOPILOT_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // ignore quota/privacy errors
  }
}

const ScalpContext = createContext<ScalpContextValue | null>(null);

export function ScalpProvider({ children }: { children: React.ReactNode }) {
  const toast = useToast();
  const [underlying, setUnderlyingState] = useState<ScalpUnderlying>('NIFTY');

  // Spot state
  const [spotPrice, setSpotPrice] = useState<number>(0);
  const [spotUpdatedAt, setSpotUpdatedAt] = useState<number | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  // Positions & PnL
  const [openPositions, setOpenPositions] = useState<VirtualPosition[]>([]);
  const [positionsTrigger, setPositionsTrigger] = useState(0);
  const [dailyRealized, setDailyRealized] = useState(0);

  // Auto-Pilot & Execution state
  const [autoPilot, setAutoPilot] = useState<AutoPilotConfig>(loadStoredAutoPilot);
  const [autoTradesCount, setAutoTradesCount] = useState<number>(0);
  const [panicPending, setPanicPending] = useState(false);
  const [audioEnabled, setAudioEnabledState] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const toggleFullscreen = useCallback(() => {
    setIsFullscreen((prev) => {
      const next = !prev;
      if (typeof document !== 'undefined') {
        if (next) {
          if (document.documentElement.requestFullscreen && !document.fullscreenElement) {
            document.documentElement.requestFullscreen().catch(() => undefined);
          }
        } else {
          if (document.fullscreenElement && document.exitFullscreen) {
            document.exitFullscreen().catch(() => undefined);
          }
        }
      }
      return next;
    });
  }, []);

  useEffect(() => {
    const handleFsChange = () => {
      if (typeof document !== 'undefined' && !document.fullscreenElement) {
        setIsFullscreen(false);
      }
    };
    document.addEventListener('fullscreenchange', handleFsChange);
    return () => document.removeEventListener('fullscreenchange', handleFsChange);
  }, []);

  // Sync audio enabled state to scalpAudio service
  const setAudioEnabled = useCallback((enabled: boolean) => {
    setAudioEnabledState(enabled);
    scalpAudio.setEnabled(enabled);
    setAutoPilot((prev) => ({ ...prev, soundAlerts: enabled }));
  }, []);

  // Persist autoPilot changes
  useEffect(() => {
    saveStoredAutoPilot(autoPilot);
  }, [autoPilot]);

  // Underlying change handler
  const setUnderlying = useCallback((u: ScalpUnderlying) => {
    setUnderlyingState(u);
    setSpotPrice(0); // clear stale spot for previous underlying immediately
    setSpotUpdatedAt(null);
  }, []);

  // Spot ticker for age calculation
  useEffect(() => {
    const timer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const spotAgeSec = useMemo(() => {
    if (!spotUpdatedAt || spotPrice <= 0) return null;
    return Math.max(0, Math.floor((nowMs - spotUpdatedAt) / 1000));
  }, [nowMs, spotUpdatedAt, spotPrice]);

  const spotStale = spotAgeSec !== null && spotAgeSec > 15;

  // Spot fetcher
  const fetchSpot = useCallback(async () => {
    try {
      const sym = underlying === 'NIFTY' ? 'NIFTY 50' : underlying;
      const res = await api.getQuote(sym);
      if (res.data?.ltp && res.data.ltp > 0) {
        setSpotPrice(res.data.ltp);
        setSpotUpdatedAt(Date.now());
      }
    } catch {
      // keep last good spot; staleness meter reflects the age
    }
  }, [underlying]);

  const { refresh: refreshSpot } = useSmartInterval(fetchSpot, 2000, {
    fireOnMount: true,
    fireOnVisible: true,
    pauseWhenHidden: true,
  });

  // Immediate refetch on underlying switch — useSmartInterval holds the
  // callback in a ref and does not restart its timer when the closure
  // changes, so without this the new underlying would show "Waiting for
  // live spot" until the next scheduled tick.
  useEffect(() => {
    void refreshSpot();
  }, [underlying, refreshSpot]);

  // Realized PnL fetcher (intraday session)
  const fetchPortfolio = useCallback(async () => {
    try {
      const res = await api.getPaperPortfolio();
      const realized = res.data?.total_realized_pnl;
      if (Number.isFinite(realized)) {
        setDailyRealized(Number(realized));
      }
    } catch {
      // retain last known realized
    }
  }, []);

  useSmartInterval(fetchPortfolio, 10000, {
    fireOnMount: true,
    fireOnVisible: true,
    pauseWhenHidden: true,
  });

  // Positions fetcher
  const fetchPositions = useCallback(async () => {
    try {
      const res = await api.getPaperPositions();
      const raw = (res.data || []) as VirtualPosition[];
      const open = raw.filter((p) => p.is_open);
      setOpenPositions(open);
    } catch {
      // retain last positions
    }
  }, []);

  const { refresh: refreshPositions } = useSmartInterval(fetchPositions, 2500, {
    fireOnMount: true,
    fireOnVisible: true,
    pauseWhenHidden: true,
  });

  const notifyOrderPlaced = useCallback(() => {
    setPositionsTrigger((prev) => prev + 1);
    void fetchPositions();
  }, [fetchPositions]);

  // Session P&L calculations
  const totalUnrealized = useMemo(() => {
    return openPositions.reduce((acc, p) => acc + (p.unrealized_pnl || 0), 0);
  }, [openPositions]);

  const totalRealizedInPositions = useMemo(() => {
    return openPositions.reduce((acc, p) => acc + (p.realized_pnl || 0), 0);
  }, [openPositions]);

  const sessionMTM = totalUnrealized + totalRealizedInPositions + dailyRealized;

  const lossUsedPct = useMemo(() => {
    if (autoPilot.maxDailyLoss <= 0) return 0;
    return Math.min(100, Math.max(0, (-sessionMTM / autoPilot.maxDailyLoss) * 100));
  }, [sessionMTM, autoPilot.maxDailyLoss]);

  // Global Panic Square-Off Handler
  const panicSquareOff = useCallback(async () => {
    if (panicPending) return;
    if (openPositions.length === 0) {
      toast.info('No open positions to square off');
      return;
    }

    try {
      setPanicPending(true);

      // Disengage auto-pilot first
      setAutoPilot((prev) => {
        if (prev.enabled) {
          scalpAudio.panic();
        }
        return { ...prev, enabled: false };
      });

      scalpAudio.panic();
      await api.squareOffAllPositions();
      toast.success('🚨 EMERGENCY SQUARE-OFF COMPLETE: All active positions closed');
      await fetchPositions();
      setPositionsTrigger((prev) => prev + 1);
    } catch (err: unknown) {
      toast.error(`Emergency exit failed: ${(err as Error)?.message || 'Unknown error'}`);
    } finally {
      setPanicPending(false);
    }
  }, [panicPending, openPositions.length, toast, fetchPositions]);

  const toggleAutoPilot = useCallback(() => {
    setAutoPilot((prev) => {
      const nextState = !prev.enabled;
      if (nextState) {
        if (prev.soundAlerts) scalpAudio.enter();
        toast.success('🤖 Auto-Pilot ARMED: Fast-path signals will auto-execute');
      } else {
        if (prev.soundAlerts) scalpAudio.limit();
        toast.info('Auto-Pilot Disengaged: Manual execution only');
      }
      return { ...prev, enabled: nextState };
    });
  }, [toast]);

  const incrementAutoTradesCount = useCallback(() => {
    setAutoTradesCount((c) => c + 1);
  }, []);

  const value = useMemo<ScalpContextValue>(() => ({
    underlying,
    setUnderlying,
    spotPrice,
    spotUpdatedAt,
    spotAgeSec,
    spotStale,
    refreshSpot,
    openPositions,
    sessionMTM,
    lossUsedPct,
    positionsTrigger,
    notifyOrderPlaced,
    refreshPositions,
    autoPilot,
    setAutoPilot,
    toggleAutoPilot,
    autoTradesCount,
    incrementAutoTradesCount,
    panicPending,
    panicSquareOff,
    audioEnabled,
    setAudioEnabled,
    isFullscreen,
    toggleFullscreen,
  }), [
    underlying,
    setUnderlying,
    spotPrice,
    spotUpdatedAt,
    spotAgeSec,
    spotStale,
    refreshSpot,
    openPositions,
    sessionMTM,
    lossUsedPct,
    positionsTrigger,
    notifyOrderPlaced,
    refreshPositions,
    autoPilot,
    toggleAutoPilot,
    autoTradesCount,
    incrementAutoTradesCount,
    panicPending,
    panicSquareOff,
    audioEnabled,
    setAudioEnabled,
    isFullscreen,
    toggleFullscreen,
  ]);

  return <ScalpContext.Provider value={value}>{children}</ScalpContext.Provider>;
}

export function useScalpContext(): ScalpContextValue {
  const ctx = useContext(ScalpContext);
  if (!ctx) {
    throw new Error('useScalpContext must be used within a ScalpProvider');
  }
  return ctx;
}
