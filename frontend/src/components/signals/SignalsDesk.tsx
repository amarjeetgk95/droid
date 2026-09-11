'use client';

/* Signals desk - the whole module lives on one confined page:
   command header (KPIs + filters) -> section tabs -> a single panel that
   scrolls internally. All data flows through useSignalsData(); parsing and
   formatting live in signalsNormalize. */

import { Fragment, useCallback, useMemo, useState } from 'react';
import {
  Activity,
  Eraser,
  Gauge,
  BrainCircuit,
  Wallet,
  Play,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import WhyPanel from '@/components/forecast/WhyPanel';
import { DirectionBadge, EmptyNote, RetryButton, fmtINR } from '@/components/ui/desk';
import { api } from '@/lib/api';
import { SignalCreateDialog } from '@/components/signals/SignalCreateDialog';
import {
  DESK_FILTERS,
  INSTRUMENT_FILTERS,
  useSignalsData,
  type DeskFilter,
  type InstrumentFilter,
} from '@/components/signals/useSignalsData';
import {
  type Tone,
  asNum,
  confPct,
  fmtConf,
  fmtDist,
  fmtTimeMs,
  fmtTtl,
  prettyKey,
  stateTone,
} from '@/components/signals/signalsNormalize';

type TabKey = 'live' | 'performance' | 'history';

const TONE_BADGE: Record<Tone, string> = {
  bull: 'b-bull',
  bear: 'b-bear',
  info: 'b-info',
  warn: 'b-warn',
  neut: 'b-neut',
};

function Skeletons({ rows = 3 }: { rows?: number }) {
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skel" style={{ height: 14, width: `${84 - i * 10}%` }}>.</div>
      ))}
    </div>
  );
}

function StateBadge({ state }: { state: string }) {
  return <span className={`badge badge-sm ${TONE_BADGE[stateTone(state)]}`}>{state}</span>;
}

function TtlPill({ label, tone }: { label: string; tone: 'ok' | 'warn' | 'expired' }) {
  return <span className={`ttl-pill${tone === 'ok' ? '' : ` ${tone}`}`}>{label}</span>;
}

function ConfCell({ conf }: { conf: number | null }) {
  return (
    <span className="mini-meter">
      <span className="mini-meter-track" aria-hidden="true">
        <i style={{ width: `${confPct(conf)}%` }} />
      </span>
      <span className="num" style={{ fontSize: 12.5, fontWeight: 650 }}>
        {fmtConf(conf)}
      </span>
    </span>
  );
}

function pnlTone(v: number | null): string {
  if (v === null) return '';
  return v > 0 ? 'v-bull' : v < 0 ? 'v-bear' : '';
}
export function SignalsDesk() {
  const {
    deskFilter,
    setDeskFilter,
    instrumentFilter,
    setInstrumentFilter,
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
  } = useSignalsData();

  const [tab, setTab] = useState<TabKey>('live');
  const [createOpen, setCreateOpen] = useState(false);

  /* AI reasoning (deep-dive) row state */
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [deepDiveCache, setDeepDiveCache] = useState<Record<string, unknown>>({});
  const [deepDiveLoading, setDeepDiveLoading] = useState<string | null>(null);
  const [deepDiveError, setDeepDiveError] = useState<Record<string, string>>({});

  const toggleWhy = useCallback(
    async (signalId: string) => {
      if (expandedId === signalId) {
        setExpandedId(null);
        return;
      }
      setExpandedId(signalId);
      if (deepDiveCache[signalId] || deepDiveLoading === signalId) return;
      setDeepDiveLoading(signalId);
      setDeepDiveError((prev) => {
        const next = { ...prev };
        delete next[signalId];
        return next;
      });
      try {
        const data = await api.getSignalDeepDive(signalId);
        setDeepDiveCache((prev) => ({ ...prev, [signalId]: data }));
      } catch (e) {
        setDeepDiveError((prev) => ({
          ...prev,
          [signalId]: e instanceof Error ? e.message : 'deep-dive unavailable',
        }));
      } finally {
        setDeepDiveLoading(null);
      }
    },
    [deepDiveCache, deepDiveLoading, expandedId],
  );

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
  const wrTone = wr === null ? '' : wr >= 50 ? 'v-bull' : 'v-bear';
  const pfTone = pf === null ? '' : pf >= 1.5 ? 'v-bull' : pf < 1 ? 'v-bear' : '';
  const expTone = exp === null ? '' : exp > 0 ? 'v-bull' : exp < 0 ? 'v-bear' : '';

  /* ---- live desk body ---- */

  const liveBody =
    activeLoading && sortedActive.length === 0 ? (
      <Skeletons />
    ) : activeError && sortedActive.length === 0 ? (
      <div>
        <EmptyNote>Active signals unavailable - {activeError}</EmptyNote>
        <div style={{ marginTop: 10 }}>
          <RetryButton onRetry={refreshAll} />
        </div>
      </div>
    ) : sortedActive.length === 0 ? (
      <div className="sig-empty">
        <Activity size={22} />
        <p className="muted" style={{ margin: 0 }}>No active signals for this filter.</p>
      </div>
    ) : (
      <div className="tbl-scroll">
        <table className="tbl">
          <thead>
            <tr>
              <th>Time</th>
              <th>Symbol</th>
              <th>Strategy</th>
              <th>Dir</th>
              <th>State</th>
              <th>Conf</th>
              <th className="r">Entry</th>
              <th className="r">SL</th>
              <th className="r">Targets</th>
              <th className="r">TTL</th>
              <th className="r">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sortedActive.map((r) => {
              const isOpen = expandedId === r.id;
              const cached = deepDiveCache[r.id];
              const ddLoading = deepDiveLoading === r.id;
              const ddErr = deepDiveError[r.id];
              const confirmed = r.state.toUpperCase().includes('CONFIRMED');
              const execDisabled = marketClosed || confirmed || executingId === r.id;
              const ttl = fmtTtl(r.expiresMs, now);
              return (
                <Fragment key={r.id}>
                  <tr>
                    <td className="num">{fmtTimeMs(r.timeMs)}</td>
                    <td style={{ fontWeight: 700 }}>{r.symbol}</td>
                    <td style={{ fontSize: 12.5 }}>{prettyKey(r.strategy)}</td>
                    <td><DirectionBadge direction={r.direction} /></td>
                    <td><StateBadge state={r.state} /></td>
                    <td><ConfCell conf={r.confidence} /></td>
                    <td className="r">
                      <div style={{ lineHeight: 1.35 }}>
                        <div className="num" style={{ fontWeight: 650 }}>
                          {r.trigger === null ? '-' : fmtINR(r.trigger)}
                        </div>
                        <div className="faint num" style={{ fontSize: 11 }}>{fmtDist(r.trigger, r.spot)}</div>
                      </div>
                    </td>
                    <td className="r num" style={{ color: 'var(--ds-bear-strong)', fontWeight: 600 }}>
                      {r.sl === null ? '-' : fmtINR(r.sl)}
                    </td>
                    <td className="r num" style={{ fontSize: 12.5 }}>
                      {r.t1 === null && r.t2 === null ? (
                        '-'
                      ) : (
                        <>
                          {r.t1 === null ? '-' : fmtINR(r.t1)}
                          {r.t2 !== null ? <span className="faint"> / {fmtINR(r.t2)}</span> : null}
                        </>
                      )}
                    </td>
                    <td className="r"><TtlPill label={ttl.label} tone={ttl.tone} /></td>
                    <td className="r">
                      <div style={{ display: 'inline-flex', gap: 6 }}>
                        <button
                          type="button"
                          className="btn icon-btn"
                          aria-expanded={isOpen}
                          title="AI reasoning"
                          onClick={() => void toggleWhy(r.id)}
                        >
                          <BrainCircuit size={14} />
                        </button>
                        <button
                          type="button"
                          className="btn icon-btn"
                          disabled={execDisabled}
                          title={marketClosed ? 'Market closed' : confirmed ? 'Already confirmed' : 'Execute paper trade'}
                          onClick={() => void executePaper(r)}
                        >
                          <Play size={14} />
                        </button>
                        <button
                          type="button"
                          className="btn icon-btn icon-danger"
                          disabled={deletingId === r.id}
                          title="Delete signal"
                          onClick={() => void deleteSignal(r)}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                  {orderNote[r.id] ? (
                    <tr key={`${r.id}-note`}>
                      <td colSpan={11} style={{ padding: '2px 14px 8px' }}>
                        <p className="muted" style={{ margin: 0, fontSize: 12 }}>{orderNote[r.id]}</p>
                      </td>
                    </tr>
                  ) : null}
                  {isOpen ? (
                    <tr key={`${r.id}-why`}>
                      <td colSpan={11} style={{ padding: 0, borderBottom: '1px solid var(--ds-border)' }}>
                        {ddLoading ? (
                          <p className="muted" style={{ margin: 0, padding: 12, fontSize: 12 }}>Loading reasoning...</p>
                        ) : ddErr ? (
                          <p className="muted" style={{ margin: 0, padding: 12, fontSize: 12 }}>
                            Reasoning unavailable - {ddErr}
                          </p>
                        ) : (
                          <div style={{ padding: 12 }}>
                            <WhyPanel
                              explain={cached ?? null}
                              direction={typeof r.direction === 'string' ? r.direction : String(r.direction ?? '')}
                              confidence={typeof r.confidence === 'number' ? r.confidence : undefined}
                              compact={false}
                              invalidationPrice={r.sl}
                              targetPrice={r.t1}
                            />
                          </div>
                        )}
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
      <div>
        <EmptyNote>Performance unavailable - {perfError}</EmptyNote>
        <div style={{ marginTop: 10 }}>
          <RetryButton onRetry={refreshAll} />
        </div>
      </div>
    ) : perf && perfStats ? (
      <div style={{ display: 'grid', gap: 16 }}>
        <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
          <div className="stat">
            <div className="stat-l">Win rate</div>
            <div className={`stat-v num ${wrTone}`}>{perfStats.f('win_rate_pct')}%</div>
            <div className="stat-s num">
              {perfStats.i('winning_signals')}W / {perfStats.i('losing_signals')}L
            </div>
          </div>
          <div className="stat">
            <div className="stat-l">Profit factor</div>
            <div className={`stat-v num ${pfTone}`}>{perfStats.f('profit_factor')}</div>
            <div className="stat-s">gross win / gross loss</div>
          </div>
          <div className="stat">
            <div className="stat-l">Expectancy</div>
            <div className={`stat-v num ${expTone}`}>{perfStats.f('expectancy_r')}R</div>
            <div className="stat-s">avg per signal</div>
          </div>
        </div>
        <div>
          <div
            style={{
              fontSize: 11,
              fontWeight: 750,
              letterSpacing: '0.07em',
              textTransform: 'uppercase',
              color: 'var(--ds-ink-3)',
              margin: '0 0 8px',
            }}
          >
            Outcomes
          </div>
          <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(132px, 1fr))' }}>
            <div className="stat"><div className="stat-l">Total</div><div className="stat-v num">{perfStats.i('total_signals')}</div></div>
            <div className="stat"><div className="stat-l">Completed</div><div className="stat-v num">{perfStats.i('completed_signals')}</div></div>
            <div className="stat"><div className="stat-l">Won</div><div className="stat-v num v-bull">{perfStats.i('winning_signals')}</div></div>
            <div className="stat"><div className="stat-l">Lost</div><div className="stat-v num v-bear">{perfStats.i('losing_signals')}</div></div>
            <div className="stat"><div className="stat-l">T1 hits</div><div className="stat-v num">{perfStats.i('target_1_hits')}</div></div>
            <div className="stat"><div className="stat-l">T2 hits</div><div className="stat-v num">{perfStats.i('target_2_hits')}</div></div>
            <div className="stat"><div className="stat-l">SL hits</div><div className="stat-v num v-bear">{perfStats.i('stop_loss_hits')}</div></div>
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

  const ledgerBody =
    auditLoading && auditRows.length === 0 ? (
      <Skeletons rows={5} />
    ) : auditError && auditRows.length === 0 ? (
      <div>
        <EmptyNote>Ledger unavailable - {auditError}</EmptyNote>
        <div style={{ marginTop: 10 }}>
          <RetryButton onRetry={refreshAll} />
        </div>
      </div>
    ) : auditRows.length === 0 ? (
      <div className="sig-empty">
        <Wallet size={22} />
        <p className="muted" style={{ margin: 0 }}>No trades yet - the ledger fills as signals execute and square off.</p>
      </div>
    ) : (
      <div style={{ display: 'grid', gap: 14 }}>
        <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))' }}>
          <div className="stat">
            <div className="stat-l">Realised</div>
            <div className={`stat-v num ${pnlTone(auditSummary?.realized ?? null)}`}>{pnlSigned(auditSummary?.realized ?? null)}</div>
            <div className="stat-s num">{auditSummary ? `${auditSummary.closed ?? '-'} closed` : '-'}</div>
          </div>
          <div className="stat">
            <div className="stat-l">Unrealised / live MTM</div>
            <div className={`stat-v num ${pnlTone(auditSummary?.unrealized ?? null)}`}>{pnlSigned(auditSummary?.unrealized ?? null)}</div>
            <div className="stat-s">open positions - live</div>
          </div>
          <div className="stat">
            <div className="stat-l">Net P&L</div>
            <div className={`stat-v num ${pnlTone(auditSummary?.total ?? null)}`}>{pnlSigned(auditSummary?.total ?? null)}</div>
            <div className="stat-s num">{auditSummary ? (auditSummary.winRate === null ? '-' : `${auditSummary.winRate}% win rate`) : '-'}</div>
          </div>
        </div>

        <div className="tbl-scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Strategy</th>
                <th>Dir</th>
                <th>Status</th>
                <th className="r">Entry</th>
                <th className="r">Live / Exit</th>
                <th className="r">Realised</th>
                <th className="r">Unrealised</th>
                <th className="r">Total</th>
              </tr>
            </thead>
            <tbody>
              {auditRows.map((r, i) => {
                const isOpen = !/(WON|LOST|CLOSED|SQUARED|STOP|TARGET_2|RUNNER)/.test(r.status.toUpperCase());
                const livePrice = r.current ?? r.exit;
                return (
                  <tr key={typeof r.id === 'string' ? r.id : `ledger-${i}`}>
                    <td className="num">{r.timeMs === null ? '-' : fmtTimeMs(r.timeMs)}</td>
                    <td style={{ fontWeight: 700 }}>{r.underlying}</td>
                    <td style={{ fontSize: 12.5 }}>{prettyKey(r.strategy)}</td>
                    <td><DirectionBadge direction={r.direction} /></td>
                    <td><StateBadge state={r.status} /></td>
                    <td className="r num">{r.entry === null ? '-' : fmtINR(r.entry)}</td>
                    <td className="r num" style={{ whiteSpace: 'nowrap' }}>
                      {isOpen ? <span className="live-dot" style={{ width: 7, height: 7, marginRight: 6, verticalAlign: 'middle' }} /> : null}
                      {livePrice === null ? '-' : fmtINR(livePrice)}
                    </td>
                    <td className={`r num ${pnlTone(r.realized)}`}>{pnlSigned(r.realized)}</td>
                    <td className={`r num ${pnlTone(r.unrealized)}`}>{isOpen ? pnlSigned(r.unrealized) : '-'}</td>
                    <td className={`r num ${pnlTone(r.total)}`}>{pnlSigned(r.total)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );


  /* ---- confined layout: command header -> tabs -> single panel ---- */

  return (
    <div className="ds-module">
      <header className="module-hero">
        <div className="toolbar">
          <div>
            <div className="flex items-center gap-2.5">
              <h2>Signals</h2>
              <span
                className={connected ? 'badge b-bull' : 'badge b-warn'}
                style={{ fontSize: 11 }}
                title={connected ? 'Live via SSE' : 'Reconnecting'}
              >
                {connected ? 'LIVE' : 'OFFLINE'}
              </span>
            </div>
            <p className="muted num">
              Active setups &amp; paper trades &middot; auto-refresh 15s &middot; live via SSE
            </p>
          </div>
          <span className="spacer" />
          <div className="module-filters">
            <label className="field">
              <span className="field-l">Setup</span>
              <select
                className="input"
                value={deskFilter}
                onChange={(e) => setDeskFilter(e.target.value as DeskFilter)}
              >
                {DESK_FILTERS.map((d) => (
                  <option key={d} value={d}>{d === 'ALL' ? 'All desks' : prettyKey(d)}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-l">Instrument</span>
              <select
                className="input"
                value={instrumentFilter}
                onChange={(e) => setInstrumentFilter(e.target.value as InstrumentFilter)}
              >
                {INSTRUMENT_FILTERS.map((s) => (
                  <option key={s} value={s}>{s === 'ALL' ? 'All' : s}</option>
                ))}
              </select>
            </label>
            <button type="button" className="btn" onClick={refreshAll} title="Refresh all">
              <RefreshCw size={14} />&nbsp;Refresh
            </button>
            {statusError ? <p className="err num">{statusError}</p> : null}
          </div>
        </div>
        <div className="kpis">
          <div className="kpi">
            <span className="kpi-l">Active</span>
            <span className="kpi-v num">{kpis.active === null ? '-' : kpis.active}</span>
          </div>
          <div className="kpi">
            <span className="kpi-l">Confirmed</span>
            <span className="kpi-v num v-bull">{kpis.confirmed === null ? '-' : kpis.confirmed}</span>
          </div>
          <div className="kpi">
            <span className="kpi-l">Armed</span>
            <span className="kpi-v num">{kpis.armed === null ? '-' : kpis.armed}</span>
          </div>
        </div>
      </header>

      <nav className="tabbar" role="tablist" aria-label="Signal sections">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'live'}
          className={tab === 'live' ? 'tab is-active' : 'tab'}
          onClick={() => setTab('live')}
        >
          <Play size={13} />&nbsp;Live setups
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'performance'}
          className={tab === 'performance' ? 'tab is-active' : 'tab'}
          onClick={() => setTab('performance')}
        >
          <Gauge size={13} />&nbsp;Performance
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'history'}
          className={tab === 'history' ? 'tab is-active' : 'tab'}
          onClick={() => setTab('history')}
        >
          <Wallet size={13} />&nbsp;P&L ledger
        </button>
        <span className="spacer" />
        {tab === 'history' ? (
          <button
            type="button"
            className="btn icon-btn"
            title="Repair / sanitize audit ledger"
            disabled={sanitizeBusy}
            onClick={() => void sanitizeAudit()}
          >
            <Eraser size={14} />
          </button>
        ) : null}
        <button type="button" className="btn is-bull" onClick={() => setCreateOpen(true)}>
          <Plus size={14} />&nbsp;New setup
        </button>
      </nav>

      <section className="panel">
        <div className="panel-scroll">
          {tab === 'history' && sanitizeNote ? (
            <p className="muted num" style={{ margin: '0 0 8px', fontSize: 12 }}>{sanitizeNote}</p>
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
    </div>
  );
}

export default SignalsDesk;