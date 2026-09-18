import { describe, expect, it } from 'vitest';
import { existsSync } from 'node:fs';
import path from 'node:path';
import {
  ALL_NAV_HREFS,
  ALL_NAV_ITEMS,
  BOTTOM_ITEMS,
  MINIMAL_NAV_GROUPS,
  NAV_GROUPS,
  STANDALONE_ITEMS,
  findNavItemByHref,
  findNavItemByShortcut,
  getNavGroups,
  getNavItems,
  getNavShortcut,
  isActivePath,
} from './nav-config';

const EXPECTED_HREFS = [
  '/',
  '/ai',
  '/execute',
  '/intel',
  '/lab',
  '/markets',
  '/options',
  '/risk',
  '/settings',
  '/signals',
  '/swing',
  '/system',
  '/war-room',
];

describe('nav-config navigation layout', () => {
  it('covers all 13 app routes in one source, with no dead links', () => {
    expect([...ALL_NAV_HREFS].sort()).toEqual(EXPECTED_HREFS);
    expect(new Set(ALL_NAV_HREFS).size).toBe(ALL_NAV_HREFS.length);
    expect(ALL_NAV_HREFS).not.toContain('/research');
    expect(ALL_NAV_HREFS).not.toContain('/forge');
  });

  it('exposes every route through exactly one group or the bottom list', () => {
    const grouped = NAV_GROUPS.flatMap((g) => g.items);
    expect(grouped).toHaveLength(11);
    expect(BOTTOM_ITEMS).toHaveLength(2);
    expect(STANDALONE_ITEMS).toHaveLength(0);
    expect([...grouped, ...BOTTOM_ITEMS].map((i) => i.href).sort()).toEqual(EXPECTED_HREFS);
  });

  it('keeps every href backed by a real page under app/(app)', () => {
    const appDir = path.resolve(process.cwd(), 'src', 'app', '(app)');
    for (const href of ALL_NAV_HREFS) {
      const page =
        href === '/'
          ? path.join(appDir, 'page.tsx')
          : path.join(appDir, ...href.slice(1).split('/'), 'page.tsx');
      expect(existsSync(page), `missing page for ${href}: ${page}`).toBe(true);
    }
  });

  it('contains forecast-first standalone anchors plus intel, signals, execute, lab, risk, system', () => {
    expect(findNavItemByHref('/')?.label).toBe('Tactical Bias');
    for (const [href, label] of [
      ['/intel', 'Intel Hub'],
      ['/signals', 'Signals'],
      ['/execute', 'Execution Cockpit'],
      ['/lab', 'Research Lab'],
      ['/risk', 'Risk Matrix'],
      ['/system', 'System Nerve'],
    ] as const) {
      expect(findNavItemByHref(href)?.label).toBe(label);
    }
  });

  it('resolves legacy /research route alias to /lab (Research Lab)', () => {
    const researchItem = findNavItemByHref('/research');
    expect(researchItem).toBeDefined();
    expect(researchItem?.href).toBe('/lab');
    expect(researchItem?.label).toBe('Research Lab');
  });

  it('resolves legacy /forge route alias to /signals (Signals)', () => {
    const forgeItem = findNavItemByHref('/forge');
    expect(forgeItem).toBeDefined();
    expect(forgeItem?.href).toBe('/signals');
    expect(forgeItem?.label).toBe('Signals');
    expect(forgeItem?.description).toContain('scanner workbench');
  });

  it('assigns clean shortcuts ⌘0, ⌘1, ⌘2, ⌘3, ⌘4, ⌘5 and ⌘,', () => {
    expect(findNavItemByHref('/war-room')?.shortcut).toBe('⌘0');
    expect(findNavItemByHref('/')?.shortcut).toBe('⌘1');
    expect(findNavItemByHref('/markets')?.shortcut).toBe('⌘2');
    expect(findNavItemByHref('/options')?.shortcut).toBe('⌘3');
    expect(findNavItemByHref('/ai')?.shortcut).toBe('⌘4');
    expect(findNavItemByHref('/swing')?.shortcut).toBe('⌘5');
    expect(findNavItemByHref('/settings')?.shortcut).toBe('⌘,');
  });

  it('uses unique keyboard shortcuts and resolves them back to items', () => {
    const shortcuts = ALL_NAV_ITEMS.map((i) => i.shortcut).filter(Boolean) as string[];
    expect(new Set(shortcuts).size).toBe(shortcuts.length);
    for (const key of ['⌘0', '⌘1', '⌘2', '⌘3', '⌘4', '⌘5', '⌘,']) {
      expect(findNavItemByShortcut(key)).toBeDefined();
    }
    expect(findNavItemByShortcut('⌘9')).toBeUndefined();
  });

  it('matches active paths without leaking across sibling routes', () => {
    expect(isActivePath('/', '/')).toBe(true);
    expect(isActivePath('/intel', '/')).toBe(false);
    expect(isActivePath('/markets', '/markets')).toBe(true);
    expect(isActivePath('/markets/fno', '/markets')).toBe(true);
    expect(isActivePath('/research', '/lab')).toBe(true);
    expect(isActivePath('/research', '/risk')).toBe(false);
    expect(isActivePath('/forge', '/signals')).toBe(true);
    expect(isActivePath('/forge', '/swing')).toBe(false);
    expect(isActivePath('/settings', '/markets')).toBe(false);
  });
});

describe('P2-4 minimal shell nav (flag on)', () => {
  it('keeps the legacy 11-item grouped nav when the flag is off', () => {
    expect(getNavGroups(false)).toBe(NAV_GROUPS);
    expect(getNavGroups(false).flatMap((g) => g.items)).toHaveLength(11);
  });

  it('collapses the grouped nav to Command / Positions / Lab / Copilot', () => {
    expect(getNavGroups(true)).toBe(MINIMAL_NAV_GROUPS);
    const items = getNavGroups(true).flatMap((g) => g.items);
    expect(items).toHaveLength(4);
    expect(items.map((i) => i.href)).toEqual(['/', '/execute', '/lab', '/ai']);
    expect(items.map((i) => i.label)).toEqual(['Command', 'Positions', 'Lab', 'Copilot']);
    expect(items.map((i) => i.shortcut)).toEqual(['⌘1', '⌘2', '⌘3', '⌘4']);
  });

  it('binds minimal hotkeys to the 4 destinations and leaves legacy bindings intact', () => {
    expect(findNavItemByShortcut('⌘1', true)?.href).toBe('/');
    expect(findNavItemByShortcut('⌘2', true)?.href).toBe('/execute');
    expect(findNavItemByShortcut('⌘3', true)?.href).toBe('/lab');
    expect(findNavItemByShortcut('⌘4', true)?.href).toBe('/ai');
    expect(findNavItemByShortcut('⌘0', true)).toBeUndefined();
    expect(findNavItemByShortcut('⌘5', true)).toBeUndefined();

    expect(findNavItemByShortcut('⌘0')).toBe(findNavItemByHref('/war-room'));
    expect(findNavItemByShortcut('⌘1')?.href).toBe('/');
    expect(findNavItemByShortcut('⌘2')?.href).toBe('/markets');
    expect(findNavItemByShortcut('⌘3')?.href).toBe('/options');
    expect(findNavItemByShortcut('⌘4')?.href).toBe('/ai');
    expect(findNavItemByShortcut('⌘5')?.href).toBe('/swing');
  });

  it('keeps Settings and System reachable in minimal mode (footer dock + long tail)', () => {
    expect(getNavItems(true).map((i) => i.href)).toEqual([
      '/',
      '/execute',
      '/lab',
      '/ai',
      '/system',
      '/settings',
    ]);
    expect(findNavItemByShortcut('⌘,', true)?.href).toBe('/settings');
    expect(ALL_NAV_HREFS).toContain('/settings');
    expect(ALL_NAV_HREFS).toContain('/system');
    expect(ALL_NAV_ITEMS).toHaveLength(13);
  });

  it('advertises only the active shortcut binding per shell mode', () => {
    expect(getNavShortcut('/', true)).toBe('⌘1');
    expect(getNavShortcut('/execute', true)).toBe('⌘2');
    expect(getNavShortcut('/markets', true)).toBeUndefined();
    expect(getNavShortcut('/settings', true)).toBe('⌘,');
    expect(getNavShortcut('/markets', false)).toBe('⌘2');
    expect(getNavShortcut('/execute', false)).toBeUndefined();
  });
});
