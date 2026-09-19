import { describe, expect, it } from 'vitest';
import type { SwingSetupDTO } from '@/lib/api/swing';
import {
  filterSwingSetups,
  swingEntryEligibility,
  swingSetupDirection,
  swingSetupStates,
  swingStateTone,
  DEFAULT_SWING_FILTERS,
  type SwingSetupFilters,
} from '@/lib/swingDesk';

function setup(overrides: Partial<SwingSetupDTO> = {}): SwingSetupDTO {
  return {
    setup_id: 'setup-1',
    underlying: 'NIFTY',
    direction: 'LONG_CALL',
    option_type: 'CE',
    strategy: 'TREND_BREAKOUT_CE',
    horizon: 'POSITIONAL',
    strike: 25000,
    expiry_date: '2026-09-22',
    contract_symbol: 'NSE:NIFTY2692225000CE',
    lot_size: 75,
    expected_holding_days: 10,
    dte: 4,
    spot_price: 24900,
    spot_trigger: 24950,
    spot_stop: 24750,
    daily_atr: 180,
    entry_premium: 120,
    stop_premium: 90,
    target_premium_1: 180,
    target_premium_2: 240,
    premium_risk_per_lot: 2250,
    iv: 0.14,
    iv_percentile: 50,
    iv_regime: 'NORMAL',
    greeks: { delta: 0.52, gamma: 0.0018, theta_day: -3.2, vega: 9.1 },
    theta_drag_ratio: 5,
    score: {
      trend: 15,
      structure: 10,
      volume: 5,
      expected_move: 10,
      iv_favorability: 8,
      greeks_quality: 10,
      theta_efficiency: 5,
      liquidity: 8,
      regime: 5,
      risk_reward: 8,
      portfolio_fit: 3,
      dte_adequacy: 4,
      total: 91,
      score_is_probability: false,
    },
    trade_validity: {
      underlying_valid: true,
      option_valid: true,
      portfolio_valid: true,
      execution_valid: true,
      overall_valid: true,
      rejection_reasons: [],
    },
    market_regime: 'TRENDING_UP',
    technical_reasons: [],
    options_reasons: [],
    risk_reasons: [],
    invalidation_rules: [],
    signal_state: 'READY',
    created_at_utc: Date.now(),
    ...overrides,
  };
}

function filters(overrides: Partial<SwingSetupFilters> = {}): SwingSetupFilters {
  return { ...DEFAULT_SWING_FILTERS, ...overrides };
}

describe('swingSetupDirection', () => {
  it('maps LONG_CALL / CE to bullish', () => {
    expect(swingSetupDirection(setup())).toBe('BULLISH');
  });

  it('maps LONG_PUT / PE to bearish (never bullish via the LONG token)', () => {
    expect(
      swingSetupDirection(setup({ direction: 'LONG_PUT', option_type: 'PE' })),
    ).toBe('BEARISH');
  });

  it('falls back to option_type when direction is unknown', () => {
    const unknown = '' as SwingSetupDTO['direction'];
    expect(swingSetupDirection(setup({ direction: unknown, option_type: 'PE' }))).toBe('BEARISH');
    expect(swingSetupDirection(setup({ direction: unknown, option_type: 'CE' }))).toBe('BULLISH');
  });
});

describe('swingStateTone', () => {
  it('tones open and actionable states', () => {
    expect(swingStateTone('ENTERED')).toBe('bull');
    expect(swingStateTone('READY')).toBe('info');
    expect(swingStateTone('TRIGGERED')).toBe('info');
    expect(swingStateTone('THETA_WARNING')).toBe('warn');
    expect(swingStateTone('INVALIDATED')).toBe('bear');
    expect(swingStateTone('EXPIRED')).toBe('bear');
    expect(swingStateTone('WATCH')).toBe('neut');
    expect(swingStateTone(null)).toBe('neut');
  });
});

describe('swingEntryEligibility', () => {
  it('allows a valid, actionable setup', () => {
    expect(swingEntryEligibility(setup())).toEqual({ eligible: true, reason: null });
  });

  it('blocks terminal and already-entered setups', () => {
    expect(swingEntryEligibility(setup({ signal_state: 'EXPIRED' })).eligible).toBe(false);
    expect(swingEntryEligibility(setup({ signal_state: 'INVALIDATED' })).eligible).toBe(false);
    expect(swingEntryEligibility(setup({ signal_state: 'ENTERED' })).eligible).toBe(false);
  });

  it('blocks invalid setups and surfaces rejection reasons', () => {
    const result = swingEntryEligibility(
      setup({
        trade_validity: {
          underlying_valid: true,
          option_valid: false,
          portfolio_valid: true,
          execution_valid: true,
          overall_valid: false,
          rejection_reasons: ['illiquid strike'],
        },
      }),
    );
    expect(result.eligible).toBe(false);
    expect(result.reason).toContain('illiquid strike');
  });
});

describe('filterSwingSetups', () => {
  const bullish = setup({ setup_id: 'a', underlying: 'NIFTY', score: { ...setup().score, total: 70 } });
  const bearish = setup({
    setup_id: 'b',
    underlying: 'BANKNIFTY',
    direction: 'LONG_PUT',
    option_type: 'PE',
    horizon: 'INTRADAY',
    signal_state: 'WATCH',
    score: { ...setup().score, total: 95 },
  });

  it('returns everything, ranked by score, when no filter is set', () => {
    const rows = filterSwingSetups([bullish, bearish], filters());
    expect(rows.map((r) => r.setup_id)).toEqual(['b', 'a']);
  });

  it('filters by underlying, direction, horizon and state', () => {
    expect(filterSwingSetups([bullish, bearish], filters({ underlying: 'NIFTY' }))).toHaveLength(1);
    expect(
      filterSwingSetups([bullish, bearish], filters({ direction: 'BEARISH' }))[0]?.setup_id,
    ).toBe('b');
    expect(
      filterSwingSetups([bullish, bearish], filters({ horizon: 'INTRADAY' }))[0]?.setup_id,
    ).toBe('b');
    expect(filterSwingSetups([bullish, bearish], filters({ state: 'READY' }))[0]?.setup_id).toBe('a');
  });

  it('treats a missing horizon as POSITIONAL', () => {
    const legacy = setup({ setup_id: 'c', horizon: undefined });
    expect(filterSwingSetups([legacy], filters({ horizon: 'POSITIONAL' }))).toHaveLength(1);
    expect(filterSwingSetups([legacy], filters({ horizon: 'INTRADAY' }))).toHaveLength(0);
  });

  it('applies the minimum score', () => {
    expect(filterSwingSetups([bullish, bearish], filters({ minScore: 80 })).map((r) => r.setup_id)).toEqual(['b']);
  });
});

describe('swingSetupStates', () => {
  it('collects distinct uppercase states', () => {
    const states = swingSetupStates([
      setup({ signal_state: 'READY' }),
      setup({ signal_state: 'entered' }),
      setup({ signal_state: 'READY' }),
    ]);
    expect(states).toEqual(['ENTERED', 'READY']);
  });
});
