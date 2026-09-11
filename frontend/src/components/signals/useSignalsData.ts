'use client';

/* Data layer for the signals desk: one hook owns every fetch (status probes,
   market session, active list, performance, audit, engines), the 15s poll,
   the SSE-driven refresh and the row actions. Desk components stay pure UI. */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { useSignalsStream } from '@/hooks/useSignalsStream';
import {
  type ActiveRow,
  type LedgerRow,
  type LedgerSummary,
  asNum,
  asStr,
  getObj,
  isHiddenTab,
  toActiveRow,
  toLedgerRow,
} from './signalsNormalize';

export type DeskFilter = 'ALL' | 'SCALP' | 'INTRADAY';
export type InstrumentFilter = 'ALL' | 'NIFTY' | 'BANKNIFTY' | 'SENSEX';

export const DESK_FILTERS: DeskFilter[] = ['ALL', 'SCALP', 'INTRADAY'];
export const INSTRUMENT_FILTERS: InstrumentFilter[] = ['ALL', 'NIFTY', 'BANKNIFTY', 'SENSEX'];

const FALLBACK_STRATEGIES = [
  'BREAKOUT',
  'MEAN_REVERSION',
  'TREND_PULLBACK',
  'VWAP_SCALP',
  'MICRO_MOMENTUM',
  'EMA_RIBBON',
  'GAMMA_SQUEEZE',
  'GAMMA_SPIKE',
  'ORB',
];

const REFRESH_EVENTS = new Set([
  'signal_created',
  'signal_deleted',
  'signals_bulk_deleted',
  'paper_execution',
  'scanner_update',
]);

export type SignalsKpis = { active: number | null; confirmed: number | null; armed: number | null };

const EMPTY_KPIS: SignalsKpis = { active: null, confirmed: null, armed: null };
export function useSignalsData() {
  /* filters */
  const [deskFilter, setDeskFilter] = useState<DeskFilter>('ALL');
  const [instrumentFilter, setInstrumentFilter] = useState<InstrumentFilter>('ALL');
  const [now, setNow] = useState(() => Date.now());

  /* status probe */
  const [kpis, setKpis] = useState<SignalsKpis>(EMPTY_KPIS);
  const [statusError, setStatusError] = useState<string | null>(null);

  /* market session (best-effort; execute stays enabled unless known closed) */
  const [marketClosed, setMarketClosed] = useState(false);

  /* active signals */
  const [activeRows, setActiveRows] = useState<ActiveRow[]>([]);
  const [activeLoading, setActiveLoading] = useState(true);
  const [activeError, setActiveError] = useState<string | null>(null);

  /* row action bookkeeping */
  const [executingId, setExecutingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [orderNote, setOrderNote] = useState<Record<string, string>>({});

  /* performance */
  const [perf, setPerf] = useState<Record<string, unknown> | null>(null);
  const [perfLoading, setPerfLoading] = useState(true);
  const [perfError, setPerfError] = useState<string | null>(null);

  /* audit ledger */
  const [auditRows, setAuditRows] = useState<LedgerRow[]>([]);
  const [auditSummary, setAuditSummary] = useState<LedgerSummary | null>(null);
  const [auditLoading, setAuditLoading] = useState(true);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [sanitizeBusy, setSanitizeBusy] = useState(false);
  const [sanitizeNote, setSanitizeNote] = useState<string | null>(null);

  /* engines (strategy universe for manual creation) */
  const [strategies, setStrategies] = useState<string[]>(FALLBACK_STRATEGIES);

  const filtersRef = useRef({ deskFilter, instrumentFilter });
  filtersRef.current = { deskFilter, instrumentFilter };  /* ----- loaders ----- */

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
      setMarketClosed(false);
    }
  }, []);

  const loadActive = useCallback(async () => {
    if (isHiddenTab()) return;
    const { deskFilter: df, instrumentFilter: inf } = filtersRef.current;
    setActiveLoading(true);
    setActiveError(null);
    try {
      const params: { desk?: string; instrument?: string } = {};
      if (df !== 'ALL') params.desk = df;
      if (inf !== 'ALL') params.instrument = inf;
      const res = await api.getSignalsActive(params);
      const raw = (res as unknown as Record<string, unknown>)?.signals;
      const list = Array.isArray(raw) ? raw : [];
      let rows = list.map(toActiveRow).filter((r): r is ActiveRow => r !== null);
      // Client-side safety net in case the backend ignores query params.
      if (inf !== 'ALL') {
        rows = rows.filter((r) => r.symbol.toUpperCase().replace(/\s+/g, '').includes(inf));
      }
      if (df === 'SCALP') {
        rows = rows.filter(
          (r) => r.isScalp === true || (r.desk ? r.desk.toUpperCase().includes('SCALP') : true),
        );
      } else if (df === 'INTRADAY') {
        rows = rows.filter(
          (r) => r.isScalp === false || (r.desk ? !r.desk.toUpperCase().includes('SCALP') : true),
        );
      }
      setActiveRows(rows);
    } catch (e) {
      setActiveRows([]);
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
    } catch (e) {
      setPerf(null);
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
      const res = await api.getSignalsAudit({ limit: 50 });
      const body = res as unknown as Record<string, unknown>;
      const raw = body?.trades;
      const sum = getObj(body?.summary);
      const list = Array.isArray(raw) ? raw : [];
      setAuditRows(list.map(toLedgerRow).filter((r): r is LedgerRow => r !== null));
      setAuditSummary({
        closed: asNum(sum?.total_closed ?? sum?.closed),
        winRate: asNum(sum?.win_rate),
        realized: asNum(sum?.net_realized_pnl),
        unrealized: asNum(sum?.net_unrealized_pnl),
        total: asNum(sum?.total_pnl),
      });
    } catch (e) {
      setAuditRows([]);
      setAuditError(e instanceof Error ? e.message : 'audit unavailable');
    } finally {
      setAuditLoading(false);
    }
  }, []);

  const loadEngines = useCallback(async () => {
    if (isHiddenTab()) return;
    try {
      const res = await api.getSignalEngines();
      const list = (res as unknown as Record<string, unknown>)?.strategies;
      if (Array.isArray(list) && list.length) {
        const names = list
          .map((s) => {
            if (typeof s === 'string') return s.trim();
            const o = getObj(s);
            return asStr(o?.name ?? o?.strategy ?? o?.id) ?? null;
          })
          .filter((s): s is string => !!s);
        if (names.length) {
          const merged = Array.from(new Set([...names.map((n) => n.toUpperCase()), ...FALLBACK_STRATEGIES]));
          setStrategies(merged);
          return;
        }
      }
    } catch {
      // keep fallbacks
    }
    setStrategies(FALLBACK_STRATEGIES);
  }, []);

  const refreshAll = useCallback(() => {
    void loadStatus();
    void loadMarket();
    void loadActive();
    void loadPerf();
    void loadAudit();
  }, [loadStatus, loadMarket, loadActive, loadPerf, loadAudit]);

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
  }, [deskFilter, instrumentFilter, loadActive]);

  // 15s poll for the active list; 5s clock keeps TTL countdowns honest.
  useEffect(() => {
    const poll = setInterval(() => {
      if (isHiddenTab()) return;
      void loadActive();
      void loadAudit();
    }, 15000);
    const clock = setInterval(() => setNow(Date.now()), 5000);
    return () => {
      clearInterval(poll);
      clearInterval(clock);
    };
  }, [loadActive, loadAudit]);

  const sseRefresh = useCallback(() => {
    if (isHiddenTab()) return;
    void loadActive();
    void loadStatus();
  }, [loadActive, loadStatus]);

  const handleStreamEvent = useCallback(
    (evt: string) => {
      if (REFRESH_EVENTS.has(evt) || evt.startsWith('signal_') || evt.startsWith('fsm')) sseRefresh();
    },
    [sseRefresh],
  );

  const { connected } = useSignalsStream({ onEvent: handleStreamEvent });

  const sortedActive = useMemo(
    () => [...activeRows].sort((a, b) => (b.timeMs ?? 0) - (a.timeMs ?? 0)),
    [activeRows],
  );

    /* ----- row actions ----- */

  const executePaper = useCallback(
    async (row: ActiveRow) => {
      if (marketClosed || row.state.toUpperCase().includes('CONFIRMED')) return;
      if (typeof window !== 'undefined') {
        const ok = window.confirm(`Execute paper trade for ${row.id} (${row.symbol} ${row.strategy})?`);
        if (!ok) return;
      }
      setExecutingId(row.id);
      setOrderNote((prev) => {
        const next = { ...prev };
        delete next[row.id];
        return next;
      });
      try {
        const res = await api.executeSignalPaper(row.id, 1);
        const r = res as unknown as Record<string, unknown>;
        const orderId = asStr(r?.order_id);
        const msg =
          asStr(r?.message) ??
          (r?.success
            ? `Filled ${asStr(r?.quantity) ?? 'â€”'} @ ${asStr(r?.fill_price) ?? 'â€”'}${orderId ? ` Â· order ${orderId.slice(0, 8)}â€¦` : ''}`
            : 'executed');
        setOrderNote((prev) => ({ ...prev, [row.id]: msg }));
        void loadActive();
        void loadAudit();
      } catch (e) {
        setOrderNote((prev) => ({
          ...prev,
          [row.id]: e instanceof Error ? e.message : 'execution failed',
        }));
      } finally {
        setExecutingId(null);
      }
    },
    [marketClosed, loadActive, loadAudit],
  );

  const deleteSignal = useCallback(
    async (row: ActiveRow) => {
      if (typeof window !== 'undefined') {
        const ok = window.confirm(`Delete signal ${row.id}?`);
        if (!ok) return;
      }
      setDeletingId(row.id);
      try {
        await api.deleteSignal(row.id);
        void loadActive();
        void loadStatus();
      } catch (e) {
        setOrderNote((prev) => ({
          ...prev,
          [row.id]: e instanceof Error ? e.message : 'delete failed',
        }));
      } finally {
        setDeletingId(null);
      }
    },
    [loadActive, loadStatus],
  );

  const sanitizeAudit = useCallback(async () => {
    setSanitizeBusy(true);
    setSanitizeNote(null);
    try {
      const res = await api.sanitizeSignalsAudit();
      const r = res as unknown as Record<string, unknown>;
      setSanitizeNote(
        `Sanitized â€” db repaired ${asStr(r?.db_restored_repaired) ?? '?'}, memory ${asStr(r?.memory_sanitized) ?? '?'}.`,
      );
      void loadAudit();
    } catch (e) {
      setSanitizeNote(e instanceof Error ? e.message : 'sanitize failed');
    } finally {
      setSanitizeBusy(false);
    }
  }, [loadAudit]);

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
    // hero KPIs
    kpis,
    statusError,
    marketClosed,
    // live desk
    sortedActive,
    activeLoading,
    activeError,
    now,
    connected,
    // performance
    perf,
    perfLoading,
    perfError,
    // ledger
    auditRows,
    auditSummary,
    auditLoading,
    auditError,
    sanitizeBusy,
    sanitizeNote,
    // engines
    strategies,
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




