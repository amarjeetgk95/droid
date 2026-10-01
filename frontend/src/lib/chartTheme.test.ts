import { afterEach, describe, expect, it, vi } from 'vitest';
import { chartTokens, resetChartTokens } from './chartTheme';
import { applyDisplayMode } from './displayMode';

afterEach(() => {
  resetChartTokens();
  vi.unstubAllGlobals();
});

describe('chartTokens', () => {
  it('returns the CSS-mirrored fallback during SSR (no window/document)', () => {
    const tokens = chartTokens();
    // Fallback values must mirror :root in globals.css.
    expect(tokens.up).toBe('#16a34a');
    expect(tokens.down).toBe('#dc2626');
    expect(tokens.accent).toBe('#7c3aed');
    expect(tokens.warn).toBe('#f59e0b');
    expect(tokens.text).toBe('#64748b');
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
    expect(tokens.down).toBe('#dc2626');

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
    expect(tokens.up).toBe('#16a34a');
    expect(tokens.down).toBe('#dc2626');
  });

  it('re-reads the palette after the display mode changes', () => {
    let bull = 'rgb(1, 2, 3)';
    vi.stubGlobal('window', {});
    vi.stubGlobal('document', {
      documentElement: {
        setAttribute: () => {},
        removeAttribute: () => {},
      },
      querySelector: () => null,
    });
    vi.stubGlobal('getComputedStyle', () => ({
      getPropertyValue: (name: string) => (name === '--ds-bull' ? bull : ''),
    }));

    expect(chartTokens().up).toBe('rgb(1, 2, 3)');

    // Windowing a chart onto the dark terminal must not keep the light candle.
    bull = 'rgb(9, 9, 9)';
    applyDisplayMode({ theme: 'dark', density: 'comfortable', contrast: 'normal' });
    expect(chartTokens().up).toBe('rgb(9, 9, 9)');
  });
});
