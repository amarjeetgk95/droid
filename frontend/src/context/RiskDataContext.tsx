'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from 'react';
import { usePolling } from '@/hooks/usePolling';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import type { AuditTradeLike } from '@/components/risk-matrix/riskUtils';

export const RISK_AUDIT_LIMIT = 200;

export type SignalsPerformance = Awaited<ReturnType<typeof api.getSignalsPerformance>>;

export interface RiskAuditResource {
  trades: AuditTradeLike[];
  loading: boolean;
  error: string | null;
  updatedAt: number | null;
  refresh: () => Promise<void>;
  removeTrades: (signalIds: string[]) => void;
}

export interface RiskPerformanceResource {
  data: SignalsPerformance | null;
  loading: boolean;
  error: string | null;
  updatedAt: number | null;
  refresh: () => Promise<void>;
}

interface RiskDataContextValue {
  audit: RiskAuditResource;
  performance: RiskPerformanceResource;
}

const RiskDataContext = createContext<RiskDataContextValue | null>(null);

export const RiskDataProvider: React.FC<{
  children: React.ReactNode;
  pollIntervalMs?: number;
  enabled?: boolean;
}> = ({ children, pollIntervalMs = 6000, enabled = true }) => {
  const [trades, setTrades] = useState<AuditTradeLike[]>([]);
  const [auditLoading, setAuditLoading] = useState(true);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [auditUpdatedAt, setAuditUpdatedAt] = useState<number | null>(null);
  const auditSeqRef = useRef(0);

  const [perf, setPerf] = useState<SignalsPerformance | null>(null);
  const [perfLoading, setPerfLoading] = useState(true);
  const [perfError, setPerfError] = useState<string | null>(null);
  const [perfUpdatedAt, setPerfUpdatedAt] = useState<number | null>(null);
  const perfSeqRef = useRef(0);

  const fetchAudit = useCallback(async () => {
    const seq = ++auditSeqRef.current;
    try {
      const res = await api.getSignalsAudit({ limit: RISK_AUDIT_LIMIT });
      if (seq !== auditSeqRef.current) return;
      setTrades(Array.isArray(res?.trades) ? (res.trades as AuditTradeLike[]) : []);
      setAuditError(null);
      setAuditUpdatedAt(Date.now());
    } catch (err) {
      if (seq !== auditSeqRef.current) return;
      setAuditError(errorMessage(err, 'Audit ledger unavailable'));
    } finally {
      if (seq === auditSeqRef.current) setAuditLoading(false);
    }
  }, []);

  const fetchPerformance = useCallback(async () => {
    const seq = ++perfSeqRef.current;
    try {
      const res = await api.getSignalsPerformance();
      if (seq !== perfSeqRef.current) return;
      setPerf(res ?? null);
      setPerfError(null);
      setPerfUpdatedAt(Date.now());
    } catch (err) {
      if (seq !== perfSeqRef.current) return;
      setPerfError(errorMessage(err, 'Performance metrics unavailable'));
    } finally {
      if (seq === perfSeqRef.current) setPerfLoading(false);
    }
  }, []);

  const load = useCallback(async () => {
    await Promise.allSettled([fetchAudit(), fetchPerformance()]);
  }, [fetchAudit, fetchPerformance]);

  usePolling(load, pollIntervalMs, enabled);

  const removeTrades = useCallback((signalIds: string[]) => {
    const removed = new Set(signalIds);
    setTrades((prev) => prev.filter((t) => !t.signal_id || !removed.has(t.signal_id)));
  }, []);

  const audit = useMemo<RiskAuditResource>(
    () => ({
      trades,
      loading: auditLoading,
      error: auditError,
      updatedAt: auditUpdatedAt,
      refresh: fetchAudit,
      removeTrades,
    }),
    [trades, auditLoading, auditError, auditUpdatedAt, fetchAudit, removeTrades],
  );

  const performance = useMemo<RiskPerformanceResource>(
    () => ({
      data: perf,
      loading: perfLoading,
      error: perfError,
      updatedAt: perfUpdatedAt,
      refresh: fetchPerformance,
    }),
    [perf, perfLoading, perfError, perfUpdatedAt, fetchPerformance],
  );

  const value = useMemo<RiskDataContextValue>(() => ({ audit, performance }), [audit, performance]);

  return <RiskDataContext.Provider value={value}>{children}</RiskDataContext.Provider>;
};

function useRiskData(): RiskDataContextValue {
  const ctx = useContext(RiskDataContext);
  if (!ctx) {
    throw new Error('Risk data hooks must be used within a RiskDataProvider');
  }
  return ctx;
}

export function useRiskAudit(): RiskAuditResource {
  return useRiskData().audit;
}

export function useRiskPerformance(): RiskPerformanceResource {
  return useRiskData().performance;
}
