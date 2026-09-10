import { describe, expect, it } from 'vitest';
import { ALL_NAV_ITEMS, ALL_NAV_HREFS, NAV_GROUPS, findNavItemByHref } from './nav-config';

describe('nav-config navigation layout', () => {
  it('exposes the standalone 1-Hour Forecast home route', () => {
    const home = findNavItemByHref('/');
    expect(home).toBeDefined();
    expect(home?.label).toBe('1-Hour Forecast');
    expect(home?.shortcut).toBe('⌘1');
    expect(ALL_NAV_HREFS).toContain('/');
  });

  it('keeps a single Context group with Market Context and Derivatives', () => {
    expect(NAV_GROUPS).toHaveLength(1);
    expect(NAV_GROUPS[0].id).toBe('context');
    expect(findNavItemByHref('/markets')?.label).toBe('Market Context');
    expect(findNavItemByHref('/options')?.label).toBe('Derivatives');
  });

  it('contains only forecast-first routes plus settings', () => {
    expect([...ALL_NAV_HREFS].sort()).toEqual(['/', '/markets', '/options', '/settings']);
    for (const dead of [
      '/crypto',
      '/paper-trading',
      '/events',
      '/market-intelligence',
      '/ai-command-center',
      '/ai-analysis',
      '/deep-insight',
    ]) {
      expect(ALL_NAV_HREFS).not.toContain(dead);
      expect(findNavItemByHref(dead)).toBeUndefined();
    }
  });

  it('uses unique keyboard shortcuts (no duplicates for quick jumps)', () => {
    const shortcuts = ALL_NAV_ITEMS.map((i) => i.shortcut).filter(Boolean) as string[];
    expect(new Set(shortcuts).size).toBe(shortcuts.length);
  });

  it('assigns clean shortcuts ⌘1, ⌘2, ⌘3 and ⌘,', () => {
    expect(findNavItemByHref('/')?.shortcut).toBe('⌘1');
    expect(findNavItemByHref('/markets')?.shortcut).toBe('⌘2');
    expect(findNavItemByHref('/options')?.shortcut).toBe('⌘3');
    expect(findNavItemByHref('/settings')?.shortcut).toBe('⌘,');
  });
});
