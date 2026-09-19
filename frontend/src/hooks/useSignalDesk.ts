'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { AutoDetectCandidate } from '@/lib/api/signals';
import { errorMessage } from '@/lib/errors';
import {
  toActiveRow,
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

export type GenerateSignalInput = {
  underlying: string;
  strategy: string;
  direction: 'BULLISH' | 'BEARISH';
  timeframe: string;
  desk: DeskScope;
  confidence?: number;
  trigger?: number | null;
  stop_loss?: number | null;
  target_1?: number | null;
  target_2?: number | null;
  rationale?: string[];
  notifyTelegram?: boolean;
  allowClosedMarket?: boolean;
  confirm?: boolean;
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

function newIdempotencyKey(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch {
    // fall through
  }
  return `sig-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export type SignalDeskState = {
  rows: ActiveRow[];
  engines: string[];
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  updatedAt: number | null;
  worker: WorkerStatus;
  refresh: () => Promise<void>;
  runScan: (desk?: string) => Promise<ScanResult>;
  generate: (input: GenerateSignalInput) => Promise<DeskActionResult>;
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
      setUpdatedAt(Date.now());
    } else {
      setError(errorMessage(signalsResult.reason, 'Active signals unavailable'));
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

  const generate = useCallback(
    async (input: GenerateSignalInput): Promise<DeskActionResult> => {
      try {
        const response = await api.generateSignal(
          {
            underlying: input.underlying,
            strategy: input.strategy,
            direction: input.direction,
            timeframe: input.timeframe,
            signal_type: input.desk,
            is_scalp: input.desk === 'SCALP',
            confidence: input.confidence ?? 80,
            trigger_level: input.trigger ?? undefined,
            stop_loss: input.stop_loss ?? undefined,
            target_1: input.target_1 ?? undefined,
            target_2: input.target_2 ?? undefined,
            rationale: input.rationale,
            notify_telegram: input.notifyTelegram ?? true,
            allow_closed_market: input.allowClosedMarket ?? false,
            confirm: input.confirm ?? false,
          },
          { idempotencyKey: newIdempotencyKey() },
        );
        await load(false);
        const id =
          response.signal && typeof response.signal === 'object'
            ? String(
                (response.signal as Record<string, unknown>).signal_id ??
                  (response.signal as Record<string, unknown>).id ??
                  '',
              )
            : '';
        const paperError = response.paper_error ? ` Paper: ${response.paper_error}` : '';
        return {
          ok: true,
          signalId: id || undefined,
          message: response.deduplicated
            ? 'Duplicate suppressed — existing signal returned.'
            : `Signal generated.${paperError}`,
        };
      } catch (err) {
        return { ok: false, message: errorMessage(err, 'Signal generation failed') };
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

  return {
    rows,
    engines,
    loading,
    refreshing,
    error,
    updatedAt,
    worker,
    refresh,
    runScan,
    generate,
    autoDetect,
    executePaper,
    removeSignal,
  };
}
