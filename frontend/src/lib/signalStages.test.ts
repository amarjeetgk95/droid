import { describe, expect, it } from 'vitest';
import type { ActiveRow } from '@/lib/signalsNormalize';
import type { VirtualPosition } from '@/lib/types';
import {
  SIGNAL_STAGES,
  ageSeconds,
  buildStageChecklist,
  closedOutcome,
  executionInfo,
  formatAge,
  groupByStage,
  matchPosition,
  stageOf,
  stageProgressPct,
} from './signalStages';

function row(patch: Partial<ActiveRow> & { state: string }): ActiveRow {
  return {
    raw: {},
    id: 'sig-1',
    timeMs: 1_000_000,
    symbol: 'NIFTY',
    strategy: 'BREAKOUT',
    direction: 'BULLISH',
    confidence: 0.8,
    confidence01: 0.8,
    score0100: null,
    trigger: 100,
    triggerLevel: 100,
    entryFill: null,
    sl: 90,
    t1: 110,
    t2: 120,
    spot: 99,
    expiresMs: null,
    expiresSource: 'none',
    desk: null,
    isScalp: null,
    incomplete: false,
    missingLevels: [],
    quarantined: false,
    quarantineReason: null,
    ...patch,
  };
}

function position(patch: Partial<VirtualPosition> & { position_id: string }): VirtualPosition {
  return {
    symbol: 'NIFTY25OCT25000CE',
    underlying: 'NIFTY',
    instrument_type: 'OPTION',
    side: 'BUY',
    product: 'INTRADAY',
    quantity: 75,
    average_price: 100,
    ltp: 100,
    unrealized_pnl: 0,
    realized_pnl: 0,
    used_margin: 0,
    is_open: true,
    ...patch,
  };
}

describe('signalStages', () => {
  it('maps every FSM state onto the five pipeline stages', () => {
    expect(stageOf('DETECTED')).toBe('DETECTED');
    expect(stageOf('VALIDATED')).toBe('DETECTED');
    expect(stageOf('ARMED')).toBe('ARMED');
    expect(stageOf('TRIGGERED')).toBe('TRIGGERED');
    expect(stageOf('CONFIRMED')).toBe('EXECUTED');
    expect(stageOf('TARGET_1_HIT')).toBe('EXECUTED');
    expect(stageOf('TARGET_2_HIT')).toBe('CLOSED');
    expect(stageOf('STOP_LOSS_HIT')).toBe('CLOSED');
    expect(stageOf('RUNNER_TIME_STOP_HIT')).toBe('CLOSED');
    expect(stageOf('INVALIDATED')).toBe('CLOSED');
    expect(stageOf('EXPIRED')).toBe('CLOSED');
    expect(stageOf('CLOSED')).toBe('CLOSED');
    expect(stageOf('  armed ')).toBe('ARMED');
  });

  it('groups rows into ordered stages with newest first', () => {
    const groups = groupByStage([
      row({ id: 'a', state: 'ARMED', timeMs: 1 }),
      row({ id: 'b', state: 'ARMED', timeMs: 5 }),
      row({ id: 'c', state: 'STOP_LOSS_HIT', timeMs: 9 }),
      row({ id: 'd', state: 'CONFIRMED', timeMs: 3 }),
    ]);
    expect(groups.map((g) => g.stage)).toEqual([...SIGNAL_STAGES]);
    const armed = groups.find((g) => g.stage === 'ARMED');
    expect(armed?.rows.map((r) => r.id)).toEqual(['b', 'a']);
    expect(groups.find((g) => g.stage === 'CLOSED')?.rows.map((r) => r.id)).toEqual(['c']);
  });

  it('computes stage progress across the pipeline', () => {
    expect(stageProgressPct('DETECTED')).toBe(0);
    expect(stageProgressPct('EXECUTED')).toBe(75);
    expect(stageProgressPct('CLOSED')).toBe(100);
  });

  it('classifies closed outcomes', () => {
    expect(closedOutcome('TARGET_1_HIT')).toBe('WIN');
    expect(closedOutcome('TARGET_2_HIT')).toBe('WIN');
    expect(closedOutcome('STOP_LOSS_HIT')).toBe('LOSS');
    expect(closedOutcome('RUNNER_TIME_STOP_HIT')).toBe('LOSS');
    expect(closedOutcome('EXPIRED')).toBe('FLAT');
    expect(closedOutcome('INVALIDATED')).toBe('FLAT');
  });

  it('formats signal age', () => {
    expect(ageSeconds(row({ state: 'ARMED', timeMs: 1000 }), 6000)).toBe(5);
    expect(ageSeconds(row({ state: 'ARMED', timeMs: null }), 6000)).toBeNull();
    expect(formatAge(null)).toBe('—');
    expect(formatAge(42)).toBe('42s');
    expect(formatAge(125)).toBe('2m 5s');
    expect(formatAge(3720)).toBe('1h 2m');
  });

  it('extracts execution fill details from the raw payload', () => {
    const filled = row({
      state: 'CONFIRMED',
      entryFill: 123.5,
      raw: {
        quantity: 75,
        option_contract: { symbol: 'NIFTY25OCT25000CE' },
        order_id: 'ord-1',
      },
    });
    expect(executionInfo(filled)).toEqual({
      fillPrice: 123.5,
      quantity: 75,
      optionSymbol: 'NIFTY25OCT25000CE',
      orderId: 'ord-1',
    });
    expect(executionInfo(row({ state: 'ARMED' }))).toEqual({
      fillPrice: null,
      quantity: null,
      optionSymbol: null,
      orderId: null,
    });
  });

  it('ticks the checklist from transition history with timestamps', () => {
    const t0 = 1_700_000_000_000;
    const steps = buildStageChecklist(
      row({
        state: 'CONFIRMED',
        raw: {
          created_at_utc: t0,
          state_history: [
            { from_state: 'DETECTED', to_state: 'ARMED', processed_timestamp: t0 + 2000, reason_code: 'SCORE_OK' },
            { from_state: 'ARMED', to_state: 'TRIGGERED', processed_timestamp: t0 + 3000, reason_code: 'TRIGGER_CROSSED' },
            { from_state: 'TRIGGERED', to_state: 'CONFIRMED', processed_timestamp: t0 + 4000, reason_code: 'PROOF_OK' },
          ],
        },
      }),
    );
    expect(steps.map((s) => [s.stage, s.status, s.timestampMs])).toEqual([
      ['DETECTED', 'done', t0],
      ['ARMED', 'done', t0 + 2000],
      ['TRIGGERED', 'done', t0 + 3000],
      ['EXECUTED', 'current', t0 + 4000],
      ['CLOSED', 'pending', null],
    ]);
    expect(steps[1].reason).toBe('SCORE_OK');
  });

  it('marks prior stages done even when history is truncated', () => {
    const t0 = 1_700_000_000_000;
    const steps = buildStageChecklist(row({ state: 'CONFIRMED', raw: { created_at_utc: t0 } }));
    expect(steps.map((s) => [s.stage, s.status, s.timestampMs])).toEqual([
      ['DETECTED', 'done', null],
      ['ARMED', 'done', null],
      ['TRIGGERED', 'done', null],
      ['EXECUTED', 'current', t0],
      ['CLOSED', 'pending', null],
    ]);
  });

  it('marks the last step terminal with the actual state label', () => {
    const t0 = 1_700_000_000_000;
    const steps = buildStageChecklist(
      row({
        state: 'STOP_LOSS_HIT',
        raw: {
          state_history: [
            { from_state: 'DETECTED', to_state: 'ARMED', processed_timestamp: t0 + 2000 },
            { from_state: 'ARMED', to_state: 'TRIGGERED', processed_timestamp: t0 + 3000 },
            { from_state: 'TRIGGERED', to_state: 'CONFIRMED', processed_timestamp: t0 + 4000 },
            { from_state: 'CONFIRMED', to_state: 'STOP_LOSS_HIT', processed_timestamp: t0 + 5000, reason_code: 'SL_HIT' },
          ],
        },
      }),
    );
    const last = steps[steps.length - 1];
    expect(last.status).toBe('terminal');
    expect(last.label).toBe('Stop loss hit');
    expect(last.timestampMs).toBe(t0 + 5000);
  });

  it('marks bypassed stages skipped when a signal expires while armed', () => {
    const t0 = 1_700_000_000_000;
    const steps = buildStageChecklist(
      row({
        state: 'EXPIRED',
        raw: {
          state_history: [
            { from_state: 'DETECTED', to_state: 'ARMED', processed_timestamp: t0 + 2000 },
            { from_state: 'ARMED', to_state: 'EXPIRED', processed_timestamp: t0 + 9000, reason_code: 'TTL_EXCEEDED' },
          ],
        },
      }),
    );
    expect(steps.map((s) => [s.stage, s.status])).toEqual([
      ['DETECTED', 'done'],
      ['ARMED', 'done'],
      ['TRIGGERED', 'skipped'],
      ['EXECUTED', 'skipped'],
      ['CLOSED', 'terminal'],
    ]);
    expect(steps[4].label).toBe('Expired');
    expect(steps[4].reason).toBe('TTL_EXCEEDED');
  });

  it('matches a paper position by option symbol first', () => {
    const executed = row({
      state: 'CONFIRMED',
      raw: { option_contract: { symbol: 'NIFTY25OCT25000CE' } },
    });
    const positions = [
      position({ position_id: 'p1', symbol: 'NIFTY25OCT25000CE' }),
      position({ position_id: 'p2', symbol: 'NIFTY25OCT25100CE' }),
    ];
    expect(matchPosition(executed, positions)?.position_id).toBe('p1');
  });

  it('falls back to a unique underlying position and refuses ambiguous matches', () => {
    const executed = row({ state: 'CONFIRMED', raw: {} });
    const single = [position({ position_id: 'p1', underlying: 'NIFTY' })];
    expect(matchPosition(executed, single)?.position_id).toBe('p1');

    const ambiguous = [
      position({ position_id: 'p1', underlying: 'NIFTY' }),
      position({ position_id: 'p2', underlying: 'NIFTY' }),
    ];
    expect(matchPosition(executed, ambiguous)).toBeUndefined();
  });

  it('ignores closed positions when matching', () => {
    const executed = row({
      state: 'CONFIRMED',
      raw: { option_contract: { symbol: 'NIFTY25OCT25000CE' } },
    });
    const closed = [position({ position_id: 'p1', symbol: 'NIFTY25OCT25000CE', is_open: false })];
    expect(matchPosition(executed, closed)).toBeUndefined();
  });
});
