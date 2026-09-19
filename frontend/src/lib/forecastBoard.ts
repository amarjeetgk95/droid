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
  if (!range || !Number.isFinite(range.mid) || range.mid === 0) return null;
  return ((range.upper - range.lower) / range.mid) * 100;
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
