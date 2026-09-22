'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import { computePaperTotals, ledgerMarkSource, type LedgerMarkSource, type PaperTotals } from '@/lib/ledger';
import {
  toLedgerRow,
  toLedgerSummary,
  maxPayloadTimestampMs,
  dataFreshness,
  type LedgerRow,
  type LedgerSummary,
} from '@/lib/signalsNormalize';
import type { PortfolioSummary, VirtualOrder, VirtualPosition } from '@/lib/types';
import { useCommandSection, useSignalEvents } from '@/context/AppStreamContext';
import { useSmartInterval } from './useSmartInterval';

type PaperSectionValue = {
  portfolio?: PortfolioSummary | null;
  positions?: VirtualPosition[] | null;
};

function narrowPaperSection(value: unknown): PaperSectionValue | null {
  if (!value || typeof value !== 'object') return null;
  return value as PaperSectionValue;
}

export type LedgerActionResult = { ok: boolean; message: string };

export type PaperLedgerState = {
  portfolio: PortfolioSummary | null;
  positions: VirtualPosition[];
  orders: VirtualOrder[];
  totals: PaperTotals;
  ledgerRows: LedgerRow[];
  ledgerSummary: LedgerSummary | null;
  liveSource: 'stream' | 'rest';
  /** Provenance of the mark behind unrealized MTM (stream vs REST snapshot). */
  markSource: LedgerMarkSource;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  updatedAt: number | null;
  /** Age of `updatedAt` in ms. Null when the payload carried no instant. */
  ageMs: number | null;
  /** True when `updatedAt` is missing or older than the staleness window. */
  stale: boolean;
  refresh: () => Promise<void>;
  closePosition: (positionId: string) => Promise<LedgerActionResult>;
  closeAll: () => Promise<LedgerActionResult>;
  resetAccount: () => Promise<LedgerActionResult>;
};

export function usePaperLedger(
  options: { safetyRefreshMs?: number | null; ledgerLimit?: number } = {},
): PaperLedgerState {
  const { safetyRefreshMs = null, ledgerLimit = 50 } = options;
  const section = useCommandSection('paper');
  const sectionValue = useMemo(() => narrowPaperSection(section?.value), [section?.value]);

  const [restPortfolio, setRestPortfolio] = useState<PortfolioSummary | null>(null);
  const [restPositions, setRestPositions] = useState<VirtualPosition[]>([]);
  const [orders, setOrders] = useState<VirtualOrder[]>([]);
  const [ledgerRows, setLedgerRows] = useState<LedgerRow[]>([]);
  const [ledgerSummary, setLedgerSummary] = useState<LedgerSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restUpdatedAt, setRestUpdatedAt] = useState<number | null>(null);
  const requestIdRef = useRef(0);

  const load = useCallback(
    async (showSpinner: boolean) => {
      const requestId = ++requestIdRef.current;
      if (showSpinner) setRefreshing(true);
      const [portfolioResult, positionsResult, ordersResult, auditResult] =
        await Promise.allSettled([
          api.getPaperPortfolio(),
          api.getPaperPositions(),
          api.getPaperOrders(),
          api.getSignalsAudit({ limit: ledgerLimit }),
        ]);
      if (requestIdRef.current !== requestId) return;

      const failures: string[] = [];
      if (portfolioResult.status === 'fulfilled') {
        setRestPortfolio(portfolioResult.value.data ?? null);
      } else {
        failures.push(errorMessage(portfolioResult.reason, 'Portfolio unavailable'));
      }
      if (positionsResult.status === 'fulfilled') {
        setRestPositions(positionsResult.value.data ?? []);
      } else {
        failures.push(errorMessage(positionsResult.reason, 'Positions unavailable'));
      }
      if (ordersResult.status === 'fulfilled') {
        setOrders(ordersResult.value.data ?? []);
      } else {
        failures.push(errorMessage(ordersResult.reason, 'Orders unavailable'));
      }
      if (auditResult.status === 'fulfilled') {
        const records = auditResult.value.trades ?? [];
        setLedgerRows(
          records
            .map((record) => toLedgerRow(record))
            .filter((row): row is LedgerRow => row !== null),
        );
        setLedgerSummary(toLedgerSummary(auditResult.value.summary as unknown as Record<string, unknown>));
      } else {
        failures.push(errorMessage(auditResult.reason, 'Ledger unavailable'));
      }

      setError(failures.length > 0 ? failures[0] : null);
      // Prefer backend instants (audit timestamp_ms / order fills) over the
      // browser clock. A fully-failed load keeps the last age (no bump).
      const anySuccess =
        portfolioResult.status === 'fulfilled' ||
        positionsResult.status === 'fulfilled' ||
        ordersResult.status === 'fulfilled' ||
        auditResult.status === 'fulfilled';
      if (anySuccess) {
        const payloadTs = maxPayloadTimestampMs([
          portfolioResult.status === 'fulfilled' ? portfolioResult.value : null,
          positionsResult.status === 'fulfilled' ? positionsResult.value : null,
          ordersResult.status === 'fulfilled' ? ordersResult.value : null,
          auditResult.status === 'fulfilled' ? auditResult.value : null,
        ]);
        // Payload instant only. A successful fetch that carries no backend
        // timestamp keeps the last known age — never stamped as "just now".
        if (payloadTs !== null) {
          setRestUpdatedAt(payloadTs);
        }
      }
      setLoading(false);
      if (showSpinner) setRefreshing(false);
    },
    [ledgerLimit],
  );

  useEffect(() => {
    void load(false);
  }, [load]);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scheduleRefresh = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      debounceRef.current = null;
      void load(false);
    }, 750);
  }, [load]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  useSignalEvents(
    useCallback(() => {
      scheduleRefresh();
    }, [scheduleRefresh]),
  );

  useSmartInterval(
    useCallback(() => load(false), [load]),
    safetyRefreshMs,
    { fireOnMount: false },
  );

  const portfolio = sectionValue?.portfolio ?? restPortfolio;
  const positions = sectionValue?.positions ?? restPositions;

  const streamUpdatedAt = section ? Date.parse(section.updated_at) : NaN;
  const updatedAtCandidates = [restUpdatedAt, Number.isFinite(streamUpdatedAt) ? streamUpdatedAt : null]
    .filter((value): value is number => value !== null);
  const updatedAt = updatedAtCandidates.length > 0 ? Math.max(...updatedAtCandidates) : null;

  const liveSource: 'stream' | 'rest' =
    sectionValue?.portfolio !== undefined || sectionValue?.positions !== undefined ? 'stream' : 'rest';

  const totals = useMemo(() => computePaperTotals(portfolio, positions), [portfolio, positions]);
  const freshness = dataFreshness(updatedAt);

  const refresh = useCallback(async () => {
    await load(true);
  }, [load]);

  const closePosition = useCallback(
    async (positionId: string): Promise<LedgerActionResult> => {
      try {
        await api.squareOffPosition(positionId);
        await load(false);
        return { ok: true, message: 'Position squared off.' };
      } catch (err) {
        return { ok: false, message: errorMessage(err, 'Square-off failed') };
      }
    },
    [load],
  );

  const closeAll = useCallback(async (): Promise<LedgerActionResult> => {
    try {
      await api.squareOffAllPositions();
      await load(false);
      return { ok: true, message: 'All positions squared off.' };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Square-off all failed') };
    }
  }, [load]);

  const resetAccount = useCallback(async (): Promise<LedgerActionResult> => {
    try {
      await api.resetPaperAccount();
      await load(false);
      return { ok: true, message: 'Paper account reset.' };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Reset failed') };
    }
  }, [load]);

  return {
    portfolio,
    positions,
    orders,
    totals,
    ledgerRows,
    ledgerSummary,
    liveSource,
    markSource: ledgerMarkSource(liveSource),
    loading,
    refreshing,
    error,
    updatedAt,
    ageMs: freshness.ageMs,
    stale: freshness.stale,
    refresh,
    closePosition,
    closeAll,
    resetAccount,
  };
}
