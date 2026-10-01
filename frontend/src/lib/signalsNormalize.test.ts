import { describe, expect, it } from 'vitest';
import {
  buildValidationGates,
  executionEligibility,
  gateStatusForScore,
  isOpenLedgerStatus,
  isTerminalSignalState,
  matchesDeskFilter,
  matchesInstrumentFilter,
  stateTone,
  sumLedgerTotals,
  toLedgerSummary,
  type LedgerRow,
} from './signalsNormalize';

function ledgerRow(over: Partial<LedgerRow>): LedgerRow {
  return {
    id: 'sig-1',
    underlying: 'NIFTY',
    strategy: 'BREAKOUT',
    direction: 'BULLISH',
    status: 'ARMED',
    outcomeLabel: null,
    isWinner: null,
    side: null,
    qty: 1,
    entry: null,
    exit: null,
    current: null,
    realized: null,
    unrealized: null,
    total: null,
    timeMs: null,
    entryTimeMs: null,
    exitTimeMs: null,
    expiry: null,
    quarantined: false,
    quarantineReason: null,
    sanitizeHint: null,
    ...over,
  };
}

describe('executionEligibility', () => {
  it('is the single predicate for terminal, confirmed and session state', () => {
    expect(executionEligibility('ARMED', false)).toEqual({ eligible: true, reason: null });
    expect(executionEligibility('TRIGGERED', false).eligible).toBe(true);

    expect(executionEligibility('CONFIRMED', false).eligible).toBe(false);
    for (const terminal of ['CLOSED', 'EXPIRED', 'INVALIDATED', 'TARGET_2_HIT', 'STOP_LOSS_HIT', 'TIME_STOP']) {
      expect(executionEligibility(terminal, false).eligible, terminal).toBe(false);
    }

    // A closed market blocks even an otherwise eligible row (fail-closed).
    expect(executionEligibility('ARMED', true).eligible).toBe(false);
  });

  it('shares the terminal predicate with isTerminalSignalState', () => {
    expect(isTerminalSignalState('TARGET_2_HIT')).toBe(true);
    expect(isTerminalSignalState('target_1_hit')).toBe(false);
    expect(isTerminalSignalState('ARMED')).toBe(false);
  });
});

describe('isOpenLedgerStatus / sumLedgerTotals', () => {
  it('treats EXPIRED and INVALIDATED as concluded, like the ledger rows', () => {
    for (const closed of ['WON', 'LOST', 'CLOSED', 'STOP_LOSS_HIT', 'TARGET_2_HIT', 'EXPIRED', 'INVALIDATED']) {
      expect(isOpenLedgerStatus(closed), closed).toBe(false);
    }
    for (const open of ['ARMED', 'CONFIRMED', 'EXECUTED', 'TARGET_1_HIT']) {
      expect(isOpenLedgerStatus(open), open).toBe(true);
    }
  });

  it('counts expired/invalidated rows as realized, never as open MTM', () => {
    const totals = sumLedgerTotals([
      ledgerRow({ id: 'a', status: 'EXPIRED', total: 100, realized: 100 }),
      ledgerRow({ id: 'b', status: 'INVALIDATED', total: -40, realized: -40 }),
      ledgerRow({ id: 'c', status: 'EXECUTED', total: 25, unrealized: 25 }),
    ]);
    expect(totals).toEqual({ realized: 60, unrealized: 25, total: 85 });
  });

  it('returns null for an empty window', () => {
    expect(sumLedgerTotals([])).toBeNull();
  });
});

describe('stateTone', () => {
  it('maps target hits to bull and stop hits to bear', () => {
    expect(stateTone('TARGET_1_HIT')).toBe('bull');
    expect(stateTone('TARGET_2_HIT')).toBe('bull');
    expect(stateTone('STOP_LOSS_HIT')).toBe('bear');
    expect(stateTone('INVALIDATED')).toBe('bear');
    expect(stateTone('EXPIRED')).toBe('warn');
    expect(stateTone('CONFIRMED')).toBe('bull');
    expect(stateTone('ARMED')).toBe('info');
  });
});

describe('filter predicates', () => {
  it('matches instruments exactly — NIFTY never matches BANKNIFTY', () => {
    expect(matchesInstrumentFilter('NIFTY', 'NIFTY')).toBe(true);
    expect(matchesInstrumentFilter('BANKNIFTY', 'NIFTY')).toBe(false);
    expect(matchesInstrumentFilter('SENSEX', 'NIFTY')).toBe(false);
    // Option symbols keep the underlying prefix followed by the date/strike.
    expect(matchesInstrumentFilter('NIFTY2590925000CE', 'NIFTY')).toBe(true);
    expect(matchesInstrumentFilter('BANKNIFTY2590925000CE', 'NIFTY')).toBe(false);
    expect(matchesInstrumentFilter('NIFTY 50', 'NIFTY')).toBe(true);
  });

  it('handles null-desk rows explicitly instead of passing every desk', () => {
    expect(matchesDeskFilter(null, null, 'SCALP')).toBe(false);
    expect(matchesDeskFilter(null, null, 'INTRADAY')).toBe(false);
    expect(matchesDeskFilter(null, true, 'SCALP')).toBe(true);
    expect(matchesDeskFilter(null, true, 'INTRADAY')).toBe(false);
    expect(matchesDeskFilter(null, false, 'INTRADAY')).toBe(true);
    expect(matchesDeskFilter('SCALP_DESK', null, 'SCALP')).toBe(true);
    expect(matchesDeskFilter('INTRADAY', null, 'SCALP')).toBe(false);
  });
});

describe('buildValidationGates', () => {
  const breakdown = {
    technical: 72,
    mtf: 58,
    fno: 38,
    regime: 66,
    ai: 81,
    ai_status: 'AVAILABLE',
    ml_score: 64,
    ml_status: 'AVAILABLE',
  };

  it('maps real confluence domains with bar-judged statuses', () => {
    const gates = buildValidationGates({ confluence_breakdown: breakdown });
    expect(gates.map((g) => [g.label, g.status])).toEqual([
      ['TECH', 'PASS'],
      ['MTF', 'WARN'],
      ['F&O', 'FAIL'],
      ['REGIME', 'PASS'],
      ['AI', 'PASS'],
      ['ML', 'PASS'],
    ]);
    expect(gates[0].score).toBe(72);
  });

  it('renders AI/ML as OFFLINE with no score instead of a fake number', () => {
    const gates = buildValidationGates({
      confluence_breakdown: { ...breakdown, ai_status: 'UNAVAILABLE', ai: null, ml_status: 'UNAVAILABLE', ml_score: null },
    });
    const ai = gates.find((g) => g.key === 'ai');
    const ml = gates.find((g) => g.key === 'ml');
    expect(ai).toEqual({ key: 'ai', label: 'AI', score: null, status: 'OFFLINE' });
    expect(ml).toEqual({ key: 'ml', label: 'ML', score: null, status: 'OFFLINE' });
    // Measured domains are unaffected by offline advisors.
    expect(gates.find((g) => g.key === 'technical')?.status).toBe('PASS');
  });

  it('omits the section when the payload carries no breakdown', () => {
    expect(buildValidationGates({})).toEqual([]);
    expect(buildValidationGates({ confluence_breakdown: null })).toEqual([]);
    expect(buildValidationGates({ confluence_breakdown: { ai_status: 'UNAVAILABLE' } })).toHaveLength(2);
  });

  it('judges scores against the 60 ARMED bar', () => {
    expect(gateStatusForScore(60)).toBe('PASS');
    expect(gateStatusForScore(59.9)).toBe('WARN');
    expect(gateStatusForScore(45)).toBe('WARN');
    expect(gateStatusForScore(44.9)).toBe('FAIL');
  });
});

describe('toLedgerSummary', () => {
  it('normalizes a 0..1 win rate to a percentage and keeps explicit pct', () => {
    expect(toLedgerSummary({ win_rate: 0.65 })?.winRate).toBe(65);
    expect(toLedgerSummary({ win_rate: 65 })?.winRate).toBe(65);
    expect(toLedgerSummary({ win_rate_pct: 1 })?.winRate).toBe(1);
    expect(toLedgerSummary({})?.winRate).toBeNull();
    expect(toLedgerSummary(null)).toBeNull();
  });

  it('exposes the global book size for the "showing N of M" label', () => {
    const summary = toLedgerSummary({ total_signals_audited: 420, closed_trades: 12 });
    expect(summary?.totalRows).toBe(420);
    expect(summary?.closed).toBe(12);
  });
});
