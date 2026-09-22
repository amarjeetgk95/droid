import { describe, expect, it } from 'vitest';

import { clampWords, firstSentence, toBirdView } from './copilotView';

describe('toBirdView verdict', () => {
  it('handles verdict-only input', () => {
    const v = toBirdView('Nifty bullish breakout with momentum');
    expect(v.verdict).toBe('Nifty bullish breakout with momentum');
    expect(v.bias).toBe('bull');
    expect(v.bullets).toEqual([]);
    expect(v.levels).toEqual([]);
  });

  it('strips VERDICT: prefix', () => {
    const v = toBirdView('VERDICT: BankNifty bearish rejection at highs');
    expect(v.verdict).toBe('BankNifty bearish rejection at highs');
    expect(v.bias).toBe('bear');
  });

  it('strips markdown bold in verdict', () => {
    const v = toBirdView('**Bullish breakout confirmed**');
    expect(v.verdict).toBe('Bullish breakout confirmed');
    expect(v.bias).toBe('bull');
  });

  it('strips markdown header in verdict', () => {
    const v = toBirdView('# Nifty wait and watch');
    expect(v.verdict).toContain('Nifty');
    expect(v.bias).toBe('warn');
  });
});

describe('toBirdView bullets', () => {
  it('caps bullets at 3', () => {
    const raw = ['Market view', '- one', '- two', '- three', '- four', '- five'].join('\n');
    const v = toBirdView(raw);
    expect(v.bullets).toEqual(['one', 'two', 'three']);
  });

  it('parses numbered lists', () => {
    const raw = ['Outlook', '1. first point', '2. second point'].join('\n');
    const v = toBirdView(raw);
    expect(v.bullets).toEqual(['first point', 'second point']);
  });
});

describe('toBirdView levels', () => {
  it('extracts ₹ levels', () => {
    const raw = ['Nifty view', 'Support at ₹25,000', 'Resistance at ₹25,500'].join('\n');
    const v = toBirdView(raw);
    expect(v.levels.length).toBeGreaterThanOrEqual(2);
    expect(v.levels.join(' ')).toContain('25,000');
    expect(v.levels.join(' ')).toContain('25,500');
  });

  it('picks up LEVELS / Sup / Res keyword lines', () => {
    const raw = ['View', 'LEVELS: watch support and resistance', 'Invalidation below low'].join('\n');
    const v = toBirdView(raw);
    expect(v.levels.length).toBeGreaterThanOrEqual(2);
  });
});

describe('toBirdView clamp and safety', () => {
  it('clamps long verdicts and bullets by words', () => {
    const longVerdict = Array.from({ length: 60 }, (_, i) => `w${i}`).join(' ');
    const longBullet = Array.from({ length: 50 }, (_, i) => `b${i}`).join(' ');
    const v = toBirdView(`${longVerdict}\n- ${longBullet}`);
    expect(v.verdict.split(/\s+/).length).toBeLessThanOrEqual(28);
    expect(v.verdict.endsWith('…')).toBe(true);
    expect(v.bullets).toHaveLength(1);
    expect(v.bullets[0].split(/\s+/).length).toBeLessThanOrEqual(22);
    expect(v.bullets[0].endsWith('…')).toBe(true);
  });

  it('never throws on empty/null/non-string', () => {
    expect(toBirdView('')).toMatchObject({ verdict: 'Market view', bias: 'neut', bullets: [], levels: [], rest: '' });
    expect(toBirdView('   \n  ')).toMatchObject({ verdict: 'Market view' });
    expect(toBirdView(null as never)).toMatchObject({ verdict: 'Market view', bias: 'neut' });
    expect(toBirdView(undefined as never)).toMatchObject({ verdict: 'Market view' });
    expect(toBirdView(42 as never)).toMatchObject({ verdict: 'Market view' });
  });

  it('caps rest at 2000 chars and skips verdict+bullets', () => {
    const raw = ['Headline', '- b1', 'keep this body', 'x'.repeat(5000)].join('\n');
    const v = toBirdView(raw);
    expect(v.rest.length).toBeLessThanOrEqual(2000);
    expect(v.rest).toContain('keep this body');
    expect(v.rest).not.toContain('Headline');
  });
});

describe('clampWords / firstSentence', () => {
  it('clamps by words with ellipsis', () => {
    expect(clampWords('a b c d', 2)).toBe('a b…');
    expect(clampWords('a b', 5)).toBe('a b');
    expect(clampWords('', 3)).toBe('');
    expect(clampWords(null as never, 3)).toBe('');
  });

  it('extracts the first sentence', () => {
    expect(firstSentence('Hello world. Second sentence.')).toBe('Hello world.');
    expect(firstSentence('No terminator')).toBe('No terminator');
    expect(firstSentence('')).toBe('');
    expect(firstSentence(null as never)).toBe('');
  });
});
