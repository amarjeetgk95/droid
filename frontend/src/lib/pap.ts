import type { PapAlignment, PapDataStatus, PapHorizon, PapLive, PapPrediction } from './api/pap';
import { toNumber } from './coerce';

export const PAP_HORIZONS = ['3m', '5m', '10m'] as const;
export const PAP_INSTRUMENTS = ['NIFTY', 'BANKNIFTY', 'SENSEX'] as const;
export const PAP_UNAVAILABLE_LABEL = 'PAP DATA UNAVAILABLE';

export type PapFreshness = 'LIVE' | 'DELAYED' | 'STALE' | 'OFFLINE';

/** Backend data_status -> UI freshness. Never upgrades STALE to LIVE. */
export function papFreshnessOf(status: unknown, ageS: unknown): PapFreshness {
  const s = String(status ?? '').toUpperCase();
  if (s === 'LIVE' || s === 'DELAYED' || s === 'STALE' || s === 'OFFLINE') return s;
  const age = toNumber(ageS, { rejectBlankString: true });
  if (age === null) return 'OFFLINE';
  if (age < 10) return 'LIVE';
  if (age <= 30) return 'DELAYED';
  return 'STALE';
}

export function freshnessBadgeClass(f: PapFreshness): string {
  if (f === 'LIVE') return 'b-bull';
  if (f === 'DELAYED') return 'b-warn';
  if (f === 'STALE') return 'b-bear';
  return 'b-neut';
}

/** Probability distribution rows for one horizon card, largest first. */
export function horizonDist(h: PapHorizon | null | undefined): Array<{ label: PapPrediction; pct: number }> {
  if (!h) return [];
  const rows = [
    { label: 'UP' as PapPrediction, pct: num(h.up) },
    { label: 'NEUTRAL' as PapPrediction, pct: num(h.neutral) },
    { label: 'DOWN' as PapPrediction, pct: num(h.down) },
  ];
  return rows.sort((a, b) => b.pct - a.pct);
}

function num(v: unknown): number {
  const n = toNumber(v, { rejectBlankString: true });
  return n === null || !Number.isFinite(n) ? 0 : Math.max(0, Math.min(100, n));
}

export function predictionTone(p: PapPrediction | string | null | undefined): 'bull' | 'bear' | 'neut' {
  const s = String(p ?? '').toUpperCase();
  if (s === 'UP' || s === 'BULLISH' || s === 'LONG') return 'bull';
  if (s === 'DOWN' || s === 'BEARISH' || s === 'SHORT') return 'bear';
  return 'neut';
}

export function predictionBadgeClass(p: PapPrediction | string | null | undefined): string {
  const t = predictionTone(p);
  return t === 'bull' ? 'b-bull' : t === 'bear' ? 'b-bear' : 'b-neut';
}

export function alignmentBadgeClass(a: PapAlignment | string | null | undefined): string {
  const s = String(a ?? '').toUpperCase();
  if (s === 'ALIGNED') return 'b-bull';
  if (s === 'CONFLICT') return 'b-bear';
  if (s === 'NEUTRAL') return 'b-neut';
  if (s === 'NO_DROID_SIGNAL') return 'b-info';
  return 'b-warn';
}

export function alignmentLabel(a: PapAlignment | string | null | undefined): string {
  const s = String(a ?? '').toUpperCase();
  if (s === 'ALIGNED') return 'ALIGNED';
  if (s === 'CONFLICT') return 'CONFLICT';
  if (s === 'NEUTRAL') return 'NEUTRAL';
  if (s === 'NO_DROID_SIGNAL') return 'NO DROID SIGNAL';
  return 'PAP UNAVAILABLE';
}

/** True when the live payload must render the unavailable state (no fake values). */
export function isPapUnavailable(live: PapLive | null | undefined): boolean {
  if (!live) return true;
  if (live.available === false) return true;
  return !live.horizons;
}

export function unavailableReason(live: PapLive | null | undefined, fallback: string): string {
  const r = live?.unavailable_reason;
  return typeof r === 'string' && r.trim() ? r : fallback;
}

/** Confidence display: null when the backend did not calibrate (no false precision). */
export function confidenceLabel(h: PapHorizon | null | undefined): string {
  if (!h) return '—';
  if (h.confidence === null || h.confidence === undefined) return '—';
  const n = toNumber(h.confidence, { rejectBlankString: true });
  return n === null ? '—' : `${n}%`;
}

export function fmtAge(ageS: number | null | undefined): string {
  const n = toNumber(ageS, { rejectBlankString: true });
  if (n === null) return 'age unknown';
  if (n < 60) return `${Math.round(n)}s`;
  return `${Math.floor(n / 60)}m ${Math.round(n % 60)}s`;
}

export function fmtClock(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false });
}

export function fmtPrice(v: number | null | undefined): string {
  const n = toNumber(v, { rejectBlankString: true });
  if (n === null) return '—';
  return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
}

export function dataStatusOf(live: PapLive | null): PapDataStatus {
  const s = String(live?.data_status ?? '').toUpperCase();
  return (['LIVE', 'DELAYED', 'STALE', 'OFFLINE'] as PapDataStatus[]).includes(s as PapDataStatus)
    ? (s as PapDataStatus)
    : 'OFFLINE';
}

/** Horizon filter label -> backend horizon_minutes. */
export function horizonToMinutes(h: string | null | undefined): number | undefined {
  const s = String(h ?? '').toLowerCase().replace(/\s/g, '');
  if (s === '3m' || s === '3') return 3;
  if (s === '5m' || s === '5') return 5;
  if (s === '10m' || s === '10') return 10;
  return undefined;
}

/** Session filter label passthrough (backend groups by IST window). */
export function isAll(v: string | null | undefined): boolean {
  return !v || String(v).toUpperCase() === 'ALL';
}
