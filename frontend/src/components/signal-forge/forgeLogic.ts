/* Pure decision helpers for the Signal Forge surface.

   Extracted so the truth-of-wall invariants (no invented levels, corridor
   guards, real response parsing) are unit-testable without rendering React. */

import {
  INDEX_CORRIDORS,
  checkInstrumentCorridor,
  checkLevelCoherence,
  classifyDirection,
  type AutoDetectCandidate,
  type SignalEngineStrategy,
} from '@/lib/api/signals';
import { toNumber } from '@/lib/coerce';

export type LevelKey = 'trigger' | 'stopLoss' | 'target1' | 'target2';

export type LevelDraft = Record<LevelKey, string>;

export const EMPTY_LEVELS: LevelDraft = {
  trigger: '',
  stopLoss: '',
  target1: '',
  target2: '',
};

/** Finite number from a number | numeric string | Decimal-as-string. */
export function finiteNumber(value: unknown): number | null {
  return toNumber(value, { rejectEmptyString: true, coerceNonString: true });
}

export { errorMessage } from '@/lib/errors';

/** Normalize the engines endpoint payload (`{id,label}` objects or strings). */
export function normalizeStrategyOptions(raw: unknown): SignalEngineStrategy[] {
  if (!Array.isArray(raw)) return [];
  const out: SignalEngineStrategy[] = [];
  const seen = new Set<string>();
  for (const item of raw) {
    let id: string | null = null;
    let label: string | undefined;
    let description: string | undefined;
    if (typeof item === 'string') {
      id = item.trim();
    } else if (item && typeof item === 'object') {
      const rec = item as Record<string, unknown>;
      const rawId = rec.id ?? rec.name ?? rec.strategy;
      id = typeof rawId === 'string' ? rawId.trim() : null;
      if (typeof rec.label === 'string') label = rec.label;
      else if (typeof rec.name === 'string') label = rec.name;
      if (typeof rec.description === 'string') description = rec.description;
    }
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push({ id, ...(label ? { label } : {}), ...(description ? { description } : {}) });
  }
  return out;
}

/** Empty form state — no level fallbacks (stale levels must never leak across
 *  instrument switches; SENSEX must never inherit BANKNIFTY values). */
export function emptyForgeForm(underlying: string): Record<string, unknown> {
  return {
    underlying,
    direction: 'CALL',
    strategy: '',
    timeframe: '5m',
    ...EMPTY_LEVELS,
    lots: 1,
    notify_telegram: true,
  };
}

export function directionToLong(direction: string): 'LONG_CALL' | 'LONG_PUT' {
  return classifyDirection(direction) === 'PUT' ? 'LONG_PUT' : 'LONG_CALL';
}

export function directionToOptionType(direction: string): 'CE' | 'PE' {
  return classifyDirection(direction) === 'PUT' ? 'PE' : 'CE';
}

export function directionToBias(direction: string): 'BULLISH' | 'BEARISH' {
  return classifyDirection(direction) === 'PUT' ? 'BEARISH' : 'BULLISH';
}

export interface CandidateLevelApplication {
  drafts: Partial<LevelDraft>;
  applied: LevelKey[];
  skipped: string[];
}

/**
 * Map a real auto-detect candidate onto level drafts.
 *
 * The backend field is `trigger` (`trigger_level` only exists as a legacy
 * alias on the request side). Values outside the instrument corridor are
 * skipped and reported — never silently written into the form.
 */
export function candidateToLevelDrafts(
  candidate: AutoDetectCandidate,
  underlying: string,
): CandidateLevelApplication {
  const raw: Record<LevelKey, unknown> = {
    trigger: candidate.trigger ?? candidate.trigger_level,
    stopLoss: candidate.stop_loss,
    target1: candidate.target_1,
    target2: candidate.target_2,
  };
  const labels: Record<LevelKey, string> = {
    trigger: 'Trigger',
    stopLoss: 'Stop loss',
    target1: 'Target 1',
    target2: 'Target 2',
  };
  const range = INDEX_CORRIDORS[String(underlying).toUpperCase()];
  const drafts: Partial<LevelDraft> = {};
  const applied: LevelKey[] = [];
  const skipped: string[] = [];
  for (const key of Object.keys(raw) as LevelKey[]) {
    const value = finiteNumber(raw[key]);
    if (value === null || value <= 0) {
      skipped.push(`${labels[key]} not published`);
      continue;
    }
    if (range && (value < range[0] || value > range[1])) {
      skipped.push(`${labels[key]} ${value} outside ${underlying} corridor [${range[0]}, ${range[1]}]`);
      continue;
    }
    drafts[key] = String(value);
    applied.push(key);
  }
  return { drafts, applied, skipped };
}

export type ForgeLevelErrors = Partial<Record<LevelKey, string>>;

export interface ForgeLevelValidation {
  ok: boolean;
  errors: ForgeLevelErrors;
  reason: string | null;
}

/**
 * Validate the manual level form: required + numeric + corridor + coherence.
 * An empty input is an error (it must never coerce to 0 and ship as a level).
 */
export function validateForgeLevels(input: {
  underlying: string;
  direction: string;
  trigger: string;
  stopLoss: string;
  target1: string;
  target2: string;
}): ForgeLevelValidation {
  const errors: ForgeLevelErrors = {};
  const range = INDEX_CORRIDORS[String(input.underlying).toUpperCase()];
  const parsed: Partial<Record<LevelKey, number>> = {};
  const values: Record<LevelKey, string> = {
    trigger: input.trigger,
    stopLoss: input.stopLoss,
    target1: input.target1,
    target2: input.target2,
  };
  for (const key of Object.keys(values) as LevelKey[]) {
    const rawText = values[key].trim();
    if (!rawText) {
      errors[key] = 'Required — enter a level (or run Auto-Detect).';
      continue;
    }
    const value = finiteNumber(rawText);
    if (value === null) {
      errors[key] = 'Enter a valid number.';
      continue;
    }
    if (value <= 0) {
      errors[key] = 'Must be greater than zero.';
      continue;
    }
    if (range && (value < range[0] || value > range[1])) {
      errors[key] = `Outside ${String(input.underlying).toUpperCase()} corridor [${range[0]}–${range[1]}].`;
      continue;
    }
    parsed[key] = value;
  }
  if (Object.keys(parsed).length < 4) {
    return { ok: false, errors, reason: 'Fix the invalid levels before generating.' };
  }
  const corridor = checkInstrumentCorridor(input.underlying, {
    trigger: parsed.trigger,
    stopLoss: parsed.stopLoss,
    target1: parsed.target1,
    target2: parsed.target2,
  });
  if (!corridor.ok) {
    return { ok: false, errors, reason: corridor.reason };
  }
  const coherence = checkLevelCoherence({
    direction: input.direction,
    trigger: parsed.trigger,
    stopLoss: parsed.stopLoss,
    target1: parsed.target1,
    target2: parsed.target2,
  });
  if (!coherence.coherent) {
    return { ok: false, errors, reason: coherence.reason };
  }
  return { ok: true, errors, reason: null };
}

export function validateLots(raw: string): string | null {
  const text = raw.trim();
  if (!text) return 'Required.';
  const value = finiteNumber(text);
  if (value === null || !Number.isInteger(value)) return 'Enter a whole number.';
  if (value < 1 || value > 50) return 'Between 1 and 50.';
  return null;
}

/* ── AI confirmation response (POST /api/v1/institutional/ai/confirm) ──
   Raw response: { short_horizon, continuation, overall_assessment,
   ai_status, error }. No `.data` envelope. */

export interface AIHorizonOutput {
  decision: string;
  direction: string;
  confidence: number | null;
  horizon_minutes: number | null;
  max_holding_minutes: number | null;
  reasoning: string[];
  invalidation_conditions: string[];
}

export interface AIConfirmationView {
  ai_status: string;
  error: string | null;
  short_horizon: AIHorizonOutput | null;
  continuation: AIHorizonOutput | null;
  overall: Record<string, unknown> | null;
}

function toRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((v): v is string => typeof v === 'string' && v.trim().length > 0);
}

function parseHorizon(value: unknown): AIHorizonOutput | null {
  const rec = toRecord(value);
  if (!rec) return null;
  const decision = typeof rec.decision === 'string' ? rec.decision.toUpperCase() : null;
  if (!decision) return null;
  return {
    decision,
    direction: typeof rec.direction === 'string' ? rec.direction.toUpperCase() : 'NEUTRAL',
    confidence: finiteNumber(rec.confidence),
    horizon_minutes: finiteNumber(rec.horizon_minutes),
    max_holding_minutes: finiteNumber(rec.max_holding_minutes),
    reasoning: toStringList(rec.reasoning),
    invalidation_conditions: toStringList(rec.invalidation_conditions),
  };
}

export function parseAIConfirmation(raw: unknown): AIConfirmationView {
  const rec = toRecord(raw);
  if (!rec) {
    return {
      ai_status: 'ERROR',
      error: 'Malformed AI confirmation response.',
      short_horizon: null,
      continuation: null,
      overall: null,
    };
  }
  const status = typeof rec.ai_status === 'string' ? rec.ai_status.toUpperCase() : 'UNKNOWN';
  const error = typeof rec.error === 'string' && rec.error.trim() ? rec.error : null;
  return {
    ai_status: status,
    error,
    short_horizon: parseHorizon(rec.short_horizon),
    continuation: parseHorizon(rec.continuation),
    overall: toRecord(rec.overall_assessment),
  };
}

/* ── ML shadow gate (GET /api/v1/ml/shadow-gate-eval) ── */

export interface MLShadowGate {
  recommendation: 'PASS' | 'VETO';
  pT1: number | null;
  threshold: number | null;
  authority: string | null;
}

/**
 * Parse the real envelope: `data.shadow_decision.recommendation` is
 * PASS | VETO and `data.shadow_decision.p_t1` its probability. Returns null
 * when the decision is absent — callers must render an unavailable state and
 * never optimistically pass.
 */
export function parseMLShadowGate(data: unknown): MLShadowGate | null {
  const rec = toRecord(data);
  const decision = toRecord(rec?.shadow_decision);
  if (!decision) return null;
  const recommendation = typeof decision.recommendation === 'string' ? decision.recommendation.toUpperCase() : '';
  if (recommendation !== 'PASS' && recommendation !== 'VETO') return null;
  return {
    recommendation,
    pT1: finiteNumber(decision.p_t1),
    threshold: finiteNumber(decision.threshold),
    authority: typeof decision.authority === 'string' ? decision.authority : null,
  };
}

/* ── Path simulation report (POST /api/v1/options-intelligence/simulate-path) ── */

export type PathScenarioKey =
  | 'fast_target'
  | 'slow_target'
  | 'sideways'
  | 'adverse_stop'
  | 'iv_crush_target'
  | 'pin_expiry'
  | 'time_stop_exit';

export interface PathScenarioView {
  key: PathScenarioKey;
  name: string;
  netPnl: number | null;
  profitable: boolean | null;
  holdingHours: number | null;
  thetaDrag: number | null;
}

const PATH_SCENARIO_KEYS: PathScenarioKey[] = [
  'fast_target',
  'slow_target',
  'sideways',
  'adverse_stop',
  'iv_crush_target',
  'pin_expiry',
  'time_stop_exit',
];

export function collectPathScenarios(report: unknown): PathScenarioView[] {
  const rec = toRecord(report);
  if (!rec) return [];
  const out: PathScenarioView[] = [];
  for (const key of PATH_SCENARIO_KEYS) {
    const scenario = toRecord(rec[key]);
    if (!scenario) continue;
    out.push({
      key,
      name:
        typeof scenario.scenario_name === 'string' && scenario.scenario_name
          ? scenario.scenario_name
          : key.replace(/_/g, ' '),
      netPnl: finiteNumber(scenario.net_pnl_total),
      profitable: typeof scenario.is_profitable === 'boolean' ? scenario.is_profitable : null,
      holdingHours: finiteNumber(scenario.holding_hours),
      thetaDrag: finiteNumber(scenario.theta_drag_total),
    });
  }
  return out;
}

/** Mean of the simulated net P&L across published scenarios. */
export function meanScenarioPnl(scenarios: PathScenarioView[]): number | null {
  const values = scenarios
    .map((s) => s.netPnl)
    .filter((v): v is number => v !== null);
  if (values.length === 0) return null;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}
