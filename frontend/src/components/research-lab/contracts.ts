import { errorMessage as canonicalErrorMessage } from '@/lib/errors';

export interface IndicatorDefinitionRow {
  indicator_id: string;
  name: string;
  category?: string | null;
  lifecycle?: string | null;
  current_version?: string | null;
  description?: string | null;
}

export interface IndicatorOutputRow {
  indicator_id: string;
  version: string;
  timestamp: string;
  instrument: string;
  timeframe: string;
  direction: string;
  score: number | null;
  confidence: number | null;
  raw_value: unknown;
  normalized_value: number | null;
  component_values: Record<string, unknown> | null;
  horizon: string | null;
  horizon_candles: number | null;
  target_price: number | null;
  invalidation_price: number | null;
  data_quality: string | null;
}

export interface ExperimentRunRow {
  run_id: string | null;
  experiment_id: string | null;
  status: string;
  sample_count: number | null;
  metrics: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface ValidationReportRow {
  sample_size: number | null;
  accuracy: number | null;
  precision: number | null;
  recall: number | null;
  f1_score: number | null;
  mfe_mean: number | null;
  mae_mean: number | null;
  win_loss_ratio: number | null;
  baseline_accuracy: number | null;
  excess_accuracy: number | null;
  confidence_interval_95: [number | null, number | null] | null;
  p_value: number | null;
  is_statistically_significant: boolean | null;
  regime_breakdown: Record<string, Record<string, number>> | null;
  session_breakdown: Record<string, Record<string, number>> | null;
}

export interface ExperimentResultRow {
  run: ExperimentRunRow;
  report: ValidationReportRow;
}

export interface ResearchPredictionRow {
  prediction_id: string;
  indicator_id: string | null;
  indicator_version: string | null;
  instrument: string | null;
  timeframe: string | null;
  timestamp: string | null;
  current_price: number | null;
  direction: string;
  score: number | null;
  confidence: number | null;
  component_values: Record<string, unknown> | null;
  forecast_horizon: string | null;
  horizon_candles: number | null;
  target_price: number | null;
  invalidation_price: number | null;
}

export interface PredictionOutcomeRow {
  outcome_id: string | null;
  prediction_id: string;
  actual_direction: string;
  actual_price_move: number | null;
  actual_pct_move: number | null;
  entry_price: number | null;
  exit_price: number | null;
  mfe: number | null;
  mae: number | null;
  target_hit: boolean | null;
  stop_hit: boolean | null;
  is_correct: boolean | null;
  evaluated_at: string | null;
}

export interface CalibrationCellRow {
  symbol: string | null;
  horizon_minutes: number | null;
  predicted_bias: string;
  n: number;
  hits: number | null;
  hit_rate: number | null;
  avg_confidence: number | null;
}

export interface CalibrationSummaryRow {
  target_spec_version: string | null;
  cells: CalibrationCellRow[];
  overall: { n: number; hits: number | null; hit_rate: number | null } | null;
  excluded_other_spec_versions: number | null;
}

export interface SettlementSummaryRow {
  settled: number | null;
  skipped: Record<string, number> | null;
  errors: number | null;
}

export interface PayoffPoint {
  spot: number;
  pnl: number;
}

export interface StrategyLegRow {
  option_type: string;
  side: string;
  strike: number;
  quantity: number;
  price: number;
  lot_size: number | null;
}

export interface StrategyTemplateRow {
  template_id: string;
  name: string;
  category: string | null;
  description: string | null;
  legs_count: number | null;
}

export interface TemplateStrategyRow {
  underlying: string | null;
  spot_price: number | null;
  legs: StrategyLegRow[];
  points: PayoffPoint[];
  max_profit: number | 'unlimited' | null;
  max_loss: number | 'unlimited' | null;
  risk_reward: number | null;
  premium_note: string | null;
}

export interface PayoffResultRow {
  underlying: string | null;
  spot_price: number | null;
  points: PayoffPoint[];
  legs_count: number | null;
}

export interface PayoffStats {
  maxProfit: number;
  maxLoss: number;
  breakevens: number[];
  spotMin: number;
  spotMax: number;
  count: number;
}

export interface PayoffSegment {
  sign: 1 | -1;
  points: PayoffPoint[];
}

export type ModelManifestMap = Record<string, Record<string, unknown>>;

export function asRecord(value: unknown): Record<string, unknown> | null {
  if (value === null || value === undefined || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

export function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

export function asString(value: unknown): string | null {
  if (typeof value === 'string') {
    const s = value.trim();
    return s ? s : null;
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return null;
}

export function asBoolean(value: unknown): boolean | null {
  if (typeof value === 'boolean') return value;
  return null;
}

export function clampInt(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, Math.trunc(value)));
}

/** Research-lab wrapper over the canonical helper; fallback text unchanged. */
export function errorMessage(err: unknown): string {
  return canonicalErrorMessage(err, 'Request failed');
}

export function isAbortError(err: unknown): boolean {
  if (err instanceof DOMException && err.name === 'AbortError') return true;
  if (err instanceof Error && err.name === 'AbortError') return true;
  return false;
}

export function formatFeatureValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return '—';
    return Number.isInteger(value) ? value.toLocaleString('en-IN') : value.toFixed(2);
  }
  if (typeof value === 'boolean') return value ? 'TRUE' : 'FALSE';
  if (Array.isArray(value)) {
    const scalar = value.every(
      (v) => v === null || v === undefined || ['string', 'number', 'boolean'].includes(typeof v),
    );
    if (scalar) return value.map((v) => (v === null || v === undefined ? '—' : String(v))).join(', ');
    return JSON.stringify(value);
  }
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function flattenRecord(
  record: Record<string, unknown> | null | undefined,
  prefix = '',
  depth = 0,
): Array<{ key: string; value: unknown }> {
  if (!record) return [];
  const out: Array<{ key: string; value: unknown }> = [];
  for (const [k, v] of Object.entries(record)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v) && depth < 2) {
      out.push(...flattenRecord(v as Record<string, unknown>, key, depth + 1));
    } else {
      out.push({ key, value: v });
    }
  }
  return out;
}

export function parseIndicatorOutput(payload: unknown): IndicatorOutputRow | null {
  const rec = asRecord(payload);
  if (!rec) return null;
  const indicatorId = asString(rec.indicator_id);
  if (!indicatorId) return null;
  return {
    indicator_id: indicatorId,
    version: asString(rec.version) ?? '—',
    timestamp: asString(rec.timestamp) ?? '',
    instrument: asString(rec.instrument) ?? '',
    timeframe: asString(rec.timeframe) ?? '',
    direction: (asString(rec.direction) ?? 'UNKNOWN').toUpperCase(),
    score: asNumber(rec.score),
    confidence: asNumber(rec.confidence),
    raw_value: rec.raw_value,
    normalized_value: asNumber(rec.normalized_value),
    component_values: asRecord(rec.component_values),
    horizon: asString(rec.horizon ?? rec.forecast_horizon),
    horizon_candles: asNumber(rec.horizon_candles),
    target_price: asNumber(rec.target_price),
    invalidation_price: asNumber(rec.invalidation_price),
    data_quality: asString(rec.data_quality),
  };
}

export function parseExperimentResult(payload: unknown): ExperimentResultRow | null {
  const rec = asRecord(payload);
  if (!rec) return null;
  const runRec = asRecord(rec.run);
  const reportRec = asRecord(rec.report);
  if (!runRec || !reportRec) return null;
  const ci = Array.isArray(reportRec.confidence_interval_95)
    ? (reportRec.confidence_interval_95 as unknown[])
    : null;
  return {
    run: {
      run_id: asString(runRec.run_id),
      experiment_id: asString(runRec.experiment_id),
      status: (asString(runRec.status) ?? 'UNKNOWN').toUpperCase(),
      sample_count: asNumber(runRec.sample_count),
      metrics: asRecord(runRec.metrics),
      error_message: asString(runRec.error_message),
      started_at: asString(runRec.started_at),
      completed_at: asString(runRec.completed_at),
    },
    report: {
      sample_size: asNumber(reportRec.sample_size),
      accuracy: asNumber(reportRec.accuracy),
      precision: asNumber(reportRec.precision),
      recall: asNumber(reportRec.recall),
      f1_score: asNumber(reportRec.f1_score),
      mfe_mean: asNumber(reportRec.mfe_mean),
      mae_mean: asNumber(reportRec.mae_mean),
      win_loss_ratio: asNumber(reportRec.win_loss_ratio),
      baseline_accuracy: asNumber(reportRec.baseline_accuracy),
      excess_accuracy: asNumber(reportRec.excess_accuracy),
      confidence_interval_95: ci ? [asNumber(ci[0]), asNumber(ci[1])] : null,
      p_value: asNumber(reportRec.p_value),
      is_statistically_significant: asBoolean(reportRec.is_statistically_significant),
      regime_breakdown: asRecord(reportRec.regime_breakdown) as Record<
        string,
        Record<string, number>
      > | null,
      session_breakdown: asRecord(reportRec.session_breakdown) as Record<
        string,
        Record<string, number>
      > | null,
    },
  };
}

export function parsePrediction(payload: unknown): ResearchPredictionRow | null {
  const rec = asRecord(payload);
  if (!rec) return null;
  const predictionId = asString(rec.prediction_id);
  if (!predictionId) return null;
  return {
    prediction_id: predictionId,
    indicator_id: asString(rec.indicator_id),
    indicator_version: asString(rec.indicator_version),
    instrument: asString(rec.instrument),
    timeframe: asString(rec.timeframe),
    timestamp: asString(rec.timestamp),
    current_price: asNumber(rec.current_price),
    direction: (asString(rec.direction) ?? 'UNKNOWN').toUpperCase(),
    score: asNumber(rec.score),
    confidence: asNumber(rec.confidence),
    component_values: asRecord(rec.component_values),
    forecast_horizon: asString(rec.forecast_horizon),
    horizon_candles: asNumber(rec.horizon_candles),
    target_price: asNumber(rec.target_price),
    invalidation_price: asNumber(rec.invalidation_price),
  };
}

export function parsePredictions(payload: unknown): ResearchPredictionRow[] | null {
  if (!Array.isArray(payload)) return null;
  return payload
    .map(parsePrediction)
    .filter((row): row is ResearchPredictionRow => row !== null);
}

export function parseOutcome(payload: unknown): PredictionOutcomeRow | null {
  const rec = asRecord(payload);
  if (!rec) return null;
  const predictionId = asString(rec.prediction_id);
  if (!predictionId) return null;
  return {
    outcome_id: asString(rec.outcome_id),
    prediction_id: predictionId,
    actual_direction: (asString(rec.actual_direction) ?? 'UNKNOWN').toUpperCase(),
    actual_price_move: asNumber(rec.actual_price_move),
    actual_pct_move: asNumber(rec.actual_pct_move),
    entry_price: asNumber(rec.entry_price),
    exit_price: asNumber(rec.exit_price),
    mfe: asNumber(rec.mfe),
    mae: asNumber(rec.mae),
    target_hit: asBoolean(rec.target_hit),
    stop_hit: asBoolean(rec.stop_hit),
    is_correct: asBoolean(rec.is_correct),
    evaluated_at: asString(rec.evaluated_at),
  };
}

export function parseCalibration(payload: unknown): CalibrationSummaryRow | null {
  const rec = asRecord(payload);
  if (!rec) return null;
  const rawCells = Array.isArray(rec.cells) ? rec.cells : [];
  const cells: CalibrationCellRow[] = [];
  for (const raw of rawCells) {
    const cell = asRecord(raw);
    if (!cell) continue;
    const bias = asString(cell.predicted_bias);
    if (!bias) continue;
    cells.push({
      symbol: asString(cell.symbol),
      horizon_minutes: asNumber(cell.horizon_minutes),
      predicted_bias: bias.toUpperCase(),
      n: asNumber(cell.n) ?? 0,
      hits: asNumber(cell.hits),
      hit_rate: asNumber(cell.hit_rate),
      avg_confidence: asNumber(cell.avg_confidence),
    });
  }
  const overallRec = asRecord(rec.overall);
  return {
    target_spec_version: asString(rec.target_spec_version),
    cells,
    overall: overallRec
      ? {
          n: asNumber(overallRec.n) ?? 0,
          hits: asNumber(overallRec.hits),
          hit_rate: asNumber(overallRec.hit_rate),
        }
      : null,
    excluded_other_spec_versions: asNumber(rec.excluded_other_spec_versions),
  };
}

export function parseSettlementSummary(payload: unknown): SettlementSummaryRow | null {
  const rec = asRecord(payload);
  if (!rec) return null;
  const skippedRec = asRecord(rec.skipped);
  const skipped: Record<string, number> = {};
  if (skippedRec) {
    for (const [reason, count] of Object.entries(skippedRec)) {
      const n = asNumber(count);
      if (n !== null) skipped[reason] = n;
    }
  }
  return {
    settled: asNumber(rec.settled),
    skipped: skippedRec ? skipped : null,
    errors: asNumber(rec.errors),
  };
}

export function parseModelManifests(payload: unknown, key: string): ModelManifestMap | null {
  const rec = asRecord(payload);
  if (!rec) return null;
  const container = asRecord(rec[key]) ?? asRecord(asRecord(rec.data)?.[key]);
  if (!container) return null;
  const out: ModelManifestMap = {};
  for (const [name, manifest] of Object.entries(container)) {
    const normalized = asRecord(manifest);
    if (normalized) out[name] = normalized;
  }
  return out;
}

export function parseStrategyTemplates(payload: unknown): StrategyTemplateRow[] | null {
  const rec = asRecord(payload);
  const rawList = Array.isArray(payload) ? payload : rec && Array.isArray(rec.data) ? rec.data : null;
  if (!rawList) return null;
  const out: StrategyTemplateRow[] = [];
  for (const raw of rawList) {
    const t = asRecord(raw);
    if (!t) continue;
    const id = asString(t.template_id ?? t.id);
    const name = asString(t.name);
    if (!id || !name) continue;
    out.push({
      template_id: id,
      name,
      category: asString(t.category),
      description: asString(t.description),
      legs_count: asNumber(t.legs_count),
    });
  }
  return out;
}

export function parsePayoffPoints(value: unknown): PayoffPoint[] {
  if (!Array.isArray(value)) return [];
  const out: PayoffPoint[] = [];
  for (const raw of value) {
    const rec = asRecord(raw);
    if (!rec) continue;
    const spot = asNumber(rec.spot ?? rec.spot_price ?? rec.price);
    const pnl = asNumber(rec.pnl ?? rec.payoff);
    if (spot === null || pnl === null) continue;
    out.push({ spot, pnl });
  }
  return out.sort((a, b) => a.spot - b.spot);
}

export function parseStrategyLegs(value: unknown): StrategyLegRow[] {
  if (!Array.isArray(value)) return [];
  const out: StrategyLegRow[] = [];
  for (const raw of value) {
    const rec = asRecord(raw);
    if (!rec) continue;
    const optionType = asString(rec.option_type);
    const side = asString(rec.side ?? rec.action);
    const strike = asNumber(rec.strike);
    const quantity = asNumber(rec.quantity);
    const price = asNumber(rec.price);
    if (!optionType || !side || strike === null || quantity === null || price === null) continue;
    out.push({
      option_type: optionType.toUpperCase(),
      side: side.toUpperCase(),
      strike,
      quantity,
      price,
      lot_size: asNumber(rec.lot_size),
    });
  }
  return out;
}

export function parseTemplateStrategy(payload: unknown): TemplateStrategyRow | null {
  const rec = asRecord(payload);
  const data = rec ? (asRecord(rec.data) ?? rec) : null;
  if (!data) return null;
  const points = parsePayoffPoints(data.payoff_curve ?? data.points);
  const maxProfit = data.max_profit;
  const maxLoss = data.max_loss;
  return {
    underlying: asString(data.underlying),
    spot_price: asNumber(data.spot_price),
    legs: parseStrategyLegs(data.legs),
    points,
    max_profit:
      maxProfit === 'unlimited'
        ? 'unlimited'
        : asNumber(maxProfit),
    max_loss:
      maxLoss === 'unlimited'
        ? 'unlimited'
        : asNumber(maxLoss),
    risk_reward: asNumber(data.risk_reward ?? data.risk_reward_ratio),
    premium_note: asString(data.premium_note ?? data.note),
  };
}

export function parsePayoffResult(payload: unknown): PayoffResultRow | null {
  const rec = asRecord(payload);
  const data = rec ? (asRecord(rec.data) ?? rec) : null;
  if (!data) return null;
  return {
    underlying: asString(data.underlying),
    spot_price: asNumber(data.spot_price),
    points: parsePayoffPoints(data.payoff_curve ?? data.points),
    legs_count: asNumber(data.legs_count),
  };
}

export function computePayoffStats(points: PayoffPoint[]): PayoffStats | null {
  const pts = parsePayoffPoints(points);
  if (pts.length < 2) return null;
  let maxProfit = -Infinity;
  let maxLoss = Infinity;
  for (const p of pts) {
    if (p.pnl > maxProfit) maxProfit = p.pnl;
    if (p.pnl < maxLoss) maxLoss = p.pnl;
  }
  const breakevens: number[] = [];
  const addBreakeven = (v: number) => {
    const rounded = round(v, 2);
    if (!breakevens.some((b) => Math.abs(b - rounded) < 1e-9)) breakevens.push(rounded);
  };
  for (const p of pts) {
    if (p.pnl === 0) addBreakeven(p.spot);
  }
  for (let i = 1; i < pts.length; i += 1) {
    const a = pts[i - 1];
    const b = pts[i];
    if ((a.pnl < 0 && b.pnl > 0) || (a.pnl > 0 && b.pnl < 0)) {
      const t = a.pnl / (a.pnl - b.pnl);
      addBreakeven(a.spot + t * (b.spot - a.spot));
    }
  }
  return {
    maxProfit,
    maxLoss,
    breakevens,
    spotMin: pts[0].spot,
    spotMax: pts[pts.length - 1].spot,
    count: pts.length,
  };
}

export function splitPayoffBySign(points: PayoffPoint[]): PayoffSegment[] {
  const pts = parsePayoffPoints(points);
  if (pts.length === 0) return [];
  const segments: PayoffSegment[] = [];
  let current: PayoffSegment | null = null;
  for (const p of pts) {
    const sign: 1 | -1 = p.pnl >= 0 ? 1 : -1;
    if (!current) {
      current = { sign, points: [p] };
      continue;
    }
    if (sign === current.sign) {
      current.points.push(p);
      continue;
    }
    const prev = current.points[current.points.length - 1];
    const denom = prev.pnl - p.pnl;
    const t = denom === 0 ? 0 : prev.pnl / denom;
    const cross: PayoffPoint = { spot: prev.spot + t * (p.spot - prev.spot), pnl: 0 };
    current.points.push(cross);
    segments.push(current);
    current = { sign, points: [cross, p] };
  }
  if (current) segments.push(current);
  return segments;
}

function round(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}
