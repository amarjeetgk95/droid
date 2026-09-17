import { describe, expect, it } from 'vitest';
import {
  checkInstrumentCorridor,
  checkLevelCoherence,
  classifyDirection,
} from '@/lib/api/signals';
import {
  candidateToLevelDrafts,
  collectPathScenarios,
  meanScenarioPnl,
  normalizeStrategyOptions,
  parseAIConfirmation,
  parseMLShadowGate,
  validateForgeLevels,
  validateLots,
} from './forgeLogic';

describe('direction classification + level coherence', () => {
  it('classifies LONG_PUT as PUT (regression: the LONG prefix must not win)', () => {
    expect(classifyDirection('LONG_PUT')).toBe('PUT');
    expect(classifyDirection('LONG_CALL')).toBe('CALL');
    expect(classifyDirection('BEARISH')).toBe('PUT');
    expect(classifyDirection('BULLISH')).toBe('CALL');
    expect(classifyDirection('')).toBe('CALL');
  });

  it('accepts coherent PUT levels instead of rejecting them as calls', () => {
    const res = checkLevelCoherence({
      direction: 'LONG_PUT',
      trigger: 51280,
      stopLoss: 51380,
      target1: 51180,
      target2: 51080,
    });
    expect(res).toEqual({ coherent: true, reason: null });
  });

  it('rejects CALL ordering for a PUT and names the PUT rule', () => {
    const res = checkLevelCoherence({
      direction: 'LONG_PUT',
      trigger: 51280,
      stopLoss: 51180,
      target1: 51380,
      target2: 51480,
    });
    expect(res.coherent).toBe(false);
    expect(res.reason).toContain('PUT');
  });

  it('still enforces CALL ordering for LONG_CALL', () => {
    expect(
      checkLevelCoherence({ direction: 'LONG_CALL', trigger: 100, stopLoss: 90, target1: 110, target2: 120 })
        .coherent,
    ).toBe(true);
    expect(
      checkLevelCoherence({ direction: 'LONG_CALL', trigger: 100, stopLoss: 110, target1: 90, target2: 80 })
        .coherent,
    ).toBe(false);
  });

  it('does not judge partial level sets client-side', () => {
    expect(checkLevelCoherence({ direction: 'LONG_PUT', trigger: 100 }).coherent).toBe(true);
    expect(checkLevelCoherence({ direction: 'LONG_PUT', trigger: 100, stopLoss: null, target1: null }).coherent).toBe(
      true,
    );
  });
});

describe('instrument corridor guard (SENSEX cannot inherit BANKNIFTY values)', () => {
  it('rejects BANKNIFTY-scale levels for SENSEX', () => {
    const res = checkInstrumentCorridor('SENSEX', {
      trigger: 51280,
      stopLoss: 51160,
      target1: 51460,
      target2: 51600,
    });
    expect(res.ok).toBe(false);
    expect(res.reason).toContain('SENSEX');
  });

  it('accepts SENSEX levels inside 70k–120k', () => {
    expect(
      checkInstrumentCorridor('SENSEX', { trigger: 80000, stopLoss: 79900, target1: 80200, target2: 80400 }).ok,
    ).toBe(true);
  });

  it('accepts BANKNIFTY 51280 and NIFTY 24360', () => {
    expect(checkInstrumentCorridor('BANKNIFTY', { trigger: 51280 }).ok).toBe(true);
    expect(checkInstrumentCorridor('NIFTY', { trigger: 24360 }).ok).toBe(true);
  });

  it('leaves unknown instruments to backend validation', () => {
    expect(checkInstrumentCorridor('FINNIFTY', { trigger: 1 }).ok).toBe(true);
  });
});

describe('validateForgeLevels', () => {
  const base = { underlying: 'NIFTY', direction: 'LONG_CALL' };

  it('flags empty inputs instead of coercing them to 0', () => {
    const res = validateForgeLevels({ ...base, trigger: '', stopLoss: '', target1: '', target2: '' });
    expect(res.ok).toBe(false);
    expect(res.errors.trigger).toBeTruthy();
    expect(res.errors.stopLoss).toBeTruthy();
    expect(res.errors.target1).toBeTruthy();
    expect(res.errors.target2).toBeTruthy();
  });

  it('flags stale BANKNIFTY values after switching to SENSEX', () => {
    const res = validateForgeLevels({
      underlying: 'SENSEX',
      direction: 'LONG_CALL',
      trigger: '51280',
      stopLoss: '51160',
      target1: '51460',
      target2: '51600',
    });
    expect(res.ok).toBe(false);
    expect(res.errors.trigger).toContain('SENSEX corridor');
  });

  it('flags incoherent ordering with the backend rule', () => {
    const res = validateForgeLevels({
      ...base,
      trigger: '24360',
      stopLoss: '24420',
      target1: '24320',
      target2: '24280',
    });
    expect(res.ok).toBe(false);
    expect(res.reason).toContain('CALL levels incoherent');
  });

  it('accepts a coherent in-corridor setup', () => {
    const res = validateForgeLevels({
      ...base,
      trigger: '24360',
      stopLoss: '24320',
      target1: '24420',
      target2: '24470',
    });
    expect(res).toEqual({ ok: true, errors: {}, reason: null });
  });

  it('rejects zero and negative levels', () => {
    const res = validateForgeLevels({ ...base, trigger: '0', stopLoss: '-5', target1: '1', target2: '2' });
    expect(res.ok).toBe(false);
    expect(res.errors.trigger).toBeTruthy();
    expect(res.errors.stopLoss).toBeTruthy();
  });
});

describe('validateLots', () => {
  it('requires a whole number between 1 and 50', () => {
    expect(validateLots('')).toBeTruthy();
    expect(validateLots('0')).toBeTruthy();
    expect(validateLots('51')).toBeTruthy();
    expect(validateLots('1.5')).toBeTruthy();
    expect(validateLots('2')).toBeNull();
  });
});

describe('candidateToLevelDrafts', () => {
  it('reads the real `trigger` field and maps stop/targets', () => {
    const res = candidateToLevelDrafts(
      { trigger: 24360, stop_loss: 24320, target_1: 24420, target_2: 24470 },
      'NIFTY',
    );
    expect(res.drafts).toEqual({
      trigger: '24360',
      stopLoss: '24320',
      target1: '24420',
      target2: '24470',
    });
    expect(res.applied).toHaveLength(4);
    expect(res.skipped).toEqual([]);
  });

  it('accepts a legacy trigger_level only as fallback', () => {
    const res = candidateToLevelDrafts({ trigger: 24360, trigger_level: 99999 }, 'NIFTY');
    expect(res.drafts.trigger).toBe('24360');
  });

  it('skips out-of-corridor values and reports them', () => {
    const res = candidateToLevelDrafts(
      { trigger: 51280, stop_loss: 51160, target_1: 51460, target_2: 51600 },
      'SENSEX',
    );
    expect(res.applied).toEqual([]);
    expect(res.skipped).toHaveLength(4);
    expect(res.skipped.join(' ')).toContain('SENSEX corridor');
  });

  it('reports missing fields without inventing them', () => {
    const res = candidateToLevelDrafts({ trigger: 24360 }, 'NIFTY');
    expect(res.drafts).toEqual({ trigger: '24360' });
    expect(res.skipped.join(' ')).toContain('Stop loss not published');
  });
});

describe('normalizeStrategyOptions', () => {
  it('accepts object and string registry entries and drops empties', () => {
    expect(
      normalizeStrategyOptions([
        { id: 'BREAKOUT', label: 'Institutional Breakout' },
        { name: 'ORB' },
        'MEAN_REVERSION',
        '',
        { id: 'BREAKOUT' },
      ]),
    ).toEqual([
      { id: 'BREAKOUT', label: 'Institutional Breakout' },
      { id: 'ORB', label: 'ORB' },
      { id: 'MEAN_REVERSION' },
    ]);
    expect(normalizeStrategyOptions(null)).toEqual([]);
  });
});

describe('parseMLShadowGate', () => {
  it('reads shadow_decision.recommendation + p_t1', () => {
    expect(parseMLShadowGate({ shadow_decision: { recommendation: 'VETO', p_t1: 0.42, threshold: 0.55 } })).toEqual({
      recommendation: 'VETO',
      pT1: 0.42,
      threshold: 0.55,
      authority: null,
    });
    expect(
      parseMLShadowGate({ shadow_decision: { recommendation: 'PASS', p_t1: 0.61, authority: 'OBSERVATIONAL_ONLY' } })
        ?.recommendation,
    ).toBe('PASS');
  });

  it('returns null instead of optimistically passing when the decision is absent', () => {
    expect(parseMLShadowGate({})).toBeNull();
    expect(parseMLShadowGate({ shadow_decision: { p_t1: 0.9 } })).toBeNull();
    expect(parseMLShadowGate(null)).toBeNull();
  });
});

describe('parseAIConfirmation', () => {
  it('parses the raw envelope-less response', () => {
    const view = parseAIConfirmation({
      ai_status: 'CONFIRMED',
      error: null,
      short_horizon: { decision: 'CONFIRM', direction: 'BULLISH', confidence: 70, reasoning: ['vwap reclaim'] },
      continuation: { decision: 'WATCH', direction: 'NEUTRAL', confidence: 50, invalidation_conditions: ['below vwap'] },
      overall_assessment: { market_bias: 'BULLISH', breakout_quality: 65, false_breakout_risk: 30 },
    });
    expect(view.ai_status).toBe('CONFIRMED');
    expect(view.short_horizon?.confidence).toBe(70);
    expect(view.continuation?.invalidation_conditions).toEqual(['below vwap']);
    expect(view.overall?.market_bias).toBe('BULLISH');
  });

  it('surfaces the error and never invents a verdict for malformed data', () => {
    const view = parseAIConfirmation(null);
    expect(view.ai_status).toBe('ERROR');
    expect(view.error).toBeTruthy();
    expect(view.short_horizon).toBeNull();
  });
});

describe('path simulation report parsing', () => {
  it('collects published scenarios only', () => {
    const scenarios = collectPathScenarios({
      fast_target: {
        scenario_name: 'Fast target',
        net_pnl_total: 4200,
        is_profitable: true,
        holding_hours: 0.5,
        theta_drag_total: -120,
      },
      sideways: { net_pnl_total: -650, is_profitable: false },
    });
    expect(scenarios.map((s) => s.key)).toEqual(['fast_target', 'sideways']);
    expect(scenarios[0].netPnl).toBe(4200);
    expect(scenarios[1].profitable).toBe(false);
    expect(meanScenarioPnl(scenarios)).toBe((4200 - 650) / 2);
  });

  it('returns null means for empty reports', () => {
    expect(collectPathScenarios({})).toEqual([]);
    expect(meanScenarioPnl([])).toBeNull();
  });
});
