'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { AutoDetectCandidate } from '@/lib/api/signals';
import { errorMessage } from '@/lib/errors';
import {
  toActiveRow,
  maxPayloadTimestampMs,
  dataFreshness,
  type ActiveRow,
  type DeskScope,
} from '@/lib/signalsNormalize';
import type { SignalEventData } from '@/lib/api/view';
import { useSignalEvents } from '@/context/AppStreamContext';
import { useSmartInterval } from './useSmartInterval';

export type SignalDeskFilters = {
  instrument?: string;
  desk?: DeskScope | 'ALL';
  strategy?: string;
};


export type ExecutePaperInput = {
  lots?: number | null;
  riskPercent?: number | null;
  allowClosedMarket?: boolean;
};

export type DeskActionResult = {
  ok: boolean;
  message: string;
  signalId?: string;
};

export type ScanResult = {
  ok: boolean;
  message: string;
  newSignals: number;
  activeSignals: number;
  scanned: string[];
};

export type WorkerStatus = {
  running: boolean | null;
  armedCount: number | null;
  confirmedCount: number | null;
  activeCount: number | null;
};



export type SignalDeskState = {
  rows: ActiveRow[];
  engines: string[];
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  updatedAt: number | null;
  /** Age of `updatedAt` in ms. Null when the payload carried no instant. */
  ageMs: number | null;
  /** True when `updatedAt` is missing or older than the staleness window. */
  stale: boolean;
  source: 'rest';
  liveSource: 'rest';
  worker: WorkerStatus;
  refresh: () => Promise<void>;
  runScan: (desk?: string) => Promise<ScanResult>;

  autoDetect: (input: { underlying: string; strategy?: string; timeframe?: string }) => Promise<AutoDetectCandidate | null>;
  executePaper: (signalId: string, input?: ExecutePaperInput) => Promise<DeskActionResult>;
  removeSignal: (signalId: string) => Promise<DeskActionResult>;
};

export function useSignalDesk(
  filters: SignalDeskFilters = {},
  options: { safetyRefreshMs?: number | null; includeClosed?: boolean } = {},
): SignalDeskState {
  const { safetyRefreshMs = null, includeClosed = true } = options;
  const [rows, setRows] = useState<ActiveRow[]>([]);
  const [engines, setEngines] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [worker, setWorker] = useState<WorkerStatus>({
    running: null,
    armedCount: null,
    confirmedCount: null,
    activeCount: null,
  });
  const requestIdRef = useRef(0);
  const filtersRef = useRef(filters);
  filtersRef.current = filters;
  const includeClosedRef = useRef(includeClosed);
  includeClosedRef.current = includeClosed;

  const load = useCallback(async (showSpinner: boolean) => {
    const requestId = ++requestIdRef.current;
    if (showSpinner) setRefreshing(true);
    const { instrument, desk, strategy } = filtersRef.current;
    const [signalsResult, statusResult, healthResult] = await Promise.allSettled([
      api.getSignalsActive({
        instrument: instrument && instrument !== 'ALL' ? instrument : undefined,
        desk: desk && desk !== 'ALL' ? desk : undefined,
        strategy: strategy || undefined,
        status: includeClosedRef.current ? 'ALL' : undefined,
      }),
      api.getSignalsStatus(),
      api.getSignalsSubsystemsHealth(),
    ]);
    if (requestIdRef.current !== requestId) return;

    if (signalsResult.status === 'fulfilled') {
      const nextRows = (signalsResult.value.signals ?? [])
        .map((raw) => toActiveRow(raw))
        .filter((row): row is ActiveRow => row !== null);
      setRows(nextRows);
      setError(null);
      // Prefer backend instants (timestamp_ms / row times) — never mask with
      // Date.now(). On failure keep the last age (no bump below).
      const payloadTs =
        maxPayloadTimestampMs([
          signalsResult.value,
          statusResult.status === 'fulfilled' ? statusResult.value : null,
        ]) ??
        (nextRows.length > 0
          ? Math.max(...nextRows.map((r) => r.timeMs ?? 0).filter((t) => t > 0), 0) || null
          : null);
      if (payloadTs !== null) {
        setUpdatedAt(payloadTs);
      }
    } else {
      setError(errorMessage(signalsResult.reason, 'Active signals unavailable'));
      // Fetch failed — keep last updatedAt so the age stays honest.
    }

    if (statusResult.status === 'fulfilled') {
      const status = statusResult.value;
      setWorker((prev) => ({
        ...prev,
        activeCount: status.active_count ?? null,
        armedCount: status.armed_count ?? null,
        confirmedCount: status.confirmed_count ?? null,
      }));
    }

    if (healthResult.status === 'fulfilled') {
      const element = healthResult.value.elements?.signal_worker;
      setWorker((prev) => ({
        ...prev,
        running: typeof element === 'boolean' ? element : null,
      }));
    } else {
      setWorker((prev) => ({ ...prev, running: null }));
    }

    setLoading(false);
    if (showSpinner) setRefreshing(false);
  }, []);

  useEffect(() => {
    setLoading(true);
    void load(false);
  }, [load, filters.instrument, filters.desk, filters.strategy]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const payload = await api.getSignalEngines();
        if (cancelled) return;
        const ids = (payload.strategies ?? []).map((entry) =>
          typeof entry === 'string' ? entry : entry.id,
        );
        setEngines(ids.filter((id): id is string => Boolean(id)));
      } catch {
        // Engine catalog is a convenience; the generator still works without it.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scheduleRefresh = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      debounceRef.current = null;
      void load(false);
    }, 500);
  }, [load]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  useSignalEvents(
    useCallback(
      (event: SignalEventData) => {
        void event;
        scheduleRefresh();
      },
      [scheduleRefresh],
    ),
  );

  useSmartInterval(
    useCallback(() => load(false), [load]),
    safetyRefreshMs,
    { fireOnMount: false },
  );

  const refresh = useCallback(async () => {
    await load(true);
  }, [load]);

  const runScan = useCallback(
    async (deskOverride?: string): Promise<ScanResult> => {
      const deskScope =
        deskOverride ??
        (filtersRef.current.desk && filtersRef.current.desk !== 'ALL'
          ? filtersRef.current.desk
          : 'ALL');
      try {
        const result = await api.getSignalsScanner(deskScope);
        await load(false);
        const newSignals = result.new_signals?.length ?? 0;
        const activeSignals = result.active_signals?.length ?? 0;
        return {
          ok: true,
          newSignals,
          activeSignals,
          scanned: result.scanned_underlyings ?? [],
          message: `Scan complete — ${newSignals} new, ${activeSignals} active across ${result.scanned_underlyings?.length ?? 0} underlying(s).`,
        };
      } catch (err) {
        return {
          ok: false,
          newSignals: 0,
          activeSignals: 0,
          scanned: [],
          message: errorMessage(err, 'Scanner unavailable'),
        };
      }
    },
    [load],
  );


  const autoDetect = useCallback(
    async (input: { underlying: string; strategy?: string; timeframe?: string }) => {
      try {
        const response = await api.autoDetectSignal(input);
        return response.candidate ?? null;
      } catch {
        return null;
      }
    },
    [],
  );

  const executePaper = useCallback(
    async (signalId: string, input?: ExecutePaperInput): Promise<DeskActionResult> => {
      try {
        const response = await api.executeSignalPaper(
          signalId,
          input?.lots ?? undefined,
          input?.riskPercent ?? undefined,
          { allowClosedMarket: input?.allowClosedMarket ?? false },
        );
        await load(false);
        return {
          ok: response.success !== false,
          message: response.message || `Paper order ${response.order_id} filled at ${response.fill_price}.`,
        };
      } catch (err) {
        return { ok: false, message: errorMessage(err, 'Paper execution failed') };
      }
    },
    [load],
  );

  const removeSignal = useCallback(
    async (signalId: string): Promise<DeskActionResult> => {
      try {
        const response = await api.deleteSignal(signalId);
        await load(false);
        return { ok: true, message: response.message || 'Signal deleted.' };
      } catch (err) {
        return { ok: false, message: errorMessage(err, 'Delete failed') };
      }
    },
    [load],
  );

  const freshness = dataFreshness(updatedAt);

  return {
    rows,
    engines,
    loading,
    refreshing,
    error,
    updatedAt,
    ageMs: freshness.ageMs,
    stale: freshness.stale,
    source: 'rest' as const,
    liveSource: 'rest' as const,
    worker,
    refresh,
    runScan,
    autoDetect,
    executePaper,
    removeSignal,
  };
}
