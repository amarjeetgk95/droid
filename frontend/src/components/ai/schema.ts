import type {
  AIDailyBriefingResponse,
  AIHistoryItem,
  AIInsightResponse,
  AIOptionsStrategyRecommendation,
  AITradeValidationResponse,
} from '@/lib/types';

/** Human-readable message from an unknown thrown value, with a fallback. */
export function errorMessage(reason: unknown, fallback: string): string {
  if (reason instanceof Error && reason.message) return reason.message;
  if (typeof reason === 'string' && reason.trim()) return reason;
  return fallback;
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

/** A value React can render directly without crashing (or undefined/null). */
function isRenderableScalar(v: unknown): boolean {
  return (
    v === undefined ||
    v === null ||
    typeof v === 'string' ||
    typeof v === 'number' ||
    typeof v === 'boolean'
  );
}

function isOptionalText(v: unknown): boolean {
  return v === undefined || v === null || typeof v === 'string';
}

function isOptionalScalarArray(v: unknown): boolean {
  return v === undefined || v === null || (Array.isArray(v) && v.every(isRenderableScalar));
}

/**
 * Backend envelopes are HTTP-200 even when the provider failed, and loosely
 * typed payloads can be malformed. These guards keep render code crash-free:
 * a payload that fails validation is reported as a visible schema error.
 */

export function isInsightResponse(v: unknown): v is AIInsightResponse {
  if (!isRecord(v) || typeof v.executive_summary !== 'string') return false;
  return (
    isOptionalText(v.simple_takeaway) &&
    isOptionalText(v.options_interpretation) &&
    isOptionalText(v.futures_flow_analysis) &&
    isOptionalText(v.regime_and_levels) &&
    isOptionalText(v.recommended_strategy_framework) &&
    isOptionalText(v.risk_management_notes) &&
    isOptionalText(v.disclaimer) &&
    isOptionalText(v.provider_used)
  );
}

export function isBriefingResponse(v: unknown): v is AIDailyBriefingResponse {
  if (!isRecord(v) || typeof v.executive_summary !== 'string') return false;
  return (
    isOptionalText(v.options_pin_and_pivots) &&
    isOptionalText(v.fii_dii_implication) &&
    isOptionalText(v.provider_used) &&
    (v.key_levels_to_watch === undefined ||
      v.key_levels_to_watch === null ||
      isRecord(v.key_levels_to_watch)) &&
    isOptionalScalarArray(v.actionable_playbook)
  );
}

export function isHistoryItem(v: unknown): v is AIHistoryItem {
  return (
    isRecord(v) &&
    typeof v.executive_summary === 'string' &&
    isRenderableScalar(v.market_bias) &&
    isRenderableScalar(v.confidence)
  );
}

export function isStrategyRecommendation(v: unknown): v is AIOptionsStrategyRecommendation {
  if (!isRecord(v) || typeof v.strategy_name !== 'string' || !Array.isArray(v.legs)) {
    return false;
  }
  const scalarFields = [
    'strike',
    'option_type',
    'action',
    'expiry',
    'estimated_premium',
    'delta',
    'theta',
  ];
  return (
    v.legs.every(
      (leg) =>
        isRecord(leg) &&
        scalarFields.every((field) => isRenderableScalar((leg as Record<string, unknown>)[field])),
    ) &&
    isOptionalText(v.rationale) &&
    isOptionalText(v.market_outlook) &&
    isOptionalText(v.max_profit_pts) &&
    isOptionalText(v.max_loss_pts) &&
    isOptionalText(v.risk_reward_ratio) &&
    isOptionalText(v.risk_management) &&
    isOptionalText(v.provider_used) &&
    isOptionalScalarArray(v.breakevens) &&
    isOptionalScalarArray(v.entry_rules) &&
    isOptionalScalarArray(v.exit_rules)
  );
}

export function isTradeValidation(v: unknown): v is AITradeValidationResponse {
  if (!isRecord(v) || typeof v.decision !== 'string' || typeof v.executive_verdict !== 'string') {
    return false;
  }
  return (
    isOptionalText(v.technical_alignment) &&
    isOptionalText(v.derivatives_alignment) &&
    isOptionalText(v.volatility_regime_check) &&
    isOptionalText(v.provider_used) &&
    isOptionalScalarArray(v.invalidation_conditions) &&
    isOptionalScalarArray(v.warning_traps)
  );
}
