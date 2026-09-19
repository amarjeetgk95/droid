/* Pure Intel-desk helpers: defensive narrowing + tone mapping for the
   institutional + events panels. No I/O, no timers — safe for unit tests.
   Backend shapes mirror backend/app/api/institutional.py and events.py. */

import { toNumber } from '@/lib/coerce';
import { getObj, pickNum, pickStr, stateTone, type Tone } from '@/lib/signalsNormalize';
import type { CanonicalEvent } from '@/lib/event-types';

/* ---------------- institutional FSM (mirrors signal.py FSM_TRANSITIONS) ---------------- */

export const INST_FSM_TRANSITIONS: Record<string, string[]> = {
  SIGNAL_CREATED: ['AI_PENDING', 'VALIDATED', 'REJECTED', 'EXPIRED', 'INVALIDATED'],
  AI_PENDING: ['AI_CONFIRMED', 'AI_REJECTED', 'AI_UNCERTAIN', 'EXPIRED', 'INVALIDATED'],
  AI_CONFIRMED: ['VALIDATED', 'REJECTED', 'EXPIRED', 'INVALIDATED'],
  AI_REJECTED: ['REJECTED', 'EXPIRED'],
  AI_UNCERTAIN: ['VALIDATED', 'REJECTED', 'EXPIRED'],
  VALIDATED: ['RISK_PENDING', 'REJECTED', 'EXPIRED', 'INVALIDATED'],
  RISK_PENDING: ['RISK_APPROVED', 'RISK_REJECTED', 'EXPIRED', 'INVALIDATED'],
  RISK_REJECTED: ['REJECTED', 'FAILED'],
  RISK_APPROVED: ['EXECUTION_PENDING', 'EXPIRED', 'INVALIDATED', 'FAILED'],
  EXECUTION_PENDING: ['EXECUTED', 'FAILED', 'REJECTED', 'EXPIRED', 'INVALIDATED', 'CANCELLED'],
  EXECUTED: [],
  REJECTED: [],
  EXPIRED: [],
  INVALIDATED: [],
  CANCELLED: [],
  FAILED: [],
};

/** Legal transition targets for an FSM state; empty when terminal or unknown. */
export function allowedInstTargets(fromState: string | null | undefined): string[] {
  if (!fromState) return [];
  return INST_FSM_TRANSITIONS[fromState.toUpperCase()] ?? [];
}

/* ---------------- tones (sg-tag / badge class suffixes) ---------------- */

export function healthTone(status: string | null | undefined): Tone {
  const s = String(status ?? '').toUpperCase();
  if (s === 'LIVE' || s === 'HEALTHY' || s === 'VALID' || s === 'AVAILABLE' || s === 'NORMAL' || s === 'YES') return 'bull';
  if (/(STALE|DEGRADED|DISCONNECTED|MISSING|OFFLINE|OPEN|NO|FAIL|REJECT|INVALID|UNHEALTHY|BLACKOUT)/.test(s)) return 'bear';
  if (/(RECENT|CLOSED|UNKNOWN|PENDING|PARTIAL|APPROACHING|REACTION|SCHEDULED|WATCH)/.test(s)) return 'warn';
  if (/(CONFIRM|ACTIVE|TRIGGERED|ARMED|SYNC|READY)/.test(s)) return 'info';
  return 'neut';
}

export function badgeClass(tone: Tone): string {
  return tone === 'bull' ? 'b-bull' : tone === 'bear' ? 'b-bear' : tone === 'warn' ? 'b-warn' : tone === 'info' ? 'b-info' : 'b-neut';
}

export function signalTone(state: string): Tone {
  return stateTone(state);
}

export function eventPhaseTone(phase: string | null | undefined): Tone {
  const p = String(phase ?? '').toUpperCase();
  if (p === 'ACTIVE') return 'bear';
  if (p === 'APPROACHING') return 'warn';
  if (p === 'SCHEDULED') return 'info';
  if (p === 'POST_EVENT' || p === 'ARCHIVED') return 'neut';
  return 'neut';
}

export function alertSeverityTone(severity: string | null | undefined): Tone {
  const s = String(severity ?? '').toUpperCase();
  if (s === 'CRITICAL') return 'bear';
  if (s === 'HIGH') return 'warn';
  if (s === 'MEDIUM') return 'info';
  return 'neut';
}

/* ---------------- institutional summaries ---------------- */

export type MiSummary = {
  regime: string | null;
  trend: string | null;
  bullish: number | null;
  bearish: number | null;
  breakoutPressure: number | null;
  breakdownPressure: number | null;
  falseBreakoutRisk: number | null;
  spot: number | null;
  dataHealth: string | null;
  feedHealth: string | null;
  shortStatus: string | null;
  contStatus: string | null;
  breakoutStatus: string | null;
  breakoutDirection: string | null;
  breakoutConfidence: number | null;
};

function pickFeedHealth(feed: unknown): string | null {
  const o = getObj(feed);
  if (!o) return typeof feed === 'string' ? feed : null;
  return pickStr(o, 'health', 'status', 'feed_health');
}

export function summarizeMIDashboard(raw: unknown): MiSummary | null {
  const o = getObj(raw);
  if (!o) return null;
  const shortH = getObj(o.short_horizon);
  const cont = getObj(o.continuation);
  const brk = getObj(o.breakout);
  const priceAction = getObj(o.price_action);
  return {
    regime: pickStr(o, 'regime'),
    trend: priceAction ? pickStr(priceAction, 'trend') : null,
    bullish: pickNum(o, 'bullish_score'),
    bearish: pickNum(o, 'bearish_score'),
    breakoutPressure: pickNum(o, 'breakout_pressure'),
    breakdownPressure: pickNum(o, 'breakdown_pressure'),
    falseBreakoutRisk: pickNum(o, 'false_breakout_risk'),
    spot: pickNum(o, 'spot_price'),
    dataHealth: pickStr(o, 'data_health'),
    feedHealth: pickFeedHealth(o.feed_health ?? o.feed),
    shortStatus: shortH ? pickStr(shortH, 'status') : null,
    contStatus: cont ? pickStr(cont, 'status') : null,
    breakoutStatus: brk ? pickStr(brk, 'status', 'candidate') : null,
    breakoutDirection: brk ? pickStr(brk, 'direction') : null,
    breakoutConfidence: brk ? pickNum(brk, 'confidence') : null,
  };
}

export type HealthRow = { instrument: string; status: string; feed: string };

export function summarizeDataHealth(raw: unknown): { rows: HealthRow[]; overall: Record<string, string> } {
  const o = getObj(raw) ?? {};
  const health = getObj(o.data_health) ?? {};
  const rows: HealthRow[] = Object.entries(health).map(([instrument, entry]) => {
    const e = getObj(entry) ?? {};
    return {
      instrument,
      status: pickStr(e, 'status', 'data_health') ?? 'UNKNOWN',
      feed: pickStr(e, 'feed', 'feed_health') ?? 'UNKNOWN',
    };
  });
  const overallRaw = getObj(o.overall) ?? {};
  const overall: Record<string, string> = {};
  for (const [k, v] of Object.entries(overallRaw)) overall[k] = typeof v === 'string' ? v : '—';
  return { rows, overall };
}

export type FeedRow = { instrument: string; health: string; detail: string | null };

export function summarizeFeedHealth(raw: unknown): FeedRow[] {
  const o = getObj(raw) ?? {};
  const feeds = getObj(o.feeds) ?? {};
  return Object.entries(feeds).map(([instrument, entry]) => {
    const e = getObj(entry) ?? {};
    return {
      instrument,
      health: pickStr(e, 'health', 'status', 'state') ?? 'UNKNOWN',
      detail: pickStr(e, 'reason', 'anomaly', 'detail'),
    };
  });
}

export type InstSignalRow = {
  id: string;
  instrument: string;
  strategy: string;
  direction: string;
  fsmState: string;
  status: string | null;
  confidence: number | null;
  ttlMs: number | null;
  expired: boolean | null;
};

export function toInstSignalRow(raw: unknown): InstSignalRow | null {
  const o = getObj(raw);
  if (!o) return null;
  const id = pickStr(o, 'signal_id', 'id');
  if (!id) return null;
  return {
    id,
    instrument: pickStr(o, 'instrument_id', 'instrument', 'underlying') ?? '—',
    strategy: pickStr(o, 'strategy') ?? '—',
    direction: pickStr(o, 'direction') ?? 'NEUTRAL',
    fsmState: pickStr(o, 'fsm_state', 'state', 'status') ?? '—',
    status: pickStr(o, 'status', 'validation_status'),
    confidence: pickNum(o, 'confidence'),
    ttlMs: pickNum(o, 'ttl_remaining_ms', 'ttl_ms'),
    expired: typeof o.is_expired === 'boolean' ? o.is_expired : null,
  };
}

export type AuditRow = {
  id: string;
  kind: string;
  summary: string;
  timeMs: number | null;
};

export function toAuditRows(records: unknown): AuditRow[] {
  if (!Array.isArray(records)) return [];
  const rows: AuditRow[] = [];
  for (const raw of records) {
    const o = getObj(raw);
    if (!o) continue;
    const id = pickStr(o, 'signal_id', 'id', 'audit_id', 'event_id') ?? '—';
    const kind = pickStr(o, 'event', 'action', 'kind', 'type') ?? 'record';
    const summary =
      pickStr(o, 'reason', 'detail', 'summary', 'message', 'to_state', 'fsm_state') ?? '—';
    let timeMs: number | null = null;
    const ts = o.timestamp ?? o.created_at ?? o.at_ms ?? o.at;
    if (typeof ts === 'number' && Number.isFinite(ts)) {
      timeMs = ts < 1e12 ? Math.round(ts * 1000) : Math.round(ts);
    } else if (typeof ts === 'string' && ts) {
      const t = new Date(ts).getTime();
      timeMs = Number.isNaN(t) ? null : t;
    }
    rows.push({ id, kind, summary, timeMs });
  }
  return rows;
}

/* ---------------- events ---------------- */

/** Honest risk flags for an event list row — derived only, never fabricated. */
export function eventRiskFlags(event: CanonicalEvent): string[] {
  const flags: string[] = [];
  if (event.temporal_phase === 'ACTIVE') flags.push('LIVE NOW');
  else if (event.temporal_phase === 'APPROACHING') flags.push('APPROACHING');
  if (event.verification_status === 'UNVERIFIED') flags.push('UNVERIFIED');
  else if (event.verification_status === 'CONFLICTING') flags.push('CONFLICTING SOURCES');
  if (event.certainty === 'RUMORED') flags.push('RUMOR');
  else if (event.certainty === 'APPROXIMATE') flags.push('TIME APPROX');
  if (event.expected_direction === 'TWO_SIDED') flags.push('TWO-SIDED');
  if (!event.processing_flags.scored) flags.push('UNSCORED');
  if (event.scores?.opportunity.final_decision === 'NO_TRADE') flags.push('NO-TRADE');
  return flags;
}

export function eventIdOf(event: CanonicalEvent): string {
  return event.canonical_event_id || event.id;
}

export function fmtClockIST(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  const d = typeof value === 'number' ? new Date(value) : new Date(String(value));
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export function fmtScore(value: unknown): string {
  const n = toNumber(value, { rejectBlankString: true });
  if (n === null) return '—';
  return n > 1 ? n.toFixed(1) : `${Math.round(n * 100)}`;
}

export function fmtTtlMs(ms: number | null | undefined, now: number): string {
  if (ms === null || ms === undefined) return '—';
  const s = Math.round((ms - now) / 1000);
  if (s <= 0) return 'expired';
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

/** Split an evidence array into readable "signal — detail" lines. */
export function evidenceLines(raw: unknown, max = 6): string[] {
  if (!Array.isArray(raw)) return [];
  const lines: string[] = [];
  for (const entry of raw.slice(0, max)) {
    const o = getObj(entry);
    if (!o) continue;
    const signal = pickStr(o, 'signal', 'dimension');
    const detail = pickStr(o, 'detail');
    if (signal && detail) lines.push(`${signal} — ${detail}`);
    else if (signal ?? detail) lines.push(signal ?? detail ?? '');
  }
  return lines.filter(Boolean);
}
