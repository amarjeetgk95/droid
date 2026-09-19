import { describe, expect, it } from 'vitest';
import {
  allowedInstTargets,
  alertSeverityTone,
  badgeClass,
  evidenceLines,
  eventPhaseTone,
  eventRiskFlags,
  fmtClockIST,
  fmtScore,
  fmtTtlMs,
  healthTone,
  summarizeDataHealth,
  summarizeFeedHealth,
  summarizeMIDashboard,
  toAuditRows,
  toInstSignalRow,
} from './intelDesk';
import type { CanonicalEvent } from './event-types';

function baseEvent(overrides: Partial<CanonicalEvent> = {}): CanonicalEvent {
  return {
    id: 'evt-1',
    canonical_event_id: 'EVT-1',
    title: 'RBI Policy',
    event_type: 'CENTRAL_BANK',
    entity_id: 'RBI',
    entity_name: 'Reserve Bank of India',
    sector: 'BANKING',
    event_timestamp: '2026-09-18T10:00:00+05:30',
    timezone: 'Asia/Kolkata',
    timestamp_precision: 'EXACT',
    verification_status: 'VERIFIED',
    certainty: 'CONFIRMED',
    expected_direction: 'UNKNOWN',
    time_horizon: 'INTRADAY',
    temporal_phase: 'SCHEDULED',
    processing_flags: {
      discovered: true,
      verified: true,
      classified: true,
      impact_mapped: true,
      scored: true,
    },
    source_priority: 'PRIMARY',
    is_active: true,
    created_at: '2026-09-17T10:00:00+05:30',
    updated_at: '2026-09-17T10:00:00+05:30',
    sources: [],
    impact_mappings: [],
    comparables: [],
    ...overrides,
  };
}

describe('allowedInstTargets', () => {
  it('returns legal targets for a known state', () => {
    expect(allowedInstTargets('RISK_APPROVED')).toEqual([
      'EXECUTION_PENDING',
      'EXPIRED',
      'INVALIDATED',
      'FAILED',
    ]);
  });

  it('returns empty for terminal and unknown states', () => {
    expect(allowedInstTargets('EXECUTED')).toEqual([]);
    expect(allowedInstTargets('NOPE')).toEqual([]);
    expect(allowedInstTargets(null)).toEqual([]);
  });
});

describe('tones', () => {
  it('maps health strings to tones', () => {
    expect(healthTone('LIVE')).toBe('bull');
    expect(healthTone('STALE')).toBe('bear');
    expect(healthTone('CLOSED')).toBe('warn');
    expect(healthTone('ACTIVE')).toBe('info');
    expect(healthTone(null)).toBe('neut');
  });

  it('maps badge classes', () => {
    expect(badgeClass('bull')).toBe('b-bull');
    expect(badgeClass('warn')).toBe('b-warn');
    expect(badgeClass('neut')).toBe('b-neut');
  });

  it('maps event phases and alert severities', () => {
    expect(eventPhaseTone('ACTIVE')).toBe('bear');
    expect(eventPhaseTone('SCHEDULED')).toBe('info');
    expect(alertSeverityTone('CRITICAL')).toBe('bear');
    expect(alertSeverityTone('INFO')).toBe('neut');
  });
});

describe('summarizeMIDashboard', () => {
  it('returns null for non-objects', () => {
    expect(summarizeMIDashboard(null)).toBeNull();
    expect(summarizeMIDashboard([])).toBeNull();
  });

  it('narrows a full dashboard payload', () => {
    const summary = summarizeMIDashboard({
      regime: 'TRENDING',
      price_action: { trend: 'BULLISH' },
      bullish_score: 72,
      bearish_score: 28,
      spot_price: '25910.5',
      data_health: 'LIVE',
      feed_health: { health: 'HEALTHY' },
      short_horizon: { status: 'WATCH' },
      continuation: { status: 'CONFIRMED' },
      breakout: { status: 'WATCH', direction: 'BULLISH', confidence: 61 },
    });
    expect(summary?.trend).toBe('BULLISH');
    expect(summary?.spot).toBe(25910.5);
    expect(summary?.feedHealth).toBe('HEALTHY');
    expect(summary?.contStatus).toBe('CONFIRMED');
    expect(summary?.breakoutConfidence).toBe(61);
  });

  it('stays null-safe on partial payloads', () => {
    const summary = summarizeMIDashboard({ regime: 'RANGING' });
    expect(summary?.spot).toBeNull();
    expect(summary?.shortStatus).toBeNull();
  });
});

describe('summarizeDataHealth / summarizeFeedHealth', () => {
  it('rows default unknown fields honestly', () => {
    const { rows, overall } = summarizeDataHealth({
      data_health: { NIFTY: { status: 'LIVE', feed: 'HEALTHY' }, BANKNIFTY: {} },
      overall: { clock_sync: 'VALID' },
    });
    expect(rows).toHaveLength(2);
    expect(rows[1]).toEqual({ instrument: 'BANKNIFTY', status: 'UNKNOWN', feed: 'UNKNOWN' });
    expect(overall.clock_sync).toBe('VALID');
  });

  it('handles empty payloads', () => {
    expect(summarizeDataHealth(null)).toEqual({ rows: [], overall: {} });
    expect(summarizeFeedHealth(null)).toEqual([]);
  });
});

describe('toInstSignalRow / toAuditRows', () => {
  it('rejects rows without an id', () => {
    expect(toInstSignalRow({ strategy: 'BREAKOUT' })).toBeNull();
  });

  it('narrows a signal row', () => {
    const row = toInstSignalRow({
      signal_id: 'sig-1',
      instrument_id: 'NIFTY',
      fsm_state: 'RISK_APPROVED',
      ttl_remaining_ms: 4200,
      is_expired: false,
    });
    expect(row?.fsmState).toBe('RISK_APPROVED');
    expect(row?.ttlMs).toBe(4200);
    expect(allowedInstTargets(row?.fsmState)).toContain('EXECUTION_PENDING');
  });

  it('skips non-object audit records', () => {
    const rows = toAuditRows([{ signal_id: 'a', event: 'CREATED' }, null, 42]);
    expect(rows).toHaveLength(1);
    expect(rows[0].id).toBe('a');
  });
});

describe('eventRiskFlags', () => {
  it('flags live, unverified, unscored events', () => {
    const flags = eventRiskFlags(
      baseEvent({
        temporal_phase: 'ACTIVE',
        verification_status: 'UNVERIFIED',
        processing_flags: {
          discovered: true,
          verified: false,
          classified: true,
          impact_mapped: false,
          scored: false,
        },
      }),
    );
    expect(flags).toContain('LIVE NOW');
    expect(flags).toContain('UNVERIFIED');
    expect(flags).toContain('UNSCORED');
  });

  it('is quiet for a clean scheduled event', () => {
    expect(eventRiskFlags(baseEvent())).toEqual([]);
  });

  it('flags NO-TRADE decisions', () => {
    const flags = eventRiskFlags(
      baseEvent({
        scores: {
          canonical_event_id: 'EVT-1',
          formula_version: 'v1',
          importance: {
            final_score: 80,
            source_authority: 1,
            scope: 1,
            historical_significance: 1,
            policy_impact: 1,
            surprise_potential: 1,
            weights_applied: {},
            excluded_components: [],
            formula_version: 'v1',
          },
          market_impact: { status: 'SCORED' },
          opportunity: {
            status: 'NO_TRADE',
            passed_gates: [],
            failed_gates: ['x'],
            final_decision: 'NO_TRADE',
          },
          final_decision: 'NO_TRADE',
          calculated_at: '2026-09-17T10:00:00+05:30',
        },
      }),
    );
    expect(flags).toContain('NO-TRADE');
  });
});

describe('formatters', () => {
  it('fmtClockIST never throws on junk', () => {
    expect(fmtClockIST(null)).toBe('—');
    expect(fmtClockIST('not-a-date')).toBe('—');
    expect(fmtClockIST('2026-09-18T10:00:00+05:30')).not.toBe('—');
  });

  it('fmtScore handles both domains', () => {
    expect(fmtScore(0.72)).toBe('72');
    expect(fmtScore(72)).toBe('72.0');
    expect(fmtScore(null)).toBe('—');
  });

  it('fmtTtlMs counts down and expires', () => {
    const now = 1_000_000;
    expect(fmtTtlMs(now + 30_000, now)).toBe('30s');
    expect(fmtTtlMs(now - 1, now)).toBe('expired');
    expect(fmtTtlMs(null, now)).toBe('—');
  });

  it('evidenceLines caps and skips junk', () => {
    expect(
      evidenceLines(
        [{ signal: 'PCR up', detail: '1.2' }, null, { signal: 'x' }],
        2,
      ),
    ).toEqual(['PCR up — 1.2']);
  });
});
