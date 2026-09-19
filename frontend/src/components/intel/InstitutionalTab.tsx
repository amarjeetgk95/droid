'use client';

/* Institutional panels: MI dashboard, data health, calls/puts, full MI,
   signal FSM with transitions + TTL, feed circuits, audit, evaluators. */

import { useCallback, useMemo, useState } from 'react';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/toast';
import { useNow } from '@/hooks/useNow';
import type { InstitutionalDeskState, InstSignalDetail } from '@/hooks/useIntelDesk';
import { getObj, pickNum, pickStr } from '@/lib/signalsNormalize';
import {
  allowedInstTargets,
  badgeClass,
  evidenceLines,
  fmtTtlMs,
  healthTone,
  signalTone,
} from '@/lib/intelDesk';
import { EvaluateForms } from './EvaluateForms';

function fmtDur(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
  if (ms <= 0) return 'expired';
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}m ${s % 60}s` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

function ScoreKv({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="sg-kv">
      <span className="l">{label}</span>
      <span className="v num">{value === null ? '—' : value}</span>
    </div>
  );
}

/** Pick a key from the record, falling back to nested summary/data objects. */
function deepPickNum(raw: Record<string, unknown> | null, ...keys: string[]): number | null {
  if (!raw) return null;
  const direct = pickNum(raw, ...keys);
  if (direct !== null) return direct;
  for (const nest of ['summary', 'data', 'options', 'chain']) {
    const o = getObj(raw[nest]);
    if (o) {
      const v = pickNum(o, ...keys);
      if (v !== null) return v;
    }
  }
  return null;
}

function deepPickStr(raw: Record<string, unknown> | null, ...keys: string[]): string | null {
  if (!raw) return null;
  const direct = pickStr(raw, ...keys);
  if (direct) return direct;
  for (const nest of ['summary', 'data', 'options', 'chain']) {
    const o = getObj(raw[nest]);
    if (o) {
      const v = pickStr(o, ...keys);
      if (v) return v;
    }
  }
  return null;
}

export function InstitutionalTab({
  desk,
  instrument,
}: {
  desk: InstitutionalDeskState;
  instrument: string;
}) {
  const { push } = useToast();
  const now = useNow(1000);
  const [inspectedId, setInspectedId] = useState<string | null>(null);
  const [inspectDetail, setInspectDetail] = useState<InstSignalDetail | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const [pendingTransition, setPendingTransition] = useState<{ id: string; to: string } | null>(null);
  const [pendingCas, setPendingCas] = useState<string | null>(null);
  const [busySignal, setBusySignal] = useState(false);
  const [ttlNote, setTtlNote] = useState<string | null>(null);
  const [feedDetailId, setFeedDetailId] = useState<string | null>(null);
  const [feedDetail, setFeedDetail] = useState<Record<string, unknown> | null>(null);
  const [pendingTrip, setPendingTrip] = useState<{ id: string; anomaly: string; reason: string } | null>(null);
  const [pendingResync, setPendingResync] = useState<string | null>(null);
  const [tripAnomaly, setTripAnomaly] = useState('MISSING');
  const [tripReason, setTripReason] = useState('manual trip');

  const miFullView = useMemo(() => {
    if (!desk.miFull) return null;
    const nested = getObj(desk.miFull.market_intelligence) ?? {};
    return { raw: desk.miFull, nested };
  }, [desk.miFull]);

  const cpRaw = useMemo(() => getObj(desk.callsPuts), [desk.callsPuts]);

  const handleInspect = useCallback(
    async (signalId: string) => {
      if (inspectedId === signalId) {
        setInspectedId(null);
        setInspectDetail(null);
        return;
      }
      setInspectedId(signalId);
      setInspecting(true);
      try {
        setInspectDetail(await desk.loadSignalDetail(signalId));
      } finally {
        setInspecting(false);
      }
    },
    [desk, inspectedId],
  );

  const handleTtl = useCallback(
    async (signalId: string) => {
      const result = await desk.checkTtl(signalId);
      setTtlNote(result.message);
      push(result.ok ? 'success' : 'error', result.message);
      if (inspectedId === signalId) {
        setInspectDetail(await desk.loadSignalDetail(signalId));
      }
    },
    [desk, inspectedId, push],
  );

  const handleTransition = useCallback(async () => {
    if (!pendingTransition) return;
    setBusySignal(true);
    try {
      const result = await desk.transition(pendingTransition.id, pendingTransition.to);
      push(result.ok ? 'success' : 'error', result.message);
      if (result.ok && inspectedId === pendingTransition.id) {
        setInspectDetail(await desk.loadSignalDetail(pendingTransition.id));
      }
    } finally {
      setBusySignal(false);
      setPendingTransition(null);
    }
  }, [desk, inspectedId, pendingTransition, push]);

  const handleCas = useCallback(async () => {
    if (!pendingCas) return;
    setBusySignal(true);
    try {
      const result = await desk.casExecute(pendingCas);
      push(result.ok ? 'success' : 'error', result.message);
      if (result.ok) setInspectDetail(await desk.loadSignalDetail(pendingCas));
    } finally {
      setBusySignal(false);
      setPendingCas(null);
    }
  }, [desk, pendingCas, push]);

  const handleFeedDetail = useCallback(
    async (instrumentId: string) => {
      if (feedDetailId === instrumentId) {
        setFeedDetailId(null);
        setFeedDetail(null);
        return;
      }
      setFeedDetailId(instrumentId);
      setFeedDetail(await desk.loadFeedDetail(instrumentId));
    },
    [desk, feedDetailId],
  );

  const handleTrip = useCallback(async () => {
    if (!pendingTrip) return;
    setBusySignal(true);
    try {
      const result = await desk.tripFeed(pendingTrip.id, pendingTrip.anomaly, pendingTrip.reason);
      push(result.ok ? 'success' : 'error', result.message);
    } finally {
      setBusySignal(false);
      setPendingTrip(null);
    }
  }, [desk, pendingTrip, push]);

  const handleResync = useCallback(async () => {
    if (!pendingResync) return;
    setBusySignal(true);
    try {
      const result = await desk.resyncFeed(pendingResync);
      push(result.ok ? 'success' : 'error', result.message);
    } finally {
      setBusySignal(false);
      setPendingResync(null);
    }
  }, [desk, pendingResync, push]);

  const miEvidence = useMemo(
    () => ({
      supporting: evidenceLines(desk.miRaw?.supporting_evidence),
      conflicting: evidenceLines(desk.miRaw?.conflicting_evidence),
    }),
    [desk.miRaw],
  );

  const fullEvidence = useMemo(
    () => ({
      supporting: evidenceLines(getObj(miFullView?.raw.evidence)?.supporting),
      conflicting: evidenceLines(getObj(miFullView?.raw.evidence)?.conflicting),
      missing: Array.isArray(getObj(miFullView?.raw.evidence)?.missing)
        ? ((getObj(miFullView?.raw.evidence)?.missing as unknown[]).map(String).slice(0, 6))
        : [],
    }),
    [miFullView],
  );

  const fullLevels = useMemo(() => {
    const levels = getObj(miFullView?.raw.levels) ?? {};
    const str = (v: unknown): string[] =>
      Array.isArray(v) ? v.map(String).slice(0, 6) : [];
    return {
      support: str(levels.support),
      resistance: str(levels.resistance),
      trigger: typeof levels.breakout_trigger === 'string' ? levels.breakout_trigger : null,
    };
  }, [miFullView]);

  return (
    <div className="flex flex-col gap-2">
      {/* Market intelligence dashboard */}
      <section className="card" aria-label="Market intelligence">
        <div className="card-hd">
          <h2 className="card-title">Market Intelligence</h2>
          {desk.mi ? (
            <span className={`badge ${badgeClass(healthTone(desk.mi.regime))}`}>
              {desk.mi.regime ?? '—'}
            </span>
          ) : null}
          <span className="card-meta num">
            {desk.mi?.spot !== null && desk.mi?.spot !== undefined ? desk.mi.spot : '—'}
          </span>
        </div>
        <div className="card-bd flex flex-col gap-2">
          {!desk.mi && !desk.loading ? (
            <p className="sg-empty">Market intelligence unavailable for {instrument}.</p>
          ) : desk.mi ? (
            <>
              <div className="sg-kvlist">
                <ScoreKv label="bullish score" value={desk.mi.bullish} />
                <ScoreKv label="bearish score" value={desk.mi.bearish} />
                <ScoreKv label="breakout pressure" value={desk.mi.breakoutPressure} />
                <ScoreKv label="breakdown pressure" value={desk.mi.breakdownPressure} />
                <ScoreKv label="false breakout risk" value={desk.mi.falseBreakoutRisk} />
                <div className="sg-kv">
                  <span className="l">trend</span>
                  <span className="v">{desk.mi.trend ?? '—'}</span>
                </div>
              </div>
              <div className="pnl-strip">
                <span className="ps">
                  <span className="ps-l">short</span>
                  <span className={`sg-tag ${signalTone(desk.mi.shortStatus ?? 'WATCH')}`}>
                    {desk.mi.shortStatus ?? '—'}
                  </span>
                </span>
                <span className="ps">
                  <span className="ps-l">continuation</span>
                  <span className={`sg-tag ${signalTone(desk.mi.contStatus ?? 'WATCH')}`}>
                    {desk.mi.contStatus ?? '—'}
                  </span>
                </span>
                <span className="ps">
                  <span className="ps-l">breakout</span>
                  <span className={`sg-tag ${signalTone(desk.mi.breakoutStatus ?? 'WATCH')}`}>
                    {[desk.mi.breakoutStatus, desk.mi.breakoutDirection].filter(Boolean).join(' · ') || '—'}
                  </span>
                </span>
                <span className="ps">
                  <span className="ps-l">data</span>
                  <span className={`sg-tag ${healthTone(desk.mi.dataHealth)}`}>
                    {desk.mi.dataHealth ?? '—'}
                  </span>
                </span>
              </div>
              {miEvidence.supporting.length > 0 || miEvidence.conflicting.length > 0 ? (
                <div className="tbl-scroll">
                  <table className="sg-table">
                    <tbody>
                      {miEvidence.supporting.map((line, i) => (
                        <tr key={`s-${i}`}><td><span className="sg-tag bull">supporting</span></td><td className="sg-rownote">{line}</td></tr>
                      ))}
                      {miEvidence.conflicting.map((line, i) => (
                        <tr key={`c-${i}`}><td><span className="sg-tag bear">conflicting</span></td><td className="sg-rownote">{line}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="sg-note">No supporting/conflicting evidence in this poll.</p>
              )}
            </>
          ) : (
            <p className="sg-note">Loading market intelligence…</p>
          )}
        </div>
      </section>

      {/* Data health */}
      <section className="card" aria-label="Data health">
        <div className="card-hd">
          <h2 className="card-title">Data Health</h2>
          <span className="card-meta">{desk.healthRows.length} instrument(s)</span>
        </div>
        <div className="card-bd">
          {desk.healthRows.length === 0 ? (
            <p className="sg-empty">{desk.loading ? 'Loading data health…' : 'No data-health rows reported.'}</p>
          ) : (
            <div className="tbl-scroll">
              <table className="sg-table">
                <thead><tr><th>Instrument</th><th>Status</th><th>Feed</th></tr></thead>
                <tbody>
                  {desk.healthRows.map((row) => (
                    <tr key={row.instrument}>
                      <td className="sg-sym">{row.instrument}</td>
                      <td><span className={`sg-tag ${healthTone(row.status)}`}>{row.status}</span></td>
                      <td className="sg-rownote">{row.feed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {Object.keys(desk.healthOverall).length > 0 ? (
            <p className="sg-note">
              {Object.entries(desk.healthOverall).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`).join(' · ')}
            </p>
          ) : null}
        </div>
      </section>

      {/* Calls & puts */}
      <section className="card" aria-label="Calls and puts">
        <div className="card-hd">
          <h2 className="card-title">Calls / Puts</h2>
          <span className="card-meta">{deepPickStr(cpRaw, 'underlying', 'instrument') ?? instrument}</span>
        </div>
        <div className="card-bd">
          {!cpRaw && !desk.loading ? (
            <p className="sg-empty">Calls/puts chain unavailable for {instrument}.</p>
          ) : !cpRaw ? (
            <p className="sg-note">Loading option chain…</p>
          ) : (
            <div className="sg-kvlist">
              <ScoreKv label="pcr" value={deepPickNum(cpRaw, 'pcr')} />
              <ScoreKv label="pcr volume" value={deepPickNum(cpRaw, 'pcr_volume')} />
              <div className="sg-kv"><span className="l">call OI</span><span className="v num">{deepPickNum(cpRaw, 'total_call_oi')?.toLocaleString() ?? '—'}</span></div>
              <div className="sg-kv"><span className="l">put OI</span><span className="v num">{deepPickNum(cpRaw, 'total_put_oi')?.toLocaleString() ?? '—'}</span></div>
              <ScoreKv label="atm strike" value={deepPickNum(cpRaw, 'atm_strike')} />
              <ScoreKv label="max pain" value={deepPickNum(cpRaw, 'max_pain', 'max_pain_strike')} />
              <div className="sg-kv"><span className="l">expiry</span><span className="v">{deepPickStr(cpRaw, 'expiry') ?? '—'}</span></div>
            </div>
          )}
        </div>
      </section>

      {/* Full MI */}
      {miFullView ? (
        <section className="card" aria-label="Full market intelligence">
          <div className="card-hd">
            <h2 className="card-title">Full MI — {instrument}</h2>
            <span className="card-meta">{pickStr(getObj(miFullView.raw.header) ?? {}, 'data_quality') ?? '—'}</span>
          </div>
          <div className="card-bd flex flex-col gap-2">
            <div className="sg-kvlist">
              <div className="sg-kv"><span className="l">regime</span><span className="v">{pickStr(getObj(miFullView.raw.market_state) ?? {}, 'regime') ?? '—'}</span></div>
              <div className="sg-kv"><span className="l">momentum</span><span className="v">{pickStr(getObj(miFullView.raw.market_state) ?? {}, 'momentum') ?? '—'}</span></div>
              <div className="sg-kv"><span className="l">breakout trigger</span><span className="v num">{fullLevels.trigger ?? '—'}</span></div>
              <div className="sg-kv"><span className="l">support</span><span className="v">{fullLevels.support.join(', ') || '—'}</span></div>
              <div className="sg-kv"><span className="l">resistance</span><span className="v">{fullLevels.resistance.join(', ') || '—'}</span></div>
            </div>
            {fullEvidence.supporting.length + fullEvidence.conflicting.length > 0 ? (
              <div className="tbl-scroll">
                <table className="sg-table">
                  <tbody>
                    {fullEvidence.supporting.map((line, i) => (
                      <tr key={`fs-${i}`}><td><span className="sg-tag bull">supporting</span></td><td className="sg-rownote">{line}</td></tr>
                    ))}
                    {fullEvidence.conflicting.map((line, i) => (
                      <tr key={`fc-${i}`}><td><span className="sg-tag bear">conflicting</span></td><td className="sg-rownote">{line}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            {fullEvidence.missing.length > 0 ? (
              <p className="sg-note">Missing evidence: {fullEvidence.missing.join(', ')}</p>
            ) : null}
          </div>
        </section>
      ) : null}

      {/* Institutional signals */}
      <section className="card" aria-label="Institutional signals">
        <div className="card-hd">
          <h2 className="card-title">Institutional Signals</h2>
          <span className="card-meta">{desk.signals.length} active</span>
        </div>
        <div className="card-bd flex flex-col gap-2">
          {ttlNote ? <p className="sg-note">{ttlNote}</p> : null}
          {desk.signals.length === 0 ? (
            <p className="sg-empty">{desk.loading ? 'Loading signals…' : `No active institutional signals for ${instrument}.`}</p>
          ) : (
            <div className="tbl-scroll">
              <table className="sg-table">
                <thead><tr><th>Signal</th><th>Strategy</th><th>State</th><th>TTL</th><th>Actions</th></tr></thead>
                <tbody>
                  {desk.signals.map((row) => (
                    <tr key={row.id} data-active={inspectedId === row.id}>
                      <td>
                        <span className="sg-sym">{row.id.slice(0, 8)}</span>
                        <div className="sg-rownote">{row.instrument} · {row.direction}</div>
                      </td>
                      <td className="sg-rownote">{row.strategy}</td>
                      <td><span className={`sg-tag ${signalTone(row.fsmState)}`}>{row.fsmState}</span></td>
                      <td>
                        <span className={`sg-tag ${row.expired ? 'bear' : 'neut'}`} title="TTL remaining">
                          {fmtDur(row.ttlMs)}
                        </span>
                      </td>
                      <td>
                        <span className="sg-actions">
                          <button type="button" className="sg-ibtn" onClick={() => void handleInspect(row.id)}>
                            {inspectedId === row.id ? 'Hide' : 'Inspect'}
                          </button>
                          <button type="button" className="sg-ibtn" title="TTL check" onClick={() => void handleTtl(row.id)}>
                            TTL
                          </button>
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {inspectedId ? (
            <div className="panel" aria-label="Signal detail">
              {inspecting ? (
                <p className="sg-note">Loading signal detail…</p>
              ) : inspectDetail ? (
                <div className="flex flex-col gap-2">
                  <div className="sg-kvlist">
                    <div className="sg-kv"><span className="l">fsm state</span><span className="v">{inspectDetail.fsmState ?? '—'}</span></div>
                    <div className="sg-kv"><span className="l">ttl remaining</span><span className="v num">{fmtDur(inspectDetail.ttlRemainingMs)}</span></div>
                    <div className="sg-kv"><span className="l">expired</span><span className="v">{inspectDetail.expired === null ? '—' : inspectDetail.expired ? 'YES' : 'NO'}</span></div>
                  </div>
                  {(() => {
                    const targets = allowedInstTargets(inspectDetail.fsmState);
                    return targets.length > 0 ? (
                      <div className="ds-filters" style={{ marginLeft: 0 }}>
                        {targets.map((to) => (
                          <button
                            key={to}
                            type="button"
                            className="btn"
                            onClick={() => setPendingTransition({ id: inspectedId, to })}
                          >
                            → {to}
                          </button>
                        ))}
                        <button type="button" className="btn btn-primary" onClick={() => setPendingCas(inspectedId)}>
                          CAS execute
                        </button>
                      </div>
                    ) : (
                      <p className="sg-note">Terminal state — no transitions available. TTL: {inspectDetail.ttlRemainingMs !== null && inspectDetail.ttlRemainingMs !== undefined ? fmtTtlMs(now + inspectDetail.ttlRemainingMs, now) : '—'}.</p>
                    );
                  })()}
                </div>
              ) : (
                <p className="sg-err">Signal detail unavailable.</p>
              )}
            </div>
          ) : null}
          {desk.history.length > 0 ? (
            <div className="tbl-scroll">
              <table className="sg-table">
                <thead><tr><th colSpan={3}>Signal history ({desk.history.length})</th></tr></thead>
                <tbody>
                  {desk.history.slice(0, 8).map((row, i) => (
                    <tr key={`${row.id}-${i}`}>
                      <td className="sg-rownote">{row.id.slice(0, 8)}</td>
                      <td><span className="sg-tag neut">{row.kind}</span></td>
                      <td className="sg-rownote">{row.summary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </section>

      {/* Feed health */}
      <section className="card" aria-label="Feed health">
        <div className="card-hd">
          <h2 className="card-title">Feed Circuits</h2>
          <span className="card-meta">{desk.feeds.length} feed(s)</span>
        </div>
        <div className="card-bd flex flex-col gap-2">
          <div className="ds-filters" style={{ marginLeft: 0 }}>
            <label className="flex flex-col gap-1">
              <span className="card-meta">anomaly</span>
              <input className="input" value={tripAnomaly} onChange={(e) => setTripAnomaly(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="card-meta">reason</span>
              <input className="input" value={tripReason} onChange={(e) => setTripReason(e.target.value)} />
            </label>
          </div>
          {desk.feeds.length === 0 ? (
            <p className="sg-empty">{desk.loading ? 'Loading feed health…' : 'No feed states reported.'}</p>
          ) : (
            <div className="tbl-scroll">
              <table className="sg-table">
                <thead><tr><th>Feed</th><th>Health</th><th>Detail</th><th>Actions</th></tr></thead>
                <tbody>
                  {desk.feeds.map((feed) => (
                    <tr key={feed.instrument} data-active={feedDetailId === feed.instrument}>
                      <td className="sg-sym">{feed.instrument}</td>
                      <td><span className={`sg-tag ${healthTone(feed.health)}`}>{feed.health}</span></td>
                      <td className="sg-rownote">{feed.detail ?? '—'}</td>
                      <td>
                        <span className="sg-actions">
                          <button type="button" className="sg-ibtn" onClick={() => void handleFeedDetail(feed.instrument)}>
                            {feedDetailId === feed.instrument ? 'Hide' : 'Detail'}
                          </button>
                          <button type="button" className="sg-ibtn danger" onClick={() => setPendingTrip({ id: feed.instrument, anomaly: tripAnomaly.trim() || 'MISSING', reason: tripReason.trim() || 'manual trip' })}>
                            Trip
                          </button>
                          <button type="button" className="sg-ibtn" onClick={() => setPendingResync(feed.instrument)}>
                            Resync
                          </button>
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {feedDetailId && feedDetail ? (
            <div className="sg-kvlist">
              {Object.entries(feedDetail).slice(0, 12).map(([k, v]) => (
                <div className="sg-kv" key={k}>
                  <span className="l">{k.replace(/_/g, ' ')}</span>
                  <span className="v">{typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean' ? String(v) : '—'}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </section>

      {/* Audit */}
      <section className="card" aria-label="Audit trail">
        <div className="card-hd">
          <h2 className="card-title">Audit Trail</h2>
          <span className="card-meta">{desk.audit.length} record(s)</span>
        </div>
        <div className="card-bd">
          {desk.audit.length === 0 ? (
            <p className="sg-empty">{desk.loading ? 'Loading audit…' : 'No audit records.'}</p>
          ) : (
            <div className="tbl-scroll">
              <table className="sg-table">
                <thead><tr><th>Ref</th><th>Event</th><th>Summary</th></tr></thead>
                <tbody>
                  {desk.audit.slice(0, 10).map((row, i) => (
                    <tr key={`${row.id}-${i}`}>
                      <td className="sg-rownote">{row.id.slice(0, 8)}</td>
                      <td><span className="sg-tag neut">{row.kind}</span></td>
                      <td className="sg-rownote">{row.summary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      <EvaluateForms desk={desk} instrument={instrument} />

      <ConfirmDialog
        open={pendingTransition !== null}
        onOpenChange={(open) => { if (!open) setPendingTransition(null); }}
        tone="primary"
        confirmLabel={`Transition to ${pendingTransition?.to ?? ''}`}
        busy={busySignal}
        title={`Transition signal ${pendingTransition?.id.slice(0, 8) ?? ''} to ${pendingTransition?.to ?? ''}?`}
        description="The institutional FSM validates the transition; illegal moves are rejected by the backend."
        onConfirm={handleTransition}
      />

      <ConfirmDialog
        open={pendingCas !== null}
        onOpenChange={(open) => { if (!open) setPendingCas(null); }}
        tone="primary"
        confirmLabel="CAS to execution pending"
        busy={busySignal}
        title="Move this signal to EXECUTION_PENDING via compare-and-swap?"
        description="CAS succeeds only from RISK_APPROVED; the signal must not be expired."
        onConfirm={handleCas}
      />

      <ConfirmDialog
        open={pendingTrip !== null}
        onOpenChange={(open) => { if (!open) setPendingTrip(null); }}
        tone="danger"
        confirmLabel="Trip feed circuit"
        busy={busySignal}
        requireTypedConfirmation="TRIP"
        title={`Trip the ${pendingTrip?.id ?? ''} feed circuit?`}
        description="Downstream consumers degrade while the circuit is open. Type TRIP to confirm."
        intentRows={pendingTrip ? [
          { label: 'Instrument', value: pendingTrip.id },
          { label: 'Anomaly', value: pendingTrip.anomaly },
          { label: 'Reason', value: pendingTrip.reason },
        ] : undefined}
        onConfirm={handleTrip}
      />

      <ConfirmDialog
        open={pendingResync !== null}
        onOpenChange={(open) => { if (!open) setPendingResync(null); }}
        tone="primary"
        confirmLabel="Request resync"
        busy={busySignal}
        requireTypedConfirmation="RESYNC"
        title={`Request resync for ${pendingResync ?? ''}?`}
        description="Asks the feed to re-authorize from a fresh snapshot. Type RESYNC to confirm."
        onConfirm={handleResync}
      />
    </div>
  );
}
