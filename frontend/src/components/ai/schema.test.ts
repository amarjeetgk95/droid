import { describe, expect, it } from 'vitest';
import {
  errorMessage,
  isBriefingResponse,
  isHistoryItem,
  isInsightResponse,
  isStrategyRecommendation,
  isTradeValidation,
} from './schema';

describe('errorMessage', () => {
  it('prefers the Error message, then strings, then the fallback', () => {
    expect(errorMessage(new Error('boom'), 'fallback')).toBe('boom');
    expect(errorMessage('direct', 'fallback')).toBe('direct');
    expect(errorMessage(undefined, 'fallback')).toBe('fallback');
    expect(errorMessage(new Error(''), 'fallback')).toBe('fallback');
  });
});

describe('payload guards', () => {
  it('accepts minimal well-formed payloads', () => {
    expect(isInsightResponse({ executive_summary: 'summary' })).toBe(true);
    expect(isBriefingResponse({ executive_summary: 'summary' })).toBe(true);
    expect(isTradeValidation({ decision: 'CONFIRM', executive_verdict: 'ok' })).toBe(true);
    expect(isHistoryItem({ executive_summary: 'past', market_bias: 'BULLISH', confidence: 61 })).toBe(true);
    expect(
      isStrategyRecommendation({
        strategy_name: 'Bull Call Spread',
        legs: [{ strike: 25000, option_type: 'CE', action: 'BUY', estimated_premium: 120 }],
      }),
    ).toBe(true);
  });

  it('rejects non-objects and missing required fields', () => {
    expect(isInsightResponse(null)).toBe(false);
    expect(isInsightResponse({})).toBe(false);
    expect(isBriefingResponse({ executive_summary: 42 })).toBe(false);
    expect(isTradeValidation({ decision: 'CONFIRM' })).toBe(false);
    expect(isHistoryItem({ executive_summary: { nested: true } })).toBe(false);
    expect(isStrategyRecommendation({ strategy_name: 'No legs' })).toBe(false);
  });

  it('rejects payload shapes that would crash the renderer', () => {
    expect(isStrategyRecommendation({ strategy_name: 'Bad leg', legs: [{ strike: {} }] })).toBe(false);
    expect(isStrategyRecommendation({ strategy_name: 'Legs not list', legs: 'nope' })).toBe(false);
    expect(
      isStrategyRecommendation({
        strategy_name: 'Bad rules',
        legs: [],
        entry_rules: [{ not: 'a string' }],
      }),
    ).toBe(false);
    expect(
      isTradeValidation({
        decision: 'WATCH',
        executive_verdict: 'ok',
        warning_traps: 'should be a list',
      }),
    ).toBe(false);
    expect(isBriefingResponse({ executive_summary: 'ok', actionable_playbook: [{}] })).toBe(false);
  });
});
