/* Ops Console pure helpers (no I/O, no React).
   Defensive parsing for operator surfaces: backend payloads vary across
   deploys, so every field is coerced to a safe shape and unknown states
   fall back to neutral tones instead of crashing. */

import { toNumber } from '@/lib/coerce';
import { getObj, pickNum, pickStr } from '@/lib/signalsNormalize';

export type OpsTone = 'bull' | 'bear' | 'info' | 'warn' | 'neut';

/** Badge class (b-*) for a tone; sg-tag class (bare word) for a tone. */
export function badgeClass(tone: OpsTone): string {
  return `b-${tone}`;
}

export function tagClass(tone: OpsTone): string {
  return tone;
}

/** Map a backend status/state token to a UI tone. Unknown -> neut. */
export function toneForStatus(value: unknown): OpsTone {
  const s = String(value ?? '').toUpperCase();
  if (/(^|_)OK$|^OK|HEALTHY|LIVE|CONNECTED|PRESENT|FRESH|CLOSED_CIRCUIT|^CLOSED$|SUCCESS|VALID/.test(s)) {
    // "CLOSED" is ambiguous: a *circuit breaker* CLOSED is healthy, but a
    // *market session* CLOSED is idle. Disambiguate below; default closed
    // (breaker state) is healthy.
    if (s === 'CLOSED' || s.includes('CIRCUIT')) return 'bull';
    return 'bull';
  }
  if (/UNHEALTHY|DOWN|ERROR|FAIL|TRIPPED|OPEN_CIRCUIT|^OPEN$|REJECT|INVALID|UNAVAILABLE|DISCONNECT/.test(s)) {
    return 'bear';
  }
  if (/DEGRADE|STALE|WARN|STALE|OFFLINE|MISSING|PLACEHOLDER|MODEL_ONLY|UNKNOWN/.test(s)) {
    return 'warn';
  }
  if (/READY|ARMED|TRIGGERED|ACTIVE|RUNNING|ENABLED|STARTED|TRUE/.test(s)) {
    return 'info';
  }
  if (/FALSE|NONE|IDLE|DISABLED|STOPPED|WEEKEND|HOLIDAY|POST_CLOSE|PRE_OPEN/.test(s)) {
    return 'neut';
  }
  return 'neut';
}

/** Session tokens are idle states, never errors: CLOSED market -> neut. */
export function toneForSession(value: unknown): OpsTone {
  const s = String(value ?? '').toUpperCase();
  if (s === 'OPEN' || s === 'LIVE') return 'bull';
  if (s === 'PRE_OPEN' || s === 'POST_CLOSE') return 'info';
  return 'neut';
}

/** Circuit-breaker state machine tone: CLOSED healthy, OPEN tripped, HALF_OPEN transitional. */
export function toneForBreaker(value: unknown): OpsTone {
  const s = String(value ?? '').toUpperCase();
  if (s === 'CLOSED') return 'bull';
  if (s === 'OPEN') return 'bear';
  if (s === 'HALF_OPEN' || s.includes('HALF')) return 'warn';
  return toneForStatus(value);
}

/** Render-safe scalar text. Objects/arrays collapse to a compact JSON stub. */
export function fmtCell(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return '—';
    return Number.isInteger(value) ? value.toLocaleString('en-IN') : String(Math.round(value * 1000) / 1000);
  }
  if (typeof value === 'string' || typeof value === 'boolean') return String(value);
  try {
    const raw = JSON.stringify(value);
    return raw.length > 80 ? `${raw.slice(0, 77)}…` : raw;
  } catch {
    return '—';
  }
}

/** Scalar-only entries of an object for kv rendering (skips nested objects). */
export function kvEntries(obj: Record<string, unknown> | null | undefined, limit = 12): Array<[string, string]> {
  if (!obj) return [];
  const out: Array<[string, string]> = [];
  for (const [key, value] of Object.entries(obj)) {
    if (value !== null && typeof value === 'object') continue;
    out.push([key.replace(/_/g, ' '), fmtCell(value)]);
    if (out.length >= limit) break;
  }
  return out;
}

export type CacheSummary = {
  backend: string | null;
  items: number | null;
  capacity: number | null;
  hitRatio: number | null;
  hits: number | null;
  misses: number | null;
  evictions: number | null;
};

export function summarizeCache(data: unknown): CacheSummary {
  const o = getObj(data) ?? {};
  return {
    backend: pickStr(o, 'backend', 'provider'),
    items: pickNum(o, 'items_count', 'items', 'size'),
    capacity: pickNum(o, 'max_capacity', 'capacity'),
    hitRatio: pickNum(o, 'hit_ratio_percent', 'hit_ratio', 'hit_rate'),
    hits: pickNum(o, 'hit_count', 'hits'),
    misses: pickNum(o, 'miss_count', 'misses'),
    evictions: pickNum(o, 'eviction_count', 'evictions'),
  };
}

export type BreakerSummary = {
  name: string | null;
  state: string | null;
  failures: number | null;
  threshold: number | null;
  totalCalls: number | null;
  tripped: number | null;
  changedAt: string | null;
};

export function summarizeBreaker(data: unknown): BreakerSummary {
  const o = getObj(data) ?? {};
  return {
    name: pickStr(o, 'name', 'breaker', 'id'),
    state: pickStr(o, 'state', 'status'),
    failures: pickNum(o, 'failure_count', 'failures'),
    threshold: pickNum(o, 'failure_threshold', 'threshold'),
    totalCalls: pickNum(o, 'total_calls', 'calls'),
    tripped: pickNum(o, 'tripped_count', 'trips'),
    changedAt: pickStr(o, 'last_state_change_at', 'last_changed_at', 'updated_at'),
  };
}

/** Feed circuit states from either the stream feed_health section or the
 *  REST /signals/feed-health payload (both use string state maps). */
export function circuitStates(value: unknown): Array<[string, string]> {
  const o = getObj(value);
  if (!o) return [];
  const feedCircuits = getObj(o.feed_circuits);
  const candidates: unknown[] = [feedCircuits?.states ?? feedCircuits, o.states];
  for (const candidate of candidates) {
    const rec = getObj(candidate);
    if (!rec) continue;
    const entries = Object.entries(rec).filter(([, v]) => typeof v === 'string');
    if (entries.length > 0) return entries as Array<[string, string]>;
  }
  return [];
}

export function countOpenCircuits(states: Array<[string, string]>): number {
  return states.filter(([, state]) => !/CLOSED|OK|HEALTHY|NORMAL|LIVE/i.test(state)).length;
}

/** Subsystem element map from /health/subsystems (`elements` object). */
export function subsystemEntries(data: unknown): Array<[string, string, OpsTone]> {
  const o = getObj(data) ?? {};
  const elements = getObj(o.elements) ?? {};
  return Object.entries(elements).map(([key, value]) => {
    const label = typeof value === 'boolean' ? (value ? 'on' : 'off') : fmtCell(value);
    const tone: OpsTone =
      typeof value === 'boolean'
        ? value
          ? 'bull'
          : 'neut'
        : toneForStatus(value);
    return [key.replace(/_/g, ' '), label, tone] as [string, string, OpsTone];
  });
}

/** Backend trigger types for the evaluate form (mirrors TriggerType enum). */
export const TRIGGER_TYPES = [
  'BREAKOUT',
  'BREAKDOWN',
  'REGIME_CHANGE',
  'P50_S_R_CROSS',
  'P50_VWAP_CROSS',
  'OI_SPIKE',
  'VOLUME_SPIKE',
  'OFI_SHIFT',
  'VOLATILITY_SHIFT',
  'NEWS_EVENT',
  'FORECAST_DISTRIBUTION_SHIFT',
  'MANUAL_ANALYSIS',
] as const;

/** Parse a numeric form field: empty -> null (absent), else finite number or null. */
export function parseNumField(raw: string): number | null {
  const t = raw.trim();
  if (!t) return null;
  return toNumber(t, { rejectBlankString: true });
}
