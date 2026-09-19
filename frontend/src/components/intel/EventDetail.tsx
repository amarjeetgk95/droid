'use client';

/* Event detail: canonical record + scores + comparables + prediction +
   live opportunity + outcome. Every slice is optional — missing slices render
   an honest note, never fabricated values. */

import { getObj, pickNum, pickStr } from '@/lib/signalsNormalize';
import {
  eventIdOf,
  eventPhaseTone,
  fmtClockIST,
  fmtScore,
  healthTone,
} from '@/lib/intelDesk';
import type { EventDetailBundle } from '@/hooks/useIntelDesk';

function Kv({ label, value }: { label: string; value: string }) {
  return (
    <div className="sg-kv">
      <span className="l">{label}</span>
      <span className="v">{value}</span>
    </div>
  );
}

export function EventDetail({
  bundle,
  loading,
  onClose,
}: {
  bundle: EventDetailBundle | null;
  loading: boolean;
  onClose: () => void;
}) {
  if (loading) {
    return (
      <section className="panel" aria-label="Event detail">
        <p className="sg-note">Loading event detail…</p>
      </section>
    );
  }
  if (!bundle || !bundle.detail) {
    return (
      <section className="panel" aria-label="Event detail">
        <p className="sg-empty">
          {bundle ? 'Event detail unavailable (event may have been removed).' : 'Select an event to inspect it.'}
        </p>
        {bundle?.errors.map((err) => (
          <p className="sg-note" key={err}>{err}</p>
        ))}
        <div className="sg-actions">
          <button type="button" className="btn" onClick={onClose}>Close</button>
        </div>
      </section>
    );
  }

  const event = bundle.detail;
  const scores = bundle.scores ?? event.scores ?? null;
  const prediction = bundle.prediction ?? event.latest_prediction ?? null;
  const comparables = bundle.comparables ?? event.comparables ?? [];
  const live = bundle.liveOpp;
  const outcome = bundle.outcome;
  const phaseTone = eventPhaseTone(event.temporal_phase);
  const verifyTone = event.verification_status === 'VERIFIED' ? 'bull' as const : healthTone(event.verification_status);
  const dirTone = event.expected_direction === 'BULLISH' ? 'bull' as const : event.expected_direction === 'BEARISH' ? 'bear' as const : 'neut' as const;
  const decisionTone = scores
    ? scores.opportunity.final_decision === 'NO_TRADE' ? 'bear' as const : 'info' as const
    : 'neut' as const;

  return (
    <section className="card" aria-label={`Event ${eventIdOf(event)}`}>
      <div className="card-hd">
        <h2 className="card-title">{event.title}</h2>
        <span className={`badge b-${phaseTone}`}>
          {event.temporal_phase.replace(/_/g, ' ')}
        </span>
        <span className="card-meta num">{eventIdOf(event).slice(0, 8)}</span>
      </div>
      <div className="card-bd flex flex-col gap-2">
        <div className="pnl-strip">
          <span className="ps">
            <span className="ps-l">verification</span>
            <span className={`sg-tag ${verifyTone}`}>
              {event.verification_status}
            </span>
          </span>
          <span className="ps">
            <span className="ps-l">direction</span>
            <span className={`sg-tag ${dirTone}`}>
              {event.expected_direction}
            </span>
          </span>
          <span className="ps">
            <span className="ps-l">decision</span>
            <span className={`sg-tag ${decisionTone}`}>
              {scores?.final_decision.replace(/_/g, ' ') ?? '—'}
            </span>
          </span>
        </div>

        {event.description ? <p className="sg-note">{event.description}</p> : null}

        <div className="sg-kvlist">
          <Kv label="event time" value={fmtClockIST(event.event_timestamp)} />
          <Kv label="type" value={`${event.event_type}${event.sub_type ? ` · ${event.sub_type}` : ''}`} />
          <Kv label="entity" value={`${event.entity_name} (${event.entity_id})`} />
          <Kv label="sector" value={event.sector} />
          <Kv label="certainty" value={event.certainty} />
          <Kv label="horizon" value={event.time_horizon} />
          <Kv label="precision" value={event.timestamp_precision} />
          <Kv label="sources" value={String(event.sources.length)} />
          <Kv label="impacts" value={event.impact_mappings.map((m) => `${m.target_symbol}:${m.impact_strength}`).join(', ') || '—'} />
        </div>

        {scores ? (
          <div className="sg-kvlist">
            <Kv label="importance" value={fmtScore(scores.importance.final_score)} />
            <Kv label="market impact" value={scores.market_impact.status === 'SCORED' ? fmtScore(scores.market_impact.final_score) : scores.market_impact.status} />
            <Kv label="opportunity" value={scores.opportunity.status === 'SCORED' ? fmtScore(scores.opportunity.final_score) : scores.opportunity.status} />
            {scores.opportunity.failed_gates.length > 0 ? (
              <Kv label="failed gates" value={scores.opportunity.failed_gates.join(', ')} />
            ) : null}
            {scores.opportunity.reason ? <Kv label="gate reason" value={scores.opportunity.reason} /> : null}
          </div>
        ) : (
          <p className="sg-note">No score snapshot for this event yet.</p>
        )}

        {comparables.length > 0 ? (
          <div className="tbl-scroll">
            <table className="sg-table">
              <thead><tr><th colSpan={3}>Comparables ({comparables.length})</th></tr></thead>
              <tbody>
                {comparables.slice(0, 6).map((c) => (
                  <tr key={c.past_event_id}>
                    <td className="sg-rownote">{fmtClockIST(c.past_event_date)}</td>
                    <td className="num">{Math.round((c.similarity_score ?? 0) * 100)}%</td>
                    <td className="sg-rownote">{c.key_comparison_factor ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="sg-note">No historical comparables for this event.</p>
        )}

        {prediction ? (
          <div className="sg-kvlist">
            <Kv label="predicted" value={`${prediction.predicted_direction} · conf ${prediction.confidence}`} />
            <Kv label="decision" value={prediction.decision.replace(/_/g, ' ')} />
            <Kv label="cutoff" value={fmtClockIST(prediction.data_cutoff_timestamp)} />
            <Kv label="immutable" value={prediction.snapshot_immutable ? 'YES' : 'NO'} />
          </div>
        ) : (
          <p className="sg-note">No immutable prediction snapshot for this event.</p>
        )}

        {live ? (
          <div className="sg-kvlist">
            <Kv label="live underlying" value={live.underlying} />
            <Kv label="opportunity" value={fmtScore(live.opportunity_score.final_score)} />
            <Kv label="strategy" value={live.strategy_state} />
            <Kv label="mode" value={live.execution_mode} />
            <Kv label="spot" value={String(pickNum(getObj(live.live_options) ?? {}, 'spot_price') ?? '—')} />
            <Kv label="pcr OI" value={String(pickStr(getObj(live.live_options) ?? {}, 'pcr_oi') ?? pickNum(getObj(live.live_options) ?? {}, 'pcr_oi') ?? '—')} />
          </div>
        ) : (
          <p className="sg-note">No live opportunity evaluation for this event right now.</p>
        )}

        {outcome ? (
          <div className="sg-kvlist">
            <Kv label="predicted" value={outcome.predicted_direction} />
            <Kv label="actual" value={outcome.actual_direction} />
            <Kv label="correct" value={outcome.prediction_correct ? 'YES' : 'NO'} />
            <Kv label="initial move" value={`${outcome.initial_move_pct}%`} />
            <Kv label="max move" value={`${outcome.maximum_move_pct}%`} />
            <Kv label="settled" value={outcome.is_settled ? 'YES' : 'NO'} />
          </div>
        ) : (
          <p className="sg-note">Outcome not yet settled for this event.</p>
        )}

        {bundle.errors.length > 0 ? (
          <div className="flex flex-col gap-1">
            {bundle.errors.map((err) => (
              <p className="sg-note" key={err}>{err}</p>
            ))}
          </div>
        ) : null}

        <div className="sg-actions">
          <button type="button" className="btn" onClick={onClose}>Close</button>
        </div>
      </div>
    </section>
  );
}
