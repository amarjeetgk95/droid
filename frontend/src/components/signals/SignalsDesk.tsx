'use client';

/* Signals terminal — institutional order-desk presentation over useSignalsData().
   Flat hairline surfaces, mono numerals, semantic color only on data. */

import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import {
  Activity,
  Eraser,
  Play,
  Plus,
  RefreshCw,
  Trash2,
  FileText,
} from 'lucide-react';
import { EmptyNote, RetryButton, fmtINR } from '@/components/ui/desk';
import { normalizeDirection } from '@/components/ui/desk';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import { ConfirmDialog, type ConfirmIntentRow } from '@/components/ui/ConfirmDialog';
import { SignalDetailDrawer } from '@/components/signals/SignalDetailDrawer';
import { SignalCreateDialog } from '@/components/signals/SignalCreateDialog';
import {
  DESK_FILTERS,
  INSTRUMENT_FILTERS,
  STATUS_FILTERS,
  useSignalsData,
  type DeskFilter,
  type InstrumentFilter,
  type StatusFilter,
} from '@/components/signals/useSignalsData';
import {
  asNum,
  confPct,
  executionEligibility,
  fmtConf,
  fmtDateTimeMs,
  fmtDist,
  fmtTimeMs,
  fmtTtl,
  isOpenLedgerStatus,
  isUnfilledLedgerRow,
  prettyKey,
  stateTone,
  sumLedgerTotals,
  type ActiveRow,
} from '@/components/signals/signalsNormalize';

type TabKey = 'live' | 'scanner' | 'performance' | 'history' | 'engines';

/** Visual order of the tablist — also the arrow-key roving order. */
const TAB_ORDER: TabKey[] = ['live', 'scanner', 'engines', 'performance', 'history'];

export type SignalsDeskProps = {
  /** URL-driven initial values (Phase 5). URL wins over internal defaults. */
  initialDeskFilter?: DeskFilter;
  initialInstrumentFilter?: InstrumentFilter;
  initialStatusFilter?: StatusFilter;
  initialTab?: TabKey;
  /** URL change callbacks — write params back (deep-linkable desk state). */
  onDeskFilterChange?: (v: DeskFilter) => void;
  onInstrumentFilterChange?: (v: InstrumentFilter) => void;
  onStatusFilterChange?: (v: StatusFilter) => void;
  onTabChange?: (v: TabKey) => void;
};

/** Descriptor for the single ConfirmDialog instance (execution safety §5). */
type PendingAction =
  | { kind: 'execute'; row: ActiveRow }
  | { kind: 'delete'; row: ActiveRow }
  | { kind: 'sanitize' };

function Skeletons({ rows = 3 }: { rows?: number }) {
  return (
    <div style={{ display: 'grid', gap: 8, padding: 16 }}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skel" style={{ height: 12, width: `${84 - i * 10}%` }}>.</div>
      ))}
    </div>
  );
}

function StateTag({ state }: { state: string }) {
  return <span className={`sg-tag ${stateTone(state) === 'bull' ? 'bull' : stateTone(state) === 'bear' ? 'bear' : stateTone(state) === 'info' ? 'info' : stateTone(state) === 'warn' ? 'warn' : 'neut'}`}>{state}</span>;
}

/** Intent block for the confirm dialog — restates exactly what will happen (EXECUTION_SAFETY.md §6). */
function confirmIntentRows(pending: PendingAction | null): ConfirmIntentRow[] {
  if (!pending) return [];
  if (pending.kind === 'sanitize') {
    return [
      { label: 'Target', value: 'Audit ledger' },
      { label: 'Action', value: 'Rewrite from backend truth' },
    ];
  }
  const r = pending.row;
  const dir = r.direction === 'BEARISH' ? 'SHORT' : r.direction === 'BULLISH' ? 'LONG' : '—';
  const rows: ConfirmIntentRow[] = [
    { label: 'Signal', value: r.id.slice(0, 8) },
    { label: 'Instrument', value: `${r.symbol} · ${dir}` },
    { label: 'Strategy', value: prettyKey(r.strategy) },
  ];
  if (pending.kind === 'execute') {
    rows.push(
      { label: 'Entry', value: r.trigger === null ? '—' : fmtINR(r.trigger) },
      { label: 'Stop', value: r.sl === null ? '—' : fmtINR(r.sl) },
      { label: 'Confidence', value: fmtConf(r.confidence) },
      { label: 'Mode', value: 'Paper trade · qty 1' },
    );
  }
  return rows;
}

function DirText({ direction }: { direction: unknown }) {
  const d = normalizeDirection(direction);
  if (d === 'NEUTRAL') return <span className="sg-dir" style={{ color: 'var(--ds-ink-3)' }}>—</span>;
  const long = d === 'BULLISH';
  return <span className={`sg-dir ${long ? 'long' : 'short'}`}>{long ? 'LONG' : 'SHORT'}</span>;
}

function TtlText({ label, tone }: { label: string; tone: 'ok' | 'warn' | 'expired' }) {
  return <span className={`sg-ttl${tone === 'ok' ? '' : ` ${tone}`}`}>{label}</span>;
}

function ConfText({ conf }: { conf: number | null }) {
  return (
    <span className="sg-conf">
      <span className="bar" aria-hidden="true">
        <i style={{ width: `${confPct(conf)}%` }} />
      </span>
      <span className="sg-num">{fmtConf(conf)}</span>
    </span>
  );
}

function pnlCls(v: number | null): string {
  if (v === null) return '';
  return v > 0 ? 'pos-num' : v < 0 ? 'neg-num' : '';
}
export function SignalsDesk({
  initialDeskFilter,
  initialInstrumentFilter,
  initialStatusFilter,
  initialTab,
  onDeskFilterChange,
  onInstrumentFilterChange,
  onStatusFilterChange,
  onTabChange,
}: SignalsDeskProps = {}) {
  const {
    deskFilter,
    setDeskFilter: setDeskFilterInternal,
    instrumentFilter,
    setInstrumentFilter: setInstrumentFilterInternal,
    statusFilter,
    setStatusFilter: setStatusFilterInternal,
    statusError,
    marketClosed,
    sortedActive,
    activeLoading,
    activeError,
    lastActiveAt,
    now,
    connected,
    feedHealth,
    perf,
    perfLoading,
    perfError,
    lastPerfAt,
    auditRows,
    auditSummary,
    auditLoading,
    auditError,
    auditLimit,
    lastPnlAt,
    sanitizeBusy,
    sanitizeNote,
    strategies,
    enginesData,
    enginesLoading,
    enginesError,
    loadEngines,
    scannerData,
    scannerLoading,
    scannerError,
    loadScanner,
    autoDetect,
    refreshAll,
    executePaper,
    deleteSignal,
    sanitizeAudit,
    afterCreate,
    executingId,
    deletingId,
    orderNote,
  } = useSignalsData({
    initialDeskFilter,
    initialInstrumentFilter,
    initialStatusFilter,
  });

  const [tab, setTabInternal] = useState<TabKey>(initialTab ?? 'live');
  const setTab = useCallback(
    (v: TabKey) => {
      setTabInternal(v);
      onTabChange?.(v);
    },
    [onTabChange],
  );
  const setDeskFilter = useCallback(
    (v: DeskFilter) => {
      setDeskFilterInternal(v);
      onDeskFilterChange?.(v);
    },
    [setDeskFilterInternal, onDeskFilterChange],
  );
  const setInstrumentFilter = useCallback(
    (v: InstrumentFilter) => {
      setInstrumentFilterInternal(v);
      onInstrumentFilterChange?.(v);
    },
    [setInstrumentFilterInternal, onInstrumentFilterChange],
  );
  const setStatusFilter = useCallback(
    (v: StatusFilter) => {
      setStatusFilterInternal(v);
      onStatusFilterChange?.(v);
    },
    [setStatusFilterInternal, onStatusFilterChange],
  );
  const [createOpen, setCreateOpen] = useState(false);

  /* Automatic-activation tab switch: arrow keys and clicks share this so the
     lazy scanner/engine loads fire once per activation. */
  const selectTab = useCallback(
    (v: TabKey) => {
      setTab(v);
      if (v === 'scanner') void loadScanner();
      if (v === 'engines') void loadEngines();
    },
    [setTab, loadScanner, loadEngines],
  );

  /* Zero-row empty states must always offer a way back to a populated view. */
  const filtersDirty = deskFilter !== 'ALL' || instrumentFilter !== 'ALL' || statusFilter !== 'ACTIVE';
  const resetFilters = useCallback(() => {
    setDeskFilter('ALL');
    setInstrumentFilter('ALL');
    setStatusFilter('ACTIVE');
  }, [setDeskFilter, setInstrumentFilter, setStatusFilter]);

  /* WAI-ARIA tablist keyboard support: arrows move + activate, Home/End jump.
     Roving tabIndex keeps a single tab stop. */
  const onTablistKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLElement>) => {
      if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(e.key)) return;
      e.preventDefault();
      const idx = TAB_ORDER.indexOf(tab);
      const next =
        e.key === 'Home'
          ? 0
          : e.key === 'End'
            ? TAB_ORDER.length - 1
            : e.key === 'ArrowRight'
              ? (idx + 1) % TAB_ORDER.length
              : (idx - 1 + TAB_ORDER.length) % TAB_ORDER.length;
      selectTab(TAB_ORDER[next]);
      document.getElementById(`sg-tab-${TAB_ORDER[next]}`)?.focus();
    },
    [tab, selectTab],
  );

  /* Execution safety (EXECUTION_SAFETY.md §5): consequential actions open an
     explicit-intent ConfirmDialog instead of firing immediately. One pending
     descriptor drives the single dialog instance. */
  const [pending, setPending] = useState<PendingAction | null>(null);
  const closePending = useCallback(() => setPending(null), []);

  /* Dossier (detail drawer) selection — works for live and ledger rows. */
  const [dossierId, setDossierId] = useState<string | null>(null);
  const openDossier = useCallback((id: string) => setDossierId(id), []);
  const closeDossier = useCallback(() => setDossierId(null), []);

  /* Keyboard row navigation state (the effect lives below, after the row
     collections it reads). j/k or arrows move, Enter opens the dossier,
     x executes (through the confirm dialog), Esc clears selection. */
  const [activeRowId, setActiveRowId] = useState<string | null>(null);

  /* performance formatting (defensive) */
  const perfStats = useMemo(() => {
    if (!perf) return null;
    const num = (k: string): number | null => asNum(perf[k]);
    const f = (k: string, digits = 2): string => {
      const v = num(k);
      return v === null ? '-' : v.toFixed(k === 'win_rate_pct' ? 1 : digits);
    };
    const i = (k: string): string => {
      const v = num(k);
      return v === null ? '-' : String(Math.round(v));
    };
    return { num, f, i };
  }, [perf]);

  const wr = perfStats?.num('win_rate_pct') ?? null;
  const pf = perfStats?.num('profit_factor') ?? null;
  const exp = perfStats?.num('expectancy_r') ?? null;
  const wrTone = wr === null ? '' : wr >= 50 ? 'pos-num' : 'neg-num';
  const pfTone = pf === null ? '' : pf >= 1.5 ? 'pos-num' : pf < 1 ? 'neg-num' : '';
  const expTone = exp === null ? '' : exp > 0 ? 'pos-num' : exp < 0 ? 'neg-num' : '';

  /* Honest feed state for FreshnessClock */
  const clockState = useMemo(() => {
    if (feedHealth) {
      if (feedHealth.status === 'CLOSED' || feedHealth.market_session?.is_open === false) return 'CLOSED';
      if (feedHealth.status === 'AUTH_REQUIRED' || feedHealth.status === 'DOWN') return 'DOWN';
      if (feedHealth.status === 'CHAIN_UNAVAILABLE') return 'DEGRADED';
      if (feedHealth.status === 'STALE') return 'STALE';
      if (feedHealth.status === 'LIVE') return 'LIVE';
      return 'SYNCING';
    }
    return connected ? 'SYNCING' : 'DOWN';
  }, [feedHealth, connected]);

  /* Last-good data kept on a transient fetch failure: say so out loud rather
     than blanking the desk. Never claims LIVE while a source is stale. */
  const staleBanners = useMemo(() => {
    const out: string[] = [];
    if (activeError && sortedActive.length > 0) out.push(`Orders refresh failed — ${activeError}`);
    if (perfError && perf) out.push(`Attribution refresh failed — ${perfError}`);
    if (auditError && auditRows.length > 0) out.push(`Ledger refresh failed — ${auditError}`);
    if (enginesError && (enginesData !== null || strategies.length > 0)) {
      out.push(`Engine registry refresh failed — ${enginesError}`);
    }
    return out;
  }, [activeError, sortedActive.length, perfError, perf, auditError, auditRows.length, enginesError, enginesData, strategies.length]);
  const lastGoodAt = useMemo(() => {
    const times = [lastActiveAt, lastPerfAt, lastPnlAt].filter((v): v is number => v !== null);
    return times.length ? new Date(Math.max(...times)) : null;
  }, [lastActiveAt, lastPerfAt, lastPnlAt]);

  const clockNote = useMemo(() => {
    if (feedHealth) {
      if (feedHealth.status === 'CLOSED') return 'NSE 15:30 IST';
      if (feedHealth.status === 'AUTH_REQUIRED') return 'FYERS re-auth';
      if (feedHealth.status === 'CHAIN_UNAVAILABLE') return 'no option chain';
      if (feedHealth.status === 'DOWN') return 'no broker ticks';
      if (feedHealth.status === 'LIVE') return 'FYERS live';
    }
    return undefined;
  }, [feedHealth]);

  const clockLastAt = useMemo(() => {
    if (feedHealth?.spot_feed?.last_tick_at) {
      return new Date(feedHealth.spot_feed.last_tick_at);
    }
    return clockState === 'LIVE' ? (lastPnlAt ? new Date(lastPnlAt) : null) : null;
  }, [feedHealth, clockState, lastPnlAt]);

  /* ---- live desk body ---- */

  const liveBody =
    activeLoading && sortedActive.length === 0 ? (
      <Skeletons />
    ) : activeError && sortedActive.length === 0 ? (
      <div className="sg-pad">
        <EmptyNote>Active signals unavailable — {activeError}</EmptyNote>
        <div style={{ marginTop: 10 }}>
          <RetryButton onRetry={refreshAll} />
        </div>
      </div>
    ) : sortedActive.length === 0 ? (
      <div className="sg-empty">
        <Activity size={20} />
        <p>{statusFilter === 'ALL' ? 'No signals found for this filter.' : 'No active signals for this filter.'}</p>
        <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
          {statusFilter !== 'ALL' ? (
            <button
              type="button"
              className="sg-link"
              style={{
                background: 'none',
                border: '1px solid var(--ds-border-subtle)',
                borderRadius: 4,
                cursor: 'pointer',
                color: 'var(--ds-accent)',
                fontSize: 11,
                padding: '4px 10px',
              }}
              onClick={() => setStatusFilter('ALL')}
            >
              Show all signal history (including expired)
            </button>
          ) : null}
          {filtersDirty ? (
            <button
              type="button"
              className="sg-link"
              style={{
                background: 'none',
                border: '1px solid var(--ds-border-subtle)',
                borderRadius: 4,
                cursor: 'pointer',
                color: 'var(--ds-accent)',
                fontSize: 11,
                padding: '4px 10px',
              }}
              onClick={resetFilters}
            >
              Reset filters
            </button>
          ) : null}
        </div>
      </div>
    ) : (
      <div className="sg-scroll">
        <table className="sg-table">
          <thead>
            <tr>
              <th className="col-hide-m">Time</th>
              <th>Symbol</th>
              <th className="col-hide-m">Strategy</th>
              <th>Side</th>
              <th className="col-hide-m">State</th>
              <th className="col-hide-m">Conf</th>
              <th className="r">Entry</th>
              <th className="r col-hide-m">Stop</th>
              <th className="r col-hide-m">Targets</th>
              <th className="r">TTL</th>
              <th className="r">Order</th>
            </tr>
          </thead>
          <tbody>
            {sortedActive.map((r) => {
              /* ONE eligibility predicate (also used by the `x` shortcut):
                 market session, terminal states and already-confirmed rows. */
              const eligibility = executionEligibility(r.state, marketClosed);
              const execDisabled = !eligibility.eligible || executingId === r.id;
              const execReason =
                eligibility.reason ??
                (executingId === r.id ? `Execution in progress — ${r.symbol} ${prettyKey(r.strategy)}` : null);
              const ttl = fmtTtl(r.expiresMs, now);
              return (
                <Fragment key={r.id}>
                  <tr data-active={activeRowId === r.id}>
                    <td><span className="sg-num">{fmtTimeMs(r.timeMs)}</span></td>
                    <td><span className="sg-sym">{r.symbol}</span></td>
                    <td><span className="sg-strat">{prettyKey(r.strategy)}</span></td>
                    <td><DirText direction={r.direction} /></td>
                    <td><StateTag state={r.state} /></td>
                    <td><ConfText conf={r.confidence} /></td>
                    <td className="r">
                      <div className="sg-num" style={{ fontWeight: 700 }}>
                        {r.trigger === null ? '—' : fmtINR(r.trigger)}
                      </div>
                      <div className="sg-num" style={{ fontSize: 10, color: 'var(--ds-ink-3)' }}>{fmtDist(r.trigger, r.spot)}</div>
                    </td>
                    <td className="r sg-num neg-num" style={{ fontWeight: 700 }}>
                      {r.sl === null ? '—' : fmtINR(r.sl)}
                    </td>
                    <td className="r sg-num">
                      {r.t1 === null && r.t2 === null ? (
                        '—'
                      ) : (
                        <>
                          {r.t1 === null ? '—' : fmtINR(r.t1)}
                          {r.t2 !== null ? <span style={{ color: 'var(--ds-ink-3)' }}> / {fmtINR(r.t2)}</span> : null}
                        </>
                      )}
                    </td>
                    <td className="r"><TtlText label={ttl.label} tone={ttl.tone} /></td>
                    <td className="r">
                      <div className="sg-actions">
                        <button
                          type="button"
                          className="sg-ibtn"
                          aria-label={`Open dossier for ${r.symbol} ${prettyKey(r.strategy)} signal`}
                          title="Open signal dossier — mechanism, levels, execution"
                          onClick={() => openDossier(r.id)}
                        >
                          <FileText size={13} />
                        </button>
                        <button
                          type="button"
                          className="sg-ibtn"
                          disabled={execDisabled}
                          aria-label={execReason ?? `Execute paper trade for ${r.symbol} ${prettyKey(r.strategy)} signal`}
                          title={execReason ?? 'Execute paper trade'}
                          onClick={() => setPending({ kind: 'execute', row: r })}
                        >
                          <Play size={13} />
                        </button>
                        <button
                          type="button"
                          className="sg-ibtn danger"
                          disabled={deletingId === r.id}
                          aria-label={`Delete ${r.symbol} ${prettyKey(r.strategy)} signal`}
                          title="Delete signal"
                          onClick={() => setPending({ kind: 'delete', row: r })}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                  {orderNote[r.id] ? (
                    <tr key={`${r.id}-note`}>
                      <td colSpan={11}>
                        <p className="sg-rownote">{orderNote[r.id]}</p>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    );

  /* ---- performance body ---- */

  const perfBody =
    perfLoading && !perf ? (
      <Skeletons rows={4} />
    ) : perfError && !perf ? (
      <div className="sg-pad">
        <EmptyNote>Performance unavailable — {perfError}</EmptyNote>
        <div style={{ marginTop: 10 }}>
          <RetryButton onRetry={refreshAll} />
        </div>
      </div>
    ) : perf && perfStats ? (
      <div className="sg-pad" style={{ display: 'grid', gap: 16 }}>
        <div className="sg-statgrid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))' }}>
          <div className="sg-stat">
            <div className="l">Win rate</div>
            <div className={`v ${wrTone}`}>{perfStats.f('win_rate_pct')}%</div>
            <div className="s">
              {perfStats.i('winning_signals')}W / {perfStats.i('losing_signals')}L
            </div>
          </div>
          <div className="sg-stat">
            <div className="l">Profit factor</div>
            <div className={`v ${pfTone}`}>{perfStats.f('profit_factor')}</div>
            <div className="s">gross win / gross loss</div>
          </div>
          <div className="sg-stat">
            <div className="l">Expectancy</div>
            <div className={`v ${expTone}`}>{perfStats.f('expectancy_r')}R</div>
            <div className="s">avg per signal</div>
          </div>
        </div>
        <div>
          <p className="sg-sect">Outcomes</p>
          <div className="sg-statgrid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))' }}>
            <div className="sg-stat"><div className="l">Total</div><div className="v">{perfStats.i('total_signals')}</div></div>
            <div className="sg-stat"><div className="l">Completed</div><div className="v">{perfStats.i('completed_signals')}</div></div>
            <div className="sg-stat"><div className="l">Won</div><div className="v pos-num">{perfStats.i('winning_signals')}</div></div>
            <div className="sg-stat"><div className="l">Lost</div><div className="v neg-num">{perfStats.i('losing_signals')}</div></div>
            <div className="sg-stat"><div className="l">T1 hits</div><div className="v">{perfStats.i('target_1_hits')}</div></div>
            <div className="sg-stat"><div className="l">T2 hits</div><div className="v">{perfStats.i('target_2_hits')}</div></div>
            <div className="sg-stat"><div className="l">SL hits</div><div className="v neg-num">{perfStats.i('stop_loss_hits')}</div></div>
          </div>
        </div>
      </div>
    ) : (
      <EmptyNote>No performance data yet.</EmptyNote>
    );

/* ---- P&L ledger (realized + live MTM) ---- */

  const pnlSigned = (v: number | null): string => {
    if (v === null) return '-';
    const sign = v > 0 ? '+' : '';
    return `${sign}${fmtINR(v)}`;
  };

  // P&L ledger = executed trades only. Unfilled setups (no fill, no exit)
  // carry no P&L and previously rendered spot triggers as fake premiums.
  const [showUnfilled, setShowUnfilled] = useState(false);
  const filledLedgerRows = useMemo(() => auditRows.filter((r) => !isUnfilledLedgerRow(r)), [auditRows]);
  const hiddenUnfilledCount = auditRows.length - filledLedgerRows.length;
  const visibleLedgerRows = useMemo(
    () => (showUnfilled ? auditRows : filledLedgerRows),
    [showUnfilled, auditRows, filledLedgerRows],
  );

  /* Live-realtime strip totals: recomputed from the filled rows on every
     render, so each `audit_pnl_update` SSE row-merge (~3s cadence) ticks the
     header instantly instead of waiting for the next backend summary poll.
     Backend `auditSummary` is the global aggregate and wins whenever the
     fetched row window may be truncated (shared AUDIT_FETCH_LIMIT + the
     backend's `total_signals_audited` count), and owns closed-count/win-rate. */
  const liveTotals = useMemo(() => sumLedgerTotals(filledLedgerRows), [filledLedgerRows]);
  /* Book size as reported by the backend aggregate; falls back to the window
     when absent. Truncation is only claimed on evidence. */
  const auditTotal = auditSummary?.totalRows ?? auditRows.length;
  const auditTruncated = auditRows.length >= auditLimit || auditTotal > auditRows.length;
  // Untruncated window: visible rows ARE the book, so the live row-sum is
  // fresher than the polled snapshot. Truncated: never trust the row-sum for
  // global totals — the backend aggregate is the only honest source.
  const trustedLiveTotals = auditTruncated ? null : liveTotals;
  const showRealized = trustedLiveTotals ? trustedLiveTotals.realized : (auditSummary?.realized ?? liveTotals?.realized ?? null);
  const showUnrealized = trustedLiveTotals ? trustedLiveTotals.unrealized : (auditSummary?.unrealized ?? liveTotals?.unrealized ?? null);
  const showNet = trustedLiveTotals ? trustedLiveTotals.total : (auditSummary?.total ?? liveTotals?.total ?? null);
  const totalsSource: 'live' | 'summary' | 'partial' | 'none' =
    trustedLiveTotals ? 'live' : auditSummary ? 'summary' : liveTotals ? 'partial' : 'none';
  const totalsTitle = (label: string): string =>
    totalsSource === 'live'
      ? `${label} — live row-sum of the full book, ticks with each SSE MTM update`
      : totalsSource === 'summary'
        ? `${label} — backend aggregate over the full book (row window truncated)`
        : totalsSource === 'partial'
          ? `${label} — partial window (sum of fetched rows only; backend aggregate unavailable)`
          : `${label} — unavailable`;

  /* Live age for the strip: ticks with `now` (1s clock) off `lastPnlAt`,
     which stamps every SSE `audit_pnl_update` merge and every audit poll.
     Backend `display_label` is only as fresh as the last FEED_STATUS/poll. */
  const pnlAgeSec = lastPnlAt === null ? null : Math.max(0, Math.round((now - lastPnlAt) / 1000));
  const stripIsLive = connected && feedHealth?.status === 'LIVE' && pnlAgeSec !== null && pnlAgeSec < 30;
  const stripLabel = stripIsLive
    ? `LIVE · ${pnlAgeSec}S AGO`
    : (feedHealth?.display_label ?? (connected ? 'SYNCING · AWAITING DATA' : 'OFFLINE · RECONNECTING'));
  const stripTitle = stripIsLive
    ? `Live MTM — last tick ${pnlAgeSec}s ago via SSE audit_pnl_update (~3s cadence)`
    : (feedHealth?.message ?? (connected ? 'SSE live connection active' : 'Connecting to SSE stream'));

  /* Keyboard row navigation (plan 8.5). Row list depends on the active tab:
     live orders on 'live', filled ledger rows on 'history'. Guarded so typing
     in inputs never triggers row actions and overlays consume their own keys. */
  const rowList = useMemo(
    () =>
      tab === 'live'
        ? sortedActive.map((r) => r.id)
        : tab === 'history'
          ? visibleLedgerRows.map((r) => (typeof r.id === 'string' ? r.id : null))
          : [],
    [tab, sortedActive, visibleLedgerRows],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const tag = t?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || t?.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (dossierId !== null || createOpen || pending !== null) return; // overlay open — it handles its own keys

      const ids = rowList.filter((x): x is string => x !== null);
      if (ids.length === 0) return;

      const idx = activeRowId === null ? -1 : ids.indexOf(activeRowId);

      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveRowId(ids[Math.min(ids.length - 1, idx + 1)]);
      } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveRowId(ids[Math.max(0, idx <= 0 ? 0 : idx - 1)]);
      } else if (e.key === 'Enter' && activeRowId) {
        e.preventDefault();
        openDossier(activeRowId);
      } else if ((e.key === 'x' || e.key === 'X') && activeRowId && tab === 'live') {
        e.preventDefault();
        const row = sortedActive.find((r) => r.id === activeRowId);
        // Same eligibility predicate as the row action button: the shortcut
        // must never reach a state the button refuses (or double-fire while
        // an execution for the row is already in flight).
        if (row && executingId !== row.id && executionEligibility(row.state, marketClosed).eligible) {
          setPending({ kind: 'execute', row });
        }
      } else if (e.key === 'Escape' && activeRowId) {
        setActiveRowId(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [rowList, activeRowId, dossierId, createOpen, pending, executingId, tab, sortedActive, marketClosed, openDossier]);

  const ledgerBody =
    auditLoading && auditRows.length === 0 ? (
      <Skeletons rows={5} />
    ) : auditError && auditRows.length === 0 ? (
      <div className="sg-pad">
        <EmptyNote>Ledger unavailable — {auditError}</EmptyNote>
        <div style={{ marginTop: 10 }}>
          <RetryButton onRetry={refreshAll} />
        </div>
      </div>
    ) : auditRows.length === 0 ? (
      <div className="sg-empty">
        <Activity size={20} />
        <p>No trades yet — the ledger fills as signals execute and square off.</p>
      </div>
    ) : filledLedgerRows.length === 0 && !showUnfilled ? (
      <div className="sg-empty">
        <Activity size={20} />
        <p>No executed trades yet — unfilled setups carry no P&amp;L.</p>
        {hiddenUnfilledCount > 0 ? (
          <button
            type="button"
            style={{
              marginTop: 8,
              background: 'none',
              border: '1px solid var(--ds-border-subtle)',
              borderRadius: 4,
              cursor: 'pointer',
              color: 'var(--ds-accent)',
              fontSize: 12,
              padding: '4px 10px',
            }}
            onClick={() => setShowUnfilled(true)}
          >
            Show {hiddenUnfilledCount} unfilled setup{hiddenUnfilledCount === 1 ? '' : 's'}
          </button>
        ) : null}
      </div>
    ) : (
      <>
        <div className="sg-strip">
          <span
            className={`sg-meta${stripIsLive ? ' on' : ''}`}
            style={{ padding: '0 14px 0 0', borderRight: '1px solid var(--ds-border-subtle)' }}
            title={stripTitle}
          >
            <i
              className={stripIsLive || feedHealth?.display_tone === 'on' ? 'on' : undefined}
              style={{
                color:
                  stripIsLive || feedHealth?.display_tone === 'on'
                    ? 'var(--ds-bull-strong)'
                    : feedHealth?.display_tone === 'down'
                    ? 'var(--ds-bear-strong)'
                    : 'var(--ds-warn)',
              }}
            />
            {stripLabel}
          </span>
          <span className="sg-cell" title={totalsTitle('Realized')}><span className="l">Realized</span><span className={`v ${pnlCls(showRealized)}`}>{pnlSigned(showRealized)}</span><span className="s">{auditSummary ? `${auditSummary.closed ?? '—'} closed` : ''}{totalsSource === 'partial' ? `${auditSummary ? ' · ' : ''}partial window` : ''}</span></span>
          <span className="sg-cell" title={totalsTitle('Unrealized')}><span className="l">Unrealized</span><span className={`v ${pnlCls(showUnrealized)}`}>{pnlSigned(showUnrealized)}</span></span>
          <span className="sg-cell" title={totalsTitle('Net')}><span className="l">Net</span><span className={`v ${pnlCls(showNet)}`}>{pnlSigned(showNet)}</span><span className="s">{auditSummary && auditSummary.winRate !== null ? `${auditSummary.winRate}% win` : ''}</span></span>
          <span
            className="sg-cell"
            title={
              auditTruncated
                ? `Fetched the latest ${auditRows.length} ledger rows of ${auditTotal} — totals above use the backend aggregate`
                : 'All ledger rows fetched — row sums are complete'
            }
          >
            <span className="l">Showing</span>
            <span className="v">{visibleLedgerRows.length} of {auditTotal}</span>
            {auditTruncated ? <span className="s">latest {auditRows.length} fetched</span> : null}
          </span>
          {hiddenUnfilledCount > 0 || showUnfilled ? (
            <span className="sg-cell">
              <button
                type="button"
                onClick={() => setShowUnfilled(!showUnfilled)}
                style={{
                  background: 'none',
                  border: '1px solid var(--ds-border-subtle)',
                  borderRadius: 4,
                  cursor: 'pointer',
                  color: showUnfilled ? 'var(--ds-accent)' : 'var(--ds-ink-2)',
                  fontSize: 11,
                  padding: '2px 8px',
                }}
              >
                {showUnfilled ? 'Showing all setups (click to hide unfilled)' : `${hiddenUnfilledCount} unfilled hidden (click to show)`}
              </button>
            </span>
          ) : null}
        </div>
        <div className="sg-scroll">
          <table className="sg-table">
          <thead>
            <tr>
              <th className="col-hide-m">Time</th>
              <th>Symbol</th>
              <th className="col-hide-m">Expiry</th>
              <th className="col-hide-m">Strategy</th>
              <th>Side</th>
              <th className="col-hide-m">Status</th>
              <th className="r">Entry</th>
              <th className="r col-hide-m">In value</th>
              <th className="r">Live / Exit</th>
              <th className="r col-hide-m">Out value</th>
              <th className="r col-hide-m">Realized</th>
              <th className="r col-hide-m">Unrealized</th>
              <th className="r">Net</th>
              <th className="r col-hide-m"><span className="sg-eyebrow">File</span></th>
            </tr>
          </thead>
            <tbody>
              {visibleLedgerRows.map((r, i) => {
                const isOpen = isOpenLedgerStatus(r.status);
                const livePrice = r.current ?? r.exit;
                const inVal = r.entry !== null && r.qty !== null ? r.entry * r.qty : null;
                const outPx = isOpen ? r.current : (r.exit ?? r.current);
                const outVal = outPx !== null && outPx !== undefined && r.qty !== null ? (outPx as number) * r.qty : null;
                return (
                  <tr key={typeof r.id === 'string' ? r.id : `ledger-${i}`} data-active={activeRowId === r.id}>
                    <td className="col-hide-m"><span className="sg-num">{r.timeMs === null ? '—' : fmtTimeMs(r.timeMs)}</span></td>
                    <td><span className="sg-sym">{r.underlying}</span></td>
                    <td className="col-hide-m"><span className="sg-num" title="Contract expiry">{r.expiry}</span></td>
                    <td className="col-hide-m"><span className="sg-strat">{prettyKey(r.strategy)}</span></td>
                    <td><DirText direction={r.direction} /></td>
                    <td className="col-hide-m"><StateTag state={r.status} /></td>
                    <td className="r">
                      <div className="sg-num" style={{ fontWeight: 700 }}>{r.entry === null ? '—' : fmtINR(r.entry)}</div>
                      <div className="sg-num" style={{ fontSize: 10, color: 'var(--ds-ink-3)' }} title="Fill timestamp">{fmtDateTimeMs(r.entryTimeMs)}</div>
                    </td>
                    <td className="r sg-num col-hide-m">{inVal === null ? '—' : fmtINR(inVal)}</td>
                    <td className="r">
                      <div className="sg-num">{livePrice === null ? '—' : fmtINR(livePrice)}</div>
                      <div
                        className="sg-num"
                        style={{ fontSize: 10, color: 'var(--ds-ink-3)' }}
                        title={isOpen ? (feedHealth?.status === 'LIVE' ? 'Live MTM' : 'Session closed mark') : 'Exit timestamp'}
                      >
                        {isOpen ? (feedHealth?.status === 'LIVE' ? 'LIVE' : 'CLOSED') : fmtDateTimeMs(r.exitTimeMs)}
                      </div>
                    </td>
                    <td className="r sg-num col-hide-m">{outVal === null ? '—' : fmtINR(outVal)}</td>
                    <td className={`r sg-num col-hide-m ${pnlCls(r.realized)}`}>{pnlSigned(r.realized)}</td>
                    <td className={`r sg-num col-hide-m ${pnlCls(r.unrealized)}`}>{isOpen ? pnlSigned(r.unrealized) : '—'}</td>
                    <td className={`r sg-num ${pnlCls(r.total)}`} style={{ fontWeight: 700 }}>{pnlSigned(r.total)}</td>
                    <td className="r col-hide-m">
                      <button
                        type="button"
                        className="sg-ibtn"
                        aria-label={`Open trade dossier for ${r.underlying} ${prettyKey(r.strategy)}`}
                        title="Open trade dossier — mechanism, fills, lifecycle"
                        onClick={() => openDossier(r.id)}
                      >
                        <FileText size={13} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </>
    );


  const [autoDetecting, setAutoDetecting] = useState(false);

  const handleAutoDetect = async () => {
    setAutoDetecting(true);
    try {
      await autoDetect(instrumentFilter !== 'ALL' ? instrumentFilter : 'NIFTY');
    } finally {
      setAutoDetecting(false);
    }
  };

  const scannerBody = (
    <div className="sg-pad" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>Real-Time Setup Scanner</h3>
          <p className="muted" style={{ margin: '2px 0 0', fontSize: 11.5 }}>
            Automated scanning across high-probability intraday & scalp strategies.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            className="sg-ibtn"
            disabled={autoDetecting}
            onClick={handleAutoDetect}
            title="Scan market and auto-register active candidate setups"
            style={{ padding: '4px 10px', height: 'auto' }}
          >
            {autoDetecting ? 'Detecting…' : '⚡ Auto-Detect'}
          </button>
          <button
            type="button"
            className="sg-primary"
            disabled={scannerLoading}
            onClick={() => void loadScanner()}
          >
            <RefreshCw size={13} className={scannerLoading ? 'animate-spin' : ''} />
            {scannerLoading ? 'Scanning…' : 'Scan Now'}
          </button>
        </div>
      </div>

      {scannerError ? (
        <p className="sg-err">{scannerError}</p>
      ) : null}

      {scannerData ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
            <div style={{ padding: '8px 12px', background: 'var(--ds-inset)', borderRadius: 6, border: '1px solid var(--ds-border)' }}>
              <span className="sg-eyebrow" style={{ display: 'block', fontSize: 10 }}>Candidates Found</span>
              <span className="sg-num" style={{ fontSize: 16, fontWeight: 700 }}>{scannerData.total_candidates}</span>
            </div>
            <div style={{ padding: '8px 12px', background: 'var(--ds-inset)', borderRadius: 6, border: '1px solid var(--ds-border)' }}>
              <span className="sg-eyebrow" style={{ display: 'block', fontSize: 10 }}>New Signals</span>
              <span className="sg-num pos-num" style={{ fontSize: 16, fontWeight: 700 }}>{scannerData.new_signals?.length ?? 0}</span>
            </div>
            <div style={{ padding: '8px 12px', background: 'var(--ds-inset)', borderRadius: 6, border: '1px solid var(--ds-border)' }}>
              <span className="sg-eyebrow" style={{ display: 'block', fontSize: 10 }}>Active in Stream</span>
              <span className="sg-num" style={{ fontSize: 16, fontWeight: 700 }}>{scannerData.active_signals?.length ?? 0}</span>
            </div>
            <div style={{ padding: '8px 12px', background: 'var(--ds-inset)', borderRadius: 6, border: '1px solid var(--ds-border)' }}>
              <span className="sg-eyebrow" style={{ display: 'block', fontSize: 10 }}>Underlyings Scanned</span>
              <span style={{ fontSize: 11.5, color: 'var(--ds-ink-2)', display: 'block', marginTop: 2 }}>
                {scannerData.scanned_underlyings?.join(', ') || '—'}
              </span>
            </div>
          </div>

          {scannerData.new_signals?.length ? (
            <div className="sg-table-wrap">
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Strategy</th>
                    <th>Direction</th>
                    <th className="r">Trigger</th>
                    <th className="r">Stop Loss</th>
                    <th className="r">Target</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {scannerData.new_signals.map((sig: any, idx: number) => (
                    <tr key={sig.id ?? idx}>
                      <td><span className="sg-sym">{sig.underlying ?? sig.symbol}</span></td>
                      <td><span className="sg-strat">{prettyKey(sig.strategy)}</span></td>
                      <td><DirText direction={sig.direction ?? sig.side} /></td>
                      <td className="r sg-num" style={{ fontWeight: 700 }}>{sig.trigger_price ? fmtINR(sig.trigger_price) : '—'}</td>
                      <td className="r sg-num neg-num">{sig.stop_loss ? fmtINR(sig.stop_loss) : '—'}</td>
                      <td className="r sg-num pos-num">{sig.target_1 ? fmtINR(sig.target_1) : '—'}</td>
                      <td><span className="sg-tag info">NEW CANDIDATE</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="sg-empty" style={{ padding: 24 }}>
              <p>No new breakthrough candidates detected in this scan cycle.</p>
            </div>
          )}
        </div>
      ) : (
        <div className="sg-empty" style={{ padding: 24 }}>
          <p>Click &quot;Scan Now&quot; to inspect all index candidates against current order book and momentum.</p>
        </div>
      )}
    </div>
  );

  const enginesBody = (
    <div className="sg-pad" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <h3 style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>Quant Signal Engine Registry</h3>
        <p className="muted" style={{ margin: '2px 0 0', fontSize: 11.5 }}>
          Registered execution engines, broker gateway status, and approved symbol universe.
        </p>
      </div>

      {enginesData ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 10 }}>
            <div style={{ padding: '10px 14px', background: 'var(--ds-inset)', borderRadius: 6, border: '1px solid var(--ds-border)' }}>
              <span className="sg-eyebrow" style={{ display: 'block', fontSize: 10 }}>Broker Execution Router</span>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ds-ink)' }}>{enginesData.broker || 'FYERS Paper Gateway'}</span>
            </div>
            <div style={{ padding: '10px 14px', background: 'var(--ds-inset)', borderRadius: 6, border: '1px solid var(--ds-border)' }}>
              <span className="sg-eyebrow" style={{ display: 'block', fontSize: 10 }}>Approved Universe</span>
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
                {enginesData.approved_universe?.map((u: string) => (
                  <span key={u} className="sg-tag info" style={{ fontSize: 10 }}>{u}</span>
                )) || <span className="muted">None configured</span>}
              </div>
            </div>
          </div>

          <div className="sg-table-wrap">
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Engine / Strategy</th>
                  <th>Desk Scope</th>
                  <th>Execution Mode</th>
                  <th>Risk Gate</th>
                </tr>
              </thead>
              <tbody>
                {(enginesData.strategies ?? []).map((st: any, idx: number) => {
                  const name = typeof st === 'string' ? st : st.name ?? st.strategy ?? st.id ?? `Strategy #${idx + 1}`;
                  const desk = st.desk ?? (name.includes('SCALP') ? 'SCALP' : 'INTRADAY');
                  return (
                    <tr key={name}>
                      <td>
                        <span className="sg-sym" style={{ fontWeight: 600 }}>{prettyKey(name)}</span>
                        {st.description && (
                          <div style={{ fontSize: 11, color: 'var(--ds-ink-3)', marginTop: 2 }}>{st.description}</div>
                        )}
                      </td>
                      <td><span className="sg-tag neut">{desk}</span></td>
                      <td><span className="sg-tag bull">PAPER LIVE</span></td>
                      <td><span className="sg-tag warn">UNKNOWN→RECONCILE</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="sg-empty" style={{ padding: 24 }}>
          <p>{enginesLoading ? 'Loading engine specifications…' : 'Engine registry specifications unavailable.'}</p>
        </div>
      )}
    </div>
  );

  /* ---- terminal layout: bar -> panel ---- */

  return (
    <div className="ds-module ds-module-fill sg">
      <header className="sg-bar">
        <span className="sg-brand">
          <span>
            <span className="sg-eyebrow">NSE F&amp;O · Paper desk</span>
            <h2 className="sg-title" title="Active setups & paper trades · auto-refresh 15s · live via SSE">Signal Desk</h2>
          </span>
          <FreshnessClock
            state={clockState}
            lastAt={clockLastAt}
            sourceLabel="SSE"
            note={clockNote}
          />
        </span>
        <nav className="sg-seg" role="tablist" aria-label="Signal sections" onKeyDown={onTablistKeyDown}>
          {TAB_ORDER.map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              id={`sg-tab-${key}`}
              aria-controls="sg-tabpanel"
              aria-selected={tab === key}
              tabIndex={tab === key ? 0 : -1}
              onClick={() => selectTab(key)}
            >
              {key === 'live' ? (
                <>
                  ORDERS{' '}
                  <span className="n">{activeLoading && sortedActive.length === 0 ? '—' : sortedActive.length}</span>
                </>
              ) : key === 'scanner' ? (
                <>SCANNER {scannerData ? <span className="n">{scannerData.total_candidates}</span> : null}</>
              ) : key === 'engines' ? (
                'ENGINES'
              ) : key === 'performance' ? (
                'ATTRIBUTION'
              ) : (
                <>
                  LEDGER / HISTORY{' '}
                  <span className="n">{showUnfilled ? auditRows.length : filledLedgerRows.length || '—'}</span>
                </>
              )}
            </button>
          ))}
        </nav>
        <span className="sg-tools">
          <label className="sg-lab">
            <span>Desk</span>
            <select
              className="sg-ctl"
              value={deskFilter}
              onChange={(e) => setDeskFilter(e.target.value as DeskFilter)}
            >
              {DESK_FILTERS.map((d) => (
                <option key={d} value={d}>{d === 'ALL' ? 'ALL' : prettyKey(d).toUpperCase()}</option>
              ))}
            </select>
          </label>
          <label className="sg-lab">
            <span>Underlying</span>
            <select
              className="sg-ctl"
              value={instrumentFilter}
              onChange={(e) => setInstrumentFilter(e.target.value as InstrumentFilter)}
            >
              {INSTRUMENT_FILTERS.map((s) => (
                <option key={s} value={s}>{s === 'ALL' ? 'ALL' : s}</option>
              ))}
            </select>
          </label>
          {tab === 'live' ? (
            <label className="sg-lab">
              <span>View</span>
              <select
                className="sg-ctl"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
              >
                {STATUS_FILTERS.map((s) => (
                  <option key={s} value={s}>{s === 'ACTIVE' ? 'ACTIVE ONLY' : 'ALL (HISTORY)'}</option>
                ))}
              </select>
            </label>
          ) : null}
          {tab === 'history' ? (
            <button
              type="button"
              className="sg-ibtn"
              aria-label="Repair and sanitize audit ledger"
              title="Repair / sanitize audit ledger"
              disabled={sanitizeBusy}
              onClick={() => setPending({ kind: 'sanitize' })}
              style={{ alignSelf: 'flex-end' }}
            >
              <Eraser size={13} />
            </button>
          ) : null}
          <button
            type="button"
            className="sg-ibtn"
            aria-label="Refresh all signal desk data"
            onClick={refreshAll}
            title="Refresh all"
            style={{ alignSelf: 'flex-end' }}
          >
            <RefreshCw size={13} />
          </button>
          <button type="button" className="sg-primary" onClick={() => setCreateOpen(true)} style={{ alignSelf: 'flex-end' }}>
            <Plus size={13} /> New order
          </button>
        </span>
        {statusError ? <p className="sg-err">{statusError}</p> : null}
      </header>

      <section className="sg-panel" role="tabpanel" id="sg-tabpanel" aria-labelledby={`sg-tab-${tab}`}>
        {staleBanners.length ? (
          <div
            role="status"
            aria-live="polite"
            className="sg-pad"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              flexWrap: 'wrap',
              borderBottom: '1px solid var(--ds-border)',
              background: 'var(--ds-warn-wash)',
            }}
          >
            <FreshnessClock state="STALE" lastAt={lastGoodAt} sourceLabel="REST" note="showing last good data" />
            <span className="muted" style={{ fontSize: 11.5 }}>
              {staleBanners.join(' · ')}
            </span>
          </div>
        ) : null}
        <div className="sg-scroll">
            {tab === 'history' && sanitizeNote ? (
              <p className="sg-note sg-pad">{sanitizeNote}</p>
            ) : null}
            {tab === 'live' ? liveBody : null}
            {tab === 'scanner' ? scannerBody : null}
            {tab === 'engines' ? enginesBody : null}
            {tab === 'performance' ? perfBody : null}
            {tab === 'history' ? ledgerBody : null}
        </div>
      </section>

      <SignalCreateDialog
        key={createOpen ? 'create-open' : 'create-closed'}
        open={createOpen}
        onOpenChange={setCreateOpen}
        strategies={strategies}
        strategiesLoading={enginesLoading}
        strategiesError={enginesError}
        onCreated={afterCreate}
      />
      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(open) => { if (!open) closePending(); }}
        busy={pending?.kind === 'execute' ? executingId !== null : pending?.kind === 'delete' ? deletingId !== null : sanitizeBusy}
        tone={pending?.kind === 'execute' ? 'primary' : 'danger'}
        title={
          pending?.kind === 'execute'
            ? `Execute paper trade — ${pending.row.symbol} ${pending.row.direction === 'BEARISH' ? 'SHORT' : pending.row.direction === 'BULLISH' ? 'LONG' : ''} ${prettyKey(pending.row.strategy)}?`
            : pending?.kind === 'delete'
              ? `Delete ${pending.row.symbol} ${prettyKey(pending.row.strategy)} signal?`
              : 'Repair / sanitize audit ledger?'
        }
        description={
          pending?.kind === 'execute'
            ? 'Places a simulated order at the signal entry. Visible in the ledger immediately.'
            : pending?.kind === 'delete'
              ? 'This removes the signal from the active desk.'
              : 'Rewrites the audit ledger from the backend source of truth.'
        }
        intentRows={confirmIntentRows(pending)}
        confirmLabel={pending?.kind === 'execute' ? 'Execute' : pending?.kind === 'delete' ? 'Delete' : 'Sanitize'}
        onConfirm={() => {
          if (!pending) return;
          if (pending.kind === 'execute') void executePaper(pending.row).then(closePending);
          else if (pending.kind === 'delete') void deleteSignal(pending.row).then(closePending);
          else void sanitizeAudit().then(closePending);
        }}
      />
      <SignalDetailDrawer signalId={dossierId} onClose={closeDossier} />
    </div>
  );
}

export default SignalsDesk;