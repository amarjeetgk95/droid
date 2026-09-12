import { describe, it, expect } from 'vitest';
import {
  evaluateSignalEligibility,
  AutoPilotGuardConfig,
} from './autoPilotGuard';

describe('Auto-Pilot Signal Eligibility and Circuit Breakers', () => {
  const defaultConfig: AutoPilotGuardConfig = {
    enabled: true,
    minConfidence: 80,
    maxConcurrent: 2,
    maxDailyLoss: 3000,
    antiChaseTolerance: 15,
  };

  it('allows eligible 1M signals within all safety boundaries', () => {
    const res = evaluateSignalEligibility({
      signalId: 'sig-1',
      confidence: 85,
      triggerPrice: 24500,
      currentSpot: 24505, // 5 pts away <= 15
      createdAtMs: Date.now() - 5000, // 5s old < 60s TTL
      ttlSeconds: 60,
      config: defaultConfig,
      currentOpenCount: 0,
      currentUnrealizedPnl: 250,
      executedIds: new Set(),
    });

    expect(res.eligible).toBe(true);
  });

  it('rejects signals when auto-pilot is disabled', () => {
    const res = evaluateSignalEligibility({
      signalId: 'sig-1',
      confidence: 90,
      triggerPrice: 24500,
      currentSpot: 24500,
      config: { ...defaultConfig, enabled: false },
      currentOpenCount: 0,
      currentUnrealizedPnl: 0,
      executedIds: new Set(),
    });

    expect(res).toEqual({ eligible: false, reason: 'DISABLED' });
  });

  it('rejects signals that have already been executed (deduplication)', () => {
    const res = evaluateSignalEligibility({
      signalId: 'sig-dup',
      confidence: 90,
      triggerPrice: 24500,
      currentSpot: 24500,
      config: defaultConfig,
      currentOpenCount: 0,
      currentUnrealizedPnl: 0,
      executedIds: new Set(['sig-dup']),
    });

    expect(res).toEqual({ eligible: false, reason: 'ALREADY_EXECUTED' });
  });

  it('trips circuit breaker when daily loss limit is exceeded', () => {
    const res = evaluateSignalEligibility({
      signalId: 'sig-1',
      confidence: 90,
      triggerPrice: 24500,
      currentSpot: 24500,
      config: defaultConfig,
      currentOpenCount: 1,
      currentUnrealizedPnl: -3200, // exceeds -3000 stop
      executedIds: new Set(),
    });

    expect(res).toEqual({ eligible: false, reason: 'DAILY_LOSS_EXCEEDED' });
  });

  it('rejects signals when max concurrent scalps limit is reached', () => {
    const res = evaluateSignalEligibility({
      signalId: 'sig-1',
      confidence: 90,
      triggerPrice: 24500,
      currentSpot: 24500,
      config: defaultConfig,
      currentOpenCount: 2, // maxConcurrent is 2
      currentUnrealizedPnl: 500,
      executedIds: new Set(),
    });

    expect(res).toEqual({ eligible: false, reason: 'MAX_CONCURRENT_REACHED' });
  });

  it('rejects signals below min confidence threshold', () => {
    const res = evaluateSignalEligibility({
      signalId: 'sig-1',
      confidence: 72, // below 80
      triggerPrice: 24500,
      currentSpot: 24500,
      config: defaultConfig,
      currentOpenCount: 0,
      currentUnrealizedPnl: 0,
      executedIds: new Set(),
    });

    expect(res).toEqual({ eligible: false, reason: 'CONFIDENCE_LOW' });
  });

  it('rejects chased signals exceeding anti-chase tolerance', () => {
    const res = evaluateSignalEligibility({
      signalId: 'sig-1',
      confidence: 85,
      triggerPrice: 24500,
      currentSpot: 24522, // 22 pts away > 15pt tolerance
      config: defaultConfig,
      currentOpenCount: 0,
      currentUnrealizedPnl: 0,
      executedIds: new Set(),
    });

    expect(res).toEqual({ eligible: false, reason: 'CHASE_WARNING' });
  });

  it('rejects expired signals past TTL', () => {
    const now = 100000;
    const res = evaluateSignalEligibility({
      signalId: 'sig-1',
      confidence: 85,
      triggerPrice: 24500,
      currentSpot: 24500,
      createdAtMs: now - 65000, // 65s ago
      ttlSeconds: 60,
      nowMs: now,
      config: defaultConfig,
      currentOpenCount: 0,
      currentUnrealizedPnl: 0,
      executedIds: new Set(),
    });

    expect(res).toEqual({ eligible: false, reason: 'EXPIRED' });
  });
});
