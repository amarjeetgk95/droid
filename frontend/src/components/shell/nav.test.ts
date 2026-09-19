import { describe, expect, it } from 'vitest';
import { MODULE_NAV, isActivePath } from './nav';

describe('isActivePath', () => {
  it('matches the dashboard only at the root', () => {
    expect(isActivePath('/', '/')).toBe(true);
    expect(isActivePath('/signals', '/')).toBe(false);
  });

  it('matches a module and its nested routes', () => {
    expect(isActivePath('/swing', '/swing')).toBe(true);
    expect(isActivePath('/swing/setup/42', '/swing')).toBe(true);
    expect(isActivePath('/swingbench', '/swing')).toBe(false);
  });

  it('treats a missing pathname as inactive', () => {
    expect(isActivePath(null, '/')).toBe(false);
    expect(isActivePath(null, '/signals')).toBe(false);
  });

  it('keeps every module href unique, rooted and described', () => {
    const hrefs = MODULE_NAV.map((item) => item.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
    expect(MODULE_NAV.some((item) => item.href === '/')).toBe(true);
    for (const item of MODULE_NAV) {
      expect(item.href.startsWith('/')).toBe(true);
      expect(item.label.length).toBeGreaterThan(0);
      expect(item.description.length).toBeGreaterThan(0);
    }
  });
});
