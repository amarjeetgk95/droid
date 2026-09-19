'use client';

/* Event intelligence panels: risk overlay, today/upcoming with risk flags,
   detail drill-down, alerts queue, track record, source health, shadow
   signals, sync triggers and manual entry. Syncs + manual entry sit behind
   ConfirmDialog; polling lives in the hook, never here. */

import { useCallback, useMemo, useState } from 'react';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/toast';
import type { EventsDeskState } from '@/hooks/useIntelDesk';
import type { CanonicalEvent } from '@/lib/event-types';
import {
  alertSeverityTone,
  badgeClass,
  eventIdOf,
  eventPhaseTone,
  eventRiskFlags,
  fmtClockIST,
  healthTone,
} from '@/lib/intelDesk';
import { EventDetail } from './EventDetail';

const EVENT_TYPES = [
  'MACRO',
  'CENTRAL_BANK',
  'COMPANY',
  'EARNINGS',
  'CORPORATE_ACTION',
  'REGULATORY',
  'POLICY',
  'GLOBAL',
  'GEOPOLITICAL',
  'SECTOR',
  'OTHER',
];

const DIRECTIONS = ['BULLISH', 'BEARISH', 'NEUTRAL', 'TWO_SIDED', 'UNKNOWN'];

function EventRows({
  events,
  selectedId,
  onOpen,
}: {
  events: CanonicalEvent[];
  selectedId: string | null;
  onOpen: (id: string) => void;
}) {
  if (events.length === 0) {
    return <p className="sg-empty">No events in this list — the engine has nothing scheduled here.</p>;
  }
  return (
    <div className="tbl-scroll">
      <table className="sg-table">
        <thead><tr><th>Event</th><th>Time</th><th>Phase</th><th>Risk flags</th></tr></thead>
        <tbody>
          {events.map((event) => {
            const id = eventIdOf(event);
            const flags = eventRiskFlags(event);
            return (
              <tr key={id} data-active={selectedId === id}>
                <td>
                  <button
                    type="button"
                    className="sg-sym"
                    style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer', textAlign: 'left' }}
                    onClick={() => onOpen(id)}
                    title="Open event detail"
                  >
                    {event.title}
                  </button>
                  <div className="sg-rownote">{event.event_type} · {event.entity_name}</div>
                </td>
                <td className="sg-rownote">{fmtClockIST(event.event_timestamp)}</td>
                <td><span className={`sg-tag ${eventPhaseTone(event.temporal_phase)}`}>{event.temporal_phase.replace(/_/g, ' ')}</span></td>
                <td>
                  {flags.length === 0 ? (
                    <span className="sg-rownote">—</span>
                  ) : (
                    flags.map((flag) => (
                      <span key={flag} className={`sg-tag ${flag === 'LIVE NOW' ? 'bear' : flag === 'NO-TRADE' ? 'warn' : 'neut'}`} style={{ marginRight: 4 }}>
                        {flag}
                      </span>
                    ))
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function EventsTab({
  desk,
  underlying,
  isOpen,
}: {
  desk: EventsDeskState;
  underlying: string;
  isOpen: boolean;
}) {
  const { push } = useToast();
  const [pendingAck, setPendingAck] = useState<string | null>(null);
  const [pendingSync, setPendingSync] = useState<'rbi' | 'corporate' | null>(null);
  const [pendingManual, setPendingManual] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);

  const [mTitle, setMTitle] = useState('');
  const [mTime, setMTime] = useState('');
  const [mType, setMType] = useState('CENTRAL_BANK');
  const [mEntity, setMEntity] = useState('RBI');
  const [mEntityName, setMEntityName] = useState('Reserve Bank of India');
  const [mSector, setMSector] = useState('BANKING');
  const [mDirection, setMDirection] = useState('UNKNOWN');
  const [mDescription, setMDescription] = useState('');

  const overlay = desk.overlay;

  const handleAck = useCallback(async () => {
    if (!pendingAck) return;
    setBusy(true);
    try {
      const result = await desk.ackAlert(pendingAck);
      push(result.ok ? 'success' : 'error', result.message);
    } finally {
      setBusy(false);
      setPendingAck(null);
    }
  }, [desk, pendingAck, push]);

  const handleSync = useCallback(async () => {
    if (!pendingSync) return;
    setBusy(true);
    try {
      const result = pendingSync === 'rbi' ? await desk.syncRbi() : await desk.syncCorporate();
      push(result.ok ? 'success' : 'error', result.message);
    } finally {
      setBusy(false);
      setPendingSync(null);
    }
  }, [desk, pendingSync, push]);

  const queueManual = useCallback(() => {
    if (!mTitle.trim() || !mTime.trim()) {
      push('error', 'Manual entry needs a title and an event time.');
      return;
    }
    const parsed = new Date(mTime);
    if (Number.isNaN(parsed.getTime())) {
      push('error', 'Event time is not a valid date.');
      return;
    }
    setPendingManual({
      title: mTitle.trim(),
      event_timestamp: parsed.toISOString(),
      event_type: mType,
      entity_id: mEntity.trim() || 'MANUAL',
      entity_name: mEntityName.trim() || mEntity.trim() || 'Manual desk',
      sector: mSector.trim() || 'UNKNOWN',
      expected_direction: mDirection,
      description: mDescription.trim() || undefined,
      source_name: 'MANUAL_OPS',
    });
  }, [mTitle, mTime, mType, mEntity, mEntityName, mSector, mDirection, mDescription, push]);

  const handleManual = useCallback(async () => {
    if (!pendingManual) return;
    setBusy(true);
    try {
      const result = await desk.createManual(pendingManual);
      push(result.ok ? 'success' : 'error', result.message);
      if (result.ok) {
        setMTitle('');
        setMTime('');
        setMDescription('');
      }
    } finally {
      setBusy(false);
      setPendingManual(null);
    }
  }, [desk, pendingManual, push]);

  const sourcesRows = useMemo(() => Object.values(desk.sources?.sources ?? {}), [desk.sources]);
  const track = desk.trackRecord;

  return (
    <div className="flex flex-col gap-2">
      {/* Risk overlay */}
      <section className="card" aria-label="Event risk overlay">
        <div className="card-hd">
          <h2 className="card-title">Event Risk Overlay</h2>
          {overlay ? (
            <span className={`badge ${badgeClass(healthTone(overlay.proximity_state === 'NORMAL' ? 'VALID' : overlay.proximity_state))}`}>
              {overlay.proximity_state.replace(/_/g, ' ')}
            </span>
          ) : null}
          <span className="card-meta">{underlying}</span>
        </div>
        <div className="card-bd">
          {!overlay && !desk.loading ? (
            <p className="sg-empty">Risk overlay unavailable for {underlying}.</p>
          ) : !overlay ? (
            <p className="sg-note">Loading risk overlay…</p>
          ) : (
            <div className="sg-kvlist">
              <div className="sg-kv"><span className="l">entry allowed</span><span className="v">{overlay.can_enter ? 'YES' : 'NO'}</span></div>
              <div className="sg-kv"><span className="l">sizing multiplier</span><span className="v num">{Math.round(overlay.sizing_multiplier * 100)}%</span></div>
              <div className="sg-kv"><span className="l">max loss dampener</span><span className="v num">{overlay.max_loss_dampener}</span></div>
              <div className="sg-kv"><span className="l">naked options</span><span className="v">{overlay.prohibit_naked_options ? 'PROHIBITED' : 'ALLOWED'}</span></div>
              <div className="sg-kv"><span className="l">trigger event</span><span className="v">{overlay.triggering_event_title ?? '—'}</span></div>
              <div className="sg-kv"><span className="l">minutes to event</span><span className="v num">{overlay.minutes_to_event ?? '—'}</span></div>
              {overlay.rejection_reason ? (
                <div className="sg-kv"><span className="l">gate reason</span><span className="v">{overlay.rejection_reason}</span></div>
              ) : null}
            </div>
          )}
          <p className="sg-note">
            {isOpen ? 'Polling every 60s while the market is open.' : 'Market closed — showing the last snapshot.'}
          </p>
        </div>
      </section>

      {/* Today / upcoming */}
      <section className="card" aria-label="Events today">
        <div className="card-hd">
          <h2 className="card-title">Today</h2>
          <span className="card-meta">{desk.today.length} event(s)</span>
        </div>
        <div className="card-bd">
          {desk.loading && desk.today.length === 0 ? (
            <p className="sg-note">Loading events…</p>
          ) : (
            <EventRows events={desk.today} selectedId={desk.selectedId} onOpen={(id) => void desk.openEvent(id)} />
          )}
        </div>
      </section>

      <section className="card" aria-label="Upcoming events">
        <div className="card-hd">
          <h2 className="card-title">Upcoming</h2>
          <span className="card-meta">{desk.upcoming.length} event(s)</span>
        </div>
        <div className="card-bd">
          {desk.loading && desk.upcoming.length === 0 ? (
            <p className="sg-note">Loading events…</p>
          ) : (
            <EventRows events={desk.upcoming} selectedId={desk.selectedId} onOpen={(id) => void desk.openEvent(id)} />
          )}
        </div>
      </section>

      {desk.selectedId ? (
        <EventDetail bundle={desk.detail} loading={desk.detailLoading} onClose={desk.closeEvent} />
      ) : null}

      {/* Alerts queue */}
      <section className="card" aria-label="Alerts queue">
        <div className="card-hd">
          <h2 className="card-title">Alerts Queue</h2>
          <span className="card-meta">{desk.alerts === null ? 'not loaded' : `${desk.alerts.length} alert(s)`}</span>
        </div>
        <div className="card-bd flex flex-col gap-2">
          <div className="ds-filters" style={{ marginLeft: 0 }}>
            <button type="button" className="btn" disabled={desk.alertsLoading} onClick={() => void desk.loadAlerts()}>
              {desk.alertsLoading ? 'Loading…' : desk.alerts === null ? 'Load alerts' : 'Reload alerts'}
            </button>
          </div>
          {desk.alerts === null && !desk.alertsLoading ? (
            <p className="sg-note">Alerts load on demand — nothing is polled here.</p>
          ) : desk.alerts !== null && desk.alerts.length === 0 ? (
            <p className="sg-empty">Alert queue is empty — nothing awaiting review.</p>
          ) : desk.alerts ? (
            <div className="tbl-scroll">
              <table className="sg-table">
                <thead><tr><th>Alert</th><th>Severity</th><th>Status</th><th>Actions</th></tr></thead>
                <tbody>
                  {desk.alerts.map((alert) => (
                    <tr key={alert.alert_id}>
                      <td>
                        <span className="sg-sym">{alert.title}</span>
                        <div className="sg-rownote">{alert.alert_type} · {fmtClockIST(alert.created_at)}</div>
                      </td>
                      <td><span className={`sg-tag ${alertSeverityTone(alert.severity)}`}>{alert.severity}</span></td>
                      <td className="sg-rownote">{alert.status.replace(/_/g, ' ')}</td>
                      <td>
                        <span className="sg-actions">
                          <button
                            type="button"
                            className="sg-ibtn"
                            disabled={alert.status === 'ACKNOWLEDGED'}
                            onClick={() => setPendingAck(alert.alert_id)}
                          >
                            Ack
                          </button>
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </section>

      {/* Track record */}
      <section className="card" aria-label="Track record">
        <div className="card-hd">
          <h2 className="card-title">Track Record</h2>
          {track ? <span className="card-meta">{track.recommendation.replace(/_/g, ' ')}</span> : null}
        </div>
        <div className="card-bd">
          {!track && !desk.loading ? (
            <p className="sg-empty">No track-record statistics published yet.</p>
          ) : !track ? (
            <p className="sg-note">Loading track record…</p>
          ) : (
            <div className="sg-kvlist">
              <div className="sg-kv"><span className="l">events evaluated</span><span className="v num">{track.total_events_evaluated}</span></div>
              <div className="sg-kv"><span className="l">settled</span><span className="v num">{track.settled_events_count}</span></div>
              <div className="sg-kv"><span className="l">directional accuracy</span><span className="v num">{track.directional_accuracy_pct}%</span></div>
              <div className="sg-kv"><span className="l">shadow win rate</span><span className="v num">{track.shadow_win_rate_pct}%</span></div>
              <div className="sg-kv"><span className="l">profit factor</span><span className="v num">{track.profit_factor}</span></div>
              <div className="sg-kv"><span className="l">expectancy (R)</span><span className="v num">{track.average_expectancy_r}</span></div>
              <div className="sg-kv"><span className="l">sample gate</span><span className="v">{track.sample_size_gate_passed ? `PASS (${track.minimum_sample_required} min)` : `ACCUMULATING (${track.minimum_sample_required} min)`}</span></div>
            </div>
          )}
        </div>
      </section>

      {/* Sources */}
      <section className="card" aria-label="Source health">
        <div className="card-hd">
          <h2 className="card-title">Source Health</h2>
          {desk.sources ? (
            <span className={`badge ${badgeClass(healthTone(desk.sources.overall_status))}`}>
              {desk.sources.overall_status}
            </span>
          ) : null}
        </div>
        <div className="card-bd">
          {sourcesRows.length === 0 ? (
            <p className="sg-empty">{desk.loading ? 'Loading sources…' : 'No source adapters reported.'}</p>
          ) : (
            <div className="tbl-scroll">
              <table className="sg-table">
                <thead><tr><th>Source</th><th>Status</th><th>Circuit</th><th className="num">Latency</th><th className="num">Errors</th></tr></thead>
                <tbody>
                  {sourcesRows.map((src) => (
                    <tr key={src.source_name}>
                      <td className="sg-sym">{src.source_name}</td>
                      <td><span className={`sg-tag ${healthTone(src.status)}`}>{src.status}</span></td>
                      <td className="sg-rownote">{src.circuit_state}</td>
                      <td className="num">{src.last_latency_ms} ms</td>
                      <td className="num">{src.consecutive_errors}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* Shadow signals */}
      <section className="card" aria-label="Shadow signals">
        <div className="card-hd">
          <h2 className="card-title">Shadow Signals</h2>
          <span className="card-meta">{desk.shadow.length} record(s)</span>
        </div>
        <div className="card-bd">
          {desk.shadow.length === 0 ? (
            <p className="sg-empty">{desk.loading ? 'Loading shadow signals…' : 'No forward-testing shadow signals.'}</p>
          ) : (
            <div className="tbl-scroll">
              <table className="sg-table">
                <thead><tr><th>Signal</th><th>Direction</th><th>Status</th><th className="num">Sim P&L</th></tr></thead>
                <tbody>
                  {desk.shadow.slice(0, 12).map((sig) => (
                    <tr key={sig.shadow_signal_id}>
                      <td>
                        <span className="sg-sym">{sig.shadow_signal_id.slice(0, 8)}</span>
                        <div className="sg-rownote">{sig.underlying} · {sig.strategy} · {sig.execution_mode}</div>
                      </td>
                      <td className="sg-rownote">{sig.direction}</td>
                      <td><span className="sg-tag neut">{sig.shadow_status}</span></td>
                      <td className="num">{sig.simulated_pnl_pct === null || sig.simulated_pnl_pct === undefined ? '—' : `${sig.simulated_pnl_pct}%`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* Sync triggers */}
      <section className="card" aria-label="Source sync">
        <div className="card-hd">
          <h2 className="card-title">Source Sync</h2>
          <span className="card-meta">manual triggers</span>
        </div>
        <div className="card-bd flex flex-col gap-2">
          <p className="sg-note">Syncs pull official sources into the engine. Confirm each run — they hit the shared backend.</p>
          <div className="ds-filters" style={{ marginLeft: 0 }}>
            <button type="button" className="btn btn-primary" onClick={() => setPendingSync('rbi')}>
              Sync RBI
            </button>
            <button type="button" className="btn btn-primary" onClick={() => setPendingSync('corporate')}>
              Sync corporate
            </button>
          </div>
        </div>
      </section>

      {/* Manual entry */}
      <section className="card" aria-label="Manual event entry">
        <div className="card-hd">
          <h2 className="card-title">Manual Entry</h2>
          <span className="card-meta">ops fallback</span>
        </div>
        <div className="card-bd flex flex-col gap-2">
          <div className="ds-filters" style={{ marginLeft: 0 }}>
            <label className="flex flex-col gap-1">
              <span className="card-meta">title *</span>
              <input className="input" value={mTitle} onChange={(e) => setMTitle(e.target.value)} placeholder="e.g. RBI MPC decision" />
            </label>
            <label className="flex flex-col gap-1">
              <span className="card-meta">event time *</span>
              <input className="input num" type="datetime-local" value={mTime} onChange={(e) => setMTime(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="card-meta">type</span>
              <select className="input" value={mType} onChange={(e) => setMType(e.target.value)}>
                {EVENT_TYPES.map((t) => (<option key={t} value={t}>{t}</option>))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="card-meta">entity id</span>
              <input className="input" value={mEntity} onChange={(e) => setMEntity(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="card-meta">entity name</span>
              <input className="input" value={mEntityName} onChange={(e) => setMEntityName(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="card-meta">sector</span>
              <input className="input" value={mSector} onChange={(e) => setMSector(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="card-meta">direction</span>
              <select className="input" value={mDirection} onChange={(e) => setMDirection(e.target.value)}>
                {DIRECTIONS.map((d) => (<option key={d} value={d}>{d}</option>))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="card-meta">description</span>
              <input className="input" value={mDescription} onChange={(e) => setMDescription(e.target.value)} placeholder="optional" />
            </label>
            <button type="button" className="btn btn-primary" onClick={queueManual}>
              Review entry
            </button>
          </div>
        </div>
      </section>

      <ConfirmDialog
        open={pendingAck !== null}
        onOpenChange={(open) => { if (!open) setPendingAck(null); }}
        tone="primary"
        confirmLabel="Acknowledge alert"
        busy={busy}
        title="Acknowledge this alert as OPS_DESK?"
        description="The alert leaves the pending review queue."
        onConfirm={handleAck}
      />

      <ConfirmDialog
        open={pendingSync !== null}
        onOpenChange={(open) => { if (!open) setPendingSync(null); }}
        tone="primary"
        confirmLabel={pendingSync === 'rbi' ? 'Sync RBI now' : 'Sync corporate now'}
        busy={busy}
        title={pendingSync === 'rbi' ? 'Trigger RBI source sync?' : 'Trigger corporate source sync?'}
        description="Pulls official sources into the shared dev backend event engine."
        onConfirm={handleSync}
      />

      <ConfirmDialog
        open={pendingManual !== null}
        onOpenChange={(open) => { if (!open) setPendingManual(null); }}
        tone="primary"
        confirmLabel="Record manual event"
        busy={busy}
        title={`Record "${String(pendingManual?.title ?? '')}"?`}
        description="Creates a canonical event in the shared backend as MANUAL_OPS."
        intentRows={pendingManual ? [
          { label: 'Type', value: String(pendingManual.event_type ?? '') },
          { label: 'Entity', value: String(pendingManual.entity_name ?? '') },
          { label: 'Direction', value: String(pendingManual.expected_direction ?? '') },
        ] : undefined}
        onConfirm={handleManual}
      />
    </div>
  );
}
