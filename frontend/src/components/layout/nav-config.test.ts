import { describe, expect, it } from 'vitest';
import { existsSync } from 'node:fs';
import path from 'node:path';
import {
  ALL_NAV_HREFS,
  ALL_NAV_ITEMS,
  BOTTOM_ITEMS,
  NAV_GROUPS,
  STANDALONE_ITEMS,
  findNavItemByHref,
  findNavItemByShortcut,
  isActivePath,
} from './nav-config';

const EXPECTED_HREFS = [
  '/',
  '/ai',
  '/execute',
  '/forge',
  '/intel',
  '/lab',
  '/markets',
  '/options',
  '/research',
  '/risk',
  '/settings',
  '/signals',
  '/swing',
  '/system',
  '/war-room',
];

describe('nav-config navigation layout', () => {
  it('covers all 15 app routes in one source, with no dead links', () => {
    expect([...ALL_NAV_HREFS].sort()).toEqual(EXPECTED_HREFS);
    expect(new Set(ALL_NAV_HREFS).size).toBe(ALL_NAV_HREFS.length);
  });

  it('exposes every route through exactly one group or the bottom list', () => {
    const grouped = NAV_GROUPS.flatMap((g) => g.items);
    expect(grouped).toHaveLength(13);
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

  it('contains forecast-first standalone anchors plus intel, forge, execute, lab, risk, system', () => {
    expect(findNavItemByHref('/')?.label).toBe('Tactical Bias');
    for (const [href, label] of [
      ['/intel', 'Intel Hub'],
      ['/forge', 'Signal Forge'],
      ['/execute', 'Execution Cockpit'],
      ['/lab', 'Research Lab'],
      ['/risk', 'Risk Matrix'],
      ['/system', 'System Nerve'],
      ['/research', 'Financial Research'],
    ] as const) {
      expect(findNavItemByHref(href)?.label).toBe(label);
    }
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
    expect(isActivePath('/research', '/risk')).toBe(false);
    expect(isActivePath('/settings', '/markets')).toBe(false);
  });
});
