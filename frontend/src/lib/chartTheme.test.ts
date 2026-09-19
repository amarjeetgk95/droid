import { afterEach, describe, expect, it, vi } from 'vitest';
import { chartTokens, resetChartTokens } from './chartTheme';

afterEach(() => {
  resetChartTokens();
  vi.unstubAllGlobals();
});

describe('chartTokens', () => {
  it('returns the CSS-mirrored fallback during SSR (no window/document)', () => {
    const tokens = chartTokens();
    // Fallback values must mirror :root in globals.css.
    expect(tokens.up).toBe('#4caf50');
    expect(tokens.down).toBe('#df5148');
    expect(tokens.accent).toBe('#387ed1');
    expect(tokens.warn).toBe('#ff9500');
    expect(tokens.text).toBe('#9b9b9b');
    expect(tokens.surface).toBe('#ffffff');

    expect(chartTokens()).toBe(tokens);
  });

  it('reads design tokens from :root and caches the result', () => {
    const values: Record<string, string> = {
      '--ds-bull': 'rgb(1, 2, 3)',
      '--ds-ink-3': '  #abcdef  ',
    };
    vi.stubGlobal('window', {});
    vi.stubGlobal('document', { documentElement: {} });
    vi.stubGlobal('getComputedStyle', () => ({
      getPropertyValue: (name: string) => values[name] ?? '',
    }));

    const tokens = chartTokens();
    expect(tokens.up).toBe('rgb(1, 2, 3)');
    expect(tokens.text).toBe('#abcdef');
    // Missing token => per-token fallback, not undefined/empty.
    expect(tokens.down).toBe('#df5148');

    values['--ds-bull'] = 'rgb(9, 9, 9)';
    expect(chartTokens()).toBe(tokens);
    expect(chartTokens().up).toBe('rgb(1, 2, 3)');

    resetChartTokens();
    expect(chartTokens().up).toBe('rgb(9, 9, 9)');
  });

  it('falls back without caching when computed styles are unavailable', () => {
    vi.stubGlobal('window', {});
    vi.stubGlobal('document', { documentElement: {} });
    vi.stubGlobal('getComputedStyle', () => {
      throw new Error('no style engine');
    });

    const tokens = chartTokens();
    expect(tokens.up).toBe('#4caf50');
    expect(tokens.down).toBe('#df5148');
  });
});
