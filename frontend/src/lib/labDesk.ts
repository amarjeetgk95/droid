import { toNumber } from '@/lib/coerce';
import { getObj, pickNum, pickStr } from '@/lib/signalsNormalize';

export type LabTab = 'forecasts' | 'indicators' | 'experiments' | 'ml';

export const LAB_TABS: Array<{ id: LabTab; label: string }> = [
  { id: 'forecasts', label: 'Forecasts' },
  { id: 'indicators', label: 'Indicators' },
  { id: 'experiments', label: 'Experiments' },
  { id: 'ml', label: 'ML Models' },
];

export type LabTone = 'bull' | 'bear' | 'neut' | 'warn' | 'info';

export function directionToneOf(direction: unknown): LabTone {
  const d = String(direction ?? '').toUpperCase();
  if (d.includes('BULL') || d.includes('LONG') || d.includes('CALL')) return 'bull';
  if (d.includes('BEAR') || d.includes('SHORT') || d.includes('PUT')) return 'bear';
  return 'neut';
}

export function toneClass(tone: LabTone): string {
  if (tone === 'bull') return 'b-bull';
  if (tone === 'bear') return 'b-bear';
  if (tone === 'warn') return 'b-warn';
  if (tone === 'info') return 'b-info';
  return 'b-neut';
}

export function tagClass(tone: LabTone): string {
  if (tone === 'bull') return 'bull';
  if (tone === 'bear') return 'bear';
  if (tone === 'warn') return 'warn';
  if (tone === 'info') return 'info';
  return 'neut';
}

export type IndicatorSummary = {
  id: string;
  name: string;
  category: string | null;
  lifecycle: string | null;
  version: string | null;
  raw: Record<string, unknown>;
};

export function toIndicatorSummary(raw: unknown): IndicatorSummary | null {
  const o = getObj(raw);
  if (!o) return null;
  const id = pickStr(o, 'indicator_id', 'id');
  if (!id) return null;
  return {
    id,
    name: pickStr(o, 'name', 'display_name', 'title') ?? id,
    category: pickStr(o, 'category'),
    lifecycle: pickStr(o, 'lifecycle', 'status'),
    version: pickStr(o, 'indicator_version', 'version'),
    raw: o,
  };
}

export type PredictionSummary = {
  id: string;
  indicatorId: string | null;
  instrument: string;
  direction: string;
  score: number | null;
  confidence: number | null;
  horizon: string | null;
  timeMs: number | null;
  raw: Record<string, unknown>;
};

function pickTimeMs(o: Record<string, unknown>): number | null {
  for (const k of ['timestamp', 'created_at', 'created_at_ms', 'evaluated_at']) {
    const v = o[k];
    if (v === null || v === undefined || v === '') continue;
    if (typeof v === 'number' && Number.isFinite(v)) {
      return v < 1e12 ? Math.round(v * 1000) : Math.round(v);
    }
    const t = Date.parse(String(v));
    if (Number.isFinite(t)) return t;
  }
  return null;
}

export function toPredictionSummary(raw: unknown): PredictionSummary | null {
  const o = getObj(raw);
  if (!o) return null;
  const id = pickStr(o, 'prediction_id', 'id');
  if (!id) return null;
  return {
    id,
    indicatorId: pickStr(o, 'indicator_id'),
    instrument: pickStr(o, 'instrument', 'symbol', 'underlying') ?? '—',
    direction: pickStr(o, 'direction') ?? 'UNKNOWN',
    score: pickNum(o, 'score'),
    confidence: pickNum(o, 'confidence', 'confidence_pct'),
    horizon: pickStr(o, 'forecast_horizon', 'horizon', 'timeframe'),
    timeMs: pickTimeMs(o),
    raw: o,
  };
}

export type SnapshotSummary = {
  id: string;
  instrument: string;
  timeframe: string | null;
  price: number | null;
  regime: string | null;
  timeMs: number | null;
  raw: Record<string, unknown>;
};

export function toSnapshotSummary(raw: unknown): SnapshotSummary | null {
  const o = getObj(raw);
  if (!o) return null;
  const id = pickStr(o, 'snapshot_id', 'id');
  if (!id) return null;
  return {
    id,
    instrument: pickStr(o, 'instrument', 'symbol') ?? '—',
    timeframe: pickStr(o, 'timeframe'),
    price: pickNum(o, 'price', 'current_price', 'spot'),
    regime: pickStr(o, 'regime'),
    timeMs: pickTimeMs(o),
    raw: o,
  };
}

export type AnnotationSummary = {
  id: string;
  instrument: string;
  title: string;
  notes: string | null;
  timeMs: number | null;
  raw: Record<string, unknown>;
};

export function toAnnotationSummary(raw: unknown): AnnotationSummary | null {
  const o = getObj(raw);
  if (!o) return null;
  const id = pickStr(o, 'annotation_id', 'id');
  if (!id) return null;
  return {
    id,
    instrument: pickStr(o, 'instrument', 'symbol') ?? '—',
    title: pickStr(o, 'title') ?? id,
    notes: pickStr(o, 'notes', 'note', 'body'),
    timeMs: pickTimeMs(o),
    raw: o,
  };
}

/** Unwrap ML envelope {data, error, meta} or a bare payload. Null when absent. */
export function unwrapMlData(raw: unknown): Record<string, unknown> | null {
  const o = getObj(raw);
  if (!o) return null;
  const inner = getObj(o.data);
  if (inner) return inner;
  if (Array.isArray(o.data)) return { items: o.data };
  return o;
}

export type MlProbs = { bull: number | null; neut: number | null; bear: number | null };

/** Defensive read of ML directional probabilities across predictor shapes. */
export function mlProbs(data: Record<string, unknown> | null): MlProbs {
  if (!data) return { bull: null, neut: null, bear: null };
  const num = (v: unknown): number | null => toNumber(v, { rejectBlankString: true });
  return {
    bull:
      num(data.bullish_prob) ??
      num(data.p_bull) ??
      num(data.bullish_pct) ??
      num((getObj(data.probabilities) ?? {}).bullish),
    neut:
      num(data.neutral_prob) ??
      num(data.p_neutral) ??
      num(data.neutral_pct) ??
      num((getObj(data.probabilities) ?? {}).neutral),
    bear:
      num(data.bearish_prob) ??
      num(data.p_bear) ??
      num(data.bearish_pct) ??
      num((getObj(data.probabilities) ?? {}).bearish),
  };
}

/** Normalize 0..100 pct vs 0..1 fraction for display; null stays null. */
export function probToPct(v: number | null): number | null {
  if (v === null || !Number.isFinite(v)) return null;
  if (v > 1) return Math.max(0, Math.min(100, v));
  if (v < 0) return null;
  return Math.round(v * 100);
}

export function fmtLabTime(ms: number | null): string {
  if (ms === null) return '—';
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
}

export function fmtLabNum(v: unknown, digits = 2): string {
  const n = toNumber(v, { rejectBlankString: true });
  if (n === null) return '—';
  return n.toFixed(digits);
}

/** Count entries of a challenger/champion manifest map. */
export function countManifests(data: Record<string, unknown> | null, key: string): number {
  if (!data) return 0;
  const inner = getObj(data[key]);
  if (!inner) return 0;
  return Object.keys(inner).length;
}

/** Shadow-gate recommendation from the eval envelope. */
export function shadowDecision(data: Record<string, unknown> | null): { label: string; tone: LabTone } {
  const node = getObj(data?.shadow_decision) ?? data;
  const rec = node ? pickStr(node, 'recommendation', 'decision') : null;
  const upper = (rec ?? '').toUpperCase();
  if (upper.includes('PASS') || upper.includes('ALLOW') || upper.includes('GO')) {
    return { label: rec ?? 'PASS', tone: 'bull' };
  }
  if (upper.includes('VETO') || upper.includes('BLOCK') || upper.includes('REJECT')) {
    return { label: rec ?? 'VETO', tone: 'bear' };
  }
  return { label: rec ?? '—', tone: 'neut' };
}

/** Summarize a CommandView forecast section value for the lab header strip. */
export function summarizeForecastSection(value: unknown): { count: number; bull: number; bear: number } {
  const o = getObj(value);
  if (!o) return { count: 0, bull: 0, bear: 0 };
  const rows = Array.isArray(o.predictions) ? o.predictions : [];
  let bull = 0;
  let bear = 0;
  for (const row of rows) {
    const inner = getObj(row);
    if (!inner) continue;
    const tone = directionToneOf(inner.direction);
    if (tone === 'bull') bull += 1;
    else if (tone === 'bear') bear += 1;
  }
  return { count: rows.length, bull, bear };
}
