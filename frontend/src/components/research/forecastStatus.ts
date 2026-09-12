/* 1H forecast v2.3 (P0) honesty helpers.
   Pure functions only (no JSX) so they run under vitest node env.
   All v2 response keys are optional — v1 payloads without new keys must
   still render, defaulting to RESEARCH status. */

export type ForecastV2Status = 'RESEARCH' | 'MVIG' | 'DEGRADED' | 'ABSTAIN';

export type ForecastV2Probabilities = {
  bullish?: number | null;
  neutral?: number | null;
  bearish?: number | null;
};

/** Minimal structural view of a forecast — v2 keys optional for v1 compat. */
export type ForecastV2Like = {
  status?: unknown;
  data_quality?: unknown;
  settleable?: unknown;
  settle_reason?: unknown;
  limitations?: unknown;
  snapshot_id?: unknown;
  prediction_id?: unknown;
  // P3-4 v2 prob UI (all optional; v1 payloads omit them).
  probabilities?: unknown;
  confidence?: unknown;
  calibrated?: unknown;
  calibrator_version?: unknown;
  calibration?: unknown;
  explain?: unknown;
  expected_range?: unknown;
};

const STATUSES: readonly ForecastV2Status[] = ['RESEARCH', 'MVIG', 'DEGRADED', 'ABSTAIN'];

/** Exact downgrade copy shown when a forecast is not settleable. */
export const UNSETTLEABLE_NOTE = 'Late-session — excluded from accuracy';

/** Verdict copy replacing the conviction line when the model abstains. */
export const ABSTAIN_VERDICT = 'ABSTAIN — INSUFFICIENT EVIDENCE';

/** Normalize any value to a v2 status. Unknown/missing → RESEARCH (pre-MVIG default). */
export function normalizeForecastStatus(v: unknown): ForecastV2Status {
  const s = typeof v === 'string' ? v.trim().toUpperCase() : '';
  return (STATUSES as readonly string[]).includes(s) ? (s as ForecastV2Status) : 'RESEARCH';
}

export function getForecastStatusLabel(f: ForecastV2Like | null | undefined): ForecastV2Status {
  return normalizeForecastStatus(f?.status);
}

export function isDegradedForecast(f: ForecastV2Like | null | undefined): boolean {
  return getForecastStatusLabel(f) === 'DEGRADED';
}

export function isAbstainForecast(f: ForecastV2Like | null | undefined): boolean {
  return getForecastStatusLabel(f) === 'ABSTAIN';
}

/** Upper-cased data-quality label (HEALTHY/DEGRADED/HEURISTIC/UNSETTLEABLE), or null when absent. */
export function getDataQualityLabel(f: ForecastV2Like | null | undefined): string | null {
  const v = f?.data_quality;
  if (typeof v !== 'string') return null;
  const s = v.trim().toUpperCase();
  return s ? s : null;
}

/** Settlement chip state: YES / NO / null (null = unknown, v1 payload — hide chip). */
export function getSettlementLabel(f: ForecastV2Like | null | undefined): 'YES' | 'NO' | null {
  if (f?.settleable === true) return 'YES';
  if (f?.settleable === false) return 'NO';
  return null;
}

/** Short display id: strips the `forecast_<horizon>_` prefix, truncates to 12 chars. */
export function shortForecastId(id: unknown): string | null {
  if (typeof id !== 'string') return null;
  const s = id.trim();
  if (!s) return null;
  return s.replace(/^forecast_[a-z0-9]+_/, '').slice(0, 12);
}

/** String array for limitations[] — drops non-string/blank entries. */
export function asStringList(v: unknown, max = 10): string[] {
  if (!Array.isArray(v)) return [];
  const out: string[] = [];
  for (const item of v) {
    if (typeof item !== 'string') continue;
    const s = item.trim();
    if (s) out.push(s);
    if (out.length >= max) break;
  }
  return out;
}

/* — P3-4 v2 probability UI helpers (pure; v1 payloads → null/UNCALIBRATED) — */

export type ProbBar = {
  key: 'bullish' | 'neutral' | 'bearish';
  label: 'BULL' | 'NEUT' | 'BEAR';
  prob: number;
  pct: number;
};

function asFinite01(v: unknown): number | null {
  if (typeof v !== 'number' || !Number.isFinite(v)) return null;
  if (v < 0 || v > 1) return null;
  return v;
}

/** Probability bars BULL/NEUT/BEAR — null when probabilities absent/invalid (v1 hidden). */
export function probabilityBars(f: ForecastV2Like | null | undefined): ProbBar[] | null {
  const p = (f as { probabilities?: unknown } | null | undefined)?.probabilities;
  if (p === null || p === undefined || typeof p !== 'object') return null;
  const rec = p as Record<string, unknown>;
  const bull = asFinite01(rec.bullish);
  const neut = asFinite01(rec.neutral);
  const bear = asFinite01(rec.bearish);
  if (bull === null || neut === null || bear === null) return null;
  if (Math.abs(bull + neut + bear - 1) > 0.01) return null;
  return [
    { key: 'bullish', label: 'BULL', prob: bull, pct: Math.round(bull * 100) },
    { key: 'neutral', label: 'NEUT', prob: neut, pct: Math.round(neut * 100) },
    { key: 'bearish', label: 'BEAR', prob: bear, pct: Math.round(bear * 100) },
  ];
}

/** Max(P) when probabilities valid, else the raw confidence field when finite, else null. */
export function maxProbability(f: ForecastV2Like | null | undefined): number | null {
  const bars = probabilityBars(f);
  if (bars) return Math.max(bars[0].prob, bars[1].prob, bars[2].prob);
  const c = (f as { confidence?: unknown } | null | undefined)?.confidence;
  if (typeof c === 'number' && Number.isFinite(c) && c >= 0 && c <= 1) return c;
  return null;
}

function readCalibrationNumbers(f: ForecastV2Like | null | undefined): { ece: number | null; n: number | null } {
  const candidates: unknown[] = [];
  try {
    const r = f as Record<string, unknown>;
    if (r && typeof r === 'object') {
      candidates.push(r.calibration);
      const ex = r.explain;
      if (ex && typeof ex === 'object') {
        const er = ex as Record<string, unknown>;
        candidates.push(er.calibration);
        candidates.push(er.calibration_metrics);
        candidates.push(er.calibrationMetrics);
      }
    }
  } catch {
    // ignore — fall through to nulls
  }
  for (const c of candidates) {
    if (c === null || c === undefined || typeof c !== 'object') continue;
    const rec = c as Record<string, unknown>;
    const eceRaw =
      rec.ece ?? rec.ECE ?? rec.ece_10 ?? rec.expected_calibration_error ?? rec.calibration_error;
    const nRaw = rec.n ?? rec.N ?? rec.fit_n ?? rec.sample_n ?? rec.count ?? rec.samples;
    let ece: number | null = null;
    let n: number | null = null;
    if (typeof eceRaw === 'number' && Number.isFinite(eceRaw) && eceRaw >= 0 && eceRaw <= 1) ece = eceRaw;
    if (typeof nRaw === 'number' && Number.isFinite(nRaw) && nRaw > 0) n = Math.round(nRaw);
    if (ece !== null || n !== null) return { ece, n };
  }
  return { ece: null, n: null };
}

/** True only when the backend marks the forecast calibrated. */
export function isCalibratedForecast(f: ForecastV2Like | null | undefined): boolean {
  return (f as { calibrated?: unknown } | null | undefined)?.calibrated === true;
}

/**
 * Calibration chip label: `LIVE ECE x.xx n=NNN` when calibrated with numbers,
 * `LIVE <calibrator_version>` when calibrated without numbers (unless none-v0),
 * plain `LIVE` when calibrated bare, else `UNCALIBRATED`.
 */
export function calibrationLabel(f: ForecastV2Like | null | undefined): string {
  if (!isCalibratedForecast(f)) return 'UNCALIBRATED';
  const { ece, n } = readCalibrationNumbers(f);
  if (ece !== null && n !== null) return `LIVE ECE ${ece.toFixed(2)} n=${n}`;
  if (ece !== null) return `LIVE ECE ${ece.toFixed(2)}`;
  const ver =
    typeof (f as { calibrator_version?: unknown } | null | undefined)?.calibrator_version === 'string'
      ? String((f as { calibrator_version?: unknown }).calibrator_version).trim()
      : '';
  if (ver && ver.toLowerCase() !== 'none-v0') return `LIVE ${ver}`;
  return 'LIVE';
}

export type ExpectedRange = { lower: number; mid: number; upper: number };

/** Neutral expected_range {lower, mid, upper} when present and finite, else null. */
export function getExpectedRange(f: ForecastV2Like | null | undefined): ExpectedRange | null {
  const r = (f as { expected_range?: unknown } | null | undefined)?.expected_range;
  if (r === null || r === undefined || typeof r !== 'object') return null;
  const rec = r as Record<string, unknown>;
  const lo = rec.lower;
  const mid = rec.mid;
  const hi = rec.upper;
  if (
    typeof lo === 'number' && Number.isFinite(lo) &&
    typeof mid === 'number' && Number.isFinite(mid) &&
    typeof hi === 'number' && Number.isFinite(hi)
  ) {
    return { lower: lo, mid, upper: hi };
  }
  return null;
}
