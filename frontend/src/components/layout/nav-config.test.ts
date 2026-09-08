import { describe, expect, it } from 'vitest';
import { ALL_NAV_ITEMS, ALL_NAV_HREFS, findNavItemByHref } from './nav-config';

describe('nav-config navigation layout', () => {
  it('contains the unified AI Command Center route', () => {
    const aiCommandCenter = findNavItemByHref('/ai-command-center');
    expect(aiCommandCenter).toBeDefined();
    expect(aiCommandCenter?.label).toBe('AI Command Center');
    expect(aiCommandCenter?.badgeKey).toBe('ai');
    expect(ALL_NAV_HREFS).toContain('/ai-command-center');
  });

  it('keeps distinct group structure intact', () => {
    expect(findNavItemByHref('/signals')).toBeDefined();
    expect(findNavItemByHref('/options-intelligence')).toBeDefined();
    expect(findNavItemByHref('/research')).toBeDefined();
  });

  it('uses unique keyboard shortcuts (no duplicates for quick jumps)', () => {
    const shortcuts = ALL_NAV_ITEMS.map((i) => i.shortcut).filter(Boolean) as string[];
    expect(new Set(shortcuts).size).toBe(shortcuts.length);
  });

  it('gives Options Intelligence a distinct icon and shortcut', () => {
    const item = findNavItemByHref('/options-intelligence');
    expect(item?.shortcut).toBe('⌘7');
    expect(item?.icon).toBeDefined();
  });
});
