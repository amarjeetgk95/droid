'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '@/lib/api';
import { withJitter } from '@/lib/signal-utils';
import { useSignalStream } from '@/hooks/useSignalStream';
import { playAlertChime } from './SignalAudio';
import type { SignalDTO } from './SignalCard';
import type { AuditTradeRecord, AuditSummary } from './SignalAuditTable';
import type { CryptoSignal } from '@/lib/types';
import { deskCache } from '@/lib/useDeskCache';

export type FilterInstrument = 'ALL' | 'NIFTY' | 'BANKNIFTY' | 'SENSEX';
export type FilterDesk = 'ALL' | 'SCALP' | 'INTRADAY';
export type FilterAssetClass = 'ALL' | 'INDEX' | 'CRYPTO';
export type OppSource = 'live' | 'scanner';
export type TrackView = 'performance' | 'ledger';
export type FilterStrategy =
  | 'ALL'
  | 'BREAKOUT'
  | 'MEAN_REVERSION'
  | 'TREND_PULLBACK'
  | 'GAMMA_SQUEEZE'
  | 'ORB'
  | 'VWAP_SCALP'
  | 'MICRO_MOMENTUM'
  | 'EMA_RIBBON'
  | 'GAMMA_SPIKE';

export interface ScanDiagnostics {
  underlying?: string;
  data_quality?: string;
  reasons?: string[];
  candidates_found?: number;
  error?: string | null;
}

function upsertSignal(list: SignalDTO[], incoming: SignalDTO): SignalDTO[] {
  if (!incoming?.signal_id) return list;
  const idx = list.findIndex((s) => s.signal_id === incoming.signal_id);
  if (idx >= 0) {
    const next = list.slice();
    next[idx] = { ...next[idx], ...incoming };
    return next;
  }
  return [incoming, ...list].slice(0, 100);
}

export function useSignalEngine() {
  const [active, setActive] = useState<SignalDTO[]>([]);
  const [activeQuality, setActiveQuality] = useState<string>('LIVE');
  const [scannerData, setScannerData] = useState<SignalDTO[]>([]);
  const [scanDiagnostics, setScanDiagnostics] = useState<ScanDiagnostics[]>([]);
  const [scanQuality, setScanQuality] = useState<string>('LIVE');
  const [loading, setLoading] = useState(false);
  const [scannerLoading, setScannerLoading] = useState(false);

  const [filterDesk, setFilterDesk] = useState<FilterDesk>('ALL');
  const [filterInstr, setFilterInstr] = useState<FilterInstrument>('ALL');
  const [filterStrat, setFilterStrat] = useState<FilterStrategy>('ALL');
  const [assetClass, setAssetClass] = useState<FilterAssetClass>('ALL');
  const [oppSource, setOppSource] = useState<OppSource>('live');
  const [trackView, setTrackView] = useState<TrackView>('ledger');
  const [cryptoSignals, setCryptoSignals] = useState<CryptoSignal[]>([]);
  const [cryptoLoading, setCryptoLoading] = useState(false);
  const [cryptoError, setCryptoError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'grid' | 'table'>('grid');
  const [soundEnabled, setSoundEnabled] = useState<boolean>(true);
  const [selectMode, setSelectMode] = useState(false);
  const [selectedOppIds, setSelectedOppIds] = useState<Set<string>>(new Set());
  const [bulkDeletingOpp, setBulkDeletingOpp] = useState(false);

  const [inspectSignalId, setInspectSignalId] = useState<string | null>(null);
  const [perfSummary, setPerfSummary] = useState<any>(null);
  const [cardsNowMs, setCardsNowMs] = useState<number>(() => Date.now());

  useEffect(() => {
    const clock = setInterval(() => setCardsNowMs(Date.now()), 1000);
    return () => clearInterval(clock);
  }, []);

  const [activeError, setActiveError] = useState<string | null>(null);
  const [scannerError, setScannerError] = useState<string | null>(null);
  const [auditError, setAuditError] = useState<string | null>(null);

  const [auditTrades, setAuditTrades] = useState<AuditTradeRecord[]>([]);
  const [auditSummary, setAuditSummary] = useState<AuditSummary | null>(null);
  const [auditLoading, setAuditLoading] = useState<boolean>(false);

  const knownSignalIds = useRef<Set<string>>(new Set());
  const activeInFlight = useRef(false);
  const auditInFlight = useRef(false);
  const scannerInFlight = useRef(false);
  const cryptoInFlight = useRef(false);
  const sseRefreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchActive = useCallback(
    async (showLoading = true) => {
      if (activeInFlight.current) return;
      const cacheKey = `signals:active:${filterInstr}:${filterStrat}:${filterDesk}`;
      const cached = deskCache.get<SignalDTO[]>(cacheKey);
      if (cached) {
        setActive(cached.data);
        if (!cached.isStale) {
          showLoading = false;
        }
      }

      activeInFlight.current = true;
      if (showLoading) setLoading(true);
      setActiveError(null);
      try {
        const res: any = await api.getSignalsActive({
          instrument: filterInstr !== 'ALL' ? filterInstr : undefined,
          strategy: filterStrat !== 'ALL' ? filterStrat : undefined,
          desk: filterDesk !== 'ALL' ? filterDesk : undefined,
        });
        const list: SignalDTO[] = res.signals || res.data?.signals || [];
        setActiveQuality(res.data_quality || res.data?.data_quality || 'LIVE');

        if (soundEnabled && knownSignalIds.current.size > 0) {
          const newConfirmed = list.filter(
            (s) => s?.signal_id && !knownSignalIds.current.has(s.signal_id) && (s.fsm_state === 'CONFIRMED' || String(s.fsm_state || '').includes('TARGET'))
          );
          if (newConfirmed.length > 0) {
            const isScalp = newConfirmed.some((s) => s.is_scalp || s.signal_type === 'SCALP');
            playAlertChime(true, isScalp);
          }
        }
        list.forEach((s) => {
          if (s?.signal_id) knownSignalIds.current.add(s.signal_id);
        });
        setActive(list);
        deskCache.set(cacheKey, list);
      } catch (e: any) {
        setActiveError(e.message || 'Failed to load quantitative signals');
      } finally {
        setLoading(false);
        activeInFlight.current = false;
      }
    },
    [filterInstr, filterStrat, filterDesk, soundEnabled]
  );

  const fetchScanner = useCallback(async (showLoading = true) => {
    if (scannerInFlight.current) return;
    const cacheKey = 'signals:scanner';
    const cached = deskCache.get<SignalDTO[]>(cacheKey);
    if (cached) {
      setScannerData(cached.data);
      if (!cached.isStale) {
        showLoading = false;
      }
    }

    scannerInFlight.current = true;
    if (showLoading) setScannerLoading(true);
    setScannerError(null);
    try {
      const res: any = await api.getSignalsScanner();
      const list: SignalDTO[] = res.active_signals || res.new_signals || [];
      setScannerData(list);
      setScanDiagnostics(res.diagnostics || res.scalp_desk?.diagnostics || []);
      setScanQuality(res.data_quality || 'LIVE');
      deskCache.set(cacheKey, list);
      if (res.errors && Object.keys(res.errors).length > 0) {
        setScannerError(
          Object.entries(res.errors)
            .map(([u, msg]) => `${u}: ${msg}`)
            .join(' • ')
            .slice(0, 300)
        );
      }
    } catch (e: any) {
      setScannerError(e.message || 'Scanner unavailable');
    } finally {
      setScannerLoading(false);
      scannerInFlight.current = false;
    }
  }, []);

  const fetchCrypto = useCallback(async (showLoading = true) => {
    if (cryptoInFlight.current) return;
    cryptoInFlight.current = true;
    if (showLoading) setCryptoLoading(true);
    setCryptoError(null);
    try {
      const res: any = await api.getCryptoSignals();
      const list: CryptoSignal[] = res?.data?.signals || res?.signals || [];
      setCryptoSignals(Array.isArray(list) ? list : []);
    } catch (e: any) {
      setCryptoError(e.message || 'Crypto signals unavailable');
    } finally {
      if (showLoading) setCryptoLoading(false);
      cryptoInFlight.current = false;
    }
  }, []);

  const fetchAudit = useCallback(async (showLoading = false) => {
    if (auditInFlight.current) return;
    auditInFlight.current = true;
    if (showLoading) setAuditLoading(true);
    setAuditError(null);
    try {
      const res: any = await api.getSignalsAudit();
      setAuditTrades(res.trades || []);
      setAuditSummary(res.summary || null);
    } catch (e: any) {
      setAuditError(e.message || 'Audit ledger unavailable');
    } finally {
      if (showLoading) setAuditLoading(false);
      auditInFlight.current = false;
    }
  }, []);

  const scheduleSseRefresh = useCallback(() => {
    if (sseRefreshTimer.current) return;
    sseRefreshTimer.current = setTimeout(() => {
      sseRefreshTimer.current = null;
      if (!document.hidden) {
        void fetchActive(false);
        void fetchAudit(false);
      }
    }, 1500);
  }, [fetchActive, fetchAudit]);

  const handleStreamEvent = useCallback(
    (e: { type: string; payload: unknown }) => {
      const t = e.type;
      const p = e.payload as Record<string, unknown>;
      const signal = (p?.signal || p) as SignalDTO | undefined;
      if (t === 'signal_deleted' && typeof p?.signal_id === 'string') {
        setActive((prev) => prev.filter((s) => s.signal_id !== p.signal_id));
        return;
      }
      if (t === 'signals_bulk_deleted' && Array.isArray((p as Record<string, unknown>)?.signal_ids)) {
        const gone = new Set(((p as Record<string, unknown>).signal_ids as unknown[]) as string[]);
        setActive((prev) => prev.filter((s) => !gone.has(s.signal_id)));
        setSelectedOppIds((prev) => {
          const next = new Set(prev);
          gone.forEach((id) => next.delete(id));
          return next;
        });
        return;
      }
      if (signal?.signal_id && (t.includes('signal') || t.includes('paper') || t.includes('execution') || t.includes('outcome') || t.includes('staged'))) {
        setActive((prev) => upsertSignal(prev, signal));
        knownSignalIds.current.add(signal.signal_id);
        if (soundEnabled && (signal.fsm_state === 'CONFIRMED' || String(signal.fsm_state || '').includes('TARGET'))) {
          playAlertChime(true, Boolean(signal.is_scalp));
        }
        return;
      }
      if (t === 'scanner_update') {
        scheduleSseRefresh();
      }
    },
    [scheduleSseRefresh, soundEnabled]
  );

  const { streamState } = useSignalStream(true, handleStreamEvent);

  useEffect(() => {
    api
      .getSignalsPerformance()
      .then((r) => setPerfSummary(r))
      .catch(() => {});
  }, []);

  useEffect(() => {
    void fetchActive(true);
    void fetchScanner(true);
    void fetchAudit(true);
    void fetchCrypto(true);

    let timeout: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;
    const loop = () => {
      if (stopped) return;
      timeout = setTimeout(() => {
        if (!document.hidden) {
          void fetchActive(false);
          void fetchAudit(false);
          void fetchCrypto(false);
        }
        loop();
      }, withJitter(18000));
    };

    let scanTimeout: ReturnType<typeof setTimeout> | null = null;
    const scanLoop = () => {
      if (stopped) return;
      scanTimeout = setTimeout(() => {
        if (!document.hidden) void fetchScanner(false);
        scanLoop();
      }, withJitter(60000));
    };
    loop();
    scanLoop();

    return () => {
      stopped = true;
      if (timeout) clearTimeout(timeout);
      if (scanTimeout) clearTimeout(scanTimeout);
      if (sseRefreshTimer.current) clearTimeout(sseRefreshTimer.current);
    };
  }, [fetchActive, fetchScanner, fetchAudit, fetchCrypto]);

  return {
    active,
    setActive,
    activeQuality,
    scannerData,
    scanDiagnostics,
    scanQuality,
    loading,
    scannerLoading,
    filterDesk,
    setFilterDesk,
    filterInstr,
    setFilterInstr,
    filterStrat,
    setFilterStrat,
    assetClass,
    setAssetClass,
    oppSource,
    setOppSource,
    trackView,
    setTrackView,
    cryptoSignals,
    cryptoLoading,
    cryptoError,
    viewMode,
    setViewMode,
    soundEnabled,
    setSoundEnabled,
    selectMode,
    setSelectMode,
    selectedOppIds,
    setSelectedOppIds,
    bulkDeletingOpp,
    setBulkDeletingOpp,
    inspectSignalId,
    setInspectSignalId,
    perfSummary,
    cardsNowMs,
    activeError,
    scannerError,
    auditError,
    auditTrades,
    auditSummary,
    auditLoading,
    streamState,
    fetchActive,
    fetchScanner,
    fetchCrypto,
    fetchAudit,
  };
}
