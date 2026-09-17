'use client';

/* Data layer for the signals desk: one hook owns every fetch (status probes,
   market session, active list, performance, audit, engines), the 15s poll,
   the SSE-driven refresh and the row actions. Desk components stay pure UI. */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { useSignalStream } from '@/hooks/useSignalStream';
import type { SignalsStreamEvent } from '@/hooks/useSignalsStream';
import { useToast } from '@/components/ui/toast';
import {
  type ActiveRow,
  type LedgerRow,
  type LedgerSummary,
  asNum,
  asStr,
  getObj,
  isHiddenTab,
  matchesDeskFilter,
  matchesInstrumentFilter,
  toActiveRow,
  toLedgerRow,
  toLedgerSummary,
} from './signalsNormalize';

export type DeskFilter = 'ALL' | 'SCALP' | 'INTRADAY';
export type InstrumentFilter = 'ALL' | 'NIFTY' | 'BANKNIFTY' | 'SENSEX';
export type StatusFilter = 'ACTIVE' | 'ALL';

export const DESK_FILTERS: DeskFilter[] = ['ALL', 'SCALP', 'INTRADAY'];
export const INSTRUMENT_FILTERS: InstrumentFilter[] = ['ALL', 'NIFTY', 'BANKNIFTY', 'SENSEX'];
export const STATUS_FILTERS: StatusFilter[] = ['ACTIVE', 'ALL'];

/** Row window requested from the audit ledger. Truncation is detected by
 *  comparing `auditRows.length` against this same constant (never a magic
 *  50) and by the backend's global `total_signals_audited` aggregate. */
export const AUDIT_FETCH_LIMIT = 100;

/* No hardcoded strategy list: when the backend is unreachable the create
   dialog shows an empty universe instead of inventing strategies. */

const REFRESH_EVENTS = new Set([
  'signal_created',
  'signal_deleted',
  'signals_bulk_deleted',
  'paper_execution',
  'scanner_update',
]);

export type SignalsKpis = { active: number | null; confirmed: number | null; armed: number | null };

export type FeedHealthTelemetry = {
  status: 'LIVE' | 'SYNCING' | 'STALE' | 'CHAIN_UNAVAILABLE' | 'DOWN' | 'CLOSED' | 'AUTH_REQUIRED';
  is_healthy_for_trading: boolean;
  display_label: string;
  display_tone: 'on' | 'warn' | 'down' | 'degraded' | 'idle';
  message: string;
  market_session?: {
    is_open: boolean;
    reason: string;
    session: string;
    timestamp_ist?: string | null;
    market_open_ist?: string | null;
    market_close_ist?: string | null;
  };
  broker?: {
    provider: string;
    configured: boolean;
    token_status: string;
    token_usable: boolean;
  };
  spot_feed?: {
    is_running: boolean;
    is_ticking: boolean;
    last_tick_at?: string | null;
    tick_age_seconds?: number | null;
    symbols_cached: number;
  };
  option_chain?: {
    chain_status: string;
    strikes: number;
    chain_age_ms: number;
    option_marks: number;
    chain_mark_status: string;
  };
  timestamp?: string;
};

const EMPTY_KPIS: SignalsKpis = { active: null, confirmed: null, armed: null };
export function useSignalsData(opts?: {
  /** URL-driven initial filters (Phase 5 deep links). */
  initialDeskFilter?: DeskFilter;
  initialInstrumentFilter?: InstrumentFilter;
  initialStatusFilter?: StatusFilter;
}) {
  const toast = useToast();
  /* filters */
  const [deskFilter, setDeskFilter] = useState<DeskFilter>(opts?.initialDeskFilter ?? 'ALL');
  const [instrumentFilter, setInstrumentFilter] = useState<InstrumentFilter>(opts?.initialInstrumentFilter ?? 'ALL');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(opts?.initialStatusFilter ?? 'ACTIVE');
  const [now, setNow] = useState(() => Date.now());

  /* status probe */
  const [kpis, setKpis] = useState<SignalsKpis>(EMPTY_KPIS);
  const [statusError, setStatusError] = useState<string | null>(null);

  /* market session (best-effort; execute stays enabled unless known closed) */
  const [marketClosed, setMarketClosed] = useState(false);
  const [feedHealth, setFeedHealth] = useState<FeedHealthTelemetry | null>(null);

  /* active signals */
  const [activeRows, setActiveRows] = useState<ActiveRow[]>([]);
  const [activeLoading, setActiveLoading] = useState(true);
  const [activeError, setActiveError] = useState<string | null>(null);
  const [lastActiveAt, setLastActiveAt] = useState<number | null>(null);

  /* row action bookkeeping */
  const [executingId, setExecutingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [orderNote, setOrderNote] = useState<Record<string, string>>({});

  /* performance */
  const [perf, setPerf] = useState<Record<string, unknown> | null>(null);
  const [perfLoading, setPerfLoading] = useState(true);
  const [perfError, setPerfError] = useState<string | null>(null);
  const [lastPerfAt, setLastPerfAt] = useState<number | null>(null);

  /* audit ledger */
  const [auditRows, setAuditRows] = useState<LedgerRow[]>([]);
  const [auditSummary, setAuditSummary] = useState<LedgerSummary | null>(null);
  const [auditLoading, setAuditLoading] = useState(true);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [lastPnlAt, setLastPnlAt] = useState<number | null>(null);
  const [sanitizeBusy, setSanitizeBusy] = useState(false);
  const [sanitizeNote, setSanitizeNote] = useState<string | null>(null);
  const lastAuditRefetchRef = useRef(0);

  /* engines (strategy universe for manual creation) */
  const [strategies, setStrategies] = useState<string[]>([]);
  const [enginesData, setEnginesData] = useState<{
    approved_universe: string[];
    broker: string;
    strategies: any[];
  } | null>(null);
  const [enginesLoading, setEnginesLoading] = useState(false);
  const [enginesError, setEnginesError] = useState<string | null>(null);

  /* scanner */
  const [scannerData, setScannerData] = useState<{
    scanned_underlyings: string[];
    total_candidates: number;
    new_signals: any[];
    active_signals: any[];
    timestamp_ms: number;
  } | null>(null);
  const [scannerLoading, setScannerLoading] = useState(false);
  const [scannerError, setScannerError] = useState<string | null>(null);

  const filtersRef = useRef({ deskFilter, instrumentFilter, statusFilter });
  filtersRef.current = { deskFilter, instrumentFilter, statusFilter };  /* ----- loaders ----- */

  const loadStatus = useCallback(async () => {
    if (isHiddenTab()) return;
    setStatusError(null);
    try {
      const res = (await api.getSignalsStatus()) as unknown as Record<string, unknown>;
      const active = asNum(res?.active_count);
      const confirmed = asNum(res?.confirmed_count ?? res?.confirmed);
      const armed = asNum(res?.armed_count ?? res?.armed);
      setKpis({ active, confirmed, armed });
    } catch (e) {
      setStatusError(e instanceof Error ? e.message : 'status unavailable');
    }
  }, []);

  const loadMarket = useCallback(async () => {
    if (isHiddenTab()) return;
    try {
      const res = (await api.getMarketStatus()) as unknown as Record<string, unknown>;
      const data = getObj(res?.data) ?? (res as Record<string, unknown>);
      const session = asStr(data?.session)?.toUpperCase();
      const isTradingDay = data?.is_trading_day;
      setMarketClosed(session === 'CLOSED' || isTradingDay === false);
    } catch {
      // Fail-closed: an unknown session must not enable execution.
      setMarketClosed(true);
    }
  }, []);

  const loadActive = useCallback(async () => {
    if (isHiddenTab()) return;
    const { deskFilter: df, instrumentFilter: inf, statusFilter: sf } = filtersRef.current;
    setActiveLoading(true);
    setActiveError(null);
    try {
      const params: { desk?: string; instrument?: string; status?: string } = {};
      if (df !== 'ALL') params.desk = df;
      if (inf !== 'ALL') params.instrument = inf;
      if (sf === 'ALL') params.status = 'ALL';
      const res = await api.getSignalsActive(params);
      const raw = (res as unknown as Record<string, unknown>)?.signals;
      const list = Array.isArray(raw) ? raw : [];
      let rows = list.map(toActiveRow).filter((r): r is ActiveRow => r !== null);
      // Client-side safety net in case the backend ignores query params.
      // Exact instrument token (NIFTY must not match BANKNIFTY) and explicit
      // desk matching (null-desk rows must not pass both desk views).
      if (inf !== 'ALL') {
        rows = rows.filter((r) => matchesInstrumentFilter(r.symbol, inf));
      }
      if (df !== 'ALL') {
        rows = rows.filter((r) => matchesDeskFilter(r.desk, r.isScalp, df));
      }
      setActiveRows(rows);
      setLastActiveAt(Date.now());
    } catch (e) {
      // Transient failure keeps last-good rows on screen and surfaces the
      // failure as stale — only a successful fetch may replace the desk.
      setActiveError(e instanceof Error ? e.message : 'active signals unavailable');
    } finally {
      setActiveLoading(false);
    }
  }, []);

  const loadPerf = useCallback(async () => {
    if (isHiddenTab()) return;
    setPerfLoading(true);
    setPerfError(null);
    try {
      const res = await api.getSignalsPerformance();
      setPerf((res as unknown as Record<string, unknown>) ?? null);
      setLastPerfAt(Date.now());
    } catch (e) {
      // Keep the last-good snapshot; the banner marks it stale.
      setPerfError(e instanceof Error ? e.message : 'performance unavailable');
    } finally {
      setPerfLoading(false);
    }
  }, []);

  const loadAudit = useCallback(async () => {
    if (isHiddenTab()) return;
    setAuditLoading(true);
    setAuditError(null);
    try {
      const res = await api.getSignalsAudit({ limit: AUDIT_FETCH_LIMIT });
      const body = res as unknown as Record<string, unknown>;
      const raw = body?.trades;
      const sum = getObj(body?.summary);
      const rawFeed = getObj(body?.feed_health);
      if (rawFeed) {
        setFeedHealth(rawFeed as unknown as FeedHealthTelemetry);
        const mkt = getObj(rawFeed.market_session);
        if (typeof mkt?.is_open === 'boolean') {
          setMarketClosed(!mkt.is_open);
        }
      }
      const list = Array.isArray(raw) ? raw : [];
      setAuditRows(list.map(toLedgerRow).filter((r): r is LedgerRow => r !== null));
      setAuditSummary(toLedgerSummary(sum));
      setLastPnlAt(Date.now());
    } catch (e) {
      // Keep last-good ledger + summary so the book doesn't blink empty on a
      // transient failure; the strip/tab banner marks it stale instead.
      setAuditError(e instanceof Error ? e.message : 'audit unavailable');
    } finally {
      setAuditLoading(false);
    }
  }, []);

  /** Merge an `audit_pnl_update` SSE delta into the ledger without refetch. */
  const applyPnlDelta = useCallback((data: unknown) => {
    const obj = getObj(data);
    if (!obj) return;
    const sum = getObj(obj.summary);
    if (sum) setAuditSummary(toLedgerSummary(sum));
    const rawTrades = obj.trades;
    if (Array.isArray(rawTrades) && rawTrades.length) {
      const deltas = rawTrades.map(toLedgerRow).filter((r): r is LedgerRow => r !== null);
      if (deltas.length) {
        setAuditRows((prev) => {
          if (!prev.length) return deltas;
          const byId = new Map(prev.map((r) => [r.id, r]));
          for (const d of deltas) byId.set(d.id, { ...(byId.get(d.id) ?? d), ...d });
          return [...byId.values()];
        });
      }
    }
    setLastPnlAt(typeof obj.timestamp_ms === 'number' ? obj.timestamp_ms : Date.now());
    setAuditError(null);
  }, []);

  /** Throttled full ledger refetch for P0 lifecycle events (max 1 / 2s). */
  const requestAuditRefetch = useCallback(() => {
    const nowMs = Date.now();
    if (nowMs - lastAuditRefetchRef.current < 2000) return;
    lastAuditRefetchRef.current = nowMs;
    void loadAudit();
  }, [loadAudit]);

  const loadEngines = useCallback(async () => {
    if (isHiddenTab()) return;
    setEnginesLoading(true);
    setEnginesError(null);
    try {
      const res = await api.getSignalEngines();
      setEnginesData(res);
      const list = (res as unknown as Record<string, unknown>)?.strategies;
      const names = Array.isArray(list)
        ? list
            .map((s) => {
              if (typeof s === 'string') return s.trim();
              const o = getObj(s);
              return asStr(o?.name ?? o?.strategy ?? o?.id) ?? null;
            })
            .filter((s): s is string => !!s)
        : [];
      // A successful fetch is authoritative: mirror the registry even when
      // empty, so the create dialog can block instead of inventing a strategy.
      setStrategies(Array.from(new Set(names.map((n) => n.toUpperCase()))));
    } catch (e) {
      // Keep the last-good strategy universe; the dialog warns that the
      // registry is stale rather than silently showing a blank select.
      setEnginesError(e instanceof Error ? e.message : 'engine registry unavailable');
    } finally {
      setEnginesLoading(false);
    }
  }, []);

  const loadScanner = useCallback(async () => {
    if (isHiddenTab()) return;
    setScannerLoading(true);
    setScannerError(null);
    try {
      const { deskFilter: df } = filtersRef.current;
      const res = await api.getSignalsScanner(df !== 'ALL' ? df : undefined);
      setScannerData(res);
    } catch (e) {
      setScannerError(e instanceof Error ? e.message : 'Scanner failed');
    } finally {
      setScannerLoading(false);
    }
  }, []);

  const autoDetect = useCallback(async (underlying: string) => {
    try {
      const res = await api.autoDetectSignal({ underlying });
      if (res.detected) {
        toast.show(`Auto-detected candidate for ${underlying}`, 'success');
        void loadActive();
      } else {
        toast.show(res.message || `No candidate setup for ${underlying}`, 'info');
      }
      return res;
    } catch (e) {
      toast.show(e instanceof Error ? e.message : 'Auto-detect failed', 'error');
      return null;
    }
  }, [toast, loadActive]);

  const refreshAll = useCallback(() => {
    void loadStatus();
    void loadMarket();
    void loadActive();
    void loadPerf();
    void loadAudit();
    void loadEngines();
    void loadScanner();
  }, [loadStatus, loadMarket, loadActive, loadPerf, loadAudit, loadEngines, loadScanner]);

  /* ----- effects ----- */

  useEffect(() => {
    void loadStatus();
    void loadMarket();
    void loadActive();
    void loadPerf();
    void loadAudit();
    void loadEngines();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void loadActive();
  }, [deskFilter, instrumentFilter, statusFilter, loadActive]);

  // Coordinated polling (no triple-fetch):
  // - 15s: active list + status probe (single-flight, always).
  // - 5s: audit ledger ONLY when SSE is offline (otherwise SSE deltas +
  //   throttled refetch own the ledger and a 15s audit poll would double it).
  // - 1s clock keeps the ledger strip age ("LIVE · Ns AGO") and TTLs ticking.
  const connectedRef = useRef(false);
  useEffect(() => {
    const poll = setInterval(() => {
      if (isHiddenTab()) return;
      void loadActive();
      void loadStatus();
    }, 15000);
    const fastLedgerPoll = setInterval(() => {
      if (isHiddenTab() || connectedRef.current) return;
      void loadAudit();
    }, 5000);
    const clock = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      clearInterval(poll);
      clearInterval(fastLedgerPoll);
      clearInterval(clock);
    };
  }, [loadActive, loadStatus, loadAudit]);

  // SSE-driven active refresh, debounced to 1s so a burst of P0 lifecycle
  // events (confirm + staged exit + outcome) collapses to one fetch.
  const sseRefreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sseRefresh = useCallback(() => {
    if (isHiddenTab()) return;
    if (sseRefreshTimer.current) return;
    sseRefreshTimer.current = setTimeout(() => {
      sseRefreshTimer.current = null;
      if (isHiddenTab()) return;
      void loadActive();
      void loadStatus();
    }, 1000);
  }, [loadActive, loadStatus]);

  const handleStreamEvent = useCallback(
    (evt: string, data: unknown) => {
      // Feed health telemetry broadcast (~5s heartbeat or on state transition)
      if (evt === 'FEED_STATUS') {
        const feedObj = getObj(data);
        if (feedObj) {
          setFeedHealth(feedObj as unknown as FeedHealthTelemetry);
          const mkt = getObj(feedObj.market_session);
          if (typeof mkt?.is_open === 'boolean') {
            setMarketClosed(!mkt.is_open);
          }
        }
        return;
      }
      // Realtime P&L path (~3s cadence): merge MTM deltas, no refetch.
      if (evt === 'audit_pnl_update') {
        if (!isHiddenTab()) applyPnlDelta(data);
        return;
      }
      // Lifecycle events change ledger membership (fill / T1 / outcome) —
      // refresh active list immediately, ledger throttled.
      if (
        evt === 'paper_execution' ||
        evt === 'signal_confirmed' ||
        evt === 'signal_staged_exit' ||
        evt === 'signal_outcome' ||
        evt === 'signal_breakeven'
      ) {
        sseRefresh();
        requestAuditRefetch();
        return;
      }
      if (REFRESH_EVENTS.has(evt) || evt.startsWith('signal_') || evt.startsWith('fsm')) sseRefresh();
    },
    [sseRefresh, applyPnlDelta, requestAuditRefetch],
  );

  /* Phase 0 shared stream: the context owns the one SSE subscription for the
     whole tab. Its event buffer is newest-first, so replay only unprocessed
     events oldest-first (a WeakSet keeps identity bookkeeping cheap). */
  const { connected, events: streamEvents } = useSignalStream();
  const processedStreamEvents = useRef<WeakSet<SignalsStreamEvent>>(new WeakSet());
  useEffect(() => {
    const fresh = streamEvents.filter((e) => !processedStreamEvents.current.has(e));
    if (fresh.length === 0) return;
    for (const e of fresh) processedStreamEvents.current.add(e);
    for (let i = fresh.length - 1; i >= 0; i -= 1) {
      handleStreamEvent(fresh[i].type, fresh[i].data);
    }
  }, [streamEvents, handleStreamEvent]);

  useEffect(() => {
    connectedRef.current = connected;
  }, [connected]);

  const sortedActive = useMemo(
    () => [...activeRows].sort((a, b) => (b.timeMs ?? 0) - (a.timeMs ?? 0)),
    [activeRows],
  );

    /* ----- row actions ----- */

  const executePaper = useCallback(
    async (row: ActiveRow, opts?: { allowClosedMarket?: boolean }) => {
      // CONFIRMED is an executable lifecycle state (filled/accepted) — only
      // a closed market blocks execution. Terminal states are still guarded
      // by the desk's disabled button; this is the fail-closed floor.
      if (marketClosed && !opts?.allowClosedMarket) {
        const msg = 'Market is closed — paper execution is disabled.';
        setOrderNote((prev) => ({ ...prev, [row.id]: msg }));
        toast.error(`Execution blocked — ${row.symbol} ${row.strategy}`, msg);
        return;
      }
      setExecutingId(row.id);
      setOrderNote((prev) => {
        const next = { ...prev };
        delete next[row.id];
        return next;
      });
      try {
        const res = await api.executeSignalPaper(row.id, 1, undefined, opts);
        const r = res as unknown as Record<string, unknown>;
        const orderId = asStr(r?.order_id);
        const msg =
          asStr(r?.message) ??
          (r?.success
            ? `Filled ${asStr(r?.quantity) ?? '—'} @ ${asStr(r?.fill_price) ?? '—'}${orderId ? ` · order ${orderId.slice(0, 8)}…` : ''}`
            : 'executed');
        setOrderNote((prev) => ({ ...prev, [row.id]: msg }));
        toast.success(`Paper trade executed — ${row.symbol} ${row.strategy}`, msg);
        void loadActive();
        void loadAudit();
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'execution failed';
        setOrderNote((prev) => ({ ...prev, [row.id]: msg }));
        toast.error(`Execution failed — ${row.symbol} ${row.strategy}`, msg);
      } finally {
        setExecutingId(null);
      }
    },
    [marketClosed, loadActive, loadAudit, toast],
  );

  const deleteSignal = useCallback(
    async (row: ActiveRow) => {
      setDeletingId(row.id);
      try {
        await api.deleteSignal(row.id);
        toast.info(`Signal deleted — ${row.symbol} ${row.strategy}`, 'Removed from the active desk.');
        void loadActive();
        void loadStatus();
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'delete failed';
        setOrderNote((prev) => ({ ...prev, [row.id]: msg }));
        toast.error(`Delete failed — ${row.symbol} ${row.strategy}`, msg);
      } finally {
        setDeletingId(null);
      }
    },
    [loadActive, loadStatus, toast],
  );

  const sanitizeAudit = useCallback(async () => {
    setSanitizeBusy(true);
    setSanitizeNote(null);
    try {
      const res = await api.sanitizeSignalsAudit();
      const r = res as unknown as Record<string, unknown>;
      const note =
        `Sanitized — db repaired ${asStr(r?.db_restored_repaired) ?? '?'}, memory ${asStr(r?.memory_sanitized) ?? '?'}.`;
      setSanitizeNote(note);
      toast.success('Audit ledger sanitized', note);
      void loadAudit();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'sanitize failed';
      setSanitizeNote(msg);
      toast.error('Ledger sanitize failed', msg);
    } finally {
      setSanitizeBusy(false);
    }
  }, [loadAudit, toast]);

  /** Called by the create dialog after a signal is generated. */
  const afterCreate = useCallback(() => {
    void loadActive();
    void loadStatus();
  }, [loadActive, loadStatus]);

  return {
    // filters
    deskFilter,
    setDeskFilter,
    instrumentFilter,
    setInstrumentFilter,
    statusFilter,
    setStatusFilter,
    // hero KPIs
    kpis,
    statusError,
    marketClosed,
    // live desk
    sortedActive,
    activeLoading,
    activeError,
    lastActiveAt,
    now,
    connected,
    feedHealth,
    // performance
    perf,
    perfLoading,
    perfError,
    lastPerfAt,
    // ledger
    auditRows,
    auditSummary,
    auditLoading,
    auditError,
    auditLimit: AUDIT_FETCH_LIMIT,
    lastPnlAt,
    sanitizeBusy,
    sanitizeNote,
    // engines
    strategies,
    enginesData,
    enginesLoading,
    enginesError,
    loadEngines,
    // scanner
    scannerData,
    scannerLoading,
    scannerError,
    loadScanner,
    autoDetect,
    // actions + row state
    refreshAll,
    executePaper,
    deleteSignal,
    sanitizeAudit,
    afterCreate,
    executingId,
    deletingId,
    orderNote,
  };
}

export default useSignalsData;




