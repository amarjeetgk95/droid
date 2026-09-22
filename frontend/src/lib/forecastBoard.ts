import type { HourForecast } from '@/lib/types';
import {
  getExpectedRange,
  getForecastStatusLabel,
  maxProbability,
  type ForecastV2Status,
} from '@/lib/forecastStatus';

export const FORECAST_HORIZONS = ['1m', '5m', '15m', '30m', '1h'] as const;

export type ForecastHorizonId = (typeof FORECAST_HORIZONS)[number];

export const HORIZON_LABELS: Record<ForecastHorizonId, string> = {
  '1m': '1m',
  '5m': '5m',
  '15m': '15m',
  '30m': '30m',
  '1h': '60m',
};

export const HORIZON_MINUTES: Record<ForecastHorizonId, number> = {
  '1m': 1,
  '5m': 5,
  '15m': 15,
  '30m': 30,
  '1h': 60,
};

export type ForecastTone = 'bull' | 'bear' | 'neut';

export function forecastInstrument(instrument: string): string {
  const v = (instrument ?? '').trim().toUpperCase();
  if (v === 'NIFTY' || v === 'NIFTY50' || v === 'NIFTY 50') return 'NIFTY 50';
  return v;
}

export type ForecastDirection = 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'UNKNOWN';

export function directionOf(f: HourForecast | null | undefined): ForecastDirection {
  const d = typeof f?.direction === 'string' ? f.direction.toUpperCase() : '';
  if (d === 'BULLISH') return 'BULLISH';
  if (d === 'BEARISH') return 'BEARISH';
  if (d === 'NEUTRAL') return 'NEUTRAL';
  return 'UNKNOWN';
}

export function directionTone(d: ForecastDirection): ForecastTone {
  if (d === 'BULLISH') return 'bull';
  if (d === 'BEARISH') return 'bear';
  return 'neut';
}

export function forecastTone(f: HourForecast | null | undefined): ForecastTone {
  if (getForecastStatusLabel(f) === 'ABSTAIN') return 'neut';
  return directionTone(directionOf(f));
}

export function directionLabel(f: HourForecast | null | undefined): string {
  if (!f) return 'NO DATA';
  if (getForecastStatusLabel(f) === 'ABSTAIN') return 'ABSTAIN';
  const d = directionOf(f);
  return d === 'UNKNOWN' ? 'NO DATA' : d;
}

export function statusClass(status: ForecastV2Status): string {
  if (status === 'DEGRADED') return 'b-warn';
  if (status === 'ABSTAIN') return 'b-neut';
  if (status === 'MVIG') return 'b-info';
  return 'b-neut';
}

export function confidencePct(f: HourForecast | null | undefined): number | null {
  const p = maxProbability(f);
  if (p !== null) return Math.round(p * 100);
  const s = f?.score;
  if (typeof s === 'number' && Number.isFinite(s)) {
    return Math.round(Math.max(0, Math.min(100, s)));
  }
  return null;
}

export type ConfidenceSource = 'probabilities' | 'score-fallback' | 'none';

/** Where confidence came from. Score fallback must be labeled in the UI. */
export function confidenceSource(f: HourForecast | null | undefined): ConfidenceSource {
  if (maxProbability(f) !== null) return 'probabilities';
  const s = f?.score;
  if (typeof s === 'number' && Number.isFinite(s)) return 'score-fallback';
  return 'none';
}

/** Fallback badge text, or null when confidence is direct / absent. */
export function confidenceFallbackLabel(f: HourForecast | null | undefined): string | null {
  return confidenceSource(f) === 'score-fallback' ? 'fallback from score' : null;
}

export type LayerRow = { key: string; label: string; pct: number; tone: ForecastTone };

const LAYER_DEFS: Array<[keyof NonNullable<HourForecast['layer_scores']>, string]> = [
  ['mtf_alignment', 'MTF'],
  ['indicators', 'IND'],
  ['ml', 'ML'],
  ['options', 'OPT'],
  ['structure', 'STR'],
];

function normalizeLayerValue(v: unknown): number | null {
  if (typeof v !== 'number' || !Number.isFinite(v)) return null;
  const norm = Math.abs(v) <= 1 ? v : v / 100;
  return Math.max(-1, Math.min(1, norm));
}

export function layerRows(f: HourForecast | null | undefined): LayerRow[] {
  const layers = f?.layer_scores;
  if (!layers || typeof layers !== 'object') return [];
  const rows: LayerRow[] = [];
  for (const [key, label] of LAYER_DEFS) {
    const norm = normalizeLayerValue(layers[key]);
    if (norm === null) continue;
    rows.push({
      key,
      label,
      pct: Math.round(Math.abs(norm) * 100),
      tone: norm > 0.05 ? 'bull' : norm < -0.05 ? 'bear' : 'neut',
    });
  }
  return rows;
}

export function expectedMovePct(f: HourForecast | null | undefined): number | null {
  const range = getExpectedRange(f);
  if (range && Number.isFinite(range.mid) && range.mid !== 0) {
    return ((range.upper - range.lower) / range.mid) * 100;
  }
  // Directional verdicts carry prices instead of a range (backend contract):
  // derive the move magnitude from the target distance so the stat is never
  // spuriously empty. Absolute value — direction is shown separately.
  // FALLBACK: label "fallback from target" in the UI, never a live range.
  const spot = f?.current_price;
  const target = f?.target_price;
  if (
    typeof spot === 'number' && Number.isFinite(spot) && spot > 0 &&
    typeof target === 'number' && Number.isFinite(target)
  ) {
    return (Math.abs(target - spot) / spot) * 100;
  }
  return null;
}

export type ExpectedMoveSource = 'range' | 'target-fallback' | 'none';

/** Where the expected-move came from. Target fallback must be labeled in the UI. */
export function expectedMoveSource(f: HourForecast | null | undefined): ExpectedMoveSource {
  const range = getExpectedRange(f);
  if (range && Number.isFinite(range.mid) && range.mid !== 0) return 'range';
  const spot = f?.current_price;
  const target = f?.target_price;
  if (
    typeof spot === 'number' && Number.isFinite(spot) && spot > 0 &&
    typeof target === 'number' && Number.isFinite(target)
  ) {
    return 'target-fallback';
  }
  return 'none';
}

/** Fallback badge text, or null when the move is a direct range / absent. */
export function expectedMoveFallbackLabel(f: HourForecast | null | undefined): string | null {
  return expectedMoveSource(f) === 'target-fallback' ? 'fallback from target' : null;
}

export type ExpectedMoveInfo = {
  /** True ONLY when a real expected_range exists — target distance is not a range. */
  available: boolean;
  /** Move magnitude in %, or null when no expected_range was supplied. */
  pct: number | null;
  /** Honest source of the move figure. */
  source: 'range' | 'none';
  /** Legacy/diagnostic source: distinguishes a target fallback from no data. */
  legacySource: ExpectedMoveSource;
  /** True when a target-derived fallback exists but is deliberately not shown. */
  fallbackAvailable: boolean;
  label: string;
};

/** Honest expected-move accessor: never invents magnitude from target distance. */
export function expectedMove(f: HourForecast | null | undefined): ExpectedMoveInfo {
  const range = getExpectedRange(f);
  if (range && Number.isFinite(range.mid) && range.mid !== 0) {
    return {
      available: true,
      pct: ((range.upper - range.lower) / range.mid) * 100,
      source: 'range',
      legacySource: 'range',
      fallbackAvailable: false,
      label: 'expected range',
    };
  }
  const legacySource = expectedMoveSource(f);
  const fallbackAvailable = legacySource === 'target-fallback';
  return {
    available: false,
    pct: null,
    source: 'none',
    legacySource,
    fallbackAvailable,
    label: fallbackAvailable
      ? 'no expected range — target fallback withheld'
      : 'no expected range',
  };
}

/** True only when the backend supplied an actual expected_range. */
export function expectedMoveAvailable(f: HourForecast | null | undefined): boolean {
  return expectedMove(f).available;
}

export type ConfidenceInfo = {
  /** True ONLY for probability-domain confidence — score is never confidence. */
  available: boolean;
  /** Probability-domain confidence %, or null when only a score exists. */
  pct: number | null;
  /** Score-domain value (0..100), kept separate from confidence. */
  scorePct: number | null;
  source: 'probability' | 'score' | 'none';
  label: string;
};

function scorePctOf(f: HourForecast | null | undefined): number | null {
  const s = f?.score;
  if (typeof s !== 'number' || !Number.isFinite(s)) return null;
  return Math.round(Math.max(0, Math.min(100, s)));
}

/** Honest confidence accessor: probabilities/confidence field only; score is flagged. */
export function confidence(f: HourForecast | null | undefined): ConfidenceInfo {
  const p = maxProbability(f);
  if (p !== null) {
    return {
      available: true,
      pct: Math.round(p * 100),
      scorePct: scorePctOf(f),
      source: 'probability',
      label: 'probability',
    };
  }
  const scorePct = scorePctOf(f);
  if (scorePct !== null) {
    return {
      available: false,
      pct: null,
      scorePct,
      source: 'score',
      label: 'score (not confidence)',
    };
  }
  return { available: false, pct: null, scorePct: null, source: 'none', label: 'no confidence data' };
}

/** True only when confidence came from the probability domain. */
export function confidenceAvailable(f: HourForecast | null | undefined): boolean {
  return confidence(f).available;
}

export type Consensus = {
  bull: number;
  bear: number;
  neut: number;
  missing: number;
  weightedScore: number;
  label: string;
  tone: ForecastTone;
};

function horizonWeight(h: ForecastHorizonId): number {
  return Math.sqrt(HORIZON_MINUTES[h]);
}

export function consensusOf(
  forecasts: Partial<Record<ForecastHorizonId, HourForecast | null | undefined>>,
): Consensus {
  let bull = 0;
  let bear = 0;
  let neut = 0;
  let missing = 0;
  let directional = 0;
  let weightSum = 0;

  for (const h of FORECAST_HORIZONS) {
    const f = forecasts[h];
    if (!f) {
      missing += 1;
      continue;
    }
    const status = getForecastStatusLabel(f);
    const dir = directionOf(f);
    if (status === 'ABSTAIN' || dir === 'UNKNOWN' || dir === 'NEUTRAL') {
      neut += 1;
      continue;
    }
    const weight = horizonWeight(h);
    weightSum += weight;
    if (dir === 'BULLISH') {
      bull += 1;
      directional += weight;
    } else {
      bear += 1;
      directional -= weight;
    }
  }

  const weightedScore = weightSum > 0 ? Math.round((directional / weightSum) * 100) : 0;
  const present = bull + bear + neut;
  let label = 'NO DATA';
  let tone: ForecastTone = 'neut';
  if (present > 0) {
    if (weightedScore >= 20) {
      label = 'BULLISH';
      tone = 'bull';
    } else if (weightedScore <= -20) {
      label = 'BEARISH';
      tone = 'bear';
    } else {
      label = 'NEUTRAL';
      tone = 'neut';
    }
  }
  return { bull, bear, neut, missing, weightedScore, label, tone };
}
