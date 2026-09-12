export interface AutoPilotGuardConfig {
  enabled: boolean;
  minConfidence: number;
  maxConcurrent: number;
  maxDailyLoss: number;
  antiChaseTolerance: number;
}

export type AutoPilotDecision =
  | { eligible: true }
  | {
      eligible: false;
      reason:
        | 'DISABLED'
        | 'ALREADY_EXECUTED'
        | 'MAX_CONCURRENT_REACHED'
        | 'DAILY_LOSS_EXCEEDED'
        | 'CONFIDENCE_LOW'
        | 'CHASE_WARNING'
        | 'EXPIRED';
    };

export function evaluateSignalEligibility({
  signalId,
  confidence,
  triggerPrice,
  currentSpot,
  createdAtMs,
  ttlSeconds = 60,
  config,
  currentOpenCount,
  currentUnrealizedPnl,
  executedIds,
  nowMs = Date.now(),
}: {
  signalId: string;
  confidence: number | null;
  triggerPrice: number | null;
  currentSpot: number | null;
  createdAtMs?: number;
  ttlSeconds?: number;
  config: AutoPilotGuardConfig;
  currentOpenCount: number;
  currentUnrealizedPnl: number;
  executedIds: Set<string>;
  nowMs?: number;
}): AutoPilotDecision {
  if (!config.enabled) {
    return { eligible: false, reason: 'DISABLED' };
  }

  if (executedIds.has(signalId)) {
    return { eligible: false, reason: 'ALREADY_EXECUTED' };
  }

  if (currentUnrealizedPnl <= -config.maxDailyLoss) {
    return { eligible: false, reason: 'DAILY_LOSS_EXCEEDED' };
  }

  if (currentOpenCount >= config.maxConcurrent) {
    return { eligible: false, reason: 'MAX_CONCURRENT_REACHED' };
  }

  const conf = confidence ?? 80;
  if (conf < config.minConfidence) {
    return { eligible: false, reason: 'CONFIDENCE_LOW' };
  }

  if (createdAtMs !== undefined) {
    const elapsed = Math.floor((nowMs - createdAtMs) / 1000);
    if (elapsed >= ttlSeconds) {
      return { eligible: false, reason: 'EXPIRED' };
    }
  }

  if (currentSpot !== null && triggerPrice !== null) {
    const dist = Math.abs(currentSpot - triggerPrice);
    if (dist > config.antiChaseTolerance) {
      return { eligible: false, reason: 'CHASE_WARNING' };
    }
  }

  return { eligible: true };
}
