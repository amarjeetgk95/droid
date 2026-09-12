'use client';

/* Signals terminal — institutional order-desk presentation over useSignalsData().
   Flat hairline surfaces, mono numerals, semantic color only on data. */

import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
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
  useSignalsData,
  type DeskFilter,
  type InstrumentFilter,
} from '@/components/signals/useSignalsData';
import {
  asNum,
  confPct,
  fmtConf,
  fmtDateTimeMs,
  fmtDist,
  fmtTimeMs,
  fmtTtl,
  isUnfilledLedgerRow,
  prettyKey,
  stateTone,
  type ActiveRow,
} from '@/components/signals/signalsNormalize';

type TabKey = 'live' | 'performance' | 'history';

export type SignalsDeskProps = {
  /** URL-driven initial values (Phase 5). URL wins over internal defaults. */
  initialDeskFilter?: DeskFilter;
  initialInstrumentFilter?: InstrumentFilter;
  initialTab?: TabKey;
  /** URL change callbacks — write params back (deep-linkable desk state). */
  onDeskFilterChange?: (v: DeskFilter) => void;
  onInstrumentFilterChange?: (v: InstrumentFilter) => void;
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
      { label: 'Confidence', value: r.confidence === null ? '—' : `${Math.round(r.confidence * 100)}%` },
      { label: 'Mode', value: 'Paper trade · qty 1' },
    );
  }
  return rows;
}

function DirText({ direction }: { direction: unknown }) {
  const d = normalizeDirection(direction);
  if (d === 'NEUTRAL') return <span className="sg-dir" style={{ color: 'var(--sg-ink-3)' }}>—</span>;
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
  initialTab,
  onDeskFilterChange,
  onInstrumentFilterChange,
  onTabChange,
}: SignalsDeskProps = {}) {
  const {
    deskFilter,
    setDeskFilter: setDeskFilterInternal,
    instrumentFilter,
    setInstrumentFilter: setInstrumentFilterInternal,
    kpis,
    statusError,
    marketClosed,
    sortedActive,
    activeLoading,
    activeError,
    now,
    connected,
    perf,
    perfLoading,
    perfError,
    auditRows,
    auditSummary,
    auditLoading,
    auditError,
    lastPnlAt,
    sanitizeBusy,
    sanitizeNote,
    strategies,
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
  const [createOpen, setCreateOpen] = useState(false);

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
        <p>No active signals for this filter.</p>
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
              const confirmed = r.state.toUpperCase().includes('CONFIRMED');
              const execDisabled = marketClosed || confirmed || executingId === r.id;
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
                      <div className="sg-num" style={{ fontSize: 10, color: 'var(--sg-ink-3)' }}>{fmtDist(r.trigger, r.spot)}</div>
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
                          {r.t2 !== null ? <span style={{ color: 'var(--sg-ink-3)' }}> / {fmtINR(r.t2)}</span> : null}
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
                          aria-label={
                            marketClosed
                              ? `Market closed — cannot execute ${r.symbol} signal`
                              : confirmed
                                ? `Already confirmed — cannot re-execute ${r.symbol} signal`
                                : `Execute paper trade for ${r.symbol} ${prettyKey(r.strategy)} signal`
                          }
                          title={marketClosed ? 'Market closed' : confirmed ? 'Already confirmed' : 'Execute paper trade'}
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
  const filledLedgerRows = useMemo(() => auditRows.filter((r) => !isUnfilledLedgerRow(r)), [auditRows]);
  const hiddenUnfilledCount = auditRows.length - filledLedgerRows.length;

  /* Keyboard row navigation (plan 8.5). Row list depends on the active tab:
     live orders on 'live', filled ledger rows on 'history'. Guarded so typing
     in inputs never triggers row actions and overlays consume their own keys. */
  const rowList = useMemo(
    () =>
      tab === 'live'
        ? sortedActive.map((r) => r.id)
        : tab === 'history'
          ? filledLedgerRows.map((r) => (typeof r.id === 'string' ? r.id : null))
          : [],
    [tab, sortedActive, filledLedgerRows],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const tag = t?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || t?.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (dossierId !== null || createOpen) return; // overlay open — it handles its own keys

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
        if (row && !marketClosed && !row.state.toUpperCase().includes('CONFIRMED')) {
          setPending({ kind: 'execute', row });
        }
      } else if (e.key === 'Escape' && activeRowId) {
        setActiveRowId(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [rowList, activeRowId, dossierId, createOpen, tab, sortedActive, marketClosed, openDossier]);

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
    ) : filledLedgerRows.length === 0 ? (
      <div className="sg-empty">
        <Activity size={20} />
        <p>No executed trades yet — unfilled setups carry no P&amp;L.</p>
      </div>
    ) : (
      <>
        <div className="sg-strip">
          <span className="sg-meta" style={{ padding: '0 14px 0 0', borderRight: '1px solid var(--sg-hair)' }}>
            <i className={connected ? 'on' : undefined} style={{ color: connected ? 'var(--ds-bull-strong)' : 'var(--ds-warn)' }} />
            {connected
              ? lastPnlAt
                ? `LIVE · ${Math.max(0, Math.round((now - lastPnlAt) / 1000))}S AGO`
                : 'LIVE · SYNCING'
              : 'OFFLINE · 5S POLL'}
          </span>
          <span className="sg-cell"><span className="l">Realized</span><span className={`v ${pnlCls(auditSummary?.realized ?? null)}`}>{pnlSigned(auditSummary?.realized ?? null)}</span><span className="s">{auditSummary ? `${auditSummary.closed ?? '—'} closed` : ''}</span></span>
          <span className="sg-cell"><span className="l">Unrealized</span><span className={`v ${pnlCls(auditSummary?.unrealized ?? null)}`}>{pnlSigned(auditSummary?.unrealized ?? null)}</span></span>
          <span className="sg-cell"><span className="l">Net</span><span className={`v ${pnlCls(auditSummary?.total ?? null)}`}>{pnlSigned(auditSummary?.total ?? null)}</span><span className="s">{auditSummary && auditSummary.winRate !== null ? `${auditSummary.winRate}% win` : ''}</span></span>
          {hiddenUnfilledCount > 0 ? <span className="sg-cell"><span className="s">{hiddenUnfilledCount} unfilled hidden</span></span> : null}
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
              {filledLedgerRows.map((r, i) => {
                const isOpen = !/(WON|LOST|CLOSED|SQUARED|STOP|TARGET_2|RUNNER)/.test(r.status.toUpperCase());
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
                      <div className="sg-num" style={{ fontSize: 10, color: 'var(--sg-ink-3)' }} title="Fill timestamp">{fmtDateTimeMs(r.entryTimeMs)}</div>
                    </td>
                    <td className="r sg-num col-hide-m">{inVal === null ? '—' : fmtINR(inVal)}</td>
                    <td className="r">
                      <div className="sg-num">{livePrice === null ? '—' : fmtINR(livePrice)}</div>
                      <div className="sg-num" style={{ fontSize: 10, color: 'var(--sg-ink-3)' }} title={isOpen ? 'Live MTM' : 'Exit timestamp'}>
                        {isOpen ? 'LIVE' : fmtDateTimeMs(r.exitTimeMs)}
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
            state={connected ? 'LIVE' : 'SYNCING'}
            lastAt={connected ? now : null}
            sourceLabel="SSE"
          />
        </span>
        <nav className="sg-seg" role="tablist" aria-label="Signal sections">
          <button type="button" role="tab" aria-selected={tab === 'live'} onClick={() => setTab('live')}>
            ORDERS <span className="n">{kpis.active ?? '—'}</span>
          </button>
          <button type="button" role="tab" aria-selected={tab === 'performance'} onClick={() => setTab('performance')}>
            ATTRIBUTION
          </button>
          <button type="button" role="tab" aria-selected={tab === 'history'} onClick={() => setTab('history')}>
            LEDGER <span className="n">{filledLedgerRows.length || '—'}</span>
          </button>
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

      <section className="sg-panel">
        <div className="sg-scroll">
          {tab === 'history' && sanitizeNote ? (
            <p className="sg-note sg-pad">{sanitizeNote}</p>
          ) : null}
          {tab === 'live' ? liveBody : null}
          {tab === 'performance' ? perfBody : null}
          {tab === 'history' ? ledgerBody : null}
        </div>
      </section>

      <SignalCreateDialog
        key={createOpen ? 'create-open' : 'create-closed'}
        open={createOpen}
        onOpenChange={setCreateOpen}
        strategies={strategies}
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